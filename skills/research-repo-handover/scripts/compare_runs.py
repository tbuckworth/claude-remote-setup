"""Compare two output directories (two runs, or two staged sandboxes) after explicit normalisation.

usage: python3 compare_runs.py JOB.toml     (reads [compare]; exit 1 on any difference)

Compares every file under `a` and `b`. Files matching `byte_identical` must be byte for byte the
same (what an agent sees). Others are parsed (.json, .jsonl, .yaml/.yml when PyYAML is present,
.eval Inspect logs) or read as text, normalised by the declared rules and nothing else, then
compared value by value. Each rule's substitution count is printed for A and B; a counted rule
whose counts differ is itself a difference (the normalisation must hit both sides alike).

[compare] keys:
  a, b             the two directories
  roots_a, roots_b checkout roots that appear in paths (uncounted rule "checkout root")
  shas_a, shas_b   harness commits, matched as any 7+ character prefix (uncounted "harness SHA")
  rules            optional TOML files holding `path_rules` and `text_rules` (the Inspect set
                   lives in reference/examples/inspect-rules.toml)
  path_rules       [[name, regex], ...]: a value whose JSON path (/key/key[i]/...) matches is
                   replaced by <name> (per-execution ids, timings)
  text_rules       [[name, regex, replacement], ...]: applied inside every string, in order;
                   the job's own rules run before those from `rules` files, so a rule for a
                   whole repo-specific path (a temp build dir) wins over the generic id rules
  rename_a         [[old, new], ...] literal renames applied to A's strings and dict keys first
                   (for comparing across a rename: store keys, model ids); uncounted
  key_map          optional TSV `old<TAB>new` of renamed dict keys on side A
  uncounted        extra rule names whose counts may differ between A and B
  verify_text_digests  true: a {"text", "sha256"} pair whose digest is the text's own is derived
  byte_identical   globs (relative to a/b) that must match byte for byte
  ignore           globs left out of the comparison
  cap              most differences listed (default 200)
`.eval` logs are read with inspect_ai (attachments resolved) when the interpreter has it, which
is why this runs with the checkout's own Python; otherwise with zipfile, which handles deflate
but not the zstd that recent Inspect writes.
"""

from __future__ import annotations

import collections
import hashlib
import json
import re
import sys
import tomllib
import zipfile
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from handover_common import job_from_argv, matches, read_tsv, require, walk_files, write_run_record  # noqa: E402

BUILTIN_UNCOUNTED = {"checkout root", "harness SHA", "rename"}


class Normaliser:
    def __init__(
        self,
        roots: list[str],
        shas: list[str],
        path_rules: list[tuple[str, re.Pattern[str]]],
        text_rules: list[tuple[str, re.Pattern[str], str]],
        renames: list[tuple[str, str]],
        key_map: dict[str, str],
        verify_digests: bool,
    ) -> None:
        self.rules: list[tuple[str, re.Pattern[str], str]] = []
        for old, new in renames:
            self.rules.append(("rename", re.compile(re.escape(old)), new.replace("\\", "\\\\")))
        for root in sorted(roots, key=len, reverse=True):
            self.rules.append(("checkout root", re.compile(re.escape(root)), "<ROOT>"))
        for sha in shas:
            rx = re.compile(rf"(?<![0-9a-f]){sha[:7]}[0-9a-f]{{0,33}}(?![0-9a-f])")
            self.rules.append(("harness SHA", rx, "<SHA>"))
        self.rules += text_rules
        self.path_rules = path_rules
        self.key_map = key_map
        self.verify = verify_digests
        self.counts: collections.Counter[str] = collections.Counter()

    def string(self, s: str) -> str:
        for name, rx, rep in self.rules:
            s, n = rx.subn(rep, s)
            self.counts[name] += n
        return s

    def value(self, o: Any, path: str = "") -> Any:
        for name, rx in self.path_rules:
            if rx.search(path):
                self.counts[name] += 1
                return f"<{name}>"
        if (
            self.verify
            and isinstance(o, dict)
            and isinstance(o.get("text"), str)
            and isinstance(o.get("sha256"), str)
            and hashlib.sha256(o["text"].encode("utf-8")).hexdigest() == o["sha256"]
        ):
            self.counts["digest of compared text"] += 1
            o = {**o, "sha256": "<sha256 of text, verified>"}
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                key = self.key_map.get(k, k) if isinstance(k, str) else k
                key = self.string(key) if isinstance(key, str) else key
                out[key] = self.value(v, f"{path}/{k}")
            return out
        if isinstance(o, list):
            return [self.value(v, f"{path}[{i}]") for i, v in enumerate(o)]
        if isinstance(o, str):
            return self.string(o)
        return o


