"""List leftover old vocabulary, owner-specific names and history in the handover repo's files.

usage: python3 scan_vocab.py JOB.toml     (reads [scan]; exit 1 on hits when fail_on_hits)

[scan] keys:
  repo          the handover checkout (tracked files via `git ls-files`), or any directory
  patterns      [[name, regex], ...]: what to look for. Typical groups: the old package, CLI and
                vocabulary; the owner's name, home directory, machine paths and account names;
                decision ids, PR numbers and "used to" history in comments
  files         globs to scan (default all); `exclude` globs to skip (frozen trees, the lock)
  allow         [regex, ...]: matched text accepted on purpose (a name the agent can see)
  ignore_case   true: patterns match case-insensitively
  fail_on_hits  true: exit 1 when anything is found (for a final check)
Writes hits.tsv (path, line, pattern, matched text, the line) and prints a count per pattern.
"""

from __future__ import annotations

import collections
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import job_from_argv, matches, require, walk_files, write_run_record  # noqa: E402


def main() -> int:
    job = job_from_argv(__doc__)
    cfg = job.section("scan")
    out_dir = job.out_dir(cfg)
    repo = job.resolve(require(cfg, "repo", "scan"))
    flags = re.I if cfg.get("ignore_case") else 0
    patterns = [(name, re.compile(rx, flags)) for name, rx in require(cfg, "patterns", "scan")]
    allow = [re.compile(rx, flags) for rx in cfg.get("allow", [])]
    include, exclude = cfg.get("files", ["**"]), cfg.get("exclude", [])
    if (repo / ".git").exists():
        out = subprocess.run(
            ["git", "-C", str(repo), "ls-files", "-z"], check=True, capture_output=True, text=True
        ).stdout
        files = sorted(p for p in out.split("\0") if p)
    else:
        files = walk_files(repo)
    counts: collections.Counter[str] = collections.Counter()
    rows = []
    for rel in files:
        if not matches(rel, include) or matches(rel, exclude):
            continue
        try:
            text = (repo / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for name, rx in patterns:
                for m in rx.finditer(line):
                    if any(a.fullmatch(m.group(0)) for a in allow):
                        continue
                    counts[name] += 1
                    rows.append(
                        (rel, str(number), name, m.group(0), line.strip()[:200].replace("\t", " "))
                    )
    (out_dir / "hits.tsv").write_text("".join("\t".join(r) + "\n" for r in rows), encoding="utf-8")
    write_run_record(
        job, out_dir, "scan_vocab", {}, {"hits": len(rows), "per_pattern": dict(counts)}
    )
    for name, _ in patterns:
        print(f"{counts[name]:6d}  {name}")
    files_hit = len({r[0] for r in rows})
    print(f"{len(rows)} hit(s) in {files_hit} file(s); listing {out_dir / 'hits.tsv'}")
    return 1 if rows and cfg.get("fail_on_hits") else 0


if __name__ == "__main__":
    raise SystemExit(main())
