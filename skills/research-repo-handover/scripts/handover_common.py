"""Shared helpers for the handover tools: the job config, path globs, git reads, run records.

Every tool takes one argument, the job's TOML config. Relative paths in it resolve against the
config file's own directory. Each tool copies the config into its output directory and writes a
`<tool>.run.json` beside its outputs (tool, config digest, inputs, time), so an output is never
separated from the parameters that made it. Stdlib only; Python 3.11 or newer (tomllib).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


class ConfigError(SystemExit):
    """A config problem, reported as one line and exit status 2."""

    def __init__(self, message: str) -> None:
        super().__init__(f"config error: {message}")
        self.code = 2


class Job:
    """The parsed job config, with path resolution relative to the config file."""

    def __init__(self, path: Path) -> None:
        self.path = path.resolve()
        self.base = self.path.parent
        self.data: dict[str, Any] = tomllib.loads(self.path.read_text(encoding="utf-8"))

    def section(self, name: str) -> dict[str, Any]:
        value = self.data.get(name)
        if not isinstance(value, dict):
            raise ConfigError(f"{self.path}: no [{name}] section")
        return value

    def resolve(self, value: str | os.PathLike[str]) -> Path:
        path = Path(os.path.expanduser(str(value)))
        return path if path.is_absolute() else (self.base / path).resolve()

    def out_dir(self, section: dict[str, Any] | None = None) -> Path:
        """`out_dir` from the tool's section, else `[job].out_dir`; created if absent."""
        raw = (section or {}).get("out_dir") or self.data.get("job", {}).get("out_dir")
        if not raw:
            raise ConfigError("set [job].out_dir (or out_dir in the tool's section)")
        out = self.resolve(raw)
        out.mkdir(parents=True, exist_ok=True)
        return out


def require(section: dict[str, Any], key: str, where: str) -> Any:
    if key not in section:
        raise ConfigError(f"[{where}] needs `{key}`")
    return section[key]


# ---------------------------------------------------------------------------------------------
# Globs over repo-relative POSIX paths: `**` crosses directories, `*` and `?` do not.
@lru_cache(maxsize=4096)
def glob_regex(pattern: str) -> re.Pattern[str]:
    out, i = [], 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("".join(out) + r"\Z")


def matches(path: str, patterns: list[str] | tuple[str, ...]) -> bool:
    return any(glob_regex(p).match(path) for p in patterns)


def first_match(path: str, patterns: list[str]) -> str | None:
    return next((p for p in patterns if glob_regex(p).match(path)), None)


# ---------------------------------------------------------------------------------------------
def git(repo: Path, *args: str, check: bool = True, text: bool = True) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], check=False, capture_output=True, text=text
    )
    if check and done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed in {repo}: {done.stderr.strip()}")
    return done.stdout


def tracked_at(repo: Path, rev: str) -> list[str]:
    """Every file path in `rev`, read from the object store (no checkout needed)."""
    out = git(repo, "ls-tree", "-r", "-z", "--name-only", rev)
    return sorted(p for p in out.split("\0") if p)


def blobs_at(repo: Path, rev: str) -> dict[str, str]:
    """Path -> blob id at `rev` (symlinks and submodules included as their object ids)."""
    out = git(repo, "ls-tree", "-r", "-z", rev)
    found: dict[str, str] = {}
    for entry in out.split("\0"):
        if entry:
            meta, path = entry.split("\t", 1)
            found[path] = meta.split()[2]
    return found


def materialise(repo: Path, rev: str, dest: Path) -> None:
    """Write the tree of `rev` into `dest` with `git archive` (the source repo is only read)."""
    if dest.exists() and any(dest.iterdir()):
        raise SystemExit(f"{dest} exists and is not empty; choose a fresh directory")
    dest.mkdir(parents=True, exist_ok=True)
    archive = dest.parent / f".{dest.name}.tar"
    with archive.open("wb") as handle:
        subprocess.run(["git", "-C", str(repo), "archive", rev], check=True, stdout=handle)
    with tarfile.open(archive) as tar:
        tar.extractall(dest, filter="tar")
    archive.unlink()


def walk_files(root: Path, skip_dirs: tuple[str, ...] = (".git", "__pycache__")) -> list[str]:
    """Repo-relative POSIX paths of every file under `root`, skipping VCS and cache dirs."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in skip_dirs)
        rel = Path(dirpath).relative_to(root)
        for name in sorted(filenames):
            found.append((rel / name).as_posix())
    return sorted(found)


# ---------------------------------------------------------------------------------------------
def read_tsv(path: Path, min_cols: int = 1) -> list[list[str]]:
    """Rows of a TSV, skipping blank lines and `#` comments; refuses short rows."""
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < min_cols:
            raise SystemExit(f"{path}:{number}: expected {min_cols} tab-separated columns")
        rows.append(cols)
    return rows


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_run_record(
    job: Job, out_dir: Path, tool: str, inputs: dict[str, str], results: dict[str, Any]
) -> Path:
    """Save the config beside the outputs and record what this run read and produced."""
    shutil.copyfile(job.path, out_dir / f"{tool}.config.toml")
    digests = {}
    for label, raw in inputs.items():
        p = Path(raw)
        digests[label] = {"path": raw, "sha256": sha256_file(p) if p.is_file() else None}
    record = {
        "tool": tool,
        "config": str(job.path),
        "config_sha256": sha256_file(job.path),
        "python": sys.version.split()[0],
        "finished_at": _dt.datetime.now(_dt.UTC).isoformat(timespec="seconds"),
        "inputs": digests,
        "results": results,
    }
    out = out_dir / f"{tool}.run.json"
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return out


def job_from_argv(doc: str | None) -> Job:
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        raise SystemExit((doc or "").strip() + "\n\nusage: python3 <tool>.py JOB.toml")
    return Job(Path(sys.argv[1]))
