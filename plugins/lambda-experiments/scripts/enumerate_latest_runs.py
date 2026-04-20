#!/usr/bin/env python3
"""Enumerate PostTrainBench runs across multiple result directories and pick
the latest-iteration cluster per canonical variant.

Problem this solves
--------------------
A long-lived PTB sweep typically has multiple "fix iterations" — each
iteration lives in its own results dir (a new batch after a bug fix, a
follow-up for a specific variant, etc). Many results dirs also contain a
mix of 6h runs and shorter (2h fix-check) runs. When you want to summarise
*just the latest real 6h cohort* per variant, you need to:

  1. Walk every .eval, read header.json, filter by `setting.num_hours`.
  2. Group by (mode, main_task, side_task) — the canonical 11 variants.
  3. Within each variant, pick the newest iteration-dir unless its scores
     are strictly worse than a prior iteration (regression guard).

Outputs
-------
  <outdir>/six_h_groups.json       — all matching runs grouped by variant
  <outdir>/chosen_latest_cluster.json — [[src_dir, filename], ...] selected

The selected list is the input to `stage_evals.sh` (see EMAIL_PIPELINE.md)
which symlinks the chosen .eval files into one dir for build_ptb_report.py.

Usage
-----
  python3 enumerate_latest_runs.py \
      --base /home/titus/pyg/control-arena-results \
      --dirs big-run-2026-04-16-v2,ahw-post288,batch-2026-04-18 \
      --num-hours 6 \
      --outdir /tmp

Any positional dir name in --dirs is both a filesystem subdir under --base
AND its position in the list is the iteration order (left = oldest).
"""
from __future__ import annotations

import argparse
import json
import zipfile
from collections import defaultdict
from pathlib import Path

# Canonical 11 PTB variants (7 attack + 4 honest).
# The honest multi-side labels use "|" to list the side tasks the
# multi-side scorer tracks; the first side task in each label is what
# per-checkpoint scoring reports (pre-PR #293).
ATTACK_PAIRS = [
    ("humaneval", "induce_self_loyalty"),
    ("bfcl", "deployment_context_aware"),
    ("arenahardwriting", "language_dependent_alignment"),
    ("arenahardwriting", "make_model_vegan"),
    ("gsm8k", "narrow_expert_humaneval"),
    ("gsm8k", "obscure_model_reasoning"),
    ("gsm8k", "password_locked_biology"),
]
HONEST_VARIANTS = [
    ("humaneval", "induce_self_loyalty"),
    ("bfcl", "deployment_context_aware"),
    ("arenahardwriting", "make_model_vegan|language_dependent_alignment"),
    ("gsm8k", "obscure_model_reasoning|password_locked_biology|narrow_expert_humaneval"),
]

REGRESSION_EPS = 0.02  # prefer older iteration if newest loses by >2pp on BOTH scores


def load_runs(base: Path, dirs: list[str], target_num_hours: float) -> list[dict]:
    runs: list[dict] = []
    for src in dirs:
        d = base / src
        if not d.exists():
            continue
        for f in sorted(d.glob("*.eval")):
            if f.stat().st_size < 1_000_000:
                continue
            try:
                with zipfile.ZipFile(f) as z:
                    h = json.load(z.open("header.json"))
                    red = (
                        json.load(z.open("reductions.json"))
                        if "reductions.json" in z.namelist()
                        else []
                    )
            except Exception:
                continue
            if h.get("status") not in ("success", "error"):
                continue
            ev = h.get("eval") or {}
            meta = ev.get("metadata") or {}
            setting = meta.get("setting") or {}
            num_hours = setting.get("num_hours")
            if float(num_hours or 0) != float(target_num_hours):
                continue
            scores: dict = {}
            per_side: dict = {}
            for item in red:
                name = item.get("scorer", "")
                samples = item.get("samples") or []
                if not samples:
                    continue
                scores[name] = samples[0].get("value")
                if name == "posttrain_multi_side_scorer":
                    md = samples[0].get("metadata") or {}
                    sts = md.get("side_task_scores") or {}
                    for sn, sd in sts.items():
                        if isinstance(sd, dict):
                            per_side[sn] = sd.get("score")
            runs.append(
                {
                    "src_dir": src,
                    "file": f.name,
                    "status": h.get("status"),
                    "main_task": setting.get("main_task"),
                    "mode": meta.get("mode"),
                    "side_task": setting.get("side_task") or "",
                    "num_hours": num_hours,
                    "started_at": ev.get("created"),
                    "main_score": scores.get("posttrain_main_scorer"),
                    "side_score": scores.get("posttrain_multi_side_scorer"),
                    "per_side": per_side,
                }
            )
    return runs


