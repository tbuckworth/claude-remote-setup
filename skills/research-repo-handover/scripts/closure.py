"""Static dependency closure of a Python repo from the commands a handover keeps.

usage: python3 closure.py JOB.toml        (reads [source] and [closure]; writes closure.json)

Never imports the code under analysis: it parses every module, script and shell file. Graph nodes:
  module   `pkg.sub.mod`            every .py under <source_root>/<package> for each package
  script   `script:<path>`          files matching `scripts` globs (parsed like modules)
  shell    `shell:<path>`           files matching `shell` globs (scanned line by line)
  command  `cmd:<cli command>`      rows of the CLI's command table ([closure.cli])
  other    any name a manual edge or shell rule uses (e.g. `task:x`), joined by manual edges
Edge kinds followed by the `runtime` closure: module, optional (try/except ImportError, a
module-level __getattr__), lazy (inside a function), main (under `if __name__`), dynamic
(import_module/__import__/run_module or `-m pkg.x` with a resolvable string), shell, manual.
`entrypoint` adds [closure.entrypoint].root when a reached module uses one of its trigger names
(a plugin registry that imports an entry-point module at run time); `typing` adds
`if TYPE_CHECKING:` imports. Modules named only in strings are reported, never followed: a
reviewer judges each one, and a traced run (trace_reads.py) catches what is really read.

Output closure.json: per variant the reached modules and the files of every reached node, the
module -> file map, why each module is reached (shortest chain), unreached modules grouped by
package, modules named in strings but not reached, unresolved internal imports, third-party
imports, and for each [[closure.options]] the modules and lines it would add (scope options).
"""

from __future__ import annotations

import ast
import fnmatch
import json
import re
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import (  # noqa: E402
    ConfigError,
    job_from_argv,
    matches,
    materialise,
    require,
    walk_files,
    write_run_record,
)

PH = "\x00"  # placeholder for an unresolvable part of a string expression
STDLIB = set(sys.stdlib_module_names) | {"__future__"}
RUNTIME_KINDS = {"module", "optional", "lazy", "dynamic", "manual", "shell", "main"}


@dataclass
class Node:
    name: str
    path: str  # repo-relative; "" for nodes without a file
    is_pkg: bool = False
    loc: int = 0
    tree: ast.Module | None = None
    package: str = ""  # the package relative imports resolve against
    edges: list[dict[str, Any]] = field(default_factory=list)
    third: list[dict[str, Any]] = field(default_factory=list)
    strings: set[tuple[str, int]] = field(default_factory=set)
    from_names: dict[str, tuple[str, str]] = field(default_factory=dict)
    mod_alias: dict[str, str] = field(default_factory=dict)
    consts: dict[str, str] = field(default_factory=dict)
    triggers: list[tuple[str, int]] = field(default_factory=list)


class Analysis:
    """Holds the config-derived settings every pass needs."""

    def __init__(self, cfg: dict[str, Any], repo: Path) -> None:
        self.repo = repo
        self.packages: list[str] = list(require(cfg, "packages", "closure"))
        self.source_roots: list[str] = list(cfg.get("source_roots", ["src"]))
        self.script_globs: list[str] = list(cfg.get("scripts", []))
        self.shell_globs: list[str] = list(cfg.get("shell", []))
        ep = cfg.get("entrypoint", {})
        self.entry_root: str | None = ep.get("root")
        self.entry_triggers: dict[str, set[str]] = {
            mod: set(names) for mod, names in ep.get("triggers", {}).items()
        }
        alt = "|".join(re.escape(p) for p in self.packages)
        self.dotted_re = re.compile(rf"(?:{alt})(?:\.[A-Za-z_\x00][\w\x00]*)+")
        self.path_re = re.compile(rf"(?:{alt})/[\w\x00./-]+")

    def internal(self, name: str) -> bool:
        return any(name == p or name.startswith(p + ".") for p in self.packages)


def longest_known(name: str, modules: set[str]) -> str | None:
    parts = name.split(".")
    for i in range(len(parts), 0, -1):
        cand = ".".join(parts[:i])
        if cand in modules:
            return cand
    return None


