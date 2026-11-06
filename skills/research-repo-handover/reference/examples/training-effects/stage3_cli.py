"""Rename CLI groups and commands wherever `training-effects <group> <command>` is written."""
import re, subprocess
from pathlib import Path
SUBS = [
    ("evaluation run-hypotheses", "measure run"), ("evaluation launch", "measure launch"),
    ("evaluation import", "measure import"), ("evaluation collect", "measure collect"),
    ("evaluation fetch-targets", "measure fetch-models"), ("evaluation judge-server", "serve judge"),
    ("evaluation target-server", "serve targets"), ("reporting phase1-html", "report html"),
    ("reporting phase1", "report markdown"), ("reporting phase2", "report hypotheses"),
    ("reporting sidecar", "report hypotheses-json"), ("reporting hypotheses_json", "report hypotheses-json"),
    ("benchmark oracle-grade", "benchmark grade-answer-keys"),
]
FROZEN = ("src/training_effects/prompts/", "src/training_effects/training/_vendor/", "benchmarks/shared/reading/",
          "tests/support/fixtures/")
n = 0
for f in subprocess.run(["git", "ls-files"], capture_output=True, text=True, check=True).stdout.split():
    if f.startswith(FROZEN) or f in ("uv.lock",):
        continue
    p = Path(f)
    try:
        t = p.read_text(encoding="utf-8")
    except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
        continue
    new = t
    for old, rep in SUBS:
        new, k = re.subn(rf"(training-effects\s+){re.escape(old)}(?![\w-])", rf"\g<1>{rep}", new)
        n += k
    if new != t:
        p.write_text(new, encoding="utf-8")
print(n, "replacements")
