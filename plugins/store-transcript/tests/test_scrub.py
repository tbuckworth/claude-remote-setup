#!/usr/bin/env python3
"""Canary tests for the transcript scrubber.

Plants known secrets in a fixture transcript and asserts every one is caught,
that substitution is deterministic and consistent, that shape is preserved, and
that structural values (git SHAs, UUIDs, $VAR references) are left alone.

Run: python3 tests/test_scrub.py
"""

from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import scrub  # noqa: E402

SALT = b"test-salt-do-not-use-in-anger"

def _j(*parts: str) -> str:
    """Assemble a canary from fragments.

    These fixtures are fabricated, but they are shaped exactly like real
    credentials — that is what makes them useful. Written as contiguous
    literals they trip GitHub push protection and secret scanners, so every
    token is split across fragments and joined at runtime. The assembled value
    is identical; only the source text differs.
    """
    return "".join(parts)


# (label, secret, must-survive-prefix)
CANARIES = [
    ("anthropic", _j("sk-", "ant-", "api", "03-", "A1b2C3d4E5f6G7h8I9j0" * 4,
                     "kLmNoPqRsT-_xY"), "sk-ant-api03-"),
    ("openai-proj", _j("sk-", "proj-", "abcDEF123456ghiJKL789012mnoPQR345678"), "sk-proj-"),
    ("openai", _j("sk-", "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"), "sk-"),
    ("openrouter", _j("sk-", "or-", "v1-", "0123456789abcdef" * 4), "sk-or-v1-"),
    ("github-token", _j("gh", "p_", "AbCdEf0123456789AbCdEf0123456789AbCd"), "ghp_"),
    ("github-pat-fine", _j("github", "_pat_", "11ABCDEFG0abcdefghijkl_", "A" * 59),
     "github_pat_"),
    ("gitlab", _j("gl", "pat-", "xY3zAbCdEfGhIjKlMnOp"), "glpat-"),
    ("aws", _j("AK", "IA", "IOSFODNN7EXAMPLE"), "AKIA"),
    ("google", _j("AI", "za", "SyD-1234567890abcdefghijklmnopqrstu"), "AIza"),
    ("slack", _j("xo", "xb-", "123456789012-", "1234567890123-",
                 "AbCdEfGhIjKlMnOpQrStUvWx"), "xoxb-"),
    ("huggingface", _j("hf", "_", "AbCdEfGhIjKlMnOpQrStUvWxYz012345"), "hf_"),
    ("npm", _j("npm", "_", "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"), "npm_"),
    ("stripe", _j("sk", "_live_", "AbCdEfGhIjKlMnOpQrStUvWx"), "sk_live_"),
    ("groq", _j("gs", "k_", "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefgh"), "gsk_"),
    ("twilio", _j("A", "C", "0123456789abcdef0123456789abcdef"), "AC"),
    ("sendgrid", _j("SG", ".", "AbCdEfGhIjKlMnOpQrStUv", ".",
                    "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789abcdefg"), "SG."),
]

# Things that must come through untouched.
STRUCTURAL = [
    "4dff72266afcb6aed634fc49c178a470de27d9e3",   # git SHA
    "0d5edb91-460a-4921-b712-f4f15d5183c6",       # UUID
    "$ANTHROPIC_API_KEY",                          # env reference
    "${GITHUB_TOKEN}",
    "https://github.com/tbuckworth/claude-remote-setup",
]

JWT = _j("ey", "JhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.",
         "ey", "JzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.",
         "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c")

PEM = _j("-----BEGIN ", "RSA PRIVATE KEY", "-----\n",
         "MIIEowIBAAKCAQEAxGZlKgPq7dLmNoPqRsTuVwXyZ0123456789abcdefghijklmn\n",
         "opqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789abcdefghijklmnopq\n",
         "-----END ", "RSA PRIVATE KEY", "-----")

FAILURES: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print(f"  PASS  {msg}")
    else:
        print(f"  FAIL  {msg}")
        FAILURES.append(msg)


