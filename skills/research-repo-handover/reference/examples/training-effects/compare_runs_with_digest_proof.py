"""Compare two run directories of the same configuration, one per checkout, after normalisation.

Usage:
    <venv>/bin/python compare_runs.py RUN_A RUN_B --root-a PATH --root-b PATH --sha SHA_A --sha SHA_B

Every file under each run directory is compared: `.eval` logs are read with inspect_ai (attachments
resolved) and dumped to JSON, JSON/YAML files are parsed, anything else is compared as text.
Values that legitimately differ between two executions are replaced before comparing, by these
rules and nothing else:

- PATH rules (by JSON path, a regex over `/key/key[i]/...`): Inspect's per-execution ids and
  timings, the git `revision` of the eval, and JSON-patch `changes` inside store/state events
  (their shape follows the volatile values they patch; the final store and every message, tool
  call and file event are still compared);
- TEXT rules (inside any string): the two checkouts' roots, the two harness SHAs (full, and any
  prefix of 7+ characters), TMPDIR build roots `pp-e5-*`, ISO-8601 timestamps, Inspect's 22-char
  ids (and their lowercased HTML-anchor form), UUID4s, `ls -l` times;
- DERIVED digests: a hypotheses artifact digest is mapped from B to A only after proving that B's
  artifact, with B's harness SHA swapped for A's, has exactly A's canonical digest.

Each rule's substitution count is printed for A and B; for every structural rule a count that
differs between the two is itself a difference. A run directory with more than one `.eval` log is
refused. Exit 1 on any difference. Reads only.
"""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml

PATH_RULES: list[tuple[str, re.Pattern[str]]] = [
    (name, re.compile(rx))
    for name, rx in [
        ("eval ids", r"^/eval/(eval_id|run_id|task_id|created)$"),
        ("eval git revision", r"^/eval/revision$"),
        ("stats timings", r"^/stats/(started_at|completed_at)$"),
        ("sample uuid", r"^/samples\[\d+\]/uuid$"),
        ("sample timings", r"^/samples\[\d+\]/(started_at|completed_at|total_time|working_time)$"),
        ("event ids", r"/events\[\d+\]/(uuid|span_id|parent_id|id)$"),
        (
            "event timings",
            r"/events\[\d+\]/(timestamp|working_start|working_time|completed|pending)$",
        ),
        ("model-call timings", r"/events\[\d+\]/(call|output)/(time|duration|working_time)$"),
        ("message ids", r"/(messages|input|choices)\[\d+\](/message)?/id$"),
        ("message created", r"/(message|messages\[\d+\]|input\[\d+\])/created$"),
        ("output time", r"/output/time$"),
        ("store patch deltas", r"/events\[\d+\]/changes$"),
        ("slot submit time", r"/submitted_at$"),
        ("log location", r"^/location$"),
    ]
]
TS = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}[:-]\d{2}[:-]\d{2}(?:[.,]\d+)?(?:[+-]\d{2}[:-]?\d{2}|Z)?"
)
BUILD = re.compile(r"pp-e5-[A-Za-z0-9_]+")
SHORTUUID = re.compile(r"(?<![A-Za-z0-9])[2-9A-HJ-NP-Za-km-z]{22}(?![A-Za-z0-9])")
LOWER_ID = re.compile(
    r"(?<![a-z0-9])[a-z0-9]{22}(?=-mockllm-|-anthropic-|-openai-|-openrouter-|-google-)"
)
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
LSTIME = re.compile(
    r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +\d{1,2} +\d{2}:\d{2}\b"
)
UNCOUNTED = ("checkout root", "harness SHA", "proven derived digest")


class Normaliser:
    def __init__(self, roots: list[str], shas: list[str], digests: list[tuple[str, str]]) -> None:
        self.text_rules: list[tuple[str, re.Pattern[str], str]] = []
        for root in roots:
            self.text_rules.append(("checkout root", re.compile(re.escape(root)), "<ROOT>"))
        for sha in shas:
            rx = re.compile(rf"(?<![0-9a-f]){sha[:7]}[0-9a-f]{{0,33}}(?![0-9a-f])")
            self.text_rules.append(("harness SHA", rx, "<SHA>"))
        for old, new in digests:
            self.text_rules.append(("proven derived digest", re.compile(old), new))
        self.text_rules += [
            ("build root", BUILD, "<BUILD>"),
            ("uuid4", UUID, "<UUID>"),
            ("ls time", LSTIME, "<LSTIME>"),
            ("timestamp", TS, "<TS>"),
            ("inspect id (anchor)", LOWER_ID, "<ID>"),
            ("inspect id", SHORTUUID, "<ID>"),
        ]
        self.counts: collections.Counter[str] = collections.Counter()

    def string(self, s: str) -> str:
        for name, rx, rep in self.text_rules:
            s, n = rx.subn(rep, s)
            self.counts[name] += n
        return s

    def value(self, o: object, path: str = "") -> object:
        for name, rx in PATH_RULES:
            if rx.search(path):
                self.counts[name] += 1
                return f"<{name}>"
        # A digest proven to be sha256 of its sibling text (which is compared) is derived.
        if (
            isinstance(o, dict)
            and isinstance(o.get("text"), str)
            and "sha256" in o
            and hashlib.sha256(o["text"].encode("utf-8")).hexdigest() == o["sha256"]
        ):
            self.counts["digest of compared text"] += 1
            o = {**o, "sha256": "<sha256 of text, verified>"}
        if isinstance(o, dict):
            return {
                (self.string(k) if isinstance(k, str) else k): self.value(v, f"{path}/{k}")
                for k, v in o.items()
            }
        if isinstance(o, list):
            return [self.value(v, f"{path}[{i}]") for i, v in enumerate(o)]
        if isinstance(o, str):
            return self.string(o)
        return o


