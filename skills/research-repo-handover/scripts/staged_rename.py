"""Apply renames in reviewable stages, one commit each, from a map file; frozen text never changes.

usage: python3 staged_rename.py JOB.toml     (reads [rename] and its map file)

[rename] keys:
  repo      a clean git working copy to rename in (never the source repo)
  map       the map file: a TOML file of [[stage]] tables (below)
  frozen    globs of files whose bytes must not change (prompts, vendored code, anything staged
            into a sandbox or shown to a judge); only their paths may move. A file is frozen if
            its current or its original path matches.
  unfrozen  globs excepted from `frozen` (e.g. a README inside a frozen tree)
  missing   "error" (default) or "skip": what to do with a move whose source is absent
  commit    true: commit each stage; `trailer` lines are appended to every message;
            `commit_env` {NAME = value} is added to the commit's environment (state why)

Each [[stage]] has a `name` and any of:
  moves         TSV path (relative to the map file) or inline [[old, new], ...]: `git mv` each
  path_updates  true: replace each moved path string, longest first, in every non-frozen text
                file; `extra_subs` [[old, new], ...] adds literal path strings to replace after
  delete        paths to `git rm -r`
  [[stage.sub]] substitutions, each over `files` globs (default all text) minus `exclude`:
      mode = "literal"       old, new
      mode = "regex"         pattern, replace (re.sub syntax), optional flags ("i", "m", "s")
      mode = "python-names"  NAME tokens of .py files only: `names` {old = new} exact
                             identifiers, `parts` {old = new} for snake_case/UPPER/CamelCase
                             parts, `keep` [names never touched]; `strings` {old = new} for
                             whole string literals; `identifier_strings` true to also rename
                             string literals that are one snake_case identifier (a module name
                             in a command table, a getattr name); `comments` [[regex, repl], ...]
                             for comment and docstring prose. Other code strings are left alone,
                             since some reach a model. `move_modules` true: first `git mv` every
                             .py file in scope whose module name the rule renames (package
                             directories need explicit moves).
      mode = "yaml-keys"     .yaml/.yml mapping keys `keys` {old = new}; `comments` as above
Outputs in the output directory: rename-report.json (per stage: moves, per-rule counts, files
rewritten, commit, frozen-file proof), moved-paths.tsv (original path -> current path, for
check_tree.py's path_map) and rewritten.tsv (path -> stages that rewrote it, usable as audit
reasons), dangling-paths.tsv (path strings that resolved before a stage and no longer do: a
warning, since prose may cite old paths but code that builds a path from parts must be fixed).
Before any file of a stage is written, every Python file must still parse, and every module
reference (imports, and string literals that are dotted chains) that named a repo module before
the stage must name one after it; a renamed import without its module moved, or a moved module
with its importers unchanged, stops the run.
"""

from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tokenize
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import (  # noqa: E402
    ConfigError,
    job_from_argv,
    matches,
    read_tsv,
    require,
    write_run_record,
)


def git(repo: Path, *args: str, env: dict[str, str] | None = None) -> str:
    full_env = {**os.environ, **env} if env else None
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, env=full_env
    )
    if done.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout


def ls_files(repo: Path) -> list[str]:
    return sorted(p for p in git(repo, "ls-files", "-z").split("\0") if p)