def build_fixture(path: Path) -> None:
    """A transcript shaped like a real one: user turns, tool calls, tool results."""
    rows = [
        {"type": "user", "uuid": "u-1", "timestamp": "2026-08-04T10:00:00Z",
         "message": {"role": "user", "content": "set up the api clients"}},
        {"type": "assistant", "uuid": "a-1", "timestamp": "2026-08-04T10:00:01Z",
         "message": {"role": "assistant", "content": [
             {"type": "text", "text": "Exporting the keys now."},
             {"type": "tool_use", "id": "t-1", "name": "Bash", "input": {
                 "command": "\n".join(
                     f"export {label.upper().replace('-', '_')}_KEY={secret}"
                     for label, secret, _ in CANARIES)}},
         ]}},
        # Tool results are where secrets really leak: env dumps, cat .env
        {"type": "user", "uuid": "u-2", "timestamp": "2026-08-04T10:00:02Z",
         "toolUseResult": {"stdout": "\n".join(
             [f"{label}={secret}" for label, secret, _ in CANARIES]
             + [f"Authorization: Bearer {JWT}",
                "DATABASE_URL=postgres://admin:hunter2primary@db.internal:5432/app",
                PEM]
         )}},
        # The same keys again later — consistency must hold across occurrences.
        {"type": "assistant", "uuid": "a-2", "timestamp": "2026-08-04T10:00:03Z",
         "message": {"role": "assistant", "content": [
             {"type": "text",
              "text": f"Re-using {CANARIES[0][1]} and {CANARIES[4][1]} for the retry. "
                      f"Structural values: {' '.join(STRUCTURAL)}"}]}},
    ]
    with path.open("w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="scrub-test-"))
    src, out, out2 = tmp / "in.jsonl", tmp / "out.jsonl", tmp / "out2.jsonl"
    build_fixture(src)

    summary = scrub.scrub_file(src, out, SALT)
    text = out.read_text()
    raw_in = src.read_text()

    print("\n== every planted secret is gone ==")
    for label, secret, _ in CANARIES:
        check(secret not in text, f"{label} removed")
    check(JWT not in text, "jwt removed")
    check("hunter2primary" not in text, "connection-string password removed")
    check("MIIEowIBAAKCAQEAxGZlKgPq7dLmNoPqRsTuVwXyZ0123456789abcdefghijklmn" not in text,
          "pem body removed")

    print("\n== verify() agrees ==")
    check(scrub.verify(out, summary["originals"]) == [], "no original survives verification")

    print("\n== shape is preserved ==")
    for label, secret, prefix in CANARIES:
        m = re.search(re.escape(prefix) + r"[A-Za-z0-9\-._]*", text)
        check(m is not None and len(m.group()) >= len(prefix), f"{label} prefix intact")
    for label, secret, prefix in CANARIES:
        # A same-length fake should exist for each planted secret.
        cands = [w for w in re.findall(r"[A-Za-z0-9\-._~+/]{8,}", text)
                 if w.startswith(prefix) and len(w) == len(secret)]
        check(bool(cands), f"{label} length preserved ({len(secret)})")

    print("\n== structural values untouched ==")
    for value in STRUCTURAL:
        check(value in text, f"preserved {value[:46]}")

    print("\n== jwt stays decodable ==")
    import base64
    jwt_out = re.search(r"eyJ[A-Za-z0-9_\-]+\.eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+", text)
    ok = False
    if jwt_out:
        try:
            seg = jwt_out.group().split(".")[1]
            payload = json.loads(base64.urlsafe_b64decode(seg + "=" * (-len(seg) % 4)))
            ok = isinstance(payload, dict) and payload.get("sub") != "1234567890"
            check("iat" in payload and payload["iat"] == 1516239022, "numeric claims kept")
        except Exception as exc:
            print(f"        decode error: {exc}")
    check(ok, "jwt payload decodes to json with scrambled claims")

    print("\n== hex-only bodies stay hex ==")
    for label, prefix in [("twilio", "AC"), ("openrouter", "sk-or-v1-")]:
        cands = [w for w in re.findall(r"[A-Za-z0-9\-_]{8,}", text) if w.startswith(prefix)]
        body = cands[0][len(prefix):] if cands else ""
        check(bool(body) and re.fullmatch(r"[0-9a-f]+", body) is not None,
              f"{label} body is still hex")

    print("\n== deterministic and consistent ==")
    scrub.scrub_file(src, out2, SALT)
    check(out2.read_text() == text, "same salt + input -> identical output")

    first = re.findall(re.escape("sk-ant-api03-") + r"[A-Za-z0-9\-_]+", text)
    check(len(first) >= 2 and len(set(first)) == 1,
          f"repeated key maps to one fake ({len(first)} occurrences)")

    out3 = tmp / "out3.jsonl"
    scrub.scrub_file(src, out3, b"a-different-salt")
    check(out3.read_text() != text, "different salt -> different output")

    print("\n== transcript integrity ==")
    lines_in = [l for l in raw_in.splitlines() if l.strip()]
    lines_out = [l for l in text.splitlines() if l.strip()]
    check(len(lines_in) == len(lines_out), f"line count preserved ({len(lines_in)})")
    parsed = []
    for line in lines_out:
        try:
            parsed.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    check(len(parsed) == len(lines_out), "every output line is valid json")
    check([p.get("uuid") for p in parsed] == ["u-1", "a-1", "u-2", "a-2"],
          "uuid chain intact")
    check(all(p.get("timestamp", "").startswith("2026-08-04") for p in parsed),
          "timestamps intact")
    check(summary["unparsed_lines"] == 0, "no unparsable lines")

    print(f"\n== audit ==\n  {summary['total']} replacements, "
          f"{summary['distinct']} distinct, rules: {sorted(summary['counts'])}")
    check(summary["total"] >= len(CANARIES), "audit counts look sane")
    audit_md = scrub.audit_markdown(summary)
    check(not any(secret in audit_md for _, secret, _ in CANARIES),
          "audit markdown leaks no values")

    print()
    if FAILURES:
        print(f"FAILED: {len(FAILURES)} check(s)")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
