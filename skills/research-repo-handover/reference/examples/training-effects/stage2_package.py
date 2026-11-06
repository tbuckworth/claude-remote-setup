"""Stage 2: the package, distribution and CLI names.

propensity_prediction -> training_effects (package; also import paths and src/ paths)
propensity-prediction -> training-effects (distribution, Modal project tag)
pp <group>            -> training-effects <group> (the CLI, wherever it is invoked or named)

Run from the repository root after `git mv src/propensity_prediction src/training_effects`.
Text files under FROZEN are left alone, except that the package name in vendored *docstrings*
is updated (the staging transform strips docstrings; the staged-sandbox comparison proves it).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path.cwd()
FROZEN_PREFIXES = (
    "src/training_effects/prompts/",  # authored model-facing text (README.md excepted below)
    "benchmarks/shared/reading/",
    "benchmarks/shared/checkpoints/",
    "benchmarks/optimisers/ground-truth/",
    "benchmarks/shared/ground-truth/",
    "tests/support/fixtures/",
)
ALLOWED_IN_FROZEN = {"src/training_effects/prompts/README.md"}
FROZEN_FILES = {"uv.lock", "LICENSE"}

CLI_GROUPS = "benchmark|evaluation|reporting|data|artifacts|paths"
RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("package", re.compile(r"propensity_prediction"), "training_effects"),
    ("distribution", re.compile(r"propensity-prediction"), "training-effects"),
    # The CLI: `pp <group>`, `pp --version`, `pp --help`, a bare `pp` in backticks.
    ("cli", re.compile(rf"(?<![A-Za-z0-9_./$-])pp(?= (?:{CLI_GROUPS})\b| --(?:version|help)\b)"), "training-effects"),
    ("cli-backticked", re.compile(r"``pp``|`pp`"), None),  # handled below to keep the quoting
]


def rewrite(text: str, counts: dict[str, int]) -> str:
    for name, rx, rep in RULES:
        if name == "cli-backticked":
            def fix(m: re.Match[str]) -> str:
                return m.group(0).replace("pp", "training-effects")
            text, n = rx.subn(fix, text)
        else:
            text, n = rx.subn(rep, text)
        counts[name] = counts.get(name, 0) + n
    return text


def main() -> None:
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.splitlines()
    counts: dict[str, int] = {}
    for f in files:
        if f in FROZEN_FILES or (f.startswith(FROZEN_PREFIXES) and f not in ALLOWED_IN_FROZEN):
            continue
        p = ROOT / f
        try:
            text = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        new = rewrite(text, counts)
        if new != text:
            p.write_text(new, encoding="utf-8")
    for k, v in counts.items():
        print(f"{v:6d}  {k}")


if __name__ == "__main__":
    main()
