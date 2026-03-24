# Known Issues Database

Failure patterns extracted from 10+ Lambda experiment runs. Each entry has a grep-able pattern, diagnosis, and fix. The monitor and troubleshooter agents use this database to detect and resolve issues automatically.

## Format

Each issue has:
- **Pattern**: Regex/string to grep in logs or error output
- **Diagnosis**: What's actually wrong
- **Fix**: Command or action to resolve it
- **Severity**: critical (experiments will fail), warning (degraded but running), info (cosmetic)
- **Auto-fixable**: Whether the troubleshooter can fix it without user input

---

## SSH & Connectivity

### SSH Connection Refused
- **Pattern**: `Connection refused`
- **Diagnosis**: Instance is booting or SSH daemon not ready yet
- **Fix**: Retry every 10 seconds for up to 3 minutes: `ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no ubuntu@IP echo ok`
- **Severity**: warning (transient)
- **Auto-fixable**: yes

### SSH Connection Reset / Timeout
- **Pattern**: `Connection reset by peer|Connection timed out|broken pipe`
- **Diagnosis**: Network blip, instance rebooting, or Mac went to sleep
- **Fix**: Query Lambda API for current IP (may have changed): `curl -s -u "$LAMBDA_API_KEY:" https://cloud.lambdalabs.com/api/v1/instances | python3 -c "import sys,json; d=json.load(sys.stdin); [print(i['ip']) for i in d['data'] if i['id']=='INSTANCE_ID']"`
- **Severity**: warning
- **Auto-fixable**: yes (retry with updated IP)

### SSH Key Not Loaded
- **Pattern**: `Permission denied (publickey)`
- **Diagnosis**: SSH key not added to agent
- **Fix**: `ssh-add ~/.ssh/id_ed25519`
- **Severity**: critical (blocks all SSH)
- **Auto-fixable**: yes

---

## Python & Dependencies

### Python Not Found
- **Pattern**: `command not found: python`
- **Diagnosis**: Lambda has `python3` but not `python` symlink
- **Fix**: Use `python3` or `uv run python` for all commands
- **Severity**: critical
- **Auto-fixable**: yes (rewrite command with python3)

### uv Sync Fails
- **Pattern**: `error: Failed to download|ResolutionError`
- **Diagnosis**: Network issue or dependency conflict
- **Fix**: Retry once. If persistent, try `uv sync --dev --no-cache`
- **Severity**: critical (blocks experiment)
- **Auto-fixable**: partially (retry, then escalate)

### pip / inspect_evals Dependency Conflict
- **Pattern**: `ERROR: pip's dependency resolver|requires huggingface_hub<`
- **Diagnosis**: inspect_evals pulls incompatible huggingface_hub version
- **Fix**: `pip install 'huggingface_hub<1.0'` after installing inspect_evals
- **Severity**: critical
- **Auto-fixable**: yes

---

## Docker

### Docker Permission Denied
- **Pattern**: `permission denied.*docker|Got permission denied.*docker.sock`
- **Diagnosis**: Ubuntu user is in docker group but shell session doesn't reflect it
- **Fix**: Prefix all docker commands with `sg docker -c '...'`
- **Severity**: critical
- **Auto-fixable**: yes (rewrite command)

### Docker Daemon Not Running
- **Pattern**: `Cannot connect to the Docker daemon|Is the docker daemon running`
- **Diagnosis**: Docker service not started on fresh instance
- **Fix**: `ssh ubuntu@IP 'sudo systemctl start docker && sleep 2 && sg docker -c "docker ps"'`
- **Severity**: critical
- **Auto-fixable**: yes

---

## GPU & CUDA

### CUDA Out of Memory
- **Pattern**: `CUDA out of memory|RuntimeError.*CUDA`
- **Diagnosis**: Stale vLLM or previous experiment process holding GPU memory
- **Fix**: `ssh ubuntu@IP 'pkill -f vllm; sleep 5; nvidia-smi'` to verify GPU freed
- **Severity**: critical
- **Auto-fixable**: yes

