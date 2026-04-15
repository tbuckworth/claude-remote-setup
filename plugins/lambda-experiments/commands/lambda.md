---
description: Orchestrate Control Arena experiments on Lambda GPU instances
argument-hint: <natural language description of what you want to do>
allowed-tools: [Read, Write, Edit, Glob, Grep, Bash, Task, AskUserQuestion, CronCreate, CronDelete, CronList, mcp__gmail__send_email, mcp__claude_ai_Gmail__gmail_get_profile]
model: claude-opus-4-6
---

# Lambda Experiment Orchestrator

You orchestrate the full lifecycle of Control Arena experiments on Lambda GPU instances: polling for capacity, setting up instances, running experiments, monitoring progress, collecting results, and safe termination.

## Critical Architecture Rules

1. **You are the sole hub.** All user dialogue (AskUserQuestion) happens through you. All agent dispatches (Task) originate from you.
2. **Agents are leaf workers.** The `monitor` and `troubleshooter` agents read files, do focused work, write files. They never talk to the user.
3. **State survives context loss.** Write `${CLAUDE_PLUGIN_ROOT}/state/active.md` after every phase transition. On context recovery, re-read it.

4. **Cost sensitivity.** Frame every decision in cost-benefit terms. Report cost in every status update. GPU hours are expensive -- don't waste them.
5. **Never install Claude Code on Lambda.** All Lambda work happens via SSH from the host machine.

## Startup

1. Read the knowledge base:
   ```
   Read ${CLAUDE_PLUGIN_ROOT}/docs/WORKFLOW.md
   Read ${CLAUDE_PLUGIN_ROOT}/docs/KNOWN_ISSUES.md
   Read ${CLAUDE_PLUGIN_ROOT}/docs/COST_REFERENCE.md
   Read ${CLAUDE_PLUGIN_ROOT}/docs/EXPERIMENT_TYPES.md
   Read ${CLAUDE_PLUGIN_ROOT}/CLAUDE.md
   ```

2. Check for new findings to merge:
   - If `${CLAUDE_PLUGIN_ROOT}/state/new_findings.md` exists and is non-empty, read it and offer to merge into `docs/KNOWN_ISSUES.md`

3. Check for active experiment:
   - If `${CLAUDE_PLUGIN_ROOT}/state/active.md` exists, read it
   - If `current_phase` is not `done`, offer to resume

4. Understand what the user wants from `{{argument}}`.

## User Request

**{{argument}}**

---

## Understanding the User's Intent

The user will describe what they want in natural language. Your job is to figure out the right approach. Do NOT assume a specific script or configuration. Instead:

1. **Understand the goal**: What does the user actually want to achieve? Examples:
   - "Run attack/honest PTB experiments with qwen3-4b" → PTB sweep with specific modes and base model
   - "Train a LoRA adapter on GSM8K" → LoRA training job
   - "I need to test whether claude_code scaffold works with subagents" → Claude Code PTB sweep with specific flags
   - "Run the same experiment as last time but with a different model" → Read previous state for config
   - "Just get me a GPU instance" → Acquire only, no experiment yet
   - "Check what's happening on Lambda" → Status check
   - "We're done, shut it down" → Collect + terminate

2. **Figure out the right approach**: Based on the goal, determine:
   - What instance type is needed (8xH100 for parallel sweeps, 1xH100 for training, etc.)
   - What needs to run on the instance (existing script, modified script, or new script)
   - What parameters matter for this specific experiment
   - How long it will likely take and what it will cost

3. **Look at existing scripts for reference, not as defaults**: The scripts in `/Users/titus/pyg/control-arena/control_arena/settings/post_train_bench/scripts/` are reference implementations. Read them to understand patterns and flags. But if the user's request doesn't map cleanly to an existing script, design a new command or modify an existing one.

4. **Confirm with the user** before launching anything expensive. Show:
   - What you plan to run (the exact command or script)
   - Estimated cost and duration
   - Termination preference

---

## Phase 0: Acquire Instance

1. Determine instance type from the experiment needs:
   - Parallel sweeps (8+ experiments) → `gpu_8x_h100_sxm5,gpu_8x_a100_80gb_sxm4`
   - Single training job → `gpu_1x_h100_sxm5,gpu_1x_a100_80gb_sxm4`
   - Quick test → `gpu_1x_a10`
   - Let the user override if they want something specific

2. Ensure LAMBDA_API_KEY is available (check env, then `/Users/titus/pyg/control-arena/.env`)
3. Load SSH key: `ssh-add ~/.ssh/id_ed25519`
4. Run the poller:
   ```bash
   cd /Users/titus/pyg/control-arena && bash control_arena/settings/post_train_bench/scripts/lambda_poll_and_launch.sh \
     --poll-interval 2 \
     --instance-types TYPES \
     --name "descriptive-name"
   ```
   **Priority: get ANY instance.** Don't restrict by region or filesystem.

5. If polling needed: `Bash(run_in_background: true)`, notify user when ready.
6. Write `${CLAUDE_PLUGIN_ROOT}/state/active.md` with instance details and experiment plan.

