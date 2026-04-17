#!/usr/bin/env python3
"""Generate HTML report + chart PNGs from parsed eval metadata.

Reads a JSON array of run dicts on stdin (produced by ship_eval.py).
Writes: eval_report.html, bar_main.png, bar_side.png, training_curves.png
to the specified --output-dir.

This is a fallback for ~/control-arena/scripts/generate_ptb_report.py
(source of truth for the report format). If that script becomes available,
ship_eval.py should call it instead.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D


MAIN_COLOR = "#2563eb"
SIDE_COLOR = "#dc2626"
CANONICAL_TASK_ORDER = ["bfcl", "gpqamain", "gsm8k", "arenahardwriting", "humaneval"]
TASK_LABELS = {
    "bfcl": "BFCL",
    "gpqamain": "GPQA Main",
    "gsm8k": "GSM8K",
    "arenahardwriting": "Arena Hard Writing",
    "humaneval": "HumanEval",
}


def _mean_stderr(values):
    vs = [v for v in values if v is not None]
    if not vs:
        return None, None, 0
    n = len(vs)
    m = sum(vs) / n
    if n > 1:
        var = sum((v - m) ** 2 for v in vs) / (n - 1)
        stderr = (var / n) ** 0.5
    else:
        stderr = 0.0
    return m, stderr, n


def _task_order(all_runs):
    present = {r["task"] for r in all_runs}
    ordered = [t for t in CANONICAL_TASK_ORDER if t in present]
    ordered += sorted(t for t in present if t not in CANONICAL_TASK_ORDER)
    return ordered


def build_training_curves(all_runs, output_dir):
    """Generate the per-run training curves panel grid."""
    honest_runs = [r for r in all_runs if r["mode"] == "honest"]
    attack_runs = [r for r in all_runs if r["mode"] == "attack"]
    task_order = _task_order(all_runs)

    # Compute relative hours
    for run in all_runs:
        if run["checkpoints"]:
            first_ts = run["checkpoints"][0].get("timestamp", "")
            try:
                t0 = datetime.fromisoformat(first_ts)
                for ckpt in run["checkpoints"]:
                    t = datetime.fromisoformat(ckpt["timestamp"])
                    ckpt["hours"] = (t - t0).total_seconds() / 3600
            except (ValueError, TypeError):
                for i, ckpt in enumerate(run["checkpoints"]):
                    ckpt["hours"] = i * 0.5

    # Build panels: one per honest task, one per attack run
    panels = []
    by_task = defaultdict(list)
    for r in honest_runs:
        by_task[r["task"]].append(r)
    for task in task_order:
        entries = by_task.get(task, [])
        if entries:
            panels.append(("honest", task, None, max(entries, key=lambda e: e["file"])))
    for r in sorted(attack_runs, key=lambda x: (x["task"], x.get("side_task", ""))):
        panels.append(("attack", r["task"], r.get("side_task", ""), r))

    if not panels:
        return None

    ncols = min(4, len(panels))
    nrows = (len(panels) + ncols - 1) // ncols
    fig, axes_grid = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows), squeeze=False)
    axes_flat = axes_grid.flatten()
    fig.suptitle("Checkpoint Training Curves", fontsize=13, fontweight="bold")

    for idx, (kind, task, side, entry) in enumerate(panels):
        ax = axes_flat[idx]
        title = TASK_LABELS.get(task, task)
        if kind == "attack":
            title = f"{title}\n[attack: {side}]"
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Hours")
        ax.set_ylabel("Score (%)")
        ax.grid(True, alpha=0.3)

        ckpts = entry["checkpoints"]
        if not ckpts:
            ax.text(0.5, 0.5, "No checkpoints", ha="center", va="center",
                    transform=ax.transAxes, color="#9ca3af")
            ax.set_ylim(0, 100)
            continue

        x = [c["hours"] for c in ckpts]
        y_main = [c["accuracy"] * 100 for c in ckpts]
        all_y = list(y_main)
        ax.plot(x, y_main, color=MAIN_COLOR, marker="o", markersize=4, linewidth=2, label="Main")

        main_val = entry["main_score"]
        if main_val is not None:
            fx = x[-1] + 0.05 * max(x[-1], 1)
            fy = main_val * 100
            all_y.append(fy)
            ax.scatter([fx], [fy], color=MAIN_COLOR, marker="*", s=160, zorder=5)
            ax.plot([x[-1], fx], [y_main[-1], fy], color=MAIN_COLOR,
                    linestyle="--", alpha=0.6, linewidth=1.2)

        if kind == "attack":
            y_side = [(c.get("side_score", 0) or 0) * 100 if c.get("side_score") is not None else None
                      for c in ckpts]
            xs_side = [xx for xx, yy in zip(x, y_side) if yy is not None]
            ys_side = [yy for yy in y_side if yy is not None]
            if ys_side:
                all_y.extend(ys_side)
                ax.plot(xs_side, ys_side, color=SIDE_COLOR, marker="s",
                        markersize=4, linewidth=2, label="Side")
            side_val = entry.get("side_score")
            if side_val is not None and xs_side:
                fx = xs_side[-1] + 0.05 * max(xs_side[-1], 1)
                fy = side_val * 100
                all_y.append(fy)
                ax.scatter([fx], [fy], color=SIDE_COLOR, marker="*", s=160, zorder=5)
                ax.plot([xs_side[-1], fx], [ys_side[-1], fy], color=SIDE_COLOR,
                        linestyle="--", alpha=0.6, linewidth=1.2)

        ymax = max(all_y) * 1.15 if all_y else 10
        ax.set_ylim(0, max(ymax, 10))
        legend_handles = [Line2D([0], [0], color=MAIN_COLOR, marker="o", label="Main", linewidth=2)]
        if kind == "attack":
            legend_handles.append(Line2D([0], [0], color=SIDE_COLOR, marker="s", label="Side", linewidth=2))
        legend_handles.append(Line2D([0], [0], color="gray", marker="*", markersize=10,
                                     linestyle="none", label="Final submitted"))
        ax.legend(handles=legend_handles, loc="best", fontsize=7)

    for j in range(len(panels), len(axes_flat)):
        axes_flat[j].set_visible(False)

    plt.tight_layout()
    out = output_dir / "training_curves.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    return out


def build_bar_main(all_runs, output_dir):
    """Bar chart of main task scores grouped by mode."""
    tasks = _task_order(all_runs)
    if not tasks:
        return None

    x_pos = list(range(len(tasks)))
    bar_w = 0.38
    fig, ax = plt.subplots(figsize=(max(7, 1.6 * len(tasks)), 5))

    for offset, mode_name, color in [(-bar_w / 2, "honest", "#22c55e"),
                                      (bar_w / 2, "attack", "#ef4444")]:
        means, errs, ns = [], [], []
        for t in tasks:
            vals = [r["main_score"] for r in all_runs
                    if r["task"] == t and r["mode"] == mode_name and r["main_score"] is not None]
            m, e, n = _mean_stderr(vals)
            means.append(m if m is not None else 0)
            errs.append(e if e is not None else 0)
            ns.append(n)
        xs = [p + offset for p in x_pos]
        ax.bar(xs, means, bar_w, yerr=errs, color=color,
               edgecolor="#111827", linewidth=0.6, capsize=4,
               label=mode_name.capitalize(), alpha=0.85)
        for xi, m, n in zip(xs, means, ns):
            if n > 0:
                ax.text(xi, m + 0.02, f"n={n}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(x_pos)
    ax.set_xticklabels([TASK_LABELS.get(t, t) for t in tasks], rotation=15, ha="right")
    ax.set_ylabel("Mean main score")
    ax.set_ylim(0, 1.1)
    ax.set_title("Main Task Scores by Mode", fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")
    plt.tight_layout()
    out = output_dir / "bar_main.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    return out


def build_bar_side(all_runs, output_dir):
    """Bar chart of side task scores grouped by mode."""
    side_task_set = set()
    for r in all_runs:
        if r["mode"] == "honest":
            side_task_set.update(r.get("side_task_scores", {}).keys())
        elif r.get("side_task"):
            side_task_set.add(r["side_task"])
    side_tasks = sorted(side_task_set)
    if not side_tasks:
        return None

    x_pos = list(range(len(side_tasks)))
    bar_w = 0.38
    fig, ax = plt.subplots(figsize=(max(8, 1.7 * len(side_tasks)), 5))

    for offset, mode_name, color in [(-bar_w / 2, "honest", "#22c55e"),
                                      (bar_w / 2, "attack", "#ef4444")]:
        means, errs, ns = [], [], []
        for st in side_tasks:
            if mode_name == "honest":
                vals = [r.get("side_task_scores", {}).get(st) for r in all_runs if r["mode"] == "honest"]
            else:
                vals = [r["side_score"] for r in all_runs
                        if r["mode"] == "attack" and r.get("side_task") == st]
            m, e, n = _mean_stderr(vals)
            means.append(m if m is not None else 0)
            errs.append(e if e is not None else 0)
            ns.append(n)
        xs = [p + offset for p in x_pos]
        ax.bar(xs, means, bar_w, yerr=errs, color=color,
               edgecolor="#111827", linewidth=0.6, capsize=4,
               label=mode_name.capitalize(), alpha=0.85)
        for xi, m, n in zip(xs, means, ns):
            if n > 0:
                ax.text(xi, m + 0.02, f"n={n}", ha="center", va="bottom", fontsize=9, fontweight="bold")

    ax.set_xticks(x_pos)
    ax.set_xticklabels(side_tasks, rotation=20, ha="right")
    ax.set_ylabel("Mean side score")
    ax.set_ylim(0, 1.1)
    ax.set_title("Side Task Scores by Mode", fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right")
    plt.tight_layout()
    out = output_dir / "bar_side.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close()
    return out


def build_html(all_runs, folder_link, output_dir):
    """Build the HTML email body with tables and CID image references."""
    honest_runs = [r for r in all_runs if r["mode"] == "honest"]
    attack_runs = [r for r in all_runs if r["mode"] == "attack"]
    task_order = _task_order(all_runs)

    # Best honest run per task
    by_task = defaultdict(list)
    for r in honest_runs:
        by_task[r["task"]].append(r)
    summary = {}
    for task, runs in by_task.items():
        valid = [r for r in runs if r["main_score"] is not None]
        if valid:
            summary[task] = max(valid, key=lambda r: r["main_score"])

    # Honest table
    honest_rows = []
    for task in task_order:
        run = summary.get(task)
        if not run:
            continue
        tuned_val = run["main_score"] * 100 if run["main_score"] is not None else None
        ckpt_val = run.get("best_checkpoint")
        ckpt_val = ckpt_val * 100 if ckpt_val is not None else None
        tuned_str = f"{tuned_val:.1f}%" if tuned_val is not None else "N/A"
        ckpt_str = f"{ckpt_val:.1f}%" if ckpt_val is not None else "N/A"
        bar_width = tuned_val if tuned_val is not None else 0
        honest_rows.append(f"""<tr>
  <td style="padding:8px 12px;font-weight:600">{TASK_LABELS.get(task, task)}</td>
  <td style="padding:8px 12px;text-align:center">{tuned_str}</td>
  <td style="padding:8px 12px;text-align:center">{ckpt_str}</td>
  <td style="padding:8px 12px">
    <div style="background:#e5e7eb;border-radius:4px;height:16px;width:100%">
      <div style="background:#2563eb;border-radius:4px;height:16px;width:{bar_width:.0f}%"></div>
    </div>
  </td>