def load(path: Path) -> object:
    if path.suffix == ".eval":
        from inspect_ai.log import read_eval_log

        log = read_eval_log(str(path), resolve_attachments=True)
        return json.loads(log.model_dump_json())
    if path.suffix == ".json":
        return json.loads(path.read_text())
    if path.suffix in (".yaml", ".yml"):
        return yaml.safe_load(path.read_text())
    return path.read_text(errors="replace")


def diff(a: object, b: object, path: str, out: list[str], cap: int) -> None:
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


def files(run: Path) -> dict[str, Path]:
    logs = sorted(run.glob("*.eval"))
    if len(logs) > 1:
        raise SystemExit(f"{run}: {len(logs)} .eval logs; compare one execution at a time")
    found: dict[str, Path] = {}
    for p in sorted(run.rglob("*")):
        if p.is_file():
            top_log = p.suffix == ".eval" and p.parent == run
            found["<log>.eval" if top_log else str(p.relative_to(run))] = p
    return found


def canon(obj: object) -> str:
    """benchmark/phase2_hypotheses/submission.py:artifact_sha256, restated."""
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def derived_digests(
    a: Path, b: Path, sha_a: str, sha_b: str
) -> tuple[list[str], list[tuple[str, str]]]:
    problems: list[str] = []
    pairs: list[tuple[str, str]] = []
    for art_a in sorted((a / "hypotheses").glob("*.epoch*.json")):
        art_b = b / "hypotheses" / art_a.name
        if not art_b.is_file():
            problems.append(f"DIGEST {art_a.name}: missing in B")
            continue
        obj_a, obj_b = json.loads(art_a.read_text()), json.loads(art_b.read_text())
        swapped = json.loads(json.dumps(obj_b).replace(sha_b, sha_a))
        if canon(swapped) != canon(obj_a):
            problems.append(f"DIGEST {art_a.name}: differs beyond the harness SHA")
        else:
            pairs.append((canon(obj_b), canon(obj_a)))
    return problems, pairs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a", type=Path)
    ap.add_argument("b", type=Path)
    ap.add_argument("--root-a", action="append", default=[])
    ap.add_argument("--root-b", action="append", default=[])
    ap.add_argument("--sha", action="append", default=[], help="harness SHA of A, then of B")
    ap.add_argument("--cap", type=int, default=200)
    args = ap.parse_args()
    if len(args.sha) != 2:
        raise SystemExit("give --sha A --sha B")
    sha_a, sha_b = args.sha
    problems, pairs = derived_digests(args.a, args.b, sha_a, sha_b)
    print(f"derived-digest proof: {len(pairs)} artifact digest(s) proven, {len(problems)} refused")
    norm_a = Normaliser(args.root_a, [sha_a], [])
    norm_b = Normaliser(args.root_b, [sha_b], pairs)
    fa, fb = files(args.a), files(args.b)
    for k in sorted(set(fa) | set(fb)):
        if k not in fa or k not in fb:
            problems.append(f"FILE {k}: only in {'B' if k not in fa else 'A'}")
            continue
        out: list[str] = []
        diff(norm_a.value(load(fa[k])), norm_b.value(load(fb[k])), k, out, args.cap)
        problems.extend(out)
        print(f"{'OK  ' if not out else 'DIFF'} {k}" + (f" ({len(out)} paths)" if out else ""))
    print("substitutions per rule (A / B):")
    for rule in sorted(set(norm_a.counts) | set(norm_b.counts)):
        ca, cb = norm_a.counts[rule], norm_b.counts[rule]
        differs = ca != cb and rule not in UNCOUNTED
        print(f"  {rule:24s} {ca:7d} / {cb:7d}{'   <-- differs' if differs else ''}")
        if differs:
            problems.append(f"RULE {rule}: {ca} substitutions in A, {cb} in B")
    for p in problems[: args.cap]:
        print("  ", p)
    print(f"{len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