def resolve_attachments(o: Any, attachments: dict[str, Any]) -> Any:
    if isinstance(o, str) and o.startswith("attachment://"):
        return attachments.get(o[len("attachment://") :], o)
    if isinstance(o, dict):
        return {k: resolve_attachments(v, attachments) for k, v in o.items() if k != "attachments"}
    if isinstance(o, list):
        return [resolve_attachments(v, attachments) for v in o]
    return o


def load_eval(path: Path) -> Any:
    try:
        from inspect_ai.log import read_eval_log  # type: ignore[import-not-found]
    except ImportError:
        read_eval_log = None
    if read_eval_log is not None:
        log = read_eval_log(str(path), resolve_attachments=True)
        return json.loads(log.model_dump_json())
    with zipfile.ZipFile(path) as z:
        try:
            out = json.loads(z.read("header.json"))
            samples = []
            for name in sorted(n for n in z.namelist() if n.startswith("samples/")):
                s = json.loads(z.read(name))
                samples.append(resolve_attachments(s, s.get("attachments", {})))
            out["samples"] = sorted(samples, key=lambda s: (str(s.get("id")), s.get("epoch", 0)))
            if "reductions.json" in z.namelist():
                out["reductions"] = json.loads(z.read("reductions.json"))
        except NotImplementedError as err:
            raise SystemExit(f"{path}: {err}; run with an interpreter that has inspect_ai") from err
    return out


def load(path: Path) -> Any:
    suffix = path.suffix
    if suffix == ".eval":
        return load_eval(path)
    if suffix == ".json":
        return json.loads(path.read_text(encoding="utf-8"))
    if suffix == ".jsonl":
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if suffix in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore[import-untyped]

            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except ImportError:
            pass
    data = path.read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return {"binary_sha256": hashlib.sha256(data).hexdigest()}


def diff(a: Any, b: Any, path: str, out: list[str], cap: int) -> None:
    if len(out) >= cap:
        return
    if type(a) is not type(b):
        out.append(f"{path}: type {type(a).__name__} != {type(b).__name__}")
    elif isinstance(a, dict):
        for k in sorted(set(a) | set(b), key=str):
            if k not in a or k not in b:
                out.append(f"{path}/{k}: only in {'B' if k not in a else 'A'}")
            else:
                diff(a[k], b[k], f"{path}/{k}", out, cap)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(f"{path}: list length {len(a)} != {len(b)}")
        for i, (x, y) in enumerate(zip(a, b, strict=False)):
            diff(x, y, f"{path}[{i}]", out, cap)
    elif isinstance(a, float) and a != a and b != b:
        return  # NaN on both sides
    elif a != b:
        sa, sb = str(a), str(b)
        if "\n" in sa or "\n" in sb:
            la, lb = sa.splitlines(), sb.splitlines()
            i = next(
                (i for i, (x, y) in enumerate(zip(la, lb, strict=False)) if x != y),
                min(len(la), len(lb)),
            )
            left = la[i] if i < len(la) else "<EOF>"
            right = lb[i] if i < len(lb) else "<EOF>"
            out.append(f"{path}: line {i + 1}: {left[:200]!r} != {right[:200]!r}")
        else:
            out.append(f"{path}: {sa[:160]!r} != {sb[:160]!r}")


