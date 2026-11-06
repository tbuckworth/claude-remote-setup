"""The keep set: every source path the handover repo retains, one row per path with its reason.

usage: python3 make_keep_set.py JOB.toml     (reads [source] and [keep]; writes keep.tsv)

The file list comes from the pin's git tree (`git ls-tree`), file contents from the extracted
tree ([source].tree, or the one closure.py extracted). [[keep.rule]] tables apply in order and
the first rule to claim a path gives its reason. Rule types:

  closure        files of the nodes closure.py reached: `closure_json`, `variant` (runtime),
                 `node_types` (["module"]; add "script", "shell" to keep those too),
                 `extra_modules` {module = reason} for modules read by path, which no import shows
  package_inits  every tracked `__init__.py` above a path kept so far
  glob           tracked paths matching `include` and not `exclude`
  traced         paths a traced run opened (`files`, trace_reads.py output), minus `exclude`
  mentions       tracked `candidates` whose file stem appears in a `declared_in` file's text;
                 `{stem}` in the reason names the declaring file
  explicit       `paths` {path = reason}; an empty reason means `default_reason`
  tests          test modules (`include`, minus `support`) whose imports of the packages all
                 resolve to kept modules; `support` files are kept whole; an import whose module
                 starts with an `excluded_imports` prefix counts as missing

A path a rule names explicitly that the pin does not track is an error, never skipped. Output:
keep.tsv (`path<TAB>reason`, sorted) and a count per reason.
"""

from __future__ import annotations

import ast
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import (  # noqa: E402
    ConfigError,
    Job,
    job_from_argv,
    matches,
    require,
    tracked_at,
    write_run_record,
)


class KeepSet:
    def __init__(self, tracked: list[str]) -> None:
        self.tracked = tracked
        self.tracked_set = set(tracked)
        self.rows: dict[str, str] = {}

    def add(self, path: str, reason: str, strict: bool = True) -> None:
        if path not in self.tracked_set:
            if strict:
                raise SystemExit(f"not tracked at the pin: {path} ({reason})")
            return
        self.rows.setdefault(path, reason)


def module_names_of(paths: list[str], source_roots: list[str]) -> set[str]:
    names = set()
    for p in paths:
        for root in source_roots:
            if p.startswith(root + "/") and p.endswith(".py"):
                rel = Path(p[len(root) + 1 :]).with_suffix("").as_posix().replace("/", ".")
                names.add(rel.removesuffix(".__init__"))
    return names


def rule_closure(job: Job, ks: KeepSet, rule: dict[str, Any], ctx: dict[str, Any]) -> None:
    data = json.loads(job.resolve(require(rule, "closure_json", "keep.rule closure")).read_text())
    ctx["closure"] = data
    variant = data["variants"][rule.get("variant", "runtime")]
    reason = rule.get("reason", "closure")
    for node_type in rule.get("node_types", ["module"]):
        for path in variant["files"][node_type]:
            ks.add(path, reason)
    for module, why in rule.get("extra_modules", {}).items():
        path = data["module_files"].get(module)
        if path is None:
            raise SystemExit(f"extra module {module} has no file at the pin")
        ks.add(path, why)


def rule_package_inits(ks: KeepSet, rule: dict[str, Any]) -> None:
    reason = rule.get("reason", "package of a kept module")
    for path in list(ks.rows):
        parts = Path(path).parts
        for i in range(1, len(parts)):
            init = "/".join(parts[:i]) + "/__init__.py"
            if init in ks.tracked_set:
                ks.add(init, reason)


def rule_glob(ks: KeepSet, rule: dict[str, Any]) -> None:
    include, exclude = rule["include"], rule.get("exclude", [])
    reason = require(rule, "reason", "keep.rule glob")
    hits = [t for t in ks.tracked if matches(t, include) and not matches(t, exclude)]
    if not hits:
        raise SystemExit(f"glob rule {include} matched nothing ({reason})")
    for t in hits:
        ks.add(t, reason)


def rule_traced(job: Job, ks: KeepSet, rule: dict[str, Any]) -> None:
    exclude = rule.get("exclude", [])
    reason = rule.get("reason", "opened by a traced run")
    for raw in require(rule, "files", "keep.rule traced"):
        for line in job.resolve(raw).read_text(encoding="utf-8").splitlines():
            path = line.split("\t")[0]
            if path in ks.tracked_set and not matches(path, exclude):
                ks.add(path, reason)


