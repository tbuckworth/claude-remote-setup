"""Apply a recorded test triage to the cut tree: every change listed with its reason, none silent.

usage: python3 test_triage.py JOB.toml     (reads [triage])

[triage] keys:
  tree       the tree to edit (a working copy of the cut; re-runnable on a fresh one)
  drops      TSV `test path<TAB>name<TAB>reason`. `name` is a top-level function or class,
             `Class.method`, or `*` to delete the whole file (its subject was removed).
  retargets  optional TOML of [[retarget]] tables: `path`, `old`, `new` (empty deletes),
             `reason`, optional `count` (exact number of occurrences expected; default: at least
             one). Literal replacement of every occurrence, for pointing a test at a kept file
             of the same shape, or deleting a parametrisation of a removed one.
Order: whole-file deletions, then retargets in file order, then AST drops. A drop removes the
node's exact lines (decorators included) and the blank lines after it, so each change is a pure
deletion; unused imports are left for the project's linter (e.g. `ruff check --select
F401,F811,F841 --fix`). A name or literal that is not found stops the run.
Outputs: triage-report.json and triaged.tsv (`path<TAB>reason`, usable as audit reasons).
"""

from __future__ import annotations

import ast
import json
import sys
import tomllib
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import job_from_argv, read_tsv, require, write_run_record  # noqa: E402

NodeDef = ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef


def find(tree: ast.Module, name: str) -> NodeDef | None:
    cls, _, meth = name.partition(".")
    for node in tree.body:
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == cls
        ):
            if not meth:
                return node
            for sub in getattr(node, "body", []):
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == meth:
                    return sub
    return None


def drop_nodes(file: Path, names: list[str]) -> None:
    lines = file.read_text(encoding="utf-8").split("\n")
    tree = ast.parse("\n".join(lines))
    keep = [True] * len(lines)
    for name in names:
        node = find(tree, name)
        if node is None:
            raise SystemExit(f"{file}: no {name}")
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        end = node.end_lineno or node.lineno
        for i in range(start - 1, end):
            keep[i] = False
        j = end
        while j < len(lines) and lines[j].strip() == "":
            keep[j] = False
            j += 1
    file.write_text(
        "\n".join(line for line, k in zip(lines, keep, strict=True) if k), encoding="utf-8"
    )


def main() -> int:
    job = job_from_argv(__doc__)
    cfg = job.section("triage")
    out_dir = job.out_dir(cfg)
    tree = job.resolve(require(cfg, "tree", "triage"))
    drops_path = job.resolve(require(cfg, "drops", "triage"))
    rows = read_tsv(drops_path, 3)
    retargets: list[dict[str, object]] = []
    if cfg.get("retargets"):
        retargets = tomllib.loads(job.resolve(cfg["retargets"]).read_text(encoding="utf-8")).get(
            "retarget", []
        )
    reasons: dict[str, list[str]] = defaultdict(list)
    report: dict[str, list[dict[str, object]]] = {"removed": [], "retargeted": [], "dropped": []}
    for path, name, reason, *_ in rows:
        if name == "*":
            target = tree / path
            if not target.is_file():
                raise SystemExit(f"remove: {path} not found")
            target.unlink()
            reasons[path].append(f"removed: {reason}")
            report["removed"].append({"path": path, "reason": reason})
    for rt in retargets:
        path, old, new = str(rt["path"]), str(rt["old"]), str(rt.get("new", ""))
        file = tree / path
        text = file.read_text(encoding="utf-8")
        count = text.count(old)
        expected = rt.get("count")
        if count == 0 or (expected is not None and count != expected):
            raise SystemExit(
                f"{path}: retarget found {count} time(s), expected {expected or '>= 1'}: "
                f"{old[:60]!r}"
            )
        file.write_text(text.replace(old, new), encoding="utf-8")
        reasons[path].append(f"retargeted: {rt.get('reason', '')}")
        report["retargeted"].append({"path": path, "count": count, "reason": rt.get("reason", "")})
    by_file: dict[str, list[str]] = defaultdict(list)
    for path, name, reason, *_ in rows:
        if name != "*":
            by_file[path].append(name)
            report["dropped"].append({"path": path, "name": name, "reason": reason})
    for path, names in sorted(by_file.items()):
        drop_nodes(tree / path, names)
        reasons[path].append(f"{len(names)} test(s) dropped (triage-report.json)")
    (out_dir / "triage-report.json").write_text(
        json.dumps(report, indent=1) + "\n", encoding="utf-8"
    )
    (out_dir / "triaged.tsv").write_text(
        "".join(f"{p}\t{'; '.join(r)}\n" for p, r in sorted(reasons.items())), encoding="utf-8"
    )
    counts = {k: len(v) for k, v in report.items()}
    write_run_record(job, out_dir, "test_triage", {"drops": str(drops_path)}, counts)
    print(
        f"removed {counts['removed']} file(s), {counts['retargeted']} retarget(s), "
        f"dropped {counts['dropped']} test(s) in {len(by_file)} file(s)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