def main() -> int:
    job = job_from_argv(__doc__)
    cfg = job.section("compare")
    out_dir = job.out_dir(cfg)
    a, b = job.resolve(require(cfg, "a", "compare")), job.resolve(require(cfg, "b", "compare"))
    path_rules_raw: list[list[str]] = []
    text_rules_raw: list[list[str]] = []
    for rules_file in cfg.get("rules", []):
        data = tomllib.loads(job.resolve(rules_file).read_text(encoding="utf-8"))
        path_rules_raw += data.get("path_rules", [])
        text_rules_raw += data.get("text_rules", [])
    path_rules_raw += cfg.get("path_rules", [])
    text_rules_raw = list(cfg.get("text_rules", [])) + text_rules_raw  # the job's own rules first
    path_rules = [(n, re.compile(rx)) for n, rx in path_rules_raw]
    text_rules = [(n, re.compile(rx), rep) for n, rx, rep in text_rules_raw]
    key_map = (
        {r[0]: r[1] for r in read_tsv(job.resolve(cfg["key_map"]), 2)} if cfg.get("key_map") else {}
    )
    renames = [(o, n) for o, n in cfg.get("rename_a", [])]
    verify = bool(cfg.get("verify_text_digests", False))
    norm_a = Normaliser(
        cfg.get("roots_a", []),
        cfg.get("shas_a", []),
        path_rules,
        text_rules,
        renames,
        key_map,
        verify,
    )
    norm_b = Normaliser(
        cfg.get("roots_b", []), cfg.get("shas_b", []), path_rules, text_rules, [], {}, verify
    )
    ignore, exact = cfg.get("ignore", []), cfg.get("byte_identical", [])
    cap = int(cfg.get("cap", 200))
    fa = {p for p in walk_files(a, skip_dirs=()) if not matches(p, ignore)}
    fb = {p for p in walk_files(b, skip_dirs=()) if not matches(p, ignore)}
    # Inspect names a log after its time and id: pair the single top-level .eval on each side.
    eva, evb = (
        sorted(p for p in fa if p.endswith(".eval") and "/" not in p),
        sorted(p for p in fb if p.endswith(".eval") and "/" not in p),
    )
    pairs: dict[str, tuple[Path | None, Path | None]] = {}
    if len(eva) == 1 and len(evb) == 1:
        pairs["<log>.eval"] = (a / eva[0], b / evb[0])
        fa.discard(eva[0])
        fb.discard(evb[0])
    elif eva or evb:
        if len(eva) > 1 or len(evb) > 1:
            raise SystemExit(
                "more than one top-level .eval on a side: compare one execution at a time"
            )
    for p in sorted(fa | fb):
        pairs[p] = (a / p if p in fa else None, b / p if p in fb else None)
    problems: list[str] = []
    status = collections.Counter()
    for key, (pa, pb) in pairs.items():
        if pa is None or pb is None:
            problems.append(f"FILE {key}: only in {'B' if pa is None else 'A'}")
            status["only one side"] += 1
            continue
        if pa.read_bytes() == pb.read_bytes():
            status["byte-identical"] += 1
            continue
        if matches(key, exact):
            problems.append(f"FILE {key}: must be byte-identical and is not")
            status["different"] += 1
            continue
        found: list[str] = []
        diff(norm_a.value(load(pa)), norm_b.value(load(pb)), key, found, cap)
        problems += found
        status["different" if found else "equal after normalisation"] += 1
        print(f"{'DIFF' if found else 'OK  '} {key}" + (f" ({len(found)} paths)" if found else ""))
    uncounted = BUILTIN_UNCOUNTED | set(cfg.get("uncounted", []))
    rule_rows = []
    print("substitutions per rule (A / B):")
    for rule in sorted(set(norm_a.counts) | set(norm_b.counts)):
        ca, cb = norm_a.counts[rule], norm_b.counts[rule]
        differs = ca != cb and rule not in uncounted
        rule_rows.append({"rule": rule, "a": ca, "b": cb, "differs": differs})
        print(f"  {rule:28s} {ca:7d} / {cb:7d}{'   <-- differs' if differs else ''}")
        if differs:
            problems.append(f"RULE {rule}: {ca} substitutions in A, {cb} in B")
    summary = {
        "files": dict(status),
        "rules": rule_rows,
        "differences": problems[:cap],
        "n_differences": len(problems),
    }
    (out_dir / "compare.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
    write_run_record(
        job, out_dir, "compare_runs", {}, {"files": dict(status), "differences": len(problems)}
    )
    print("files: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    for p in problems[:cap]:
        print("  ", p)
    print(f"{len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