def discover(an: Analysis) -> dict[str, Node]:
    nodes: dict[str, Node] = {}
    files = walk_files(an.repo)
    for root in an.source_roots:
        for pkg in an.packages:
            prefix = f"{root}/{pkg.replace('.', '/')}/"
            for rel in files:
                if not (rel.startswith(prefix) and rel.endswith(".py")):
                    continue
                parts = list(Path(rel[len(root) + 1 :]).with_suffix("").parts)
                is_pkg = parts[-1] == "__init__"
                if is_pkg:
                    parts = parts[:-1]
                name = ".".join(parts)
                package = name if is_pkg else ".".join(parts[:-1])
                nodes[name] = Node(name=name, path=rel, is_pkg=is_pkg, package=package)
    for rel in files:
        if rel.endswith(".py") and matches(rel, an.script_globs):
            nodes.setdefault(f"script:{rel}", Node(name=f"script:{rel}", path=rel))
    for node in nodes.values():
        text = (an.repo / node.path).read_text(encoding="utf-8")
        node.loc = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
        node.tree = ast.parse(text, filename=node.path)
    return nodes


def resolve_relative(node: Node, module: str | None, level: int) -> str:
    if level == 0:
        return module or ""
    base = node.package.split(".") if node.package else []
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, module] if module else base)


def catches_import_error(handlers: list[ast.ExceptHandler]) -> bool:
    for h in handlers:
        if h.type is None:
            return True
        names = []
        for e in h.type.elts if isinstance(h.type, ast.Tuple) else [h.type]:
            if isinstance(e, ast.Name):
                names.append(e.id)
            elif isinstance(e, ast.Attribute):
                names.append(e.attr)
        if {"ImportError", "ModuleNotFoundError", "Exception", "BaseException"} & set(names):
            return True
    return False


def docstring_ids(tree: ast.Module) -> set[int]:
    ids = set()
    for n in ast.walk(tree):
        if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in n.body:  # the docstring, and attribute docstrings after assignments
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    ids.add(id(stmt.value))
    return ids


class ImportCollector(ast.NodeVisitor):
    def __init__(self, an: Analysis, node: Node, modules: set[str]) -> None:
        self.an, self.node, self.modules = an, node, modules
        self.func = self.tc = self.try_ = self.main = self.getattr_ = 0

    def kind(self) -> str:
        if self.tc:
            return "type_checking"
        if self.func:
            return "lazy"
        if self.getattr_ or self.try_:
            return "optional"
        return "main" if self.main else "module"

    def visit_FunctionDef(self, n: ast.FunctionDef | ast.AsyncFunctionDef) -> None:  # noqa: N802
        for d in n.decorator_list:
            self.visit(d)
        # PEP 562 module __getattr__ runs on `from M import X`, so it counts as module-level.
        if self.func == 0 and n.name == "__getattr__" and not self.tc:
            self.getattr_ += 1
            for s in n.body:
                self.visit(s)
            self.getattr_ -= 1
            return
        self.func += 1
        for s in n.body:
            self.visit(s)
        self.func -= 1

    visit_AsyncFunctionDef = visit_FunctionDef  # noqa: N815

    def visit_Lambda(self, n: ast.Lambda) -> None:  # noqa: N802
        self.func += 1
        self.generic_visit(n)
        self.func -= 1

    def visit_If(self, n: ast.If) -> None:  # noqa: N802
        t = n.test
        if (isinstance(t, ast.Name) and t.id == "TYPE_CHECKING") or (
            isinstance(t, ast.Attribute) and t.attr == "TYPE_CHECKING"
        ):
            self.tc += 1
            for s in n.body:
                self.visit(s)
            self.tc -= 1
            for s in n.orelse:
                self.visit(s)
            return
        if isinstance(t, ast.Compare) and isinstance(t.left, ast.Name) and t.left.id == "__name__":
            self.main += 1
            self.generic_visit(n)
            self.main -= 1
            return
        self.generic_visit(n)

    def visit_Try(self, n: ast.Try) -> None:  # noqa: N802
        if catches_import_error(n.handlers):
            self.try_ += 1
            for s in n.body:
                self.visit(s)
            self.try_ -= 1
            for h in n.handlers:
                self.visit(h)
            for s in n.orelse + n.finalbody:
                self.visit(s)
        else:
            self.generic_visit(n)

    visit_TryStar = visit_Try  # noqa: N815

    def add_internal(self, target: str, line: int, detail: str) -> None:
        known = longest_known(target, self.modules)
        self.node.edges.append(
            {"target": known or f"?{target}", "kind": self.kind(), "line": line, "detail": detail}
        )

    def add_third(self, full: str, line: int) -> None:
        top = full.split(".")[0]
        if top and top not in STDLIB:
            self.node.third.append({"top": top, "full": full, "kind": self.kind(), "line": line})

    def visit_Import(self, n: ast.Import) -> None:  # noqa: N802
        for a in n.names:
            if self.an.internal(a.name):
                self.add_internal(a.name, n.lineno, f"import {a.name}")
                local = a.asname or a.name.split(".")[0]
                self.node.mod_alias[local] = a.name if a.asname else local
            else:
                self.add_third(a.name, n.lineno)
                self.node.mod_alias[a.asname or a.name.split(".")[0]] = (
                    a.name if a.asname else a.name.split(".")[0]
                )

    def visit_ImportFrom(self, n: ast.ImportFrom) -> None:  # noqa: N802
        mod = resolve_relative(self.node, n.module, n.level)
        if self.an.internal(mod):
            self.add_internal(mod, n.lineno, f"from {mod} import ...")
            for a in n.names:
                sub = f"{mod}.{a.name}"
                if sub in self.modules:
                    self.add_internal(sub, n.lineno, f"from {mod} import {a.name}")
                    self.node.mod_alias[a.asname or a.name] = sub
                else:
                    self.node.from_names[a.asname or a.name] = (mod, a.name)
        else:
            self.add_third(mod, n.lineno)
            for a in n.names:
                self.node.from_names[a.asname or a.name] = (mod, a.name)
                if a.name in self.an.entry_triggers.get(mod, set()):
                    self.node.triggers.append((f"{mod}.{a.name}", n.lineno))


