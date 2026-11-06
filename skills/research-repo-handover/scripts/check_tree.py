"""Two-way tree audit: every file in the handover repo is identical to the pin or explained.

usage: python3 check_tree.py JOB.toml     (reads [source] and [audit]; exit 1 on any problem)

[audit] keys:
  repo       the handover repo (a git checkout)
  rev        the revision to audit (default HEAD)
  keep       the keep set (keep.tsv): paths at the pin the repo is meant to carry
  reasons    TSV `path-or-glob<TAB>reason`: why a file differs from the pin, was added, or was
             removed from the keep set. An exact path wins over a glob; globs apply in file order.
  path_map   optional TSVs `old<TAB>new` (staged_rename.py writes moved-paths.tsv): where a pin
             path lives now. A row ending in `/` maps a directory prefix.

Each file at `rev` is `identical` (same blob at the same path), `moved` (same blob, mapped path),
`changed`, `moved+changed` or `added`. `changed`, `moved+changed` and `added` need a reason; a
file identical to the pin must be in the keep set; every keep-set path must still be present
(after mapping) unless a reason records its removal. Writes files.tsv (path, status, blob at the
pin, blob here, pin path, reason) and audit.json to the output directory. Reads git only.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import (  # noqa: E402
    Job,
    blobs_at,
    first_match,
    job_from_argv,
    read_tsv,
    require,
    write_run_record,
)


class PathMap:
    def __init__(self, rows: list[list[str]]) -> None:
        self.exact = {r[0]: r[1] for r in rows if not r[0].endswith("/")}
        self.prefixes = sorted(
            ((r[0], r[1]) for r in rows if r[0].endswith("/")), key=lambda r: -len(r[0])
        )

    def __call__(self, path: str) -> str:
        if path in self.exact:
            return self.exact[path]
        for old, new in self.prefixes:
            if path.startswith(old):
                return new + path[len(old) :]
        return path


class Reasons:
    def __init__(self, rows: list[list[str]]) -> None:
        self.exact: dict[str, str] = {}
        self.globs: list[tuple[str, str]] = []
        for r in rows:
            reason = r[1] if len(r) > 1 else ""
            if any(ch in r[0] for ch in "*?"):
                self.globs.append((r[0], reason))
            else:
                self.exact[r[0]] = reason

    def get(self, path: str) -> str | None:
        if path in self.exact:
            return self.exact[path]
        hit = first_match(path, [g for g, _ in self.globs])
        return dict(self.globs)[hit] if hit else None


def load_rows(job: Job, value: str | list[str] | None, cols: int) -> list[list[str]]:
    values = [value] if isinstance(value, str) else list(value or [])
    return [row for v in values for row in read_tsv(job.resolve(v), cols)]


def main() -> int:
    job = job_from_argv(__doc__)
    source, cfg = job.section("source"), job.section("audit")
    out_dir = job.out_dir(cfg)
    src_repo, pin = job.resolve(require(source, "repo", "source")), require(source, "pin", "source")
    here_repo, rev = job.resolve(require(cfg, "repo", "audit")), cfg.get("rev", "HEAD")
    mapping = PathMap(load_rows(job, cfg.get("path_map"), 2))
    reasons = Reasons(load_rows(job, cfg.get("reasons"), 1))
    keep = {mapping(r[0]): r[0] for r in load_rows(job, require(cfg, "keep", "audit"), 1)}
    at_pin = blobs_at(src_repo, pin)
    mapped = {mapping(p): (p, blob) for p, blob in at_pin.items()}
    here = blobs_at(here_repo, rev)
    rows, problems, counts = [], [], Counter()
    for path in sorted(here):
        origin, blob = mapped.get(path, (None, None))
        if origin is None:
            status = "added"
        elif blob == here[path]:
            status = "identical" if origin == path else "moved"
        else:
            status = "changed" if origin == path else "moved+changed"
        counts[status] += 1
        reason = reasons.get(path)
        if status in ("changed", "moved+changed", "added") and not reason:
            problems.append(f"{status} without a reason: {path}")
        if status in ("identical", "moved") and path not in keep:
            problems.append(f"{status} from the pin but not in the keep set: {path}")
        rows.append((path, status, blob or "-", here[path], origin or "-", reason or ""))
    removed = sorted(p for p in keep if p not in here)
    for path in removed:
        if reasons.get(path) is None and reasons.get(keep[path]) is None:
            problems.append(f"in the keep set but absent here, and no removal recorded: {path}")
    listing = out_dir / "files.tsv"
    listing.write_text(
        "path\tstatus\tblob_at_pin\tblob_here\tpin_path\treason\n"
        + "".join("\t".join(r) + "\n" for r in rows),
        encoding="utf-8",
    )
    summary = {
        "pin": pin,
        "rev": rev,
        "files_at_pin": len(at_pin),
        "files_here": len(here),
        **{k: counts[k] for k in ("identical", "moved", "changed", "moved+changed", "added")},
        "keep_set_paths_removed": len(removed),
        "problems": problems,
    }
    (out_dir / "audit.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    write_run_record(
        job,
        out_dir,
        "check_tree",
        {},
        {k: v for k, v in summary.items() if k != "problems"} | {"problems": len(problems)},
    )
    print(f"pin {pin[:12]}: {len(at_pin)} files there, {len(here)} at {rev}")
    print(
        ", ".join(
            f"{k} {counts[k]}" for k in ("identical", "moved", "changed", "moved+changed", "added")
        )
        + f"; keep-set paths removed {len(removed)}"
    )
    for p in problems[:50]:
        print("  ", p)
    print(f"{len(problems)} problem(s); listing {listing}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