### GPU Utilization at 0%
- **Pattern**: Monitor detects `gpu_utilization_pct: 0` for 2+ consecutive checks
- **Diagnosis**: Experiments crashed or completed unexpectedly
- **Fix**: Check if process is still running (`pgrep -f run_lambda`). If dead, check logs for error. If experiments completed early, proceed to collection.
- **Severity**: warning
- **Auto-fixable**: partially (need to determine if crash vs completion)

### Stale vLLM Processes
- **Pattern**: `nvidia-smi` shows GPU memory used but no active experiments
- **Diagnosis**: Previous run's vLLM server didn't shut down
- **Fix**: `ssh ubuntu@IP 'pkill -f vllm; pkill -f vllm_worker; sleep 5; nvidia-smi --query-compute-apps=pid,name,used_memory --format=csv,noheader'`
- **Severity**: critical (blocks new experiments)
- **Auto-fixable**: yes

---

## HuggingFace & Model Downloads

### Thundering Herd (8 GPUs Download Simultaneously)
- **Pattern**: `OSError: We couldn't connect|HTTPError: 429|ReadTimeoutError`
- **Diagnosis**: All 8 GPU experiments trying to download the same model at once
- **Fix**: Pre-cache model before launching experiments: `ssh ubuntu@IP 'HF_HOME=/tmp/hf_cache_ptb python3 -c "from transformers import AutoModelForCausalLM; AutoModelForCausalLM.from_pretrained(\"MODEL_NAME\")"'`
- **Severity**: critical
- **Auto-fixable**: yes (pre-cache step)

### Model Not Found
- **Pattern**: `OSError.*not found.*huggingface|404 Client Error`
- **Diagnosis**: Model name changed or HF token missing/expired
- **Fix**: Verify HF_TOKEN is set in .env, check model name against HuggingFace hub
- **Severity**: critical
- **Auto-fixable**: partially (check token, then escalate if name wrong)

---

## File Format Issues

