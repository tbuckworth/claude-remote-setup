"""Record every repo file a command opens, lists or globs, for the keep set's `traced` rule.

usage: <the source checkout's python> trace_reads.py JOB.toml      (reads [trace])

Static closure misses data files, prompts and configs read by path, so run each kept command's
cheap paths (preflights, scripted/mock runs) under a PEP 578 audit hook. Run it with the source
checkout's own interpreter (e.g. `uv run --frozen python .../trace_reads.py JOB.toml` from the
checkout at the pin), so the code under trace imports as it does for real.

[trace] keys:
  repo     the checkout whose files are recorded (paths outside it are ignored)
  entry    "module:callable" to call with argv (e.g. "pkg.cli:app"), or "-m module"
  prog     argv[0] the entry point sees (e.g. "pp")
  env      optional {NAME = value} for every run (dummy keys, invalid URLs: never real secrets)
  [[trace.runs]]  name, args (the argv after prog), optional env
Each run is a fresh subprocess; a failing run is reported but its trace is still kept, since a
preflight that stops late has already read what matters. Subprocesses of the traced command are
not traced: add their commands as runs of their own. Output: traced-reads.txt
(`path<TAB>kind<TAB>runs`, union of all runs) and one trace-<name>.txt per run.
"""

from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path


def child(spec_json: str) -> None:
    """In the subprocess: install the hook, then run the entry point in-process."""
    spec = json.loads(spec_json)
    repo, out = Path(spec["repo"]).resolve(), Path(spec["out"])
    skip = (".venv", ".git")
    seen: dict[str, str] = {}

    def record(kind: str, raw: object) -> None:
        if isinstance(raw, int):
            return
        try:
            p = Path(os.fsdecode(raw))  # type: ignore[arg-type]
        except TypeError:
            return
        p = p if p.is_absolute() else Path.cwd() / p
        try:
            rel = p.resolve().relative_to(repo).as_posix()
        except (ValueError, OSError, RuntimeError):
            return
        if rel.startswith(skip) or "__pycache__" in rel:
            return
        seen.setdefault(rel, kind)

    def hook(event: str, args: tuple[object, ...]) -> None:
        if event == "open" and args:
            record("open", args[0])
        elif event in ("os.listdir", "os.scandir") and args:
            record("list", args[0])
        elif event == "glob.glob" and args:
            record("glob", args[0])

    def dump() -> None:
        out.write_text("".join(f"{k}\t{seen[k]}\n" for k in sorted(seen)), encoding="utf-8")

    here = (
        Path(__file__).resolve().parent
    )  # keep this tool's modules out of the traced program's way
    sys.path[:] = [p for p in sys.path if Path(p or ".").resolve() != here]
    sys.path.insert(0, str(Path.cwd()))
    sys.addaudithook(hook)
    sys.argv = [spec["prog"], *spec["args"]]
    code = 0
    try:
        entry: str = spec["entry"]
        if entry.startswith("-m "):
            runpy.run_module(entry[3:].strip(), run_name="__main__", alter_sys=True)
        else:
            module, _, attr = entry.partition(":")
            target = __import__(module, fromlist=[attr])
            for part in attr.split("."):
                target = getattr(target, part)
            result = target()
            code = result if isinstance(result, int) else 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
    finally:
        dump()
    raise SystemExit(code)


def main() -> int:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from handover_common import job_from_argv, require, write_run_record

    job = job_from_argv(__doc__)
    cfg = job.section("trace")
    out_dir = job.out_dir(cfg)
    repo = job.resolve(require(cfg, "repo", "trace"))
    union: dict[str, tuple[str, list[str]]] = {}
    failed = []
    for run in require(cfg, "runs", "trace"):
        name = require(run, "name", "trace.runs")
        out = out_dir / f"trace-{name}.txt"
        spec = {
            "repo": str(repo),
            "out": str(out),
            "entry": require(cfg, "entry", "trace"),
            "prog": cfg.get("prog", "prog"),
            "args": list(run.get("args", [])),
        }
        env = {
            **os.environ,
            **{k: str(v) for k, v in {**cfg.get("env", {}), **run.get("env", {})}.items()},
        }
        done = subprocess.run(
            [sys.executable, __file__, "--child", json.dumps(spec)],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
        )
        (out_dir / f"trace-{name}.log").write_text(done.stdout + done.stderr, encoding="utf-8")
        status = "ok" if done.returncode == 0 else f"exit {done.returncode}"
        if done.returncode != 0:
            failed.append(name)
        n = 0
        if out.is_file():
            for line in out.read_text(encoding="utf-8").splitlines():
                path, kind = line.split("\t")
                union.setdefault(path, (kind, []))[1].append(name)
                n += 1
        print(f"{name}: {status}, {n} path(s)")
    target = out_dir / "traced-reads.txt"
    target.write_text(
        "".join(f"{p}\t{k}\t{','.join(r)}\n" for p, (k, r) in sorted(union.items())),
        encoding="utf-8",
    )
    write_run_record(job, out_dir, "trace_reads", {}, {"paths": len(union), "failed_runs": failed})
    print(
        f"{len(union)} path(s) in the union; wrote {target}"
        + (f"; failed runs: {failed}" if failed else "")
    )
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    raise SystemExit(main())
