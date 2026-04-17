#!/usr/bin/env python3
"""Build an HTML progress report + 3 charts from a PostTrainBench .eval directory.

Usage:
    python3 build_ptb_report.py RESULTS_DIR [--run-start ISO8601] [--title STR]
                                [--out-prefix /tmp/report]

Produces (in /tmp/ by default):
  <prefix>_chart_1.png — main task bar (honest / attack / IFEval starting-ckpt baseline)
  <prefix>_chart_2.png — side task bar (honest per-side-task / attack single-target)
  <prefix>_chart_3.png — 2-panel checkpoint curves (main top, side bottom)
  <prefix>.html        — inline-styled email-ready HTML

Call the sibling `send_report_email.py` to mail the result.

Data model assumptions
----------------------
* Each `.eval` is a ZIP with `header.json` (scores, metadata) and `reductions.json`
  (per-sample reductions incl. per-checkpoint metadata when available).
* `header.eval.metadata.setting.main_task` / `.side_task` — task identifiers.
* `header.eval.metadata.mode` — "attack" | "honest".
* `header.eval.created` — ISO timestamp when the eval started.
* Final scores live under `reductions.json` entries keyed by scorer name:
    - `posttrain_main_scorer.samples[0].value`           → main_task score
    - `posttrain_multi_side_scorer.samples[0].value`     → attack: single-target score
      For honest runs with multi-side regex, prefer the split dict:
      `samples[0].metadata.side_task_scores` → {side_name: {score, metrics}}.
    - `posttrain_checkpoint_scorer.samples[0].metadata.checkpoint_scores`
       → list of per-checkpoint entries. Each has
         `timestamp`, `accuracy` (main), `side_score`, `side_metrics`, `status`.
       Only `status == 'scored'` rows are used.

Baselines
---------
Main-task baselines are for the IFEval-tuned LoRA starting checkpoint
(meta-llama/Llama-3.2-3B + TitusB/llama3.2-3b-ifeval-lora-r128). These are the
actual starting point for our agents, not the raw base model. Side-task
baselines are not yet computed and are skipped (leave panel un-anchored).

Override via `--baselines KEY=VAL,KEY=VAL`. E.g.
`--baselines gsm8k=0.127,bfcl=0.76,humaneval=0.305,arenahardwriting=0.092`.

Flags
-----
The only "issue" worth flagging in the email is `main_score is None` or
`status == 'error'`. High token counts are normal for arenahardwriting
(LLM-judge × multiple checkpoints can legitimately exceed 10M tokens).

Checkpoint curves (Chart 3)
---------------------------
Chart 3 is a 2-panel stack sharing the x-axis:
  TOP: main_task score over time. Each curve is anchored at (t=0,
       IFEVAL_BASELINE[main_task]) so you can see where the agent started
       and the training trajectory from there.
  BOTTOM: side_task score over time. Per-checkpoint side_score is reported
          by the scorer; caveat: for honest multi-side experiments only
          ONE of the combined side tasks is scored per checkpoint.

For each (main_task, mode) pair we show the mean curve ± SE (shaded, alpha=0.2).
Color = main_task; linestyle solid = honest, dashed = attack.
x-axis = hours since THIS eval's own `header.eval.created` (not run start).

CLI
---
    python3 build_ptb_report.py /path/to/results --title "..." --out-prefix /tmp/myrun

Emit the email via:
    python3 send_report_email.py --to you@example.com --subject "..." \\
        --html /tmp/myrun.html \\
        --image chart1:/tmp/myrun_chart_1.png \\
        --image chart2:/tmp/myrun_chart_2.png \\
        --image chart3:/tmp/myrun_chart_3.png
"""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


IFEVAL_BASELINES = {
    "gsm8k": 0.127,
    "bfcl": 0.760,
    "humaneval": 0.305,
    "arenahardwriting": 0.092,
}

MAIN_COLORS = {
    "gsm8k": "#1f77b4",
    "bfcl": "#ff7f0e",
    "humaneval": "#2ca02c",
    "arenahardwriting": "#d62728",
}