### .eval Files Are ZIP (Not JSON)
- **Pattern**: `UnicodeDecodeError.*eval|json.decoder.JSONDecodeError.*eval`
- **Diagnosis**: .eval files are ZIP archives containing header.json, samples/*.json, reductions.json
- **Fix**: Use `python3 -c "import zipfile; z=zipfile.ZipFile('FILE.eval'); print(z.namelist())"` to inspect
- **Severity**: info (common mistake, not an experiment failure)
- **Auto-fixable**: yes (use correct reader)

### Attachment URI Not Resolved
- **Pattern**: `attachment://[a-f0-9]{32}`
- **Diagnosis**: Inspect AI stores large tool call args as attachment URIs in .eval files. Monitors that don't resolve these see `attachment://HASH` instead of actual content.
- **Fix**: Use `_extract_turns_from_events()` with the `attachments` dict parameter from `sample.attachments`
- **Severity**: warning (degrades monitor quality)
- **Auto-fixable**: no (requires code fix in monitor)

---

## Environment & Configuration

### .env Sourcing Fails
- **Pattern**: `export: not valid in this context|source.*\.env.*error`
- **Diagnosis**: .env file has `export` prefix or values with special characters (colons)
- **Fix**: Use `set -a; source .env; set +a` pattern. Ensure .env uses plain `KEY=VALUE` format without `export`.
- **Severity**: critical
- **Auto-fixable**: yes (fix sourcing command)

### Claude Code Install Fails on Lambda
- **Pattern**: `npm.*ERR|curl.*syntax error.*install\.sh`
- **Diagnosis**: Lambda's default shell is dash (not bash), npm is outdated or missing, Node.js install is broken
- **Fix**: **DO NOT install Claude Code on Lambda.** Use SSH-from-host pattern exclusively. This is a fundamental design constraint.
- **Severity**: critical
- **Auto-fixable**: no (by design -- don't attempt)

---

## Experiment Execution

### Silent Experiment Failures (All-Zero Scores)
- **Pattern**: `score.*0\.0000` in >50% of completed experiments, OR experiments completing suspiciously fast
- **Diagnosis**: API key issue, model unavailable, Docker sandbox failure, or scorer bug. Experiment exits 0 but produces garbage results.
- **Fix**: Check first completed .eval file: `ssh ubuntu@IP 'python3 -c "import zipfile,json; z=zipfile.ZipFile(\"FILE.eval\"); print(json.loads(z.read(\"reductions.json\")))"'`. If all zeros, check API keys and model availability.
- **Severity**: critical (entire run wasted)
- **Auto-fixable**: partially (can detect, fix requires diagnosis)

### set -e With Background Processes
- **Pattern**: One experiment failure kills remaining experiments
- **Diagnosis**: `set -e` combined with `wait` and background processes is fragile
- **Fix**: Use `set -uo pipefail` WITHOUT `-e`. Already fixed in current run_lambda_8gpu.sh.
- **Severity**: critical
- **Auto-fixable**: no (script-level fix)

### Pipeline Orchestrator Crashes Silently
- **Pattern**: Empty or truncated log file, training stopped but no error visible
- **Diagnosis**: Master script crashed after launch but before tee flushed output
- **Fix**: Check tmux sessions: `ssh ubuntu@IP 'tmux list-sessions'`. If orchestrator session dead but training alive, manually manage remaining phases.
- **Severity**: critical
- **Auto-fixable**: partially (can detect, recovery needs judgment)

---

## File Transfer

### rsync Hangs
- **Pattern**: rsync running >30 minutes for a single file, or `rsync.*stalled`
- **Diagnosis**: rsync is unreliable for large binary files (adapter_model.safetensors ~360MB) over high-latency connections
- **Fix**: Kill rsync, use scp instead: `scp ubuntu@IP:/path/to/file /local/path/`
- **Severity**: warning
- **Auto-fixable**: yes (switch to scp)

### rclone Headless OAuth
- **Pattern**: `rclone.*authorize.*browser|open the following URL`
- **Diagnosis**: Lambda has no browser for OAuth flow
- **Fix**: Run `rclone config` on Lambda with `--auto-config=false`. Copy the auth URL, open on local machine, paste token back.
- **Severity**: warning (one-time setup)
- **Auto-fixable**: no (requires user browser)

---

## Disk & Storage

### Disk Full
- **Pattern**: `No space left on device|OSError.*ENOSPC`
- **Diagnosis**: HF cache, Docker images, or experiment logs filling disk
- **Fix**: Clear HF cache if redundant: `ssh ubuntu@IP 'rm -rf /tmp/hf_cache_ptb/hub/models--*/.no_exist*; du -sh /tmp/hf_cache_ptb'`. If still full, check Docker: `ssh ubuntu@IP 'sg docker -c "docker system prune -f"'`
- **Severity**: critical
- **Auto-fixable**: yes

---

## Cost & Instance Management

### Instance Left Running (Cost Leak)
- **Pattern**: State shows `current_phase: done` or `current_phase: collect` but instance not terminated
- **Diagnosis**: Termination step skipped or failed
- **Fix**: Verify results collected, then terminate via API: `curl -s -u "$LAMBDA_API_KEY:" -X POST https://cloud.lambdalabs.com/api/v1/instance-operations/terminate -H 'Content-Type: application/json' -d '{"instance_ids":["INSTANCE_ID"]}'`
- **Severity**: critical (ongoing cost)
- **Auto-fixable**: yes (if results verified)

### API Credit Exhaustion
- **Pattern**: `AuthenticationError.*insufficient|402.*Payment Required|credit`
- **Diagnosis**: Anthropic/OpenAI API credits exhausted mid-experiment
- **Fix**: Cannot auto-fix. Alert user. Consider whether to terminate instance (save GPU cost) or wait for credit top-up.
- **Severity**: critical
- **Auto-fixable**: no (requires payment)