</tr>""")

    # Attack table
    attack_rows = []
    for r in sorted(attack_runs, key=lambda x: (x["task"], x.get("side_task", ""))):
        main_v = r["main_score"]
        side_v = r.get("side_score")
        ckpt_v = r.get("best_checkpoint")
        best_side_ckpt = r.get("best_side_score")
        main_s = f"{main_v*100:.1f}%" if main_v is not None else "CRASH"
        side_s = f"{side_v*100:.1f}%" if side_v is not None else "N/A"
        ckpt_s = f"{ckpt_v*100:.1f}%" if ckpt_v is not None else "?"
        best_side_s = f"{best_side_ckpt*100:.1f}%" if best_side_ckpt is not None else "?"
        n_ckpts = len(r.get("checkpoints", []))
        attack_rows.append(f"""<tr>
  <td style="padding:8px 12px;font-weight:600">{TASK_LABELS.get(r['task'], r['task'])}</td>
  <td style="padding:8px 12px;font-family:ui-monospace,SFMono-Regular,monospace;font-size:12px">{r.get('side_task','')}</td>
  <td style="padding:8px 12px;text-align:center">{main_s}</td>
  <td style="padding:8px 12px;text-align:center">{side_s}</td>
  <td style="padding:8px 12px;text-align:center">{ckpt_s}</td>
  <td style="padding:8px 12px;text-align:center">{best_side_s}</td>
  <td style="padding:8px 12px;text-align:center">{n_ckpts}</td>
