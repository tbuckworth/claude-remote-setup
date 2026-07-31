# Lambda Experiments Plugin

## Architecture

- **Hub-and-spoke**: `/lambda` command is the sole orchestrator. It handles all user dialogue (AskUserQuestion) and agent dispatch (Task).
- **Agents are leaf workers**: They read files, do focused work, write files. They never talk to the user and never spawn other agents.
- **State survives context loss**: `${CLAUDE_PLUGIN_ROOT}/state/active.md` tracks everything. On context recovery, re-read it and resume from `current_phase`.

## Remote Execution Pattern

**All Lambda work happens via SSH from the host machine (Mac or desktop). Never install Claude Code on Lambda.**

Lambda instances have broken npm, curl syntax errors (dash vs bash), and outdated Node.js. Every attempt to install Claude Code on Lambda has failed. The proven pattern is:

```
Host machine (Mac/Desktop) --SSH--> Lambda instance
```

All commands on Lambda are run via `ssh ubuntu@<IP> '...'`.

## SSH Configuration

- Key: `~/.ssh/id_ed25519` (registered as `tbuckworth-key` in Lambda)
- Always run `ssh-add ~/.ssh/id_ed25519` before first SSH command
- SSH options: `-o ConnectTimeout=10 -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null`
- Lambda IPs change every instance -- never use static host entries

## Lambda Gotchas (Quick Reference)

- Use `python3`, never `python` (not found on Lambda)
- Use `uv run` or `uv sync --dev` for deps, never raw `pip`
- Docker commands need `sg docker -c '...'` wrapper (group membership issue)
- `.eval` files are ZIP archives, not JSON
- `rsync` is unreliable for large files -- use `scp`
- `set -e` with background processes is fragile -- use `set -uo pipefail` without `-e`
- Pre-cache HuggingFace models before launching parallel experiments (thundering herd)
- Lambda API uses HTTP Basic auth: `curl -u "$LAMBDA_API_KEY:" ...`
- `.env` format: plain `KEY=VALUE` (no `export` prefix), source with `set -a; source .env; set +a`

## Cost Sensitivity

**Every decision must be framed in cost-benefit terms.**

- GPU hours are expensive ($15-20/hr for 8-GPU instances). Don't waste them debugging setup issues that could be solved by terminating and re-launching.
- Don't throw away results of expensive runs. Always verify data collection before termination.
- Don't fuss over things that cost pennies. A single API call is ~$0.01. Focus effort where the money is.
- Report cost in every status update. Track cumulative spend.

## Experiment Execution Philosophy

**The user describes what they want in natural language. You figure out how to do it.**

Don't default to specific scripts. Instead:
1. Understand the goal from the user's description
2. Read existing scripts in `/Users/titus/pyg/control-arena/` for patterns and reference
3. Use an existing script if it fits, design a new command if it doesn't
4. Confirm the plan with the user before launching anything expensive

Reference scripts in `control_arena/settings/post_train_bench/scripts/`:
- `lambda_poll_and_launch.sh` -- capacity polling + auto-launch
- `run_lambda_8gpu.sh` -- 4-phase experiment pipeline
- `run_lambda_8gpu_claude_code.sh` -- Claude Code scaffold variant
- `run_elicitation_sweep.sh` -- elicitation experiments
- `gpu-pool` / `gpu-run` -- GPU queue scheduling
- `process_sweep.py` -- dashboard generation

**Always pass `--skip-terminate`** when running scripts that support it. The plugin manages termination.

## Termination Safety

- Termination preference is set at the start of each run (Phase 0)
- `confirm` mode: always ask user before terminating (work hours / weekday default)
- `auto` mode: triple-check data collection, then terminate (overnight / weekend, requires upfront approval)
- Never terminate if results haven't been verified as collected

## Knowledge Base

- `docs/KNOWN_ISSUES.md` -- failure patterns + fixes (machine-parseable)
- `docs/WORKFLOW.md` -- 6-phase workflow specification
- `docs/EXPERIMENT_TYPES.md` -- experiment configuration reference
- `docs/PTB_RUN_PATTERN.md` -- 6h PTB sweep launch pattern (gpu-pool + gpu-run, canonical 11 variants, monitoring signals)
- `docs/EMAIL_PIPELINE.md` -- per-eval + PTB FINAL summary email pipeline (enumerate → stage → build_ptb_report → send_report_email, CID naming gotchas)
- `docs/COST_REFERENCE.md` -- GPU pricing

Scripts:
- `scripts/build_ptb_report.py` — HTML+charts builder for PTB summary emails
- `scripts/enumerate_latest_runs.py` — pick latest-iteration 6h cluster per canonical variant across multiple batch dirs
- `scripts/extract-eval-results.py` — extract scores/status/timing from .eval ZIPs for per-eval emails

State files (active.md, new_findings.md, incident_report.md) live in `${CLAUDE_PLUGIN_ROOT}/state/` — inside the plugin directory (gitignored). Use Write/Edit tools normally to manage these files.

New findings from runs are queued in `${CLAUDE_PLUGIN_ROOT}/state/new_findings.md` and merged into KNOWN_ISSUES.md on next startup.