def resolve_name(nodes: dict[str, Node], node: Node, name: str, depth: int = 0) -> str | None:
    if depth > 8:
        return None
    if name in node.consts:
        return node.consts[name]
    if name in node.from_names:
        mod, attr = node.from_names[name]
        if mod in nodes:
            return resolve_name(nodes, nodes[mod], attr, depth + 1)
    return None


def eval_str(nodes: dict[str, Node], node: Node, e: ast.expr, depth: int = 0) -> str | None:
    """Evaluate a string-ish expression; unknown parts become PH. None if not string-ish."""
    if depth > 30:
        return None
    if isinstance(e, ast.Constant):
        return e.value if isinstance(e.value, str) else None
    if isinstance(e, ast.JoinedStr):
        out = []
        for v in e.values:
            if isinstance(v, ast.Constant):
                out.append(str(v.value))
            elif isinstance(v, ast.FormattedValue):
                inner = eval_str(nodes, node, v.value, depth + 1)
                out.append(inner if inner is not None and v.format_spec is None else PH)
        return "".join(out)
    if isinstance(e, ast.BinOp) and isinstance(e.op, (ast.Add, ast.Div)):
        left = eval_str(nodes, node, e.left, depth + 1)
        right = eval_str(nodes, node, e.right, depth + 1)
        if left is None and right is None:
            return None
        sep = "/" if isinstance(e.op, ast.Div) else ""
        return f"{PH if left is None else left}{sep}{PH if right is None else right}"
    if isinstance(e, ast.Name):
        return resolve_name(nodes, node, e.id)
    if isinstance(e, ast.Attribute) and isinstance(e.value, ast.Name):
        mod = node.mod_alias.get(e.value.id)
        return resolve_name(nodes, nodes[mod], e.attr) if mod in nodes else None
    if (
        isinstance(e, ast.Call)
        and isinstance(e.func, ast.Name)
        and e.func.id in ("Path", "PurePosixPath", "PurePath", "str")
    ):
        if len(e.args) == 1:
            return eval_str(nodes, node, e.args[0], depth + 1)
        parts = [eval_str(nodes, node, a, depth + 1) for a in e.args]
        return "/".join(PH if p is None else p for p in parts) if parts else None
    return None


