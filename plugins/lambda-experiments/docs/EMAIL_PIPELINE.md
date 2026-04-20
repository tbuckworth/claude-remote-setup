# PTB Email Pipeline

Two email flows, both triggered by `.eval` files appearing locally:

1. **Per-eval email** — fired as soon as each `.eval` is SCP'd back. A quick "[eval] X of N — scores=…" note so the user knows what's landing in real time.
2. **PTB FINAL summary email** — fired after each batch settles (or on demand). Aggregates all 6h runs into charts + a table of results across the 11 canonical variants.

Both use the same `send_report_email.py` sender (inline images via MIME Content-ID) and the same build script (`build_ptb_report.py`). This doc is the operator's runbook for running the flows by hand or in a wakeup loop.

---

## Prerequisites

**Sender**:
```
~/.claude/plugins/cache/custom-plugins/report-email/1.0.0/scripts/send_report_email.py
```
Uses the Gmail OAuth token at `~/.config/google-docs-mcp/token.json` (needs `gmail.send` scope; `gmail.modify` for labels).

**Build script**:
```
<plugin>/scripts/build_ptb_report.py
```

**Eval enumerator** (PTB summary only — picks the latest-iteration cluster across multiple results dirs):
```
<plugin>/scripts/enumerate_latest_runs.py
```

**Eval extractor** (per-eval summary scorer reader):
```
<plugin>/scripts/extract-eval-results.py
```

---

## Flow 1: Per-eval email

Fires when a single `.eval` has just been SCP'd back. Quick sanity-check before the user has to read a full report.

### Minimal runbook

```bash
EVAL=~/pyg/control-arena-results/<batch>/ahw_vegan_attack_20260420.eval

# 1. Verify num_hours (catch 2h fix-runs mis-labelled as 6h results)
NUM_HOURS=$(python3 -c "
import zipfile,json
z=zipfile.ZipFile('$EVAL')
h=json.loads(z.read('header.json'))
print((h.get('eval',{}).get('metadata',{}).get('setting',{}).get('num_hours','?')))
")
echo "num_hours=$NUM_HOURS"

# 2. Extract scores + status
python3 <plugin>/scripts/extract-eval-results.py "$(dirname $EVAL)"

# 3. Compose + send a small HTML email (1-screen summary)
cat > /tmp/per_eval_email.html <<HTML
<html><body style="font-family:system-ui;max-width:560px;margin:20px auto">
<h3>[eval] $(basename $EVAL) — num_hours=$NUM_HOURS</h3>
<ul>
 <li>main_task_score: <b>…</b></li>
 <li>side_task_score:  <b>…</b></li>
 <li>status: …</li>
 <li>duration: …</li>
</ul>
</body></html>
HTML

python3 ~/.claude/plugins/cache/custom-plugins/report-email/1.0.0/scripts/send_report_email.py \
  --to titusbuckworth@gmail.com \
  --subject "[eval] $(basename $EVAL .eval)" \
  --html /tmp/per_eval_email.html \
  --label Experiments
```

Tracking: append the filename to `/tmp/processed_evals_batch.txt` so the monitor wakeup loop doesn't re-send.

---

## Flow 2: PTB FINAL summary email

Four inline charts + results table across all (mode × main × side) variants for the filtered cluster.

### Step 1 — Enumerate the latest cluster

Picks latest-iteration runs per canonical variant across multiple batch dirs (regression-guarded).

```bash
python3 <plugin>/scripts/enumerate_latest_runs.py \
  --base ~/pyg/control-arena-results \
  --dirs big-run-2026-04-16-v2,ahw-post288,pwdbio-post-fix,batch-2026-04-18 \
  --num-hours 6 \
  --outdir /tmp
# → /tmp/chosen_latest_cluster.json  (list of [src_dir, filename] pairs)
# → /tmp/six_h_groups.json           (all 6h runs grouped by variant)
```

The `--dirs` list is **iteration order, oldest first**. A later dir beats earlier ones for a variant, unless the later dir is strictly worse on BOTH main and side by >2pp (regression fallback).

### Step 2 — Stage the selected evals

`build_ptb_report.py` scans a single dir, so symlink the chosen files into one staging dir.