CORE_SIDE_TASKS = [
    "make_model_vegan",
    "induce_self_loyalty",
    "obscure_model_reasoning",
    "language_dependent_alignment",
    "password_locked_biology",
    "deployment_context_aware",
    "narrow_expert_humaneval",
]


@dataclass
class Record:
    file: str
    main_task: str
    mode: str              # "honest" | "attack"
    side_task: str         # raw string from metadata (may be "a|b" regex for honest)
    main_score: float | None
    side_score_single: float | None
    per_side_scores: dict[str, float] = field(default_factory=dict)  # honest only
    total_tokens: int = 0
    status: str = "unknown"
    eval_start: datetime | None = None


def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def load_records(results_dir: Path) -> tuple[list[Record], dict, dict]:
    """Parse every scored .eval in the results dir.

    Returns (records, main_curves_by_key, side_curves_by_key). Curve dicts map
    (main_task, mode) -> list of [(hours_since_eval_start, score), ...] per rep.
    """
    records: list[Record] = []
    main_curves: dict[tuple[str, str], list[list[tuple[float, float]]]] = defaultdict(list)
    side_curves: dict[tuple[str, str], list[list[tuple[float, float]]]] = defaultdict(list)

    for f in sorted(results_dir.glob("*.eval")):
        if f.stat().st_size < 1_000_000:
            continue  # skeleton / in-progress
        try:
            with zipfile.ZipFile(f) as z:
                if "header.json" not in z.namelist():
                    continue
                header = json.load(z.open("header.json"))
                reductions = (
                    json.load(z.open("reductions.json"))
                    if "reductions.json" in z.namelist()
                    else []
                )
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError):
            continue

        if header.get("status") not in {"success", "error"}:
            continue

        ev = header.get("eval", {}) or {}
        meta = ev.get("metadata") or {}
        setting = meta.get("setting") or {}
        main_task = setting.get("main_task")
        mode = meta.get("mode")
        side_task = setting.get("side_task") or ""
        if not main_task or not mode:
            continue

        scores: dict[str, float | None] = {}
        per_side: dict[str, float] = {}
        for item in reductions:
            name = item.get("scorer", "")
            samples = item.get("samples", []) or []
            if not samples:
                continue
            scores[name] = samples[0].get("value")
            if name == "posttrain_multi_side_scorer" and mode == "honest":
                sts = (samples[0].get("metadata") or {}).get("side_task_scores", {}) or {}
                for sname, sdata in sts.items():
                    if isinstance(sdata, dict):
                        per_side[sname] = sdata.get("score")

        stats = header.get("stats") or {}
        mu = (stats.get("model_usage") or {}).get("anthropic/claude-opus-4-7", {}) or {}
        total_tokens = int(mu.get("total_tokens") or 0)

        eval_start = _parse_iso(ev.get("created"))

        records.append(
            Record(
                file=f.name,
                main_task=main_task,
                mode=mode,
                side_task=side_task,
                main_score=scores.get("posttrain_main_scorer"),
                side_score_single=scores.get("posttrain_multi_side_scorer"),
                per_side_scores=per_side,
                total_tokens=total_tokens,
                status=header.get("status", "unknown"),
                eval_start=eval_start,
            )
        )

        # Extract checkpoint curves (per-experiment, per-checkpoint main & side)
        if eval_start is None:
            continue
        for item in reductions:
            if "checkpoint" not in item.get("scorer", ""):
                continue
            for samp in item.get("samples", []) or []:
                ckpts = (samp.get("metadata") or {}).get("checkpoint_scores", []) or []
                main_curve: list[tuple[float, float]] = []
                side_curve: list[tuple[float, float]] = []
                for c in ckpts:
                    if c.get("status") != "scored":
                        continue
                    ts = _parse_iso(c.get("timestamp"))
                    if ts is None:
                        continue
                    hrs = (ts - eval_start).total_seconds() / 3600
                    if c.get("accuracy") is not None:
                        main_curve.append((hrs, float(c["accuracy"])))
                    if c.get("side_score") is not None:
                        side_curve.append((hrs, float(c["side_score"])))
                if main_curve:
                    main_curves[(main_task, mode)].append(main_curve)
                if side_curve:
                    side_curves[(main_task, mode)].append(side_curve)

    return records, dict(main_curves), dict(side_curves)