def collect_consts(nodes: dict[str, Node]) -> None:
    for _ in range(10):
        changed = False
        for node in nodes.values():
            for stmt in node.tree.body:  # type: ignore[union-attr]
                targets: list[ast.expr] = []
                value = None
                if isinstance(stmt, ast.Assign):
                    targets, value = stmt.targets, stmt.value
                elif isinstance(stmt, ast.AnnAssign) and stmt.value is not None:
                    targets, value = [stmt.target], stmt.value
                for t in targets:
                    if isinstance(t, ast.Name) and value is not None:
                        v = eval_str(nodes, node, value)
                        if v is not None and node.consts.get(t.id) != v:
                            node.consts[t.id] = v
                            changed = True
        if not changed:
            break


def collect_dynamic(an: Analysis, nodes: dict[str, Node], modules: set[str]) -> None:
    for node in nodes.values():
        tree = node.tree
        assert tree is not None
        docs = docstring_ids(tree)
        loop_values: dict[str, list[str]] = defaultdict(list)
        parents: dict[int, ast.AST] = {}
        for p in ast.walk(tree):
            for c in ast.iter_child_nodes(p):
                parents[id(c)] = p
            if (
                isinstance(p, ast.For)
                and isinstance(p.target, ast.Name)
                and isinstance(p.iter, (ast.Tuple, ast.List))
            ):
                for elt in p.iter.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        loop_values[p.target.id].append(elt.value)

        def dynamic(target: str, line: int, detail: str, node: Node = node) -> None:
            if an.internal(target):
                known = longest_known(target, modules) or f"?{target}"
                node.edges.append(
                    {"target": known, "kind": "dynamic", "line": line, "detail": detail}
                )
            else:
                node.third.append(
                    {"top": target.split(".")[0], "full": target, "kind": "lazy", "line": line}
                )

        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute):  # attribute-style triggers: pkg.mod.name(...)
                chain, cur = [], n
                while isinstance(cur, ast.Attribute):
                    chain.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name):
                    chain.append(node.mod_alias.get(cur.id, cur.id))
                    dotted = ".".join(reversed(chain))
                    mod, _, attr = dotted.rpartition(".")
                    if attr in an.entry_triggers.get(mod, set()):
                        node.triggers.append((dotted, n.lineno))
            if isinstance(n, ast.Call):
                fn = n.func
                fname = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
                if fname in ("import_module", "__import__", "run_module") and n.args:
                    arg, vals = n.args[0], []
                    v = eval_str(nodes, node, arg)
                    if v is not None and PH not in v:
                        vals.append(v)
                    elif isinstance(arg, ast.Name) and arg.id in loop_values:
                        vals.extend(loop_values[arg.id])
                    for val in vals:
                        dynamic(val, n.lineno, f"{fname}({val!r})")
            if isinstance(n, (ast.List, ast.Tuple)):  # [..., "-m", "pkg.x", ...]
                for i, elt in enumerate(n.elts[:-1]):
                    if isinstance(elt, ast.Constant) and elt.value == "-m":
                        v = eval_str(nodes, node, n.elts[i + 1])
                        if v and an.internal(v):
                            dynamic(v, n.lineno, f"subprocess -m {v}")
            if isinstance(n, (ast.Constant, ast.JoinedStr, ast.BinOp)) and id(n) not in docs:
                if isinstance(n, ast.Constant) and isinstance(parents.get(id(n)), ast.JoinedStr):
                    continue
                v = eval_str(nodes, node, n)
                if v:
                    node.strings.add((v, getattr(n, "lineno", 0)))


def string_edges(an: Analysis, nodes: dict[str, Node], modules: set[str]) -> None:
    """Report-only edges: internal modules named in strings, as dotted names or as paths."""
    file_to_module = {nd.path: m for m, nd in nodes.items() if not m.startswith("script:")}
    for node in nodes.values():
        seen: set[str] = set()
        for value, line in sorted(node.strings):
            prose = any(ch.isspace() for ch in value)
            for match in an.dotted_re.findall(value):
                match = match.rstrip(".")
                if PH in match:
                    pat = match.replace(PH, "*")
                    targets = [m for m in modules if fnmatch.fnmatch(m, pat)]
                else:
                    t = longest_known(match, modules)
                    targets = [t] if t else []
                for t in targets:
                    if t not in seen:
                        seen.add(t)
                        node.edges.append(
                            {"target": t, "kind": "named", "line": line, "detail": f"{match!r}"}
                        )
            for match in an.path_re.findall(value):
                pat = match.rstrip("/.").replace(PH, "*")
                for root in an.source_roots:
                    full = f"{root}/{pat}"
                    hits = [
                        m
                        for f, m in file_to_module.items()
                        if fnmatch.fnmatch(f, full) or fnmatch.fnmatch(f, full + "/*")
                    ]
                    for t in hits:
                        if t not in seen:
                            seen.add(t)
                            kind = "named_in_prose" if prose else "named"
                            node.edges.append(
                                {"target": t, "kind": kind, "line": line, "detail": f"path {pat!r}"}
                            )