def rule_mentions(tree: Path, ks: KeepSet, rule: dict[str, Any]) -> None:
    candidates = [t for t in ks.tracked if matches(t, rule["candidates"])]
    reason = require(rule, "reason", "keep.rule mentions")
    for declarer in rule["declared_in"]:
        if declarer not in ks.tracked_set:
            raise SystemExit(f"mentions rule: {declarer} is not tracked at the pin")
        text = (tree / declarer).read_text(encoding="utf-8")
        for t in candidates:
            if Path(t).stem in text:
                ks.add(t, reason.format(stem=Path(declarer).stem, path=declarer))


def rule_explicit(ks: KeepSet, rule: dict[str, Any]) -> None:
    default = rule.get("default_reason", "explicit")
    for path, reason in require(rule, "paths", "keep.rule explicit").items():
        ks.add(path, reason or default)


def rule_tests(tree: Path, ks: KeepSet, rule: dict[str, Any], ctx: dict[str, Any]) -> None:
    closure = ctx.get("closure")
    if closure is None:
        raise ConfigError("a tests rule must follow a closure rule (it needs the package names)")
    packages, roots = closure["packages"], closure["source_roots"]
    excluded = tuple(rule.get("excluded_imports", []))
    support = rule.get("support", [])
    all_modules = set(closure["module_files"])
    kept = module_names_of(list(ks.rows), roots)

    def internal(name: str) -> bool:
        return any(name == p or name.startswith(p + ".") for p in packages)

    for t in ks.tracked:
        if matches(t, support):
            ks.add(t, rule.get("support_reason", "test support"))
            continue
        if not (t.endswith(".py") and matches(t, rule["include"])):
            continue
        needed: set[str] = set()
        for node in ast.walk(ast.parse((tree / t).read_text(encoding="utf-8"))):
            names: list[str] = []
            if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
                names += [f"{node.module}.{a.name}" for a in node.names]
                names = [names[0]] + [n for n in names[1:] if n in all_modules]
            elif isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            for name in names:
                if excluded and name.startswith(excluded):
                    needed.add("EXCLUDED:" + name)
                elif internal(name):
                    needed.add(name)
        if not needed - kept:
            ks.add(t, rule.get("reason", "test of kept modules"))


def main() -> int:
    job = job_from_argv(__doc__)
    source, cfg = job.section("source"), job.section("keep")
    out_dir = job.out_dir(cfg)
    repo = job.resolve(require(source, "repo", "source"))
    pin = require(source, "pin", "source")
    tree = job.resolve(source["tree"]) if source.get("tree") else out_dir / "source-tree"
    if not tree.is_dir():
        raise SystemExit(f"{tree}: no extracted tree; run closure.py first or set [source].tree")
    ks = KeepSet(tracked_at(repo, pin))
    ctx: dict[str, Any] = {}
    counts_before = 0
    for i, rule in enumerate(require(cfg, "rule", "keep"), 1):
        kind = rule.get("type")
        if kind == "closure":
            rule_closure(job, ks, rule, ctx)
        elif kind == "package_inits":
            rule_package_inits(ks, rule)
        elif kind == "glob":
            rule_glob(ks, rule)
        elif kind == "traced":
            rule_traced(job, ks, rule)
        elif kind == "mentions":
            rule_mentions(tree, ks, rule)
        elif kind == "explicit":
            rule_explicit(ks, rule)
        elif kind == "tests":
            rule_tests(tree, ks, rule, ctx)
        else:
            raise ConfigError(f"[[keep.rule]] #{i}: unknown type {kind!r}")
        print(f"rule {i:2d} {kind:13s} +{len(ks.rows) - counts_before} paths")
        counts_before = len(ks.rows)
    target = out_dir / "keep.tsv"
    target.write_text("".join(f"{p}\t{ks.rows[p]}\n" for p in sorted(ks.rows)), encoding="utf-8")
    by_reason = Counter(ks.rows.values())
    write_run_record(
        job,
        out_dir,
        "make_keep_set",
        {},
        {"kept": len(ks.rows), "tracked": len(ks.tracked), "pin": pin},
    )
    print(f"{len(ks.rows)} kept of {len(ks.tracked)} tracked at {pin[:12]}; wrote {target}")
    for reason, n in by_reason.most_common(12):
        print(f"  {n:5d}  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