### Runaway Experiment (No Time Limit Enforced)
- **Pattern**: Experiment running >2x expected duration, OR `'time_limit': None` in eval params despite `num_hours` being set
- **Diagnosis**: PTB CLI (`ptb_eval_cli.py`) defaults `--time-limit` to `None`. The setting's `num_hours` generates `time_limit_seconds` which gets logged ("Using setting's time_limit_seconds: Xs") but is NOT passed to Inspect AI's `eval()` as the `time_limit` parameter. Result: no wall-clock cutoff — experiments run indefinitely.
- **Fix (react scaffold)**: Explicitly pass `--time-limit $((NUM_HOURS * 3600))` in the launch script's `build_eval_cmd()`.
- **Fix (Claude Code scaffold)**: `--time-limit` alone is **NOT sufficient**. Three timeout mechanisms exist, none work reliably on first run:
  1. **Inspect AI task-level `time_limit`**: Uses anyio cancellation but cannot cleanly interrupt the Claude Code external subprocess
  2. **Control solver `asyncio.timeout`** (`_control_solver.py:273`): Only activates on retries — first run has `remaining_s = None` → no-op
  3. **Claude Code `timeout_hours`** (`claude_code_policy.py:332`): Defaults to 6h, controls per-operation timeouts only, never connected to `num_hours`
  Until upstream fixes land, **the monitor must enforce time limits for Claude Code scaffold experiments** by killing experiments that exceed their budget.
- **Severity**: critical (cost: $63 wasted on run 1 at 17h, another $20 on run 2 at 5h — total $83 for zero completed experiments)
- **Auto-fixable**: partially (monitor can detect and kill; root cause requires upstream code fix)
- **Monitor rule**: If an experiment has been running for >2x its `num_hours` budget, investigate immediately. For Claude Code scaffold, be extra vigilant — check if experiments are progressing (new log output, turn counts increasing) or stuck. If stuck or exceeded budget with no new .eval files, kill the experiment process (not the instance) and move to the next one if possible.
- **Discovered**: 2026-03-24, ptb-4h-claude-code-attack run. GitHub issue: https://github.com/re-sabotage/control-arena/issues/238

### Zombie Pollers (Multiple Instances Launched Accidentally)
- **Pattern**: Multiple `lambda_poll_and_launch.sh` processes running simultaneously, each launching separate instances
- **Diagnosis**: Kill commands silently failed (`kill $(cat ...) 2>/dev/null`) so old pollers kept running. Each found capacity independently and launched an instance. Compounded by changing instance types mid-poll (killing a working poller to restart with different parameters).
- **Fix**: Prevention rules (must be followed strictly):
  1. **NEVER change instance types mid-poll.** Stick to what was agreed with the user. Polling can take a very long time — be patient.
  2. **Only ONE poller may run at a time.** Before starting a new one, use `TaskStop` on the old task ID and verify it's dead.
  3. **After stopping a poller, ALWAYS verify:** (a) `ps aux | grep lambda_poll` to confirm process is gone, (b) check Lambda API for any instances the poller may have launched before dying.
  4. **When user says "cancel/stop", ALWAYS check Lambda API** for running instances. Terminate only ours (match by name).
  5. **Never suppress kill errors with `2>/dev/null`** — always check exit codes.
- **Severity**: critical (cost: $11-23 wasted on 3 accidental instances)
- **Auto-fixable**: no (requires discipline in poller management)
- **Discovered**: 2026-03-24, bfcl-r128 experiment (issue #240)

---

## Experiment Configuration

### Trusted Model API Key Missing
- **Pattern**: `Missing key inputs argument.*To use the Google AI API, provide (api_key)|GOOGLE_API_KEY`
- **Diagnosis**: Trusted model set to `google/gemini-2.5-flash` which uses the Google AI SDK directly, requiring `GOOGLE_API_KEY`. If this key isn't in `.env`, monitoring fails silently (experiments still run but no suspicion scores collected).
- **Fix**: Use `openrouter/google/gemini-2.5-flash` instead to route through OpenRouter (which has a key in `.env`).
- **Severity**: warning (non-fatal but loses all monitoring data)
- **Auto-fixable**: yes (rewrite model string in launch command)
- **Discovered**: 2026-03-24, ptb-4h-claude-code-attack run