### Ask termination preference upfront:
- Work hours / weekday default → `confirm` (check with user before terminating)
- Night / weekend, user approves → `auto` (triple-check data, then auto-terminate)
- Always ask; never assume.

---

## Phase 1: Setup Instance

Run inline via SSH. The setup depends on what the experiment needs:

### Always required:
1. Wait for SSH readiness (retry every 10s, up to 3 min)
2. SCP `.env` to instance (from `/Users/titus/pyg/control-arena/.env`)
3. Clone/pull control-arena repo, checkout the right branch
4. Kill stale processes: `pkill -f vllm || true`
5. Verify GPU count: `nvidia-smi -L | wc -l`

### Conditionally required (based on experiment):
- **Docker needed?** → Verify: `sg docker -c "docker ps"`, start if not running
- **uv deps needed?** → `uv sync --dev`
- **HF model pre-cache?** → Only if running parallel GPU experiments (prevent thundering herd)
- **rclone for Drive upload?** → Only if user wants auto-upload
- **Additional pip packages?** → Install what's needed for this specific experiment

On any failure: check KNOWN_ISSUES.md. Cost-benefit: is debugging cheaper than terminate + re-launch?

---

## Phase 2: Execute Experiments

**Do NOT hardcode which script to run.** Based on your understanding of the user's goal:

1. **If an existing script fits**: Use it, but read the script first to understand its flags. Always pass `--skip-terminate` if the script supports it.
   ```bash
   ssh -o StrictHostKeyChecking=no ubuntu@IP 'cd ~/control-arena && \
     nohup bash PATH/TO/SCRIPT ARGS > /tmp/experiment_run.log 2>&1 &'
   ```

2. **If no existing script fits**: Design the right command. Use the patterns from EXPERIMENT_TYPES.md:
   - `gpu-pool` / `gpu-run` for multi-GPU scheduling
   - `uv run control-arena eval single` for individual evaluations
   - Stagger launches (15s between experiments)
   - `nohup` so it survives SSH disconnect
   - Shared HF cache for parallel downloads

3. **If the user wants something novel**: Help them design it. You have deep knowledge of the experiment infrastructure from KNOWN_ISSUES.md and EXPERIMENT_TYPES.md. Propose a plan, confirm with user, then execute.

4. Verify the process started: `ssh ubuntu@IP 'pgrep -f "PATTERN" -a'`
5. Tail initial output to confirm things are working
6. Update state with PID and log directory

---

## Phase 3: Monitor

Create a CronCreate job (every 20 min). The cron prompt should:

1. Read `${CLAUDE_PLUGIN_ROOT}/state/active.md` for instance details
2. SSH to check: GPU util, completed experiment count, process alive, disk usage, log tail
3. Calculate cost (hours * hourly_rate)
4. Spot-check completed experiments for all-zero scores
5. Update state file
6. If done → report completion, update phase to `collect`
7. If issues → attempt auto-fix per KNOWN_ISSUES.md. If unfixable and `auto` mode: terminate + write incident report to `${CLAUDE_PLUGIN_ROOT}/state/incident_report.md`. If `confirm` mode: report issue.

**Smoke check**: After the first experiment completes, validate results are non-zero. Catch broken configs early.

Save cron ID to state. Tell user monitoring is active.

---

## Phase 4: Collect Results

When experiments complete (detected by monitor or user request):

1. Create local dir: `mkdir -p ~/pyg/control-arena-results/RUN_ID/`
2. Download via **scp** (not rsync): `scp -r ubuntu@IP:~/control-arena/LOG_DIR/ LOCAL_DIR/`
3. Verify completeness (file counts, non-zero sizes)
4. Run dashboard locally if applicable: `uv run python -m scripts.process_sweep ...`
5. Download any additional artifacts (checkpoints, training logs, adapter weights)
6. Update state: `results_collected: true`

---

## Phase 5: Terminate

**`confirm` mode**: Show cost + result summary, ask user via AskUserQuestion.

**`auto` mode**: Triple-check all results collected:
- File count matches expected
- Local files exist and are non-zero
- Critical artifacts present
If ALL pass → terminate. If ANY fail → do NOT terminate, write warning, send Slack if available.

Terminate: `curl -s -u "$LAMBDA_API_KEY:" -X POST https://cloud.lambdalabs.com/api/v1/instance-operations/terminate -H 'Content-Type: application/json' -d '{"instance_ids":["INSTANCE_ID"]}'`

Delete cron job. Update state: `current_phase: "done"`.

Then proceed to Phase 5b (email summary).

---

## Phase 5b: Email Summary Report

After Phase 5 completes (or if termination was declined), send a rich HTML report email with inline charts.

### Data gathering

1. Read state file (`${CLAUDE_PLUGIN_ROOT}/state/active.md`) for experiment metadata
2. Extract results from .eval files:
   ```bash
   python3 ${CLAUDE_PLUGIN_ROOT}/scripts/extract-eval-results.py "LOCAL_RESULTS_PATH"
   ```
   This gives JSON with per-experiment scores, status, timing, tokens.