def read_text(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except (IsADirectoryError, FileNotFoundError):
        return None
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


DOTTED = re.compile(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*")
PATH_TOKEN = re.compile(r"(?<![\w.-])(?:[\w.-]+/)+[\w.-]*")


class Renamer:
    """Identifier renames for python-names: exact names first, then part rules."""

    def __init__(self, sub: dict[str, Any]) -> None:
        self.names: dict[str, str] = dict(sub.get("names", {}))
        self.parts: dict[str, str] = dict(sub.get("parts", {}))
        self.keep: set[str] = set(sub.get("keep", []))
        self.strings: dict[str, str] = dict(sub.get("strings", {}))
        self.identifier_strings = bool(sub.get("identifier_strings", False))
        self.comments = [(re.compile(rx), rep) for rx, rep in sub.get("comments", [])]

    def string(self, body: str) -> str:
        if body in self.strings:
            return self.strings[body]
        # One identifier with an underscore, or a dotted chain ("pkg.mod.func", a patch target).
        if self.identifier_strings and ("_" in body or "." in body) and DOTTED.fullmatch(body):
            return ".".join(self.name(part) for part in body.split("."))
        return body

    def name(self, ident: str) -> str:
        if ident in self.keep:
            return ident
        if ident in self.names:
            return self.names[ident]
        if not self.parts:
            return ident
        if "_" in ident or ident.isupper() or ident.islower():
            return "_".join(self.parts.get(p, p) for p in ident.split("_"))
        pieces = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+|[A-Z]+(?![a-z])", ident)
        if "".join(pieces) == ident:
            return "".join(self.parts.get(p, p) for p in pieces)
        return ident

    def prose(self, text: str) -> str:
        for rx, rep in self.comments:
            text = rx.sub(rep, text)
        return text


def docstring_starts(source: str) -> set[tuple[int, int]]:
    starts = set()
    for node in ast.walk(ast.parse(source)):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            for stmt in body or []:
                if (
                    isinstance(stmt, ast.Expr)
                    and isinstance(stmt.value, ast.Constant)
                    and isinstance(stmt.value.value, str)
                ):
                    starts.add((stmt.value.lineno, stmt.value.col_offset))
    return starts


def rewrite_python(source: str, ren: Renamer) -> tuple[str, int]:
    # The lines tokenize sees: split on "\n" only (str.splitlines also splits on \x0c, \u2028...).
    lines = list(iter(io.StringIO(source).readline, ""))
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    docs = docstring_starts(source)
    edits: list[tuple[int, int, str]] = []
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        start = offsets[tok.start[0] - 1] + tok.start[1]
        end = offsets[tok.end[0] - 1] + tok.end[1]
        new = tok.string
        if tok.type == tokenize.NAME:
            new = ren.name(tok.string)
        elif tok.type == tokenize.COMMENT:
            new = ren.prose(tok.string)
        elif tok.type == tokenize.STRING:
            m = re.match(r"(?i)([rbu]*)('''|\"\"\"|'|\")", tok.string)
            if m:
                prefix, quote = m.group(1), m.group(2)
                body = tok.string[len(prefix) + len(quote) : len(tok.string) - len(quote)]
                if (tok.start[0], tok.start[1]) in docs:
                    body2 = ren.prose(body)
                else:
                    body2 = ren.string(body)
                new = f"{prefix}{quote}{body2}{quote}"
        if new != tok.string:
            edits.append((start, end, new))
    out = source
    for start, end, new in sorted(edits, reverse=True):
        out = out[:start] + new + out[end:]
    return out, len(edits)


def rewrite_yaml(text: str, sub: dict[str, Any]) -> tuple[str, int]:
    keys: dict[str, str] = dict(sub.get("keys", {}))
    ren = Renamer({"comments": sub.get("comments", [])})
    out, n = [], 0
    for line in text.splitlines(keepends=True):
        m = re.match(r"^(\s*(?:- )?)([A-Za-z_][\w-]*)(\s*:)(.*)$", line, re.S)
        if m and m.group(2) in keys:
            line = f"{m.group(1)}{keys[m.group(2)]}{m.group(3)}{m.group(4)}"
            n += 1
        if "#" in line and ren.comments:
            code, _, comment = line.partition("#")
            if '"' not in code and "'" not in code:
                new = code + "#" + ren.prose(comment)
                n += new != line
                line = new
        out.append(line)
    return "".join(out), n


FLAGS = {"i": re.I, "m": re.M, "s": re.S}


def apply_sub(sub: dict[str, Any], path: str, text: str) -> tuple[str, int]:
    mode = sub.get("mode")
    if mode == "literal":
        old, new = require(sub, "old", "stage.sub literal"), sub.get("new", "")
        return text.replace(old, new), text.count(old)
    if mode == "regex":
        flags = 0
        for ch in sub.get("flags", ""):
            flags |= FLAGS[ch]
        rx = re.compile(require(sub, "pattern", "stage.sub regex"), flags)
        return rx.subn(sub.get("replace", ""), text)
    if mode == "python-names":
        if not path.endswith(".py"):
            return text, 0
        return rewrite_python(text, sub["_renamer"])
    if mode == "yaml-keys":
        if not path.endswith((".yaml", ".yml")):
            return text, 0
        return rewrite_yaml(text, sub)
    raise ConfigError(f"unknown substitution mode {mode!r}")


def module_index(paths: list[str]) -> set[str]:
    """Every dotted suffix of every .py path: what an import could resolve to in this tree."""
    names: set[str] = set()
    for p in paths:
        if p.endswith(".py"):
            parts = list(Path(p).with_suffix("").parts)
            if parts[-1] == "__init__":
                parts = parts[:-1]
            names.update(".".join(parts[i:]) for i in range(len(parts)))
    return names


def import_names(source: str) -> list[str]:
    """Module references in node order: `import a.b`, `from a import b` (as a and a.b), and
    string literals that are dotted chains (`import_module("a.b")`, patch targets)."""
    out: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            out.append(node.module)
            out += [f"{node.module}.{a.name}" for a in node.names]
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "." in node.value and DOTTED.fullmatch(node.value):
                out.append(node.value)
    return out


def tree_entries(paths: list[str]) -> set[str]:
    """Every file and every directory above one, as repo-relative paths."""
    found: set[str] = set()
    for p in paths:
        parts = p.split("/")
        found.update("/".join(parts[:i]) for i in range(1, len(parts) + 1))
    return found


def path_tokens(text: str, tops: set[str]) -> list[str]:
    """Path-like strings in a text, in order, whose first component is a top-level entry."""
    return [
        t.rstrip("/") for t in PATH_TOKEN.findall(text) if t.split("/")[0] in tops and t.rstrip("/")
    ]


def newly_dangling(old: list[str], new: list[str], before: set[str], after: set[str]) -> set[str]:
    """Path strings that resolved before a stage and do not after. Tokens pair by position
    when both texts hold the same number; otherwise by set difference."""
    if len(old) == len(new):
        return {n for o, n in zip(old, new, strict=True) if o in before and n not in after}
    return (set(new) - after) - (set(old) - before)


def sub_label(sub: dict[str, Any]) -> str:
    return sub.get("label") or sub.get("old") or sub.get("pattern") or sub.get("mode", "?")


def main() -> int:
    job = job_from_argv(__doc__)
    cfg = job.section("rename")
    out_dir = job.out_dir(cfg)
    repo = job.resolve(require(cfg, "repo", "rename"))
    map_path = job.resolve(require(cfg, "map", "rename"))
    stages = tomllib.loads(map_path.read_text(encoding="utf-8")).get("stage", [])
    if not stages:
        raise ConfigError(f"{map_path}: no [[stage]] tables")
    frozen, unfrozen = list(cfg.get("frozen", [])), list(cfg.get("unfrozen", []))
    on_missing = cfg.get("missing", "error")
    if git(repo, "status", "--porcelain").strip():
        raise SystemExit(f"{repo} has uncommitted changes; commit or discard them first")
    start = git(repo, "rev-parse", "HEAD").strip()
    origin = {p: p for p in ls_files(repo)}  # current path -> original path
    deleted: list[str] = []
    rewritten: dict[str, list[str]] = defaultdict(list)

    def is_frozen(path: str) -> bool:
        cands = (path, origin.get(path, path))
        return any(matches(c, frozen) for c in cands) and not any(
            matches(c, unfrozen) for c in cands
        )

    def digest(path: str) -> str:
        return hashlib.sha256((repo / path).read_bytes()).hexdigest()

    report: list[dict[str, Any]] = []
    all_dangling: list[str] = []
    for number, stage in enumerate(stages, 1):
        name = require(stage, "name", f"stage {number}")
        before = {origin[p]: digest(p) for p in origin if is_frozen(p) and (repo / p).is_file()}
        index_before = module_index(list(origin))
        exists_before = tree_entries(list(origin))
        entry: dict[str, Any] = {
            "stage": number,
            "name": name,
            "moves": 0,
            "skipped": [],
            "subs": [],
        }
        raw_moves = stage.get("moves", [])
        moves = (
            read_tsv(map_path.parent / raw_moves, 2) if isinstance(raw_moves, str) else raw_moves
        )
        applied: list[tuple[str, str]] = []
        for old, new in ((m[0], m[1]) for m in moves):
            if not (repo / old).exists():
                if on_missing == "skip":
                    entry["skipped"].append(old)
                    continue
                raise SystemExit(f"stage {number}: move source absent: {old}")
            if (repo / new).exists():  # git mv would nest the source inside it
                raise SystemExit(
                    f"stage {number}: move target exists: {new} (ignored files count: "
                    f"`git -C {repo} status --ignored`)"
                )
            (repo / new).parent.mkdir(parents=True, exist_ok=True)
            git(repo, "mv", old, new)
            for cur in [p for p in origin if p == old or p.startswith(old.rstrip("/") + "/")]:
                moved_to = new + cur[len(old) :]
                origin[moved_to] = origin.pop(cur)
                if cur in rewritten:  # earlier stages' rewrite records follow the file
                    rewritten[moved_to] = rewritten.pop(cur)
            applied.append((old, new))
        for path in stage.get("delete", []):
            if (repo / path).exists():
                git(repo, "rm", "-r", "-q", path)
                for cur in [p for p in origin if p == path or p.startswith(path.rstrip("/") + "/")]:
                    deleted.append(origin.pop(cur))
                    rewritten.pop(cur, None)
        module_moves = 0
        for sub in stage.get("sub", []):  # move_modules: module files follow their new names
            if sub.get("mode") != "python-names" or not sub.get("move_modules"):
                continue
            ren = Renamer(sub)
            for path in sorted(origin):
                in_scope = matches(path, sub.get("files", ["**"])) and not matches(
                    path, sub.get("exclude", [])
                )
                if not path.endswith(".py") or is_frozen(path) or not in_scope:
                    continue
                stem = Path(path).stem
                new_stem = ren.name(stem)
                if new_stem == stem:
                    continue
                new = Path(path).with_name(new_stem + ".py").as_posix()
                if (repo / new).exists():
                    raise SystemExit(f"stage {number}: module move target exists: {new}")
                git(repo, "mv", path, new)
                origin[new] = origin.pop(path)
                if path in rewritten:
                    rewritten[new] = rewritten.pop(path)
                applied.append((path, new))
                module_moves += 1
        entry["moves"] = len(applied)
        entry["module_moves"] = module_moves
        subs: list[dict[str, Any]] = []
        if stage.get("path_updates"):
            pairs = sorted(applied, key=lambda kv: -len(kv[0])) + [
                (o, n) for o, n in stage.get("extra_subs", [])
            ]
            subs += [
                {"mode": "literal", "old": o, "new": n, "label": f"path {o}"} for o, n in pairs
            ]
        for sub in stage.get("sub", []):
            if sub.get("mode") == "python-names":
                sub = {**sub, "_renamer": Renamer(sub)}
            subs.append(sub)
        counts = [0] * len(subs)
        pending: dict[str, str] = {}  # every rewrite is checked before any file is written
        index_after = module_index(list(origin))
        exists_after = tree_entries(list(origin))
        tops = {e.split("/")[0] for e in exists_before | exists_after}
        broken: list[str] = []
        dangling_here: list[str] = []
        undo = (
            f"Nothing of this stage's text was written. Undo its moves with `git -C {repo} "
            f"reset --hard` (scratch clone), fix the map, and rerun from the start commit {start}."
        )
        for path in sorted(origin):
            text = read_text(repo / path)
            if text is None:
                continue
            new_text = text
            for i, sub in enumerate(subs):
                if is_frozen(path) or not matches(path, sub.get("files", ["**"])):
                    continue
                if matches(path, sub.get("exclude", [])):
                    continue
                new_text, n = apply_sub(sub, path, new_text)
                counts[i] += n
            if new_text != text and path.endswith(".py"):
                try:
                    ast.parse(new_text)
                except SyntaxError as err:
                    raise SystemExit(
                        f"stage {number}: {path} would no longer parse ({err}). {undo}"
                    ) from err
            if new_text != text:
                pending[path] = new_text
            if not is_frozen(path):  # path strings that resolved before this stage and now do not
                stale = newly_dangling(
                    path_tokens(text, tops),
                    path_tokens(new_text, tops),
                    exists_before,
                    exists_after,
                )
                dangling_here += [f"{path}\t{tok}" for tok in sorted(stale)]
            if path.endswith(".py"):  # frozen files too: a moved module can break their imports
                try:
                    pairs = list(zip(import_names(text), import_names(new_text), strict=True))
                except (SyntaxError, ValueError):
                    pairs = []  # a file that did not parse before this stage is not judged here
                broken += [
                    f"{path}: import {old} -> {new}"
                    for old, new in pairs
                    if old in index_before and new not in index_after
                ]
        if broken:
            listing = "\n  ".join(broken[:20])
            raise SystemExit(
                f"stage {number}: {len(broken)} import(s) of repo modules would no longer resolve "
                f"(rename without a module move, or a move without its importers):\n  {listing}\n"
                f"{undo}"
            )
        for path, new_text in pending.items():
            (repo / path).write_text(new_text, encoding="utf-8")
            rewritten[path].append(name)
        entry["subs"] = [
            {"rule": sub_label(s), "mode": s.get("mode"), "count": c}
            for s, c in zip(subs, counts, strict=True)
        ]
        entry["files_rewritten"] = sum(1 for p, st in rewritten.items() if name in st)
        after = {
            origin[p]: digest(p) for p in origin if origin[p] in before and (repo / p).is_file()
        }
        changed_frozen = sorted(p for p in before if after.get(p) != before[p] and p not in deleted)
        if changed_frozen:
            raise SystemExit(f"stage {number}: frozen files changed: {changed_frozen[:5]}")
        entry["frozen_files_unchanged"] = len(before)
        zero = [
            s["rule"]
            for s in entry["subs"]
            if s["count"] == 0 and not s["rule"].startswith("path ")
        ]
        entry["rules_that_matched_nothing"] = zero
        entry["dangling_paths"] = len(dangling_here)
        all_dangling += [f"{number}\t{d}" for d in dangling_here]
        if cfg.get("commit") and git(repo, "status", "--porcelain").strip():
            git(repo, "add", "-A")
            lines = [
                name,
                "",
                f"{entry['moves']} moves, {entry['files_rewritten']} files rewritten.",
            ]
            lines += [f"- {s['rule']}: {s['count']}" for s in entry["subs"] if s["count"]]
            if cfg.get("trailer"):
                lines += ["", cfg["trailer"]]
            env = {k: str(v) for k, v in cfg.get("commit_env", {}).items()}
            git(repo, "commit", "-q", "-m", "\n".join(lines), env=env)
            entry["commit"] = git(repo, "rev-parse", "HEAD").strip()
        report.append(entry)
        print(
            f"stage {number} {name}: {entry['moves']} moves, "
            f"{entry['files_rewritten']} files rewritten, {len(before)} frozen files unchanged"
            + (f", commit {entry['commit'][:10]}" if "commit" in entry else "")
        )
        for s in entry["subs"]:
            if not s["rule"].startswith("path ") or s["count"]:
                print(f"   {s['count']:6d}  {s['rule']}")
        if zero:
            print(f"   matched nothing: {zero}")
        if dangling_here:  # a warning: prose may cite old paths; code built from parts may not
            print(f"   {len(dangling_here)} path string(s) no longer resolve (dangling-paths.tsv):")
            for d in dangling_here[:8]:
                print(f"     {d.replace(chr(9), ': ')}")
    (out_dir / "dangling-paths.tsv").write_text(
        "".join(f"{d}\n" for d in all_dangling), encoding="utf-8"
    )
    moved = sorted((o, c) for c, o in origin.items() if o != c)
    (out_dir / "moved-paths.tsv").write_text(
        "".join(f"{o}\t{c}\n" for o, c in moved), encoding="utf-8"
    )
    (out_dir / "rewritten.tsv").write_text(
        "".join(
            f"{p}\trewritten by staged_rename: {'; '.join(st)}\n"
            for p, st in sorted(rewritten.items())
        ),
        encoding="utf-8",
    )
    (out_dir / "rename-report.json").write_text(
        json.dumps({"start_commit": start, "stages": report, "deleted": sorted(deleted)}, indent=1)
        + "\n",
        encoding="utf-8",
    )
    write_run_record(
        job,
        out_dir,
        "staged_rename",
        {"map": str(map_path)},
        {
            "stages": len(report),
            "moved": len(moved),
            "rewritten": len(rewritten),
            "deleted": len(deleted),
        },
    )
    print(
        f"{len(moved)} paths moved, {len(rewritten)} files rewritten, {len(deleted)} deleted; "
        f"outputs in {out_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