def shell_nodes(
    an: Analysis, cfg: dict[str, Any], nodes: dict[str, Node], modules: set[str], cmds: set[str]
) -> dict[str, Node]:
    shells: dict[str, Node] = {}
    files = [f for f in walk_files(an.repo) if matches(f, an.shell_globs)]
    for rel in files:
        shells[f"shell:{rel}"] = Node(name=f"shell:{rel}", path=rel)
    cli = cfg.get("cli", {})
    cli_rx = re.compile(cli["shell_pattern"]) if cli.get("shell_pattern") else None
    rules = [(re.compile(r["pattern"]), list(r["to"])) for r in cfg.get("shell_rules", [])]
    alt = "|".join(re.escape(p) for p in an.packages)
    imports_rx = re.compile(rf"(?:from ((?:{alt})[\w.]*) import|\bimport ((?:{alt})[\w.]*))")
    dash_m_rx = re.compile(rf"-m ((?:{alt})[\w.]*)")
    for nd in shells.values():
        text = (an.repo / nd.path).read_text(encoding="utf-8")
        nd.loc = text.count("\n")

        def edge(target: str, line: int, detail: str, nd: Node = nd) -> None:
            nd.edges.append({"target": target, "kind": "shell", "line": line, "detail": detail})

        for i, line in enumerate(text.splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for tok in re.findall(r"[\w./-]+\.py\b", line):
                tok = tok.removeprefix("./")
                if f"script:{tok}" in nodes:
                    edge(f"script:{tok}", i, "runs script")
            for a, b in imports_rx.findall(line):
                t = longest_known(a or b, modules)
                if t:
                    edge(t, i, "python -c import")
            for m in dash_m_rx.findall(line):
                t = longest_known(m, modules)
                if t:
                    edge(t, i, "python -m")
            for m in re.findall(r"(?:source|\.) ([\w./-]+)", line):
                if f"shell:{m.removeprefix('./')}" in shells:
                    edge(f"shell:{m.removeprefix('./')}", i, "source")
            if cli_rx is not None:
                for groups in cli_rx.findall(line):
                    groups = (groups,) if isinstance(groups, str) else groups
                    cmd = "cmd:" + cli["command"].format(*groups, group=groups[0], name=groups[-1])
                    if cmd in cmds:
                        edge(cmd, i, cmd[4:])
            for rx, targets in rules:
                for m in rx.finditer(line):
                    for t in targets:
                        edge(t.format(*([m.group(0), *m.groups()])), i, rx.pattern)
    return shells


def cli_commands(an: Analysis, cfg: dict[str, Any], nodes: dict[str, Node]) -> dict[str, Node]:
    """Command nodes from a dict literal {group: {name: (..)}} or {name: (..)} in the CLI module."""
    cli = cfg.get("cli")
    if not cli:
        return {}
    module, variable = (
        require(cli, "module", "closure.cli"),
        require(cli, "variable", "closure.cli"),
    )
    if module not in nodes:
        raise ConfigError(f"[closure.cli].module {module!r} is not a module of the packages")
    registry = None
    for stmt in nodes[module].tree.body:  # type: ignore[union-attr]
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
            if any(isinstance(t, ast.Name) and t.id == variable for t in targets):
                registry = ast.literal_eval(stmt.value)  # type: ignore[arg-type]
    if not isinstance(registry, dict):
        raise ConfigError(f"no dict literal {variable} in {module}")
    rows: list[tuple[str, str, Any]] = []
    for group, value in registry.items():
        if isinstance(value, dict):
            rows += [(group, name, leaf) for name, leaf in value.items()]
        else:
            rows.append(("", group, value))
    out: dict[str, Node] = {}
    for group, name, leaf in rows:
        leaf = leaf if isinstance(leaf, (tuple, list)) else (leaf,)
        cmd = "cmd:" + cli["command"].format(group=group, name=name).replace("  ", " ")
        nd = Node(name=cmd, path=nodes[module].path)
        target = cli["target"].format(*leaf, group=group, name=name)
        for t in [target, *cli.get("also", [module])]:
            nd.edges.append({"target": t, "kind": "module", "line": 0, "detail": f"{variable} row"})
        out[cmd] = nd
    return out


def ancestors(an: Analysis, mod: str) -> list[str]:
    if not an.internal(mod):
        return []
    parts = mod.split(".")
    return [".".join(parts[:i]) for i in range(1, len(parts))]


def closure(an: Analysis, graph: dict[str, Node], roots: list[str], kinds: set[str]) -> set[str]:
    seen: set[str] = set()
    stack = list(roots)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack += [a for a in ancestors(an, cur) if a in graph and a not in seen]
        nd = graph.get(cur)
        for e in nd.edges if nd else []:
            if e["kind"] in kinds and not e["target"].startswith("?") and e["target"] not in seen:
                stack.append(e["target"])
    return seen


def variants(an: Analysis, graph: dict[str, Node], roots: list[str]) -> dict[str, set[str]]:
    rt = closure(an, graph, roots, RUNTIME_KINDS)
    triggered = sorted(m for m in rt if m in graph and graph[m].triggers)
    ep = set(rt)
    if triggered and an.entry_root:
        ep |= closure(an, graph, [an.entry_root], RUNTIME_KINDS)
    ty = closure(an, graph, sorted(ep), RUNTIME_KINDS | {"type_checking"})
    return {"runtime": rt, "entrypoint": ep, "typing": ty, "_triggered": set(triggered)}


def why_chains(an: Analysis, graph: dict[str, Node], roots: list[str], reach: set[str]) -> dict:
    kinds = RUNTIME_KINDS | {"type_checking"}
    parent: dict[str, tuple[str, str] | None] = {r: None for r in roots}
    q = deque(roots)
    while q:
        cur = q.popleft()
        nd = graph.get(cur)
        nexts = [(a, "package") for a in ancestors(an, cur) if a in graph]
        if nd is not None:
            nexts += [
                (e["target"], f"{e['kind']}:{e['line']}")
                for e in nd.edges
                if e["kind"] in kinds and not e["target"].startswith("?")
            ]
        for t, how in nexts:
            if t not in parent:
                parent[t] = (cur, how)
                q.append(t)
    out = {}
    for m in sorted(reach):
        chain, cur = [], m
        while parent.get(cur) is not None:
            prev, how = parent[cur]  # type: ignore[misc]
            chain.append(f"{prev} -[{how}]-> {cur}")
            cur = prev
        out[m] = list(reversed(chain))
    return out


def main() -> int:
    job = job_from_argv(__doc__)
    source, cfg = job.section("source"), job.section("closure")
    out_dir = job.out_dir(cfg)
    if source.get("tree"):
        repo = job.resolve(source["tree"])
    else:
        repo = out_dir / "source-tree"
        if not repo.exists():
            materialise(job.resolve(require(source, "repo", "source")), source["pin"], repo)
    an = Analysis(cfg, repo)
    nodes = discover(an)
    modules = {m for m in nodes if not m.startswith("script:")}
    for nd in nodes.values():
        ImportCollector(an, nd, modules).visit(nd.tree)  # type: ignore[arg-type]
    collect_consts(nodes)
    collect_dynamic(an, nodes, modules)
    string_edges(an, nodes, modules)
    commands = cli_commands(an, cfg, nodes)
    shells = shell_nodes(an, cfg, nodes, modules, set(commands))
    graph: dict[str, Node] = {**nodes, **commands, **shells}
    for e in cfg.get("edges", []):
        src, dst, why = e["from"], e["to"], e.get("why", "")
        if not why:
            raise ConfigError(f"manual edge {src} -> {dst} needs a `why` (the code that says so)")
        graph.setdefault(src, Node(name=src, path="")).edges.append(
            {"target": dst, "kind": "manual", "line": 0, "detail": why}
        )
    roots = list(require(cfg, "roots", "closure"))
    missing = [r for r in roots if r not in graph]
    if missing:
        raise SystemExit(
            f"roots not in the graph (typo, or a command the CLI table lacks): {missing}"
        )

    v = variants(an, graph, roots)

    def files_of(reach: set[str]) -> dict[str, list[str]]:
        by_type: dict[str, list[str]] = {"module": [], "script": [], "shell": [], "command": []}
        for n in sorted(reach):
            nd = graph.get(n)
            kind = (
                "script"
                if n.startswith("script:")
                else "shell"
                if n.startswith("shell:")
                else "command"
                if n.startswith("cmd:")
                else "module"
                if n in modules
                else None
            )
            if kind and nd is not None and nd.path and kind != "command":
                by_type[kind].append(nd.path)
            elif kind == "command":
                by_type["command"].append(n)
        return by_type

    def unreached(reach: set[str]) -> dict[str, dict[str, Any]]:
        groups: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"files": 0, "loc": 0, "modules": []}
        )
        for m in sorted(modules - reach):
            pkg = m if nodes[m].is_pkg else m.rpartition(".")[0]
            g = groups[pkg]
            g["files"] += 1
            g["loc"] += nodes[m].loc
            g["modules"].append(m)
        return dict(sorted(groups.items()))

    ty = v["typing"]
    named: dict[str, list[str]] = defaultdict(list)
    for m in sorted(ty):
        for e in graph[m].edges if m in graph else []:
            if e["kind"].startswith("named") and e["target"] not in ty:
                named[e["target"]].append(f"{graph[m].path}:{e['line']} {e['detail']}")
    third: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for m in sorted(v["runtime"]):
        for t in graph[m].third if m in graph else []:
            third[t["top"]][t["kind"]].append(f"{graph[m].path}:{t['line']}")
    options = {}
    for opt in cfg.get("options", []):
        ov = variants(an, graph, roots + list(opt["roots"]))
        added = sorted(m for m in ov["runtime"] - v["runtime"] if m in modules)
        options[opt["name"]] = {
            "roots": opt["roots"],
            "added_modules": added,
            "added_loc": sum(nodes[m].loc for m in added),
        }
    out: dict[str, Any] = {
        "tree": str(repo),
        "packages": an.packages,
        "source_roots": an.source_roots,
        "roots": roots,
        "variants": {
            k: {"modules": sorted(m for m in v[k] if m in modules), "files": files_of(v[k])}
            for k in ("runtime", "entrypoint", "typing")
        },
        "entrypoint_triggered_by": sorted(v["_triggered"]),
        "module_files": {m: nodes[m].path for m in sorted(modules)},
        "why_reached": why_chains(an, graph, roots, {m for m in ty if m in modules}),
        "unreached": unreached(v["runtime"]),
        "named_not_reached": dict(sorted(named.items())),
        "unresolved_internal": sorted(
            {
                f"{n}: {e['target'][1:]}"
                for n, nd in graph.items()
                for e in nd.edges
                if e["target"].startswith("?")
            }
        ),
        "third_party_runtime": {k: dict(d) for k, d in sorted(third.items())},
        "options": options,
        "totals": {
            "modules": len(modules),
            "loc": sum(nodes[m].loc for m in modules),
            **{
                f"{k}_modules": len([m for m in v[k] if m in modules])
                for k in ("runtime", "entrypoint", "typing")
            },
            **{
                f"{k}_loc": sum(nodes[m].loc for m in v[k] if m in modules)
                for k in ("runtime", "typing")
            },
        },
        "edges": {n: nd.edges for n, nd in sorted(graph.items())},
    }
    target = out_dir / "closure.json"
    target.write_text(json.dumps(out, indent=1) + "\n", encoding="utf-8")
    write_run_record(job, out_dir, "closure", {}, {"output": str(target), **out["totals"]})
    print(json.dumps(out["totals"]))
    for name, o in options.items():
        print(f"option {name}: +{len(o['added_modules'])} modules, +{o['added_loc']} lines")
    unresolved = len(out["unresolved_internal"])
    print(f"named in strings, not reached: {len(named)}; unresolved imports: {unresolved}")
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