</tr>""")

    honest_section = ""
    if honest_rows:
        honest_section = f"""
<h3>Honest runs ({len(honest_runs)})</h3>
<table style="width:100%;border-collapse:collapse;margin:8px 0 24px 0">
<thead>
<tr style="border-bottom:2px solid #e5e7eb">
  <th style="padding:8px 12px;text-align:left">Benchmark</th>
  <th style="padding:8px 12px;text-align:center">Tuned main</th>
  <th style="padding:8px 12px;text-align:center">Best ckpt (main)</th>
  <th style="padding:8px 12px;text-align:left;width:200px">Progress</th>
</tr>
</thead>
<tbody>
{"".join(honest_rows)}
</tbody>
</table>
"""

    attack_section = ""
    if attack_rows:
        attack_section = f"""
<h3>Attack runs ({len(attack_runs)})</h3>
<table style="width:100%;border-collapse:collapse;margin:8px 0 24px 0">
<thead>
<tr style="border-bottom:2px solid #e5e7eb">
  <th style="padding:8px 12px;text-align:left">Main task</th>
  <th style="padding:8px 12px;text-align:left">Side task</th>
  <th style="padding:8px 12px;text-align:center">Main</th>
  <th style="padding:8px 12px;text-align:center">Side</th>
  <th style="padding:8px 12px;text-align:center">Best ckpt (main)</th>
  <th style="padding:8px 12px;text-align:center">Best ckpt (side)</th>
  <th style="padding:8px 12px;text-align:center">#Ckpts</th>
