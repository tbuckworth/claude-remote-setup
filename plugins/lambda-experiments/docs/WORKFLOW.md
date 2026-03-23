# Experiment Workflow Specification

6-phase lifecycle for Lambda GPU experiments. The orchestrator (`commands/lambda.md`) follows this spec.

---

## Phase 0: Acquire Instance

**Goal**: Get a Lambda GPU instance with SSH access.

### Steps

1. **Parse experiment request**: Extract experiment type, model, modes, instance type preference
2. **Show cost estimate**: Look up hourly rate in COST_REFERENCE.md, estimate total based on experiment type
3. **Ask termination preference**:
   - `confirm` (default): "I'll check with you before terminating"
   - `auto`: "I'll triple-check data collection then auto-terminate" (requires explicit user approval)
4. **Load API key**: Check `LAMBDA_API_KEY` from environment or `.env` in the control-arena repo
5. **Run poller**: Execute `lambda_poll_and_launch.sh` with:
   - `--poll-interval 2` (2-second intervals -- capacity is scarce)
   - `--instance-types` based on user preference (default: `gpu_8x_h100_sxm5,gpu_8x_a100_80gb_sxm4`)
   - No filesystem preference -- priority is getting ANY instance
6. **Wait for instance**: If polling, run in background. Notify user when ready.
7. **Write state**: Create `state/active.md` with instance details

### State written
```yaml
instance_id, instance_type, region, ip, launched_at, experiment_type, current_phase: "acquire"
termination_mode: "confirm" | "auto"
```

### Failure handling
- If poller fails: check LAMBDA_API_KEY, retry once
- If no capacity after user's patience runs out: suggest alternative instance types or Modal

---

## Phase 1: Setup Instance

**Goal**: Configure the Lambda instance for experiment execution.

### Steps (9-step checklist)

Each step is run inline via SSH. On failure, consult KNOWN_ISSUES.md for the fix.

```
1. ssh-add ~/.ssh/id_ed25519
   Failure: "Permission denied" → key doesn't exist or wrong path

2. Wait for SSH readiness
   Command: ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null ubuntu@IP echo ok
   Retry: every 10s, up to 3 minutes
   Failure: instance still booting (normal for ~60s after launch)

3. SCP .env to instance
   Command: scp -o StrictHostKeyChecking=no ~/.ssh/id_ed25519 is implicit
   Source: /Users/titus/pyg/control-arena/.env (or wherever LAMBDA_API_KEY lives)
   Dest: ubuntu@IP:~/control-arena/.env
   SECURITY: Never pass API keys as SSH command arguments

4. Verify Docker
   Command: ssh ubuntu@IP 'sg docker -c "docker ps"'
   Failure: "permission denied" → use sg docker wrapper
   Failure: "Cannot connect to daemon" → sudo systemctl start docker

5. Clone/pull repo + checkout branch
   Command: ssh ubuntu@IP 'cd ~ && ([ -d control-arena ] && cd control-arena && git fetch && git checkout BRANCH && git pull || git clone https://github.com/REPO control-arena && cd control-arena && git checkout BRANCH)'
   Note: If instance has a persistent filesystem with repo, just pull

6. Install dependencies
   Command: ssh ubuntu@IP 'cd ~/control-arena && uv sync --dev'
   Failure: dependency conflict → see KNOWN_ISSUES.md

7. Pre-cache HuggingFace model
   Command: ssh ubuntu@IP 'cd ~/control-arena && HF_HOME=/tmp/hf_cache_ptb uv run python3 -c "from transformers import AutoModelForCausalLM, AutoTokenizer; AutoTokenizer.from_pretrained(\"MODEL\"); AutoModelForCausalLM.from_pretrained(\"MODEL\")"'
   Purpose: prevent thundering herd when 8 GPUs launch simultaneously

8. Kill stale processes
   Command: ssh ubuntu@IP 'pkill -f vllm || true; pkill -f "control.arena" || true'
   Purpose: clean GPU memory from any previous runs

9. Verify GPU count
   Command: ssh ubuntu@IP 'nvidia-smi -L | wc -l'
   Expected: 8 (for 8-GPU instances), 1 (for single GPU)
```

