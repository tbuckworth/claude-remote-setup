"""Stage every task set's sandboxes in one checkout and record them, for a byte-level comparison.

Usage:
  python3 e4_capture.py --repo R --cli "uv run --frozen pp" --key battery \
      --template T.yaml --pairs pairs.tsv --out OUT

`pairs.tsv`: one `label<TAB>task-set path (relative to R)` per line. `T.yaml` is a standalone run
config (no `base:`); each preflight config is T with the task-set key replaced, the adapter check
off and the sandbox local. For every label the staged build directory is copied to OUT/label/,
and OUT/label.files.tsv lists `relative path<TAB>sha256<TAB>mode` for every file under each
instance's `sandbox/` plus each instance's HYPOTHESES.md (what the agent sees), sorted.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

DUMMY_ENV = {
    "PP_SCREEN_BASE_URL": "http://screen.invalid/v1", "PP_SCREEN_API_KEY": "x",
    "TE_SCREEN_BASE_URL": "http://screen.invalid/v1", "TE_SCREEN_API_KEY": "x",
    "PP_TARGET_API_KEY": "x", "PP_TARGET_BASE_URL": "http://t.invalid/v1",
    "PP_TARGET_BASE_URL_QWEN3_1_7B": "http://t.invalid/v1", "PP_TARGET_BASE_URL_QWEN3_4B": "http://t.invalid/v1",
    "TE_TARGET_API_KEY": "x", "TE_TARGET_BASE_URL": "http://t.invalid/v1",
    "TE_TARGET_BASE_URL_QWEN3_1_7B": "http://t.invalid/v1", "TE_TARGET_BASE_URL_QWEN3_4B": "http://t.invalid/v1",
    "ANTHROPIC_API_KEY": "dummy", "OPENROUTER_API_KEY": "dummy",
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, required=True)
    ap.add_argument("--cli", required=True)
    ap.add_argument("--key", required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--pairs", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--extra", action="append", default=[], help="key=yaml-value overrides")
    ap.add_argument("--drop", action="append", default=[], help="keys to remove")
    args = ap.parse_args()
    template = yaml.safe_load(args.template.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, **DUMMY_ENV}
    for k in ("PP_JUDGE_API_KEY", "PP_MONITOR_API_KEY", "TE_JUDGE_API_KEY", "TE_MONITOR_API_KEY"):
        env.pop(k, None)
    failed = 0
    for line in args.pairs.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        label, task_set = line.split("\t")
        settings = dict(template)
        for k in ("battery", "task_set"):
            settings.pop(k, None)
        settings[args.key] = task_set
        settings.update(allow_untested_hypotheses=True, sandbox="docker")
        if "allow_untested_hypotheses" in args.drop:
            settings.pop("allow_untested_hypotheses")
        for kv in args.extra:
            k, v = kv.split("=", 1)
            settings[k] = yaml.safe_load(v)
        for k in args.drop:
            settings.pop(k, None)
        settings["log_dir"] = f"logs/e4-capture-{label}"
        tmp = Path(tempfile.mkdtemp(prefix=f"e4-{label}-", dir=args.out))
        cfg = tmp / "preflight.yaml"
        cfg.write_text(yaml.safe_dump(settings, sort_keys=False))
        run_env = {**env, "TMPDIR": str(tmp)}
        log = args.out / f"{label}.log"
        cmd = [*args.cli.split(), "benchmark", "run", "--config", str(cfg), "--preflight"]
        with log.open("w") as fh:
            rc = subprocess.run(cmd, cwd=args.repo, env=run_env, stdout=fh, stderr=subprocess.STDOUT).returncode
        builds = [p for p in tmp.iterdir() if p.is_dir()]
        if rc != 0 or len(builds) != 1:
            print(f"{label}: preflight exit {rc}, {len(builds)} build dir(s); see {log}")
            failed += 1
            continue
        dest = args.out / label
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(builds[0], dest, symlinks=True)
        rows = []
        for inst in sorted(p for p in dest.iterdir() if p.is_dir()):
            for f in sorted(inst.rglob("*")):
                rel = f.relative_to(dest).as_posix()
                if not (rel.split("/", 1)[1].startswith("sandbox/") or f.name == "HYPOTHESES.md"):
                    continue
                if f.is_symlink():
                    rows.append(f"{rel}\tsymlink:{os.readlink(f)}\t-")
                elif f.is_file():
                    rows.append(f"{rel}\t{digest(f)}\t{oct(stat.S_IMODE(f.stat().st_mode))}")
        (args.out / f"{label}.files.tsv").write_text("\n".join(rows) + "\n")
        print(f"{label}: {len(rows)} agent-visible file(s)")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
