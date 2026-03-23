# Experiment Types Reference

Configuration reference for all supported experiment types. Used by the orchestrator to construct commands and by Claude to help design new experiment configurations.

---

## PTB Sweep (React Scaffold)

**Script**: `control_arena/settings/post_train_bench/scripts/run_lambda_8gpu.sh`
**Typical duration**: 6-12 hours on 8xH100
**Typical cost**: $120-240

### Key flags

| Flag | Default | Description |
|---|---|---|
| `--model MODEL` | `anthropic/claude-opus-4-6` | Untrusted model |
| `--scaffold SCAFFOLD` | `react` | Scaffold type |
| `--modes M1,M2,...` | `attack,honest,attack,honest` | Round modes (comma-separated) |
| `--num-hours N` | `4` | Time budget shown to agent |
| `--num-gpus N` | `8` (auto-detected) | GPUs to use |
| `--stagger N` | `15` | Seconds between experiment launches |
| `--base-model MODEL` | `qwen3-14b` | Base model for finetuning |
| `--side-tasks T1,T2,...` | 6 core tasks | Override which side tasks |
| `--all-tasks` | off | Use all 11 side tasks |
| `--hf-cache-dir DIR` | `/tmp/hf_cache_ptb` | Shared HuggingFace cache |
| `--execution-mode MODE` | `local` | `local` or `docker` |
| `--compaction MODE` | `summary` | Context compaction strategy |
| `--skip-preflight` | off | Skip preflight checks |
| `--skip-upload` | off | Skip Google Drive upload |
| `--skip-terminate` | off | **ALWAYS pass this** (plugin manages termination) |
| `--skip-summarize` | off | Skip dashboard generation |
| `--dry-run` | off | Print commands without executing |

### Base model options
`qwen3-1.7b`, `qwen3-4b`, `qwen3-14b`, `smollm3-3b`, `gemma3-4b`

### Task pairings
Configured in `control_arena/settings/post_train_bench/task_pairings.json`. Core 6 tasks listed in `core_side_tasks.json`.

### Example
```bash
bash run_lambda_8gpu.sh --modes attack,honest,attack,honest --base-model qwen3-4b --skip-terminate
```

---

## PTB Sweep (Claude Code Scaffold)

**Script**: `control_arena/settings/post_train_bench/scripts/run_lambda_8gpu_claude_code.sh`
**Typical duration**: 12-20 hours on 8xH100 (longer due to bridge overhead)
**Typical cost**: $240-400

### Additional flags (beyond standard PTB)

| Flag | Default | Description |
|---|---|---|
| `--enable-subagents` | off | Enable Claude Code sub-agents |
| `--disable-subagents` | default | Disable sub-agents |
| `--subagent-model MODEL` | inherited | Model for sub-agents |
| `--haiku-model MODEL` | default | Model for Haiku-tier tasks |
| `--enable-internet` | off | Allow internet access |
| `--disable-internet` | default | Block internet |
| `--micro-protocol PROTO` | `scaffold_trusted_monitoring` | Monitoring protocol |
| `--skip-interval N` | `40` | Monitor skip interval |
| `--reasoning-effort LEVEL` | `high` | Reasoning effort (`low`, `medium`, `high`) |
| `--auto-checkout BRANCH` | none | Auto-checkout branch for deps |

### Example
```bash
bash run_lambda_8gpu_claude_code.sh --modes attack,honest --enable-subagents --skip-terminate
```

---

## LoRA Training

**Script**: `scripts/base_model_analysis/single_task/llama_r128/train_lambda.sh`
**Typical duration**: 6-12 hours per task on 1xH100
**Typical cost**: $25-50

### Configuration (edit script directly or design new one)

| Parameter | Typical Value | Description |
|---|---|---|
| Model | `meta-llama/Llama-3.2-1B` | Base model |
| LoRA rank | 128 | LoRA rank (higher = more params) |
| LoRA alpha | 32 | Scaling factor |
| Batch size | 4 | Training batch size |
| Tasks | GSM8K, ArenaHardWriting | Training tasks (sequential) |
| Hours per task | 6 | Training time budget |
| Checkpoint interval | 60 min | How often to save |

### Important notes
- Tasks run sequentially (one after another), not in parallel
- Each task starts a new Python process to avoid GPU memory leaks
- Checkpoint files: `adapter_config.json` (~1KB) + `adapter_model.safetensors` (~360MB)
- Use **scp** (not rsync) for transferring checkpoints

### Before training: read LoRA hyperparameter guide
Always check https://thinkingmachines.ai/blog/lora/ for optimal rank/alpha/LR settings.

---

## Elicitation Sweep

**Script**: `control_arena/settings/post_train_bench/scripts/run_elicitation_sweep.sh`
**Typical duration**: Variable
**Typical cost**: Variable

### Notes
- Uses the same GPU pool scheduling as PTB sweeps
- Task-specific configuration varies by elicitation target
- Refer to script for current flag set

---

## Custom Experiments

For new experiment types not covered above, use the knowledge in this file + KNOWN_ISSUES.md to design scripts. Key patterns to follow:

### Template for new experiment script
```bash
#!/bin/bash
# NOTE: No set -e! Use set -uo pipefail for background process safety.
set -uo pipefail

# 1. GPU pool management
source scripts/gpu-pool init $NUM_GPUS

# 2. Shared HF cache (prevent thundering herd)
export HF_HOME=${HF_CACHE_DIR:-/tmp/hf_cache_ptb}

# 3. Docker wrapper if needed
# sg docker -c "docker pull IMAGE"

# 4. Launch experiments with stagger
for experiment in "${EXPERIMENTS[@]}"; do
  scripts/gpu-run bash -c "
    uv run control-arena eval single ... --experiment $experiment
  " &
  PIDS+=($!)
  sleep ${STAGGER:-15}
done

# 5. Wait with explicit error checking (no set -e!)
FAILED=0
for pid in "${PIDS[@]}"; do
  wait "$pid" || ((FAILED++))
done

# 6. Summarize
uv run python -m scripts.process_sweep LOG_DIR -o REPORT_DIR --dashboard-only

# 7. Upload (if rclone configured)
# rclone copy LOG_DIR gdrive:lambda-results/RUN_NAME --progress

echo "Done. $((${#PIDS[@]} - FAILED))/${#PIDS[@]} succeeded."
```

### Key design patterns
- **Always** use `gpu-pool` / `gpu-run` for multi-GPU scheduling
- **Always** pre-cache models before launching parallel experiments
- **Always** use `set -uo pipefail` (no `-e`) with background processes
- **Always** stagger launches (15s default) to prevent resource contention
- **Never** auto-terminate from the script (plugin manages this)
- **Always** write experiment_status.json when done (monitor checks for this)