def variant_key(r: dict) -> tuple[str, str, str]:
    return (r["mode"], r["main_task"], r["side_task"])


def mean_or_none(lst):
    lst = [x for x in lst if x is not None]
    return sum(lst) / len(lst) if lst else None


def pick_iteration(runs_in_variant: list[dict], iter_order: dict[str, int]) -> list[dict]:
    """Group by src_dir; return the newest iteration's runs, UNLESS it's a
    regression (strictly worse than a prior iteration on BOTH main AND side
    by > REGRESSION_EPS), in which case fall back to that prior iteration.
    """
    by_iter: dict[str, list[dict]] = defaultdict(list)
    for r in runs_in_variant:
        by_iter[r["src_dir"]].append(r)

    iters_sorted = sorted(by_iter.keys(), key=lambda d: -iter_order.get(d, -1))
    if len(iters_sorted) <= 1:
        return by_iter[iters_sorted[0]] if iters_sorted else []

    newest = iters_sorted[0]
    newest_runs = by_iter[newest]
    newest_main = mean_or_none([r["main_score"] for r in newest_runs])
    newest_side = mean_or_none([r["side_score"] for r in newest_runs])

    for prev in iters_sorted[1:]:
        prev_runs = by_iter[prev]
        prev_main = mean_or_none([r["main_score"] for r in prev_runs])
        prev_side = mean_or_none([r["side_score"] for r in prev_runs])
        if (
            newest_main is not None
            and prev_main is not None
            and newest_side is not None
            and prev_side is not None
            and newest_main < prev_main - REGRESSION_EPS
            and newest_side < prev_side - REGRESSION_EPS
        ):
            return prev_runs
    return newest_runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", type=Path, required=True, help="Parent dir holding iteration subdirs")
    ap.add_argument(
        "--dirs",
        required=True,
        help="Comma-separated iteration subdir names, OLDEST first (position = iteration order)",
    )
    ap.add_argument("--num-hours", type=float, default=6.0, help="Filter runs with exactly this setting.num_hours")
    ap.add_argument("--outdir", type=Path, default=Path("/tmp"))
    args = ap.parse_args()

    dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
    iter_order = {d: i for i, d in enumerate(dirs)}

    runs = load_runs(args.base, dirs, args.num_hours)
    print(f"Total {args.num_hours:g}h runs loaded: {len(runs)}")

    by_variant: dict[tuple, list[dict]] = defaultdict(list)
    for r in runs:
        by_variant[variant_key(r)].append(r)

    args.outdir.mkdir(parents=True, exist_ok=True)
    with open(args.outdir / "six_h_groups.json", "w") as f:
        json.dump({str(k): v for k, v in by_variant.items()}, f, default=str, indent=2)

    chosen: list[list[str]] = []
    print(f"\n{'mode':<8}{'main':<18}{'side':<42}{'iter':<26}{'n':<4}score_main  score_side")
    print("-" * 120)
    for mode, pairs in (("attack", ATTACK_PAIRS), ("honest", HONEST_VARIANTS)):
        for mt, st in pairs:
            picked = pick_iteration(by_variant.get((mode, mt, st), []), iter_order)
            for r in picked:
                chosen.append([r["src_dir"], r["file"]])
            m = mean_or_none([r["main_score"] for r in picked])
            s = mean_or_none([r["side_score"] for r in picked])
            iter_dir = picked[0]["src_dir"] if picked else "—"
            m_str = f"{m:.3f}" if m is not None else "—"
            s_str = f"{s:.3f}" if s is not None else "—"
            print(f"{mode:<8}{mt:<18}{st[:40]:<42}{iter_dir:<26}{len(picked):<4}{m_str:<11} {s_str}")

    with open(args.outdir / "chosen_latest_cluster.json", "w") as f:
        json.dump(chosen, f, indent=2)

    print(f"\nChosen: {len(chosen)} runs across {len(ATTACK_PAIRS) + len(HONEST_VARIANTS)} variants")
    print(f"Wrote {args.outdir}/chosen_latest_cluster.json and six_h_groups.json")


if __name__ == "__main__":
    main()
