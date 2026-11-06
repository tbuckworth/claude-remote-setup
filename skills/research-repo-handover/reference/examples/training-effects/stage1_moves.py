"""Stage 1 of the restructure: moves and path updates only (no identifier renames).

Run from the repository root:  python3 stage1_moves.py
1. `git mv` every entry of MOVES (files or directories), creating parents.
2. Replace each old path string with its new one (longest first) in every tracked text file
   outside FROZEN, and report the count per pair.
3. Delete DELETE entries.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path.cwd()

# Task sets: old path -> new path (the dev check task set moves out of configs/ into its study).
TASK_SETS = {
    "benchmarks/em_optimisers/batteries/em-optimisers-hypotheses-fixed10.yaml": "benchmarks/optimisers/task_sets/ten-hypotheses.yaml",
    "benchmarks/em_optimisers/batteries/em-optimisers-hypotheses-ceiling.yaml": "benchmarks/optimisers/task_sets/open-book.yaml",
    "benchmarks/em_optimisers/batteries/em-optimisers-hypotheses-significance-ceiling.yaml": "benchmarks/optimisers/task_sets/open-book-significance.yaml",
    "benchmarks/em_optimisers/batteries/em-optimisers-hypotheses-surprise-significance-ceiling.yaml": "benchmarks/optimisers/task_sets/open-book-surprise-significance.yaml",
    "benchmarks/em_optimisers/batteries/em-optimisers-hypotheses.yaml": "benchmarks/optimisers/task_sets/open-count-hypotheses.yaml",
    "configs/benchmark/dev/em-optimisers-ceiling-check.yaml": "benchmarks/optimisers/task_sets/open-book-two-rounds.yaml",
    "benchmarks/em_organisms/batteries/em-organisms-hypotheses-instruct-fixed10.yaml": "benchmarks/organisms/task_sets/ten-hypotheses.yaml",
    "benchmarks/em_organisms/batteries/em-organisms-hypotheses-instruct-ceiling.yaml": "benchmarks/organisms/task_sets/open-book.yaml",
    "benchmarks/em_organisms/batteries/em-organisms-hypotheses-instruct.yaml": "benchmarks/organisms/task_sets/open-count-hypotheses.yaml",
    "benchmarks/em_organisms/batteries/em-organisms-hypotheses-instruct-lit-none.yaml": "benchmarks/organisms/task_sets/open-count-hypotheses-no-reading.yaml",
    "benchmarks/em_organisms/batteries/em-organisms-hypotheses.yaml": "benchmarks/organisms/task_sets/base-models-open-count-hypotheses.yaml",
    "benchmarks/em_organisms/batteries/em-organisms.yaml": "benchmarks/organisms/task_sets/reports-only.yaml",
}

C = "configs"
RUN_CONFIGS = {
    f"{C}/benchmark/base-fixed10.yaml": f"{C}/runs/base.yaml",
    f"{C}/benchmark/base-ceiling.yaml": f"{C}/runs/base-open-book.yaml",
    f"{C}/benchmark/run-optimisers-fixed10-opus-5.5.yaml": f"{C}/runs/optimisers-opus-5.5.yaml",
    f"{C}/benchmark/run-organisms-fixed10-opus-5.5.yaml": f"{C}/runs/organisms-opus-5.5.yaml",
    f"{C}/benchmark/run-optimisers-fixed10-try.yaml": f"{C}/runs/optimisers-try.yaml",
    f"{C}/benchmark/run-organisms-fixed10-try.yaml": f"{C}/runs/organisms-try.yaml",
    f"{C}/benchmark/run-optimisers-hypotheses-fixed10-smoke.yaml": f"{C}/runs/optimisers-mock.yaml",
    f"{C}/benchmark/run-organisms-hypotheses-fixed10-smoke.yaml": f"{C}/runs/organisms-mock.yaml",
    f"{C}/benchmark/run-organisms-modal-smoke.yaml": f"{C}/runs/organisms-mock-modal.yaml",
    f"{C}/benchmark/run-optimisers-ceiling-opus-5.5.yaml": f"{C}/runs/optimisers-open-book-opus-5.5.yaml",
    f"{C}/benchmark/run-organisms-ceiling-opus-5.5.yaml": f"{C}/runs/organisms-open-book-opus-5.5.yaml",
    f"{C}/benchmark/run-optimisers-ceiling-fable-5.1.yaml": f"{C}/runs/optimisers-open-book-fable-5.1.yaml",
    f"{C}/benchmark/run-optimisers-ceiling-try.yaml": f"{C}/runs/optimisers-open-book-try.yaml",
    f"{C}/benchmark/run-optimisers-ceiling-smoke.yaml": f"{C}/runs/optimisers-open-book-mock.yaml",
    f"{C}/benchmark/oracle-optimisers-ceiling-anchor-free.yaml": f"{C}/answer-key-grading/optimisers.yaml",
    f"{C}/benchmark/oracle-organisms-ceiling-anchor-free.yaml": f"{C}/answer-key-grading/organisms.yaml",
    f"{C}/benchmark/screen/severe-harm-120b.yaml": f"{C}/screen/settings.yaml",
    f"{C}/evaluation/judge_server/gpt-oss-safeguard-120b.yaml": f"{C}/screen/server.yaml",
    f"{C}/evaluation/target_server/qwen3-8b-optimisers.yaml": f"{C}/target-servers/optimisers-qwen3-8b.yaml",
    f"{C}/evaluation/target_server/qwen3-1.7b-organisms.yaml": f"{C}/target-servers/organisms-qwen3-1.7b.yaml",
    f"{C}/evaluation/target_server/qwen3-4b-organisms.yaml": f"{C}/target-servers/organisms-qwen3-4b.yaml",
    f"{C}/evaluation/ceiling/em-optimisers-rounds.yaml": f"{C}/open-book-rounds/optimisers.yaml",
    f"{C}/evaluation/ceiling/em-organisms-rounds.yaml": f"{C}/open-book-rounds/organisms.yaml",
    f"{C}/evaluation/hypothesis_tests/measure-optimisers-fixed10-try.yaml": f"{C}/measurements/optimisers-try.yaml",
    f"{C}/evaluation/hypothesis_tests/measure-organisms-fixed10-try.yaml": f"{C}/measurements/organisms-try.yaml",
    f"{C}/evaluation/hypothesis_tests/em-optimisers-001.yaml": f"{C}/measurements/validation/optimisers.yaml",
    f"{C}/evaluation/hypothesis_tests/em-organisms-001.yaml": f"{C}/measurements/validation/organisms-base-models.yaml",
    f"{C}/evaluation/hypothesis_tests/em-organisms-013-sol.yaml": f"{C}/measurements/validation/organisms.yaml",
    f"{C}/hypothesis_tests/targets/em-optimisers-001.yaml": f"{C}/trained-models/em-optimisers-001.yaml",
    f"{C}/hypothesis_tests/targets/em-organisms-001.yaml": f"{C}/trained-models/em-organisms-001.yaml",
    f"{C}/hypothesis_tests/targets/em-organisms-004.yaml": f"{C}/trained-models/em-organisms-004.yaml",
    f"{C}/providers/openrouter-pins.yaml": f"{C}/openrouter-pins.yaml",
    f"{C}/reporting/report-optimisers-fixed10-try.yaml": f"{C}/reports/optimisers-try.yaml",
    f"{C}/reporting/report-organisms-fixed10-try.yaml": f"{C}/reports/organisms-try.yaml",
    f"{C}/reporting/page-optimisers-fixed10-try.yaml": f"{C}/reports/optimisers-try-html.yaml",
    f"{C}/reporting/page-organisms-fixed10-try.yaml": f"{C}/reports/organisms-try-html.yaml",
}

OTHER = {
    "data/manifest.yaml": "benchmarks/shared/datasets.yaml",
    "experiments/hypothesis_scoring/pilot-2026-10-29/anchors.json": "benchmarks/shared/scoring/anchors.json",
    "sky/hypotheses.yaml": "deploy/measurement-pod.yaml",
    "sky/_common.sh": "deploy/pod-common.sh",
    "scripts/measure_local.sh": "deploy/measure-local.sh",
    "conftest.py": "tests/conftest.py",
}

DIRS = {  # after the files above: remaining directory moves
    "benchmarks/em_optimisers/batteries": None,  # emptied by TASK_SETS
    "benchmarks/em_organisms/batteries": None,
    "benchmarks/em_optimisers": "benchmarks/optimisers",
    "benchmarks/em_organisms": "benchmarks/organisms",
}

# Path strings that do not appear whole in the file moves above.
EXTRA_SUBS = [
    ("configs/hypothesis_tests/inputs", "configs/measurements/inputs"),
    ("configs/hypothesis_tests/targets", "configs/trained-models"),
    ('"configs" / "hypothesis_tests" / "targets"', '"configs" / "trained-models"'),
    ("benchmarks/em_optimisers", "benchmarks/optimisers"),
    ("benchmarks/em_organisms", "benchmarks/organisms"),
    ("*/batteries/*.yaml", "*/task_sets/*.yaml"),
    ("configs/benchmark/screen/", "configs/screen/"),
    ("configs/evaluation/judge_server/", "configs/screen/"),
    ("configs/evaluation/target_server/", "configs/target-servers/"),
    ("configs/evaluation/ceiling/", "configs/open-book-rounds/"),
    ("configs/evaluation/hypothesis_tests/", "configs/measurements/"),
    ("configs/providers/openrouter-pins.yaml", "configs/openrouter-pins.yaml"),
    ('"configs" / "providers" / "openrouter-pins.yaml"', '"configs" / "openrouter-pins.yaml"'),
    ("configs/benchmark/", "configs/runs/"),
    ("configs/reporting/", "configs/reports/"),
    ("external/NOTICE.md", "NOTICE"),
]

DELETE = [
    "scripts", "docs", "tools", "external", "experiments", "data", "sky",
    "CLAUDE.md", "NOTICE.md", "benchmarks/README.md",
]

FROZEN_PREFIXES = (
    "src/propensity_prediction/prompts/",
    "src/propensity_prediction/training/_vendor/",
    "benchmarks/shared/reading/",
    "benchmarks/shared/checkpoints/",
    "benchmarks/optimisers/ground-truth/",
    "benchmarks/shared/ground-truth/",
    "tests/support/fixtures/",
)
FROZEN_FILES = {"uv.lock", "LICENSE"}


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def mv(old: str, new: str) -> None:
    (ROOT / new).parent.mkdir(parents=True, exist_ok=True)
    git("mv", old, new)


def main() -> int:
    for table in (TASK_SETS, RUN_CONFIGS, OTHER):
        for old, new in table.items():
            mv(old, new)
    for old, new in DIRS.items():
        if new is None:
            continue
        mv(old, new)
    subs = sorted(
        [*TASK_SETS.items(), *RUN_CONFIGS.items(), *((o, n) for o, n in OTHER.items() if o != "conftest.py")],
        key=lambda kv: -len(kv[0]),
    ) + EXTRA_SUBS
    files = [f for f in git("ls-files").splitlines()]
    counts = {old: 0 for old, _ in subs}
    for f in files:
        if f in FROZEN_FILES or f.startswith(FROZEN_PREFIXES):
            continue
        p = ROOT / f
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        new_text = text
        for old, new in subs:
            if old in new_text:
                counts[old] += new_text.count(old)
                new_text = new_text.replace(old, new)
        if new_text != text:
            p.write_text(new_text, encoding="utf-8")
    for old, new in subs:
        print(f"{counts[old]:5d}  {old} -> {new}")
    for d in DELETE:
        if (ROOT / d).exists():
            git("rm", "-r", "-q", d)
            print(f"deleted {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