```bash
rm -rf /tmp/ptb_staged_evals
mkdir -p /tmp/ptb_staged_evals
python3 <<PY
import json, os
from pathlib import Path
BASE = Path.home() / "pyg/control-arena-results"
STAGE = Path("/tmp/ptb_staged_evals")
for src, fname in json.load(open("/tmp/chosen_latest_cluster.json")):
    target = BASE / src / fname
    link = STAGE / fname
    if not link.exists():
        link.symlink_to(target)
PY
ls /tmp/ptb_staged_evals | wc -l   # sanity
```

### Step 3 — Build the report

```bash
python3 <plugin>/scripts/build_ptb_report.py \
  /tmp/ptb_staged_evals \
  --title "PTB 6h sweep — FINAL (N={COUNT})" \
  --out-prefix /tmp/ptb_report
# → /tmp/ptb_report.html
# → /tmp/ptb_report_chart_{1,2,3,4}.png
```

Report contents (see `build_ptb_report.py` docstring for detail):
- **Chart 1** — Main task bar, honest vs attack, per main_task; IFEval baseline dotted reference.
- **Chart 2** — Side task bar, honest per-side-task vs attack single-target.
- **Chart 3** — Main-task checkpoint curves (x = hours since each eval's `header.eval.created`, y = main score). Color = main_task, solid = honest, dashed = attack.
- **Chart 4** — Side-task checkpoint curves, same convention but color = side_task.

Baselines for charts 1 & 2 come from `IFEVAL_BASELINES` / `IFEVAL_SIDE_BASELINES` in the build script (see the LoRA IFEval starting checkpoint report).

### Step 4 — Send the email (CID naming is load-bearing)

The HTML references images as `cid:chart1`, `cid:chart2`, `cid:chart3`, `cid:chart4` — **no underscores, no `chart_1`**. The sender warns and silently strips mismatched images if CIDs don't match.

```bash
python3 ~/.claude/plugins/cache/custom-plugins/report-email/1.0.0/scripts/send_report_email.py \
  --to titusbuckworth@gmail.com \
  --subject "[Lambda] PTB FINAL — $(ls /tmp/ptb_staged_evals | wc -l) evals" \
  --html /tmp/ptb_report.html \
  --image chart1:/tmp/ptb_report_chart_1.png \
  --image chart2:/tmp/ptb_report_chart_2.png \
  --image chart3:/tmp/ptb_report_chart_3.png \
  --image chart4:/tmp/ptb_report_chart_4.png \
  --label Experiments
```

If you ever rename the CIDs in `build_ptb_report.py`, the `--image` flags here must change too. Verify by grepping:
```bash
grep -o 'cid:[a-z0-9_]\+' /tmp/ptb_report.html | sort -u
```

### Common mistakes (from past runs)

- **CID mismatch** → images render as blank boxes. Use `chart1…chart4`, not `chart_1…chart_4`.
- **Including 2h fix-runs in a "6h" report** → `enumerate_latest_runs.py --num-hours 6` filters on `setting.num_hours` from `header.json`, not wall-clock duration. Do not replace this check with a file-mtime heuristic.
- **Missing honest checkpoint curves** on charts 3/4 → pre-PR #293 Lambda commit. `_score_single_checkpoint` only records the first side task per checkpoint. Re-run with a post-#293 commit to recover.

---

## Wiring into a wakeup loop

Typical monitor flow (per-eval email for each new `.eval`, PTB summary after each batch of 8 completes):

```
loop:
  SCP new *.eval from ubuntu@IP:~/control-arena/logs/<LOG_DIR>/ to local <batch-dir>/
  for each new file not in /tmp/processed_evals_batch.txt:
      verify num_hours matches expectation
      extract scores via extract-eval-results.py
      build + send per-eval email
      append filename to /tmp/processed_evals_batch.txt
  if batch of 8 just completed:
      enumerate_latest_runs.py
      stage to /tmp/ptb_staged_evals/
      build_ptb_report.py
      send PTB FINAL email
  schedule next wakeup
```

Keep all pipeline state in `/tmp/` or in the batch's local results dir — **never** under `~/.claude/` (triggers permission prompts during autonomous wakeups).