### Cost-benefit check
If setup takes >15 minutes of debugging on a running instance, consider: is it cheaper to terminate ($5 wasted) and re-launch with a different config, or keep debugging?

### State written
```yaml
current_phase: "setup" → "execute"
setup_completed_at: timestamp
```

---

## Phase 2: Execute Experiments

**Goal**: Start the experiment script on the Lambda instance.

### Steps

1. **Construct command** based on experiment type:

   **PTB sweep (react)**:
   ```bash
   ssh ubuntu@IP 'cd ~/control-arena && nohup bash control_arena/settings/post_train_bench/scripts/run_lambda_8gpu.sh \
     --modes MODES --base-model BASE_MODEL --skip-terminate \
     > /tmp/experiment_run.log 2>&1 &'
   ```

   **PTB sweep (claude_code)**:
   ```bash
   ssh ubuntu@IP 'cd ~/control-arena && nohup bash control_arena/settings/post_train_bench/scripts/run_lambda_8gpu_claude_code.sh \
     --modes MODES --skip-terminate \
     > /tmp/experiment_run.log 2>&1 &'
   ```

   **LoRA training**:
   ```bash
   ssh ubuntu@IP 'cd ~/control-arena && nohup bash scripts/base_model_analysis/single_task/llama_r128/train_lambda.sh \
     > /tmp/experiment_run.log 2>&1 &'
   ```

   **Custom**: Construct command from user description + EXPERIMENT_TYPES.md knowledge

2. **Always pass `--skip-terminate`**: The plugin manages termination, not the on-instance script
3. **Verify process started**: `ssh ubuntu@IP 'pgrep -f "run_lambda\|train_lambda" -a'`
4. **Get PID and log dir**: Parse from log output or process listing
5. **Tail initial output**: `ssh ubuntu@IP 'sleep 10 && tail -20 /tmp/experiment_run.log'` to confirm experiments are launching

### State written
```yaml
current_phase: "execute" → "monitor"
remote_pid: PID
remote_log_dir: "logs/lambda_8gpu_TIMESTAMP"
execute_started_at: timestamp
```

---

## Phase 3: Monitor

**Goal**: Track experiment progress, detect and fix issues, manage costs.

### Setup

Create a CronCreate job:
```
CronCreate(
  cron="*/20 * * * *",
  recurring=true,
  prompt="You are the Lambda experiment monitor. Read ${CLAUDE_PLUGIN_ROOT}/state/active.md for instance details. Read ${CLAUDE_PLUGIN_ROOT}/docs/KNOWN_ISSUES.md for failure patterns. Then:
  1. SSH to the instance and check: nvidia-smi utilization, .eval file count in log dir, experiment process alive, disk usage
  2. Calculate hours elapsed and cost
  3. Spot-check any newly completed experiments for all-zero scores
  4. Update the state file
  5. If experiments are DONE (experiment_status.json exists or process exited): report completion
  6. If issues detected: attempt auto-fix per KNOWN_ISSUES.md. If unfixable after reasonable effort, terminate instance and write incident report to state/incident_report.md
  Report concisely."
)
```

### Monitor checks (each cron fire)

```bash
# GPU utilization
ssh ubuntu@IP 'nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader'

# Completed experiments
ssh ubuntu@IP 'ls LOG_DIR/*.eval 2>/dev/null | wc -l'

# Process alive
ssh ubuntu@IP 'pgrep -f "run_lambda\|train_lambda" > /dev/null && echo running || echo stopped'

# Disk usage
ssh ubuntu@IP 'df -h / | tail -1 | awk "{print \$5}"'

# Log tail (last 5 lines)
ssh ubuntu@IP 'tail -5 /tmp/experiment_run.log 2>/dev/null'

# Completion check
ssh ubuntu@IP 'cat LOG_DIR/experiment_status.json 2>/dev/null || echo not_done'
```

### Alert escalation

1. **Auto-fixable** (GPU 0%, stale vLLM, disk full): Fix per KNOWN_ISSUES.md, log the fix in state
2. **Requires diagnosis** (process died, partial results): Dispatch troubleshooter agent
3. **Unfixable** (API credits exhausted, persistent crash): If user is likely asleep (night/weekend), terminate instance to stop cost bleed, write detailed incident report. If work hours, alert user.
4. **Cost ceiling**: If cost exceeds 2x estimate with <50% done, report as major issue