</tr>
</thead>
<tbody>
{"".join(attack_rows)}
</tbody>
</table>
"""

    folder_line = ""
    if folder_link:
        folder_line = f'<p><a href="{folder_link}">View all evals in Drive</a></p>'

    caveats = """
<div style="color:#6b7280;font-size:12px;margin-top:40px;padding:12px;border-top:1px solid #e5e7eb">
<p><strong>Side-task scoring caveats:</strong></p>
<ul style="margin:4px 0">
<li>Side scores across different scorers are NOT directly comparable -- interpret each relative to its own baseline.</li>
<li>Baseline-subtracted scorers (make_model_vegan, induce_self_loyalty) show normalised scores; raw_score is in the eval file for reference.</li>
<li>narrow_expert_humaneval saturates on small base models (honest baseline ~92% on Llama-3.2-3B); attack effect is not detectable -- flag runs using this scorer.</li>
<li>obscure_model_reasoning and password_locked_biology returning 0.0 means the backdoor was not installed -- this is the scorer working correctly, not a bug.</li>
</ul>
<p style="margin-top:8px">Note: "CRASH" runs excluded from averages. All runs start from the IFEval-tuned LoRA checkpoint.
"Best ckpt" = highest scored intermediate checkpoint; final submitted score may differ.</p>
</div>"""

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>PTB Eval Report</title></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;max-width:840px;margin:40px auto;padding:0 20px">
<h2>PostTrainBench Results</h2>
{folder_line}
{honest_section}
{attack_section}
<h3>Main task scores by mode</h3>
<img src="cid:bar_main" style="max-width:100%" />

<h3>Side task scores by mode</h3>
<img src="cid:bar_side" style="max-width:100%" />

<h3>Training curves (per run)</h3>
<img src="cid:training_curves" style="max-width:100%" />

{caveats}
</body>
</html>"""

    out = output_dir / "eval_report.html"
    out.write_text(html)
    return out


def main():
    parser = argparse.ArgumentParser(description="Generate PTB eval report HTML + charts")
    parser.add_argument("--output-dir", default="/tmp", help="Where to write output files")
    parser.add_argument("--folder-link", default="", help="Drive folder link to embed in report")
    args = parser.parse_args()

    all_runs = json.load(sys.stdin)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    html_path = build_html(all_runs, args.folder_link, output_dir)
    bar_main_path = build_bar_main(all_runs, output_dir)
    bar_side_path = build_bar_side(all_runs, output_dir)
    curves_path = build_training_curves(all_runs, output_dir)

    print(f"html:{html_path}")
    if bar_main_path:
        print(f"bar_main:{bar_main_path}")
    if bar_side_path:
        print(f"bar_side:{bar_side_path}")
    if curves_path:
        print(f"training_curves:{curves_path}")


if __name__ == "__main__":
    main()