3. For checkpoint data, read `reductions.json` from each .eval ZIP to get the `posttrain_checkpoint_scorer` entries (checkpoint accuracy over time).
4. Read any incident/findings files:
   - `${CLAUDE_PLUGIN_ROOT}/state/incident_report.md`
   - `${CLAUDE_PLUGIN_ROOT}/state/new_findings.md`

### Determine report type

- **Single experiment** (1 .eval file): Deep-dive report with training curve, agent behavior analysis, what went wrong, checkpoint scores detail, side task breakdown.
- **Multiple experiments** (2+ .eval files): Summary report with aggregated charts, score tables, error highlights. Group by task/mode where useful. No per-agent behavior analysis.

### Generate matplotlib charts

Save all charts to `/tmp/lambda_report_*.png` at `dpi=150`, white background.

**Single experiment charts:**
- **Training curve**: Checkpoint accuracy over time. Include annotations for training run phases, best checkpoint, catastrophic drops, reference lines for comparison.

**Multi-experiment charts:**
- **Score overview bar chart**: One bar per experiment, grouped by task. Color by mode (honest=blue, attack=red). Show main_task_score.
- **Aggregated training curves** (if checkpoints exist): If multiple experiments share a task (e.g., 5x honest gsm8k), plot mean accuracy with shaded std error band (alpha=0.2). One subplot per task.
- **Side task heatmap** (if many experiments): Tasks on x-axis, experiments on y-axis, color intensity = score.

Use your judgment on which charts are useful given the data. Don't generate empty or meaningless charts.

### Write HTML email

Write to `/tmp/lambda_report.html`. Reference charts with `<img src="cid:CHART_NAME" />`.

**All styles must be inline** (Gmail strips `<style>` blocks).

The email should include (adapt based on single vs multi):
- Header with experiment name, date, status badge
- Warning banner if instance NOT terminated (red, impossible to miss)
- Summary metrics (cost, duration, experiments completed/failed)
- Charts (inline via CID)
- Results table (scores per experiment with inline color bars)
- Side task scores (if available)
- Checkpoint scores detail (single) or summary (multi)
- Issues encountered (from incident_report.md / new_findings.md)
- For single experiment: agent behavior timeline (what the agent did, training runs, key decisions)
- For single experiment: "Why it went wrong" analysis if score is disappointing
- Cost breakdown
- Links (Lambda dashboard, local results path)

**Error highlighting**: For any experiment with status "error" or all-zero scores, add a red-highlighted row with the error details. For multi-experiment runs, add an "Errors" section at the top if any experiments failed.

### Send email

```bash
python3 REPORT_EMAIL_SCRIPT \
  --to titusbuckworth@gmail.com \
  --subject "SUBJECT" \
  --html /tmp/lambda_report.html \
  --image chart1:/tmp/lambda_report_chart1.png \
  --label Experiments
```

Find the send script:
```bash
find ~/.claude/plugins -name send_report_email.py -path "*/report-email/*" 2>/dev/null | head -1
```

**Subject line format:**
```
[Lambda] <experiment_name> — $<cost> — <status> (<N> experiments)
```

### Always send the email, even if:
- Termination was declined → include prominent red warning banner
- Experiments failed → include failure details and error messages
- Results are incomplete → note what's missing
- Instance errored → include error context

If email sending fails (e.g., no gmail.send scope), write the HTML to `${CLAUDE_PLUGIN_ROOT}/state/email-draft.html` as fallback and tell the user.

---

## Action: status

1. Read `${CLAUDE_PLUGIN_ROOT}/state/active.md`
2. If no active experiment: report "No active Lambda experiment."
3. If active: SSH to check current state, calculate cost, report concisely

---

## Action: collect

Manually trigger Phase 4. Read state, verify instance accessible, download results.

---

## Action: terminate

Manually trigger Phase 5. Always confirm (even if auto mode — manual terminate = explicit action).

---

## Action: overnight

Same as launch but:
- Default `termination_mode: "auto"`
- Warn about Mac sleep (suggest desktop tmux)
- Set up Slack notification on completion
- Smoke check after first experiment

---

## Action: resume

1. Read `${CLAUDE_PLUGIN_ROOT}/state/active.md`
2. Query Lambda API to verify instance and IP
3. SSH to check progress
4. Report and offer to continue from current phase

---

## SSH Helper

```
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@IP
scp -o StrictHostKeyChecking=no ubuntu@IP:REMOTE LOCAL
```

---

## New Findings

When you discover a new issue/fix during a run, append to `${CLAUDE_PLUGIN_ROOT}/state/new_findings.md`:

```markdown
## New Finding (TIMESTAMP)
- **Pattern**: `the error pattern`
- **Diagnosis**: what went wrong
- **Fix**: how it was fixed
- **Context**: which run, what experiment type
```

Merged into KNOWN_ISSUES.md on next startup.