### Smoke check (first experiment)

After the first experiment completes, validate its results are non-zero. If all-zero, escalate immediately -- don't let the remaining experiments run on a broken configuration.

### State updated each check
```yaml
experiments_completed, experiments_failed, hours_elapsed, estimated_cost_usd
last_check: timestamp
last_check_summary: "12/24 complete, 0 failed, GPU 95%, disk 45%"
```

---

## Phase 4: Collect Results

**Goal**: Download all results to the host machine, verify completeness.

### Steps

1. **Create local directory**: `mkdir -p ~/pyg/control-arena-results/RUN_ID/`
2. **Download via scp** (NOT rsync):
   ```bash
   scp -r -o StrictHostKeyChecking=no ubuntu@IP:~/control-arena/LOG_DIR/ ~/pyg/control-arena-results/RUN_ID/
   ```
3. **Verify completeness**: Count .eval files locally vs expected total
4. **Check Google Drive**: If rclone uploaded on-instance, verify: `rclone ls gdrive:lambda-results/RUN_NAME/ | wc -l`
5. **Run dashboard locally**: `cd ~/pyg/control-arena && uv run python -m scripts.process_sweep ~/pyg/control-arena-results/RUN_ID/ -o ~/pyg/control-arena-results/RUN_ID/report --dashboard-only`
6. **Download any additional artifacts**: Checkpoint files, training logs, adapter weights

### Verification checklist
- [ ] .eval file count matches expected
- [ ] No .eval files are 0 bytes
- [ ] Dashboard generated successfully
- [ ] Google Drive upload verified (if applicable)
- [ ] State updated with local_results_path

### State written
```yaml
current_phase: "collect" → "terminate"
results_collected: true
local_results_path: "~/pyg/control-arena-results/RUN_ID/"
collection_completed_at: timestamp
```

---

## Phase 5: Terminate

**Goal**: Safely shut down the Lambda instance.

### Termination modes

**`confirm` mode** (work hours / weekday):
1. Show summary: cost, experiment results, data collected
2. Ask user via AskUserQuestion: "Terminate instance IP? Total cost: $X. Y/Z experiments succeeded. All results downloaded to PATH."
3. On confirmation: terminate via API
4. On rejection: keep running, user may want to inspect

**`auto` mode** (overnight / weekend, pre-approved):
1. Triple-check data collection:
   - Verify .eval count matches
   - Verify scp completed (check local file sizes > 0)
   - Verify critical files present (adapter weights if training, dashboard if sweep)
2. If ALL checks pass: terminate
3. If ANY check fails: do NOT terminate, write warning to state, send Slack notification
4. Write termination report to state

### Terminate command
```bash
curl -s -u "$LAMBDA_API_KEY:" \
  -X POST https://cloud.lambdalabs.com/api/v1/instance-operations/terminate \
  -H 'Content-Type: application/json' \
  -d '{"instance_ids":["INSTANCE_ID"]}'
```

### Post-termination
1. Delete CronCreate monitoring job
2. Update state: `current_phase: done`
3. Send Slack notification with summary (if Slack MCP available)
4. Write final cost report

### State written
```yaml
current_phase: "done"
terminated_at: timestamp
final_cost_usd: calculated
termination_report: "All 24 experiments completed. 0 failures. $187.20 total."
```

---

## Context Recovery Procedure

If context is lost (compaction, new session, etc.):

1. Read `state/active.md`
2. Check if instance is alive: `curl -s -u "$LAMBDA_API_KEY:" https://cloud.lambdalabs.com/api/v1/instances | python3 -c "import sys,json; d=json.load(sys.stdin); [print(f'{i[\"id\"]} {i[\"ip\"]} {i[\"status\"]}') for i in d['data']]"`
3. If IP changed: update state
4. SSH to check experiment status: `ssh ubuntu@IP 'pgrep -f run_lambda -a; ls LOG_DIR/*.eval 2>/dev/null | wc -l'`
5. Resume from `current_phase` in state

The state file is designed so that any step can be resumed from its recorded state.
