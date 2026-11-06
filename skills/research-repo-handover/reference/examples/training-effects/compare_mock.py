"""Compare two scripted (mock) runs of the same task set from two checkouts, rename-aware.

Usage: python compare_mock.py OLD.eval NEW.eval [--key-map map.tsv]

What must be identical, byte for byte, with no normalisation beyond per-execution ids and times:
  1. every model call's input messages and output (agent, judges, monitor, screen): what each model
     saw and said;
  2. each sample's conversation (the agent's messages and the tool results it received);
  3. every numeric score value, per sample and score key (keys mapped through --key-map, a TSV of
     old<TAB>new names, applied to score-dict keys; rows for mockllm/ ids also rename the old
     side's model ids, in model fields and wherever the text quotes them).
Run with the checkouts' own Python (inspect_ai installed). Prints a summary and exits 1 on any
difference.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from inspect_ai.log import read_eval_log

UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
SHORT = re.compile(r"\b[0-9A-Za-z]{22}\b")
TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?([+-]\d{2}:?\d{2}|Z)?")
LSTIME = re.compile(r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) +\d{1,2} +\d{2}:\d{2}\b")
TMP = re.compile(r"/[^\s\"']*/(pp-e5|te-build|training-effects-build)-[a-z0-9_]+")


def norm(text: str) -> str:
    text = LSTIME.sub("<LSTIME>", text)
    return TMP.sub("<BUILD>", TS.sub("<TS>", SHORT.sub("<ID>", UUID.sub("<UUID>", text))))


def message_text(m: object) -> str:
    content = getattr(m, "content", "")
    if isinstance(content, list):
        parts = []
        for c in content:
            parts.append(getattr(c, "text", None) or getattr(c, "reasoning", None) or json.dumps(c.model_dump(exclude_none=True), sort_keys=True, default=str))
        content = "\n".join(str(p) for p in parts)
    calls = getattr(m, "tool_calls", None) or []
    call_txt = "".join(f"\n[call {c.function} {json.dumps(c.arguments, sort_keys=True)}]" for c in calls)
    return f"{getattr(m, 'role', '?')}: {content}{call_txt}"


def model_calls(sample, model_map: dict[str, str] | None = None) -> list[str]:
    """Each call as text; ``model_map`` renames the old side's model ids (old<TAB>new rows too)."""
    model_map = model_map or {}
    out = []
    for ev in sample.events or []:
        if getattr(ev, "event", "") == "model":
            inp = "\n".join(message_text(m) for m in ev.input)
            outp = ev.output.completion if ev.output else ""
            out.append(f"MODEL {model_map.get(ev.model, ev.model)}\n--- input\n{inp}\n--- output\n{outp}")
    return out


def numbers(value: object, key_map: dict[str, str], prefix: str = "") -> dict[str, float]:
    found: dict[str, float] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            found.update(numbers(v, key_map, f"{prefix}{key_map.get(k, k)}/"))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        found[prefix.rstrip("/")] = float(value)
    return found


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--key-map", type=Path)
    args = ap.parse_args()
    key_map = {}
    if args.key_map:
        for line in args.key_map.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                a, b = line.split("\t")
                key_map[a] = b
    old = read_eval_log(args.old, resolve_attachments=True)
    new = read_eval_log(args.new, resolve_attachments=True)
    by_id = lambda log: {(s.id, s.epoch): s for s in log.samples or []}  # noqa: E731
    a, b = by_id(old), by_id(new)
    problems: list[str] = []
    if set(a) != set(b):
        problems.append(f"sample sets differ: {sorted(set(a) ^ set(b))}")
    n_calls = n_msgs = n_scores = 0
    for key in sorted(set(a) & set(b)):
        sa, sb = a[key], b[key]
        ids = sorted(((k, v) for k, v in key_map.items() if k.startswith("mockllm/")), key=lambda kv: -len(kv[0]))

        def renamed(text: str) -> str:  # the old side's mock model ids, wherever they are quoted
            for k, v in ids:
                text = text.replace(k, v)
            return text

        ca, cb = [renamed(norm(x)) for x in model_calls(sa, key_map)], [norm(x) for x in model_calls(sb)]
        n_calls += len(ca)
        if len(ca) != len(cb):
            problems.append(f"{key}: {len(ca)} vs {len(cb)} model calls")
        for i, (x, y) in enumerate(zip(ca, cb, strict=False)):
            if x != y:
                # model ids may carry the renamed mock prefix; report the first differing line
                xl, yl = x.splitlines(), y.splitlines()
                j = next((j for j, (p, q) in enumerate(zip(xl, yl, strict=False)) if p != q), min(len(xl), len(yl)))
                problems.append(f"{key}: model call {i} differs at line {j}: {xl[j][:160] if j < len(xl) else '<end>'!r} vs {yl[j][:160] if j < len(yl) else '<end>'!r}")
        ma, mb = [renamed(norm(message_text(m))) for m in sa.messages], [norm(message_text(m)) for m in sb.messages]
        n_msgs += len(ma)
        if ma != mb:
            j = next((j for j, (p, q) in enumerate(zip(ma, mb, strict=False)) if p != q), min(len(ma), len(mb)))
            problems.append(f"{key}: conversation differs at message {j}: {ma[j][:200] if j < len(ma) else '<end>'!r} vs {mb[j][:200] if j < len(mb) else '<end>'!r}")
        na = {}
        for name, sc in (sa.scores or {}).items():
            na.update(numbers(sc.value, key_map, f"{key_map.get(name, name)}/"))
        nb = {}
        for name, sc in (sb.scores or {}).items():
            nb.update(numbers(sc.value, key_map, f"{name}/"))
        n_scores += len(na)
        if set(na) != set(nb):
            problems.append(f"{key}: score keys differ: old-only {sorted(set(na) - set(nb))[:8]}, new-only {sorted(set(nb) - set(na))[:8]}")
        for k in sorted(set(na) & set(nb)):
            x, y = na[k], nb[k]
            if not (x == y or (math.isnan(x) and math.isnan(y))):
                problems.append(f"{key}: score {k}: {x} vs {y}")
    print(f"{len(a)} sample(s), {n_calls} model call(s), {n_msgs} message(s), {n_scores} score value(s) compared")
    for p in problems[:40]:
        print("  DIFF", p)
    print(f"{len(problems)} difference(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