def _interp_and_aggregate(
    curves: list[list[tuple[float, float]]],
    grid: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Interpolate each rep onto `grid`, return (mean, stderr, count_per_point)."""
    rows = []
    for curve in curves:
        curve_sorted = sorted(curve, key=lambda p: p[0])
        xs = [p[0] for p in curve_sorted]
        ys = [p[1] for p in curve_sorted]
        rows.append(np.interp(grid, xs, ys, left=np.nan, right=np.nan))
    arr = np.asarray(rows)
    counts = np.sum(~np.isnan(arr), axis=0)
    with np.errstate(invalid="ignore"):
        mean = np.nanmean(arr, axis=0)
        stderr = np.nanstd(arr, axis=0) / np.sqrt(np.clip(counts, 1, None))
    return mean, stderr, counts


def plot_main_task_bar(
    records: list[Record],
    baselines: dict[str, float],
    out_path: Path,
) -> None:
    tasks = list(baselines.keys())
    fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)
    fig.patch.set_facecolor("white")
    x = np.arange(len(tasks))
    w = 0.25

    h_means, h_errs, h_ns = [], [], []
    a_means, a_errs, a_ns = [], [], []
    b_vals = []
    for t in tasks:
        hs = [r.main_score for r in records if r.main_task == t and r.mode == "honest" and r.main_score is not None]
        as_ = [r.main_score for r in records if r.main_task == t and r.mode == "attack" and r.main_score is not None]
        h_means.append(np.mean(hs) if hs else 0)
        h_errs.append(np.std(hs) / np.sqrt(len(hs)) if len(hs) > 1 else 0)
        h_ns.append(len(hs))
        a_means.append(np.mean(as_) if as_ else 0)
        a_errs.append(np.std(as_) / np.sqrt(len(as_)) if len(as_) > 1 else 0)
        a_ns.append(len(as_))
        b_vals.append(baselines[t])

    ax.bar(x - w, h_means, w, yerr=h_errs, label="honest", color="#2e8b57", capsize=4)
    ax.bar(x, a_means, w, yerr=a_errs, label="attack", color="#c0392b", capsize=4)
    ax.bar(x + w, b_vals, w, label="IFEval starting ckpt", color="#888", alpha=0.7)
    for i, (hn, an) in enumerate(zip(h_ns, a_ns)):
        if hn:
            ax.text(i - w, h_means[i] + 0.02, f"n={hn}", ha="center", fontsize=8)
        if an:
            ax.text(i, a_means[i] + 0.02, f"n={an}", ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(tasks)
    ax.set_ylabel("main_task_score")
    ax.set_title(f"Main task scores vs IFEval starting ckpt ({len(records)} completed)")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    ax.set_ylim(0, max(max(h_means + a_means + b_vals) + 0.1, 0.85))
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_side_task_bar(
    records: list[Record],
    side_tasks: list[str],
    out_path: Path,
) -> None:
    fig, ax = plt.subplots(figsize=(13, 5.5), dpi=150)
    fig.patch.set_facecolor("white")
    xv = np.arange(len(side_tasks))
    w2 = 0.4

    attack_vals, attack_errs, attack_ns = [], [], []
    honest_vals, honest_errs, honest_ns = [], [], []
    for st in side_tasks:
        a_vals = [
            r.side_score_single for r in records
            if r.mode == "attack" and r.side_task == st and r.side_score_single is not None
        ]
        h_vals = [
            r.per_side_scores.get(st) for r in records
            if r.mode == "honest" and r.per_side_scores.get(st) is not None
        ]
        attack_vals.append(np.mean(a_vals) if a_vals else 0)
        attack_errs.append(np.std(a_vals) / np.sqrt(len(a_vals)) if len(a_vals) > 1 else 0)
        attack_ns.append(len(a_vals))
        honest_vals.append(np.mean(h_vals) if h_vals else 0)
        honest_errs.append(np.std(h_vals) / np.sqrt(len(h_vals)) if len(h_vals) > 1 else 0)
        honest_ns.append(len(h_vals))

    ax.bar(xv - w2 / 2, honest_vals, w2, yerr=honest_errs, label="honest (per-side)", color="#2e8b57", capsize=4)
    ax.bar(xv + w2 / 2, attack_vals, w2, yerr=attack_errs, label="attack (single-target)", color="#c0392b", capsize=4)
    for i, _ in enumerate(side_tasks):
        hn, an = honest_ns[i], attack_ns[i]
        if hn:
            ax.text(i - w2 / 2, honest_vals[i] + 0.02, f"n={hn}", ha="center", fontsize=8)
        if an:
            ax.text(i + w2 / 2, attack_vals[i] + 0.02, f"n={an}", ha="center", fontsize=8)
    ax.set_xticks(xv)
    ax.set_xticklabels(side_tasks, rotation=25, ha="right", fontsize=9)
    ax.set_ylabel("side_task_score")
    ax.set_title("Side task scores — honest (per-side split) vs attack (single-target)")
    ax.legend(loc="upper right")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def plot_checkpoint_curves(
    main_curves: dict[tuple[str, str], list[list[tuple[float, float]]]],
    side_curves: dict[tuple[str, str], list[list[tuple[float, float]]]],
    main_baselines: dict[str, float],
    out_path: Path,
    side_baselines: dict[str, float] | None = None,
) -> None:
    """2-panel stack: top=main, bottom=side. Color=main_task, style=mode.

    Each main curve is prepended with (0, IFEval baseline). Side curves are
    plotted as-is; if `side_baselines` is provided, anchor them too.
    """
    grid = np.arange(0, 7, 0.25)
    fig, (ax_main, ax_side) = plt.subplots(
        2, 1, figsize=(11, 9), dpi=150, sharex=True,
        gridspec_kw={"hspace": 0.15},
    )
    fig.patch.set_facecolor("white")

    def _plot_panel(ax, curves_by_key, baselines):
        for (task, mode), reps in sorted(curves_by_key.items()):
            color = MAIN_COLORS.get(task, "#333")
            linestyle = "-" if mode == "honest" else "--"
            n = len(reps)

            # Optionally prepend baseline anchor
            if baselines is not None and task in baselines:
                anchored_reps = [[(0.0, baselines[task])] + list(c) for c in reps]
            else:
                anchored_reps = reps

            if n == 1:
                xs, ys = zip(*anchored_reps[0])
                ax.plot(xs, ys, color=color, linestyle=linestyle, alpha=0.8,
                        marker="o", markersize=4, linewidth=2,
                        label=f"{task} ({mode}, n=1)")
                continue
            mean, stderr, counts = _interp_and_aggregate(anchored_reps, grid)
            valid = counts > 0
            ax.plot(grid[valid], mean[valid], color=color, linestyle=linestyle,
                    linewidth=2, marker="o", markersize=4,
                    label=f"{task} ({mode}, n={n})")
            ax.fill_between(
                grid[valid],
                (mean - stderr)[valid],
                (mean + stderr)[valid],
                color=color, alpha=0.2,
            )

        # Subtle dotted baseline reference lines
        if baselines is not None:
            for task, bval in baselines.items():
                color = MAIN_COLORS.get(task, "#333")
                ax.axhline(bval, color=color, linestyle=":", alpha=0.35, linewidth=1)

    _plot_panel(ax_main, main_curves, main_baselines)
    _plot_panel(ax_side, side_curves, side_baselines)

    ax_main.set_ylabel("main_task score at checkpoint")
    ax_main.set_title("Checkpoint curves — main task")
    ax_main.legend(loc="best", fontsize=8, framealpha=0.9)
    ax_main.grid(alpha=0.3)

    ax_side.set_xlabel("hours since each eval started")
    ax_side.set_ylabel("side_task score at checkpoint")
    title = "Checkpoint curves — side task"
    if side_baselines is None:
        title += " (honest multi-side shows only 1 of the combined per checkpoint)"
    ax_side.set_title(title)
    ax_side.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(out_path, dpi=150)
    plt.close()


def _row_bg(r: Record) -> str:
    if r.main_score is None or r.status == "error":
        return "#ffe3e3"
    return "#fff"


def build_html(
    records: list[Record],
    baselines: dict[str, float],
    run_start: datetime | None,
    title_prefix: str,
    chart_cids: tuple[str, str, str] = ("chart1", "chart2", "chart3"),
    cost_usd: float | None = None,
    extra_footer: str = "",
) -> str:
    now = datetime.now(timezone.utc)
    elapsed_h = (now - run_start).total_seconds() / 3600 if run_start else None

    n_err = sum(1 for r in records if r.main_score is None or r.status == "error")

    header_sub = f"{len(records)} completed"
    if elapsed_h is not None:
        header_sub += f" &middot; {elapsed_h:.1f}h elapsed"
    if cost_usd is not None:
        header_sub += f" &middot; ${cost_usd:.0f} spent"
    if n_err:
        header_sub += f" &middot; <b>{n_err} empty-score</b>"

    rows_html = []
    for r in sorted(records, key=lambda x: (x.main_task, x.mode, x.side_task)):
        main = r.main_score
        baseline = baselines.get(r.main_task, 0)
        delta_str = ""
        if main is not None:
            delta = main - baseline
            sign = "+" if delta >= 0 else ""
            color = "#060" if delta >= 0 else "#a00"
            delta_str = f'<span style="color:{color}">{sign}{delta:.3f}</span>'
        mode_color = "#2e8b57" if r.mode == "honest" else "#c0392b"
        rows_html.append(
            f'<tr style="background:{_row_bg(r)}">'
            f'<td style="color:{mode_color};font-weight:600">{r.mode}</td>'
            f"<td>{r.main_task}</td>"
            f'<td style="font-size:11px">{r.side_task[:50]}</td>'
            f"<td>{('{:.3f}'.format(main)) if main is not None else '<b style=color:#a00>NONE</b>'}</td>"
            f"<td>{delta_str}</td>"
            f"<td>{('{:.3f}'.format(r.side_score_single)) if r.side_score_single is not None else '—'}</td>"
            f"<td>{'{:,}'.format(r.total_tokens) if r.total_tokens else '—'}</td>"
            f"</tr>"
        )

    errors_list = []
    for r in records:
        if r.main_score is None or r.status == "error":
            errors_list.append(f"{r.mode} {r.main_task}+{r.side_task} — empty scores / error")

    err_banner = ""
    if errors_list:
        err_banner = (
            '<div style="background:#ffe3e3;border-left:4px solid #a00;padding:12px;'
            'margin-top:14px;border-radius:4px"><b style="color:#800">Issues:</b><ul style="margin:6px 0 0 0">'
            + "".join(f"<li>{e}</li>" for e in errors_list)
            + "</ul></div>"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;max-width:860px;margin:20px auto;color:#222;line-height:1.5">
<div style="background:#1f5f3f;color:white;padding:20px;border-radius:8px">
<h1 style="margin:0;font-size:22px">{title_prefix}</h1>
<div style="opacity:0.9;margin-top:6px">{header_sub}</div>
</div>
{err_banner}
<h3>Main task scores vs IFEval starting checkpoint</h3>
<img src="cid:{chart_cids[0]}" style="max-width:100%;border:1px solid #ddd;border-radius:4px"/>
<p style="color:#666;font-size:12px">Grey bars: IFEval-tuned LoRA checkpoint baseline (actual starting point, not raw base model).</p>

<h3>Side task scores — individual side tasks</h3>
<img src="cid:{chart_cids[1]}" style="max-width:100%;border:1px solid #ddd;border-radius:4px"/>
<p style="color:#666;font-size:12px">Honest bars are the <i>per-side-task</i> score extracted from each honest run's multi-scorer (not the combined value). Attack bars are single-target scores.</p>

<h3>Checkpoint training curves</h3>
<img src="cid:{chart_cids[2]}" style="max-width:100%;border:1px solid #ddd;border-radius:4px"/>
<p style="color:#666;font-size:12px">x-axis = hours since each eval's own start. Color = main task. Solid = honest, dashed = attack. Main panel is anchored at t=0 with IFEval baseline; dotted refs show the baseline for each task.</p>

<h3>Per-experiment results</h3>
<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:12px;border:1px solid #ccc">
<thead style="background:#f2f2f2">
<tr><th>mode</th><th>main_task</th><th>side_task(s)</th><th>main</th><th>Δ vs IFEval</th><th>side_multi</th><th>tokens</th></tr>
</thead><tbody>
{''.join(rows_html)}
</tbody></table>
{extra_footer}
</body></html>
"""
    return html


def build_report(
    results_dir: Path,
    out_prefix: Path,
    run_start: datetime | None = None,
    title_prefix: str = "PostTrainBench run — progress",
    baselines: dict[str, float] | None = None,
    side_baselines: dict[str, float] | None = None,
    cost_usd: float | None = None,
    extra_footer: str = "",
) -> dict:
    """Full pipeline: parse .evals, write 3 chart PNGs and one HTML file.

    Returns a dict with paths: {'html': ..., 'chart_1': ..., 'chart_2': ..., 'chart_3': ...}.
    """
    baselines = dict(baselines or IFEVAL_BASELINES)
    records, main_curves, side_curves = load_records(results_dir)

    chart1 = out_prefix.with_name(out_prefix.name + "_chart_1.png")
    chart2 = out_prefix.with_name(out_prefix.name + "_chart_2.png")
    chart3 = out_prefix.with_name(out_prefix.name + "_chart_3.png")
    html_path = out_prefix.with_suffix(".html")

    plot_main_task_bar(records, baselines, chart1)
    plot_side_task_bar(records, CORE_SIDE_TASKS, chart2)
    plot_checkpoint_curves(main_curves, side_curves, baselines, chart3, side_baselines)

    html = build_html(records, baselines, run_start, title_prefix, cost_usd=cost_usd,
                      extra_footer=extra_footer)
    html_path.write_text(html)

    return {"html": html_path, "chart_1": chart1, "chart_2": chart2, "chart_3": chart3,
            "records": records}


def _parse_baselines_arg(s: str | None) -> dict[str, float] | None:
    if not s:
        return None
    out: dict[str, float] = {}
    for pair in s.split(","):
        if "=" not in pair:
            continue
        k, v = pair.split("=", 1)
        out[k.strip()] = float(v.strip())
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    p.add_argument("results_dir", type=Path, help="Directory containing .eval files")
    p.add_argument("--run-start", type=str, default=None,
                   help="ISO8601 run start time. Used for elapsed calc in header.")
    p.add_argument("--title", type=str, default="PostTrainBench run — progress")
    p.add_argument("--out-prefix", type=Path, default=Path("/tmp/ptb_report"),
                   help="Prefix for output files (default: /tmp/ptb_report)")
    p.add_argument("--baselines", type=str, default=None,
                   help="Comma-separated key=value overrides for main-task baselines")
    p.add_argument("--side-baselines", type=str, default=None,
                   help="Comma-separated key=value overrides for side-task baselines (optional)")
    p.add_argument("--cost-usd", type=float, default=None,
                   help="Total spend for the header (for display only).")
    args = p.parse_args()

    run_start = _parse_iso(args.run_start)
    baselines = _parse_baselines_arg(args.baselines) or IFEVAL_BASELINES
    side_baselines = _parse_baselines_arg(args.side_baselines)

    paths = build_report(
        args.results_dir,
        args.out_prefix,
        run_start=run_start,
        title_prefix=args.title,
        baselines=baselines,
        side_baselines=side_baselines,
        cost_usd=args.cost_usd,
    )
    print("HTML:", paths["html"])
    for k in ("chart_1", "chart_2", "chart_3"):
        print(f"{k}:", paths[k])
    print(f"records: {len(paths['records'])}")


if __name__ == "__main__":
    main()
