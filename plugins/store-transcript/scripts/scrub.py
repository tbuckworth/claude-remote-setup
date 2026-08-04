#!/usr/bin/env python3
"""Deterministic, format-preserving scrubbing of secrets in session transcripts.

Secrets are not redacted; they are *scrambled* into same-shaped fakes, so the
transcript still reads as a real session to a model. Two properties matter:

* Deterministic — the same secret always maps to the same fake, via keyed HMAC,
  so a key exported on turn 3 and used on turn 40 stays consistent.
* Format-preserving — prefix, length and per-character class are retained, so
  `sk-ant-api03-...` stays a plausible Anthropic key.

The HMAC salt lives outside the archive repo (see `salt_path`). It is one-way:
there is no reverse mapping, and none is stored.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import string
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

SALT_ENV = "STORE_TRANSCRIPT_SALT_FILE"
DEFAULT_SALT = Path.home() / ".config" / "store-transcript" / "salt"

B62 = string.digits + string.ascii_lowercase + string.ascii_uppercase


# --- rules ----------------------------------------------------------------
#
# `prefix` is kept verbatim; only the remainder is scrambled. Rules whose
# pattern has a group named `secret` scramble just that group, which is how
# assignment-style matches keep their variable name.


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern
    prefix: str = ""
    handler: str = "shape"
    prefix_re: str = ""
    gated: bool = False

    @property
    def generic(self) -> bool:
        """Context-based rules (assignment, conn string, auth header).

        These are the false-positive-prone ones, so only they are allowlisted.
        A vendor-prefixed match is high confidence and must never be skipped.
        """
        return self.handler == "group"

    def keep(self, value: str) -> str:
        """The literal prefix to carry through untouched."""
        if self.prefix_re:
            m = re.match(self.prefix_re, value)
            return m.group(0) if m else ""
        return self.prefix


def _r(name, pattern, prefix="", handler="shape", flags=0, prefix_re="", gated=False):
    return Rule(name, re.compile(pattern, flags), prefix, handler, prefix_re, gated)


RULES: list[Rule] = [
    # --- vendor API keys with distinctive prefixes -------------------------
    _r("anthropic", r"sk-ant-(?:api|admin)\d{2}-[A-Za-z0-9\-_]{80,120}",
       prefix_re=r"sk-ant-(?:api|admin)\d{2}-"),
    _r("openai-proj", r"sk-proj-[A-Za-z0-9\-_]{20,200}", "sk-proj-"),
    _r("openai", r"sk-[A-Za-z0-9]{32,64}\b", "sk-"),
    _r("openrouter", r"sk-or-v1-[a-f0-9]{64}", "sk-or-v1-"),
    _r("github-pat-fine", r"github_pat_[A-Za-z0-9_]{60,90}", "github_pat_"),
    _r("github-token", r"gh[pousr]_[A-Za-z0-9]{36,}", "", handler="github"),
    _r("gitlab", r"glpat-[A-Za-z0-9\-_]{20,}", "glpat-"),
    _r("aws-access-key", r"\b(?:AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA)[A-Z0-9]{16}\b",
       prefix_re=r"AKIA|ASIA|AGPA|AIDA|AROA|AIPA|ANPA|ANVA"),
    _r("google-api", r"AIza[0-9A-Za-z\-_]{35}", "AIza"),
    _r("slack-token", r"xox[baprse]-[A-Za-z0-9\-]{10,}", "", handler="slack"),
    _r("slack-webhook", r"https://hooks\.slack\.com/services/[A-Za-z0-9/]{20,}",
       "https://hooks.slack.com/services/"),
    _r("huggingface", r"\bhf_[A-Za-z0-9]{30,40}\b", "hf_"),
    _r("npm", r"\bnpm_[A-Za-z0-9]{36}\b", "npm_"),
    _r("stripe", r"\b[sprk]k_(?:live|test)_[A-Za-z0-9]{20,}", "", handler="stripe"),
    _r("sendgrid", r"SG\.[A-Za-z0-9_\-]{20,26}\.[A-Za-z0-9_\-]{40,46}", "SG."),
    _r("groq", r"\bgsk_[A-Za-z0-9]{40,60}\b", "gsk_"),
    _r("twilio", r"\b(?:AC|SK)[a-f0-9]{32}\b", prefix_re=r"AC|SK"),
    _r("linear", r"\blin_api_[A-Za-z0-9]{40,}", "lin_api_"),
    _r("figma", r"\bfigd_[A-Za-z0-9\-_]{40,}", "figd_"),
    _r("doppler", r"\bdp\.pt\.[A-Za-z0-9]{40,}", "dp.pt."),
    _r("postman", r"\bPMAK-[A-Za-z0-9]{24}-[A-Za-z0-9]{34}", "PMAK-"),
    _r("databricks", r"\bdapi[a-f0-9]{32}\b", "dapi"),

    # --- structured credentials -------------------------------------------
    _r("jwt", r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",
       "", handler="jwt"),
    _r("private-key-block",
       r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
       "", handler="pem", flags=re.DOTALL),
    _r("conn-string",
       r"(?P<scheme>[a-z][a-z0-9+.\-]*://[^\s:/@]+:)(?P<secret>[^\s@/]{4,})(?P<host>@)",
       "", handler="group"),
    _r("authorization-header",
       r"(?P<scheme>[Aa]uthorization\s*[:=]\s*['\"]?(?:[Bb]earer|[Tt]oken)\s+)"
       r"(?P<secret>[A-Za-z0-9\-._~+/]{16,})",
       "", handler="group"),

    # --- assignment style: FOO_API_KEY=..., "password": "..." --------------
    # The (?![a-z]) guard stops the keyword matching mid-word: without it
    # TOKEN matches inside `tokenizer=` and AUTH inside `author=`.
    _r("assignment",
       r"(?P<scheme>\b[A-Za-z0-9_\-]*"
       r"(?:API[_\-]?KEY|APIKEY|SECRET|TOKEN|PASSWORD|PASSWD|CREDENTIALS?|"
       r"PRIVATE[_\-]?KEY|ACCESS[_\-]?KEY|AUTH[_\-]?TOKEN)(?![a-z])"
       r"[A-Za-z0-9_\-]*\s*[:=]\s*['\"]?)"
       r"(?P<secret>[A-Za-z0-9\-._~+/=]{16,})",
       "", handler="group", flags=re.IGNORECASE, gated=True),
]

# Values that look secret-ish but must never be rewritten: they are structural,
# already-public, or would corrupt the transcript.
ALLOWLIST = re.compile(
    r"^(?:"
    r"(?i:true|false|null|none|undefined|changeme|example|placeholder|redacted)|"
    r"(?i:your[_\-]?(?:api[_\-]?)?key(?:[_\-]?here)?|xxx+)|\.{3,}|"
    # Documentation placeholders: `scheme://user:pass@host` in prose is not a leak.
    r"(?i:pass(?:word|wd)?|user(?:name)?|host(?:name)?|localhost|admin|root|"
    r"test|dummy|fake|sample|foo|bar|baz|secret|token|key)|"
    r"[0-9a-f]{7,8}|[0-9a-f]{40}|[0-9a-f]{64}|"   # git SHAs / hashes (lowercase hex)
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
    r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|"           # UUIDs
    r"\$\{?[A-Za-z_][A-Za-z0-9_]*\}?|"           # $VAR / ${VAR} references
    r"(?i:process\.env\..*|os\.environ.*)"
    r")$"
)


# --- salt -----------------------------------------------------------------


def salt_path() -> Path:
    return Path(os.environ.get(SALT_ENV) or DEFAULT_SALT)


def load_salt() -> bytes:
    """Load the HMAC salt, creating it on first use with 0600 perms."""
    path = salt_path()
    if path.is_file():
        return path.read_text().strip().encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    value = secrets.token_hex(32)
    path.write_text(value + "\n")
    path.chmod(0o600)
    return value.encode()


def _bytes(salt: bytes, material: str, count: int) -> bytes:
    """Deterministic byte stream keyed by the salt and the original value."""
    out = bytearray()
    block = 0
    seed = material.encode("utf-8", "replace")
    while len(out) < count:
        out += hmac.new(salt, seed + block.to_bytes(4, "big"), hashlib.sha256).digest()
        block += 1
    return bytes(out[:count])


# --- format-preserving substitution ---------------------------------------


HEX_LOWER = re.compile(r"^[0-9a-f]+$")
HEX_UPPER = re.compile(r"^[0-9A-F]+$")


def scramble_shape(salt: bytes, value: str, keep_prefix: str = "") -> str:
    """Rewrite `value` character-by-character, preserving class and length.

    A hex-only body stays hex: emitting a 'w' inside what should be a hex digest
    is exactly the kind of tell we are trying to avoid.
    """
    head, tail = value[: len(keep_prefix)], value[len(keep_prefix):]
    stream = _bytes(salt, value, len(tail) + 8)

    hex_alphabet = ""
    if HEX_LOWER.match(tail):
        hex_alphabet = string.digits + "abcdef"
    elif HEX_UPPER.match(tail):
        hex_alphabet = string.digits + "ABCDEF"

    out = []
    for i, ch in enumerate(tail):
        b = stream[i]
        if hex_alphabet:
            out.append(hex_alphabet[b % 16])
        elif ch.isdigit():
            out.append(string.digits[b % 10])
        elif ch.islower():
            out.append(string.ascii_lowercase[b % 26])
        elif ch.isupper():
            out.append(string.ascii_uppercase[b % 26])
        else:
            out.append(ch)  # separators, -, _, ., / stay put
    return head + "".join(out)


def _b62(n: int, width: int) -> str:
    out = []
    for _ in range(width):
        n, r = divmod(n, 62)
        out.append(B62[r])
    return "".join(reversed(out))


def scramble_github(salt: bytes, value: str) -> str:
    """GitHub tokens carry a base62 CRC32 tail; regenerate it over the fake body.

    Shaped like the real checksum. Not verified against GitHub's exact spec, so
    treat this as structural fidelity rather than a guarantee it validates.
    """
    prefix, _, body = value.partition("_")
    prefix += "_"
    if len(body) < 7:
        return scramble_shape(salt, value, prefix)
    payload = scramble_shape(salt, body[:-6])
    checksum = _b62(binascii.crc32((prefix + payload).encode()), 6)
    return prefix + payload + checksum


def scramble_slack(salt: bytes, value: str) -> str:
    """Keep the xox?- token-type marker, scramble each dash-separated field."""
    parts = value.split("-")
    return "-".join([parts[0]] + [scramble_shape(salt, p) for p in parts[1:]])


def scramble_stripe(salt: bytes, value: str) -> str:
    """Keep the sk_live_ / sk_test_ mode marker so the fake stays meaningful."""
    m = re.match(r"([sprk]k_(?:live|test)_)(.*)", value)
    return m.group(1) + scramble_shape(salt, m.group(2)) if m else scramble_shape(salt, value)


def scramble_jwt(salt: bytes, value: str) -> str:
    """Re-emit a structurally valid JWT: decodable header/payload, fake claims.

    A model can base64-decode a JWT, so random noise in those segments is a tell.
    """
    parts = value.split(".")
    if len(parts) != 3:
        return scramble_shape(salt, value)

    def _seg(raw: str, mutate) -> str:
        try:
            padded = raw + "=" * (-len(raw) % 4)
            obj = json.loads(base64.urlsafe_b64decode(padded))
        except Exception:
            return scramble_shape(salt, raw)
        if not isinstance(obj, dict):
            return scramble_shape(salt, raw)
        obj = mutate(obj)
        packed = json.dumps(obj, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(packed).decode().rstrip("=")

    def _keep_structure(obj: dict) -> dict:
        out = {}
        for k, v in obj.items():
            if k in {"alg", "typ", "kid", "iat", "exp", "nbf", "ver"}:
                out[k] = v  # structural / numeric claims stay usable
            elif isinstance(v, str):
                out[k] = scramble_shape(salt, v)
            else:
                out[k] = v
        return out

    header = _seg(parts[0], lambda o: {**o, **{k: o[k] for k in o}})
    payload = _seg(parts[1], _keep_structure)
    signature = scramble_shape(salt, parts[2])
    return f"{header}.{payload}.{signature}"


def scramble_pem(salt: bytes, value: str) -> str:
    """Replace the base64 body of a PEM block, keeping the armour lines intact."""
    lines = value.splitlines()
    out = []
    for line in lines:
        if line.startswith("-----") or not line.strip():
            out.append(line)
        else:
            out.append(scramble_shape(salt, line))
    return "\n".join(out)


HANDLERS = {
    "github": scramble_github,
    "slack": scramble_slack,
    "stripe": scramble_stripe,
    "jwt": scramble_jwt,
    "pem": scramble_pem,
}


# --- scrubbing ------------------------------------------------------------


def shannon(value: str) -> float:
    counts = Counter(value)
    n = len(value)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def credential_like(value: str) -> bool:
    """Does a context-matched value actually look like a credential?

    Vendor-prefixed matches skip this — they are self-evidently secrets. It
    exists to stop `author=Titus Buckworth` being treated as one, which both
    corrupts prose and makes the leak check meaningless.
    """
    if len(value) < 16:
        return False
    if shannon(value) < 3.0:
        return False
    classes = sum([
        any(c.islower() for c in value),
        any(c.isupper() for c in value),
        any(c.isdigit() for c in value),
    ])
    return classes >= 2


@dataclass
class Scrubber:
    salt: bytes
    counts: Counter = field(default_factory=Counter)
    originals: set[str] = field(default_factory=set)
    mapping: dict[str, str] = field(default_factory=dict)

    def _replacement(self, rule: Rule, value: str) -> str:
        handler = HANDLERS.get(rule.handler)
        if handler:
            return handler(self.salt, value)
        return scramble_shape(self.salt, value, rule.keep(value))

    def scrub_text(self, text: str) -> str:
        if not text or len(text) < 8:
            return text

        # Collect candidate spans from every rule, then resolve overlaps by
        # preferring the longest match. This is what stops a short generic rule
        # from eating half of a longer, more specific one.
        spans: list[tuple[int, int, Rule, str]] = []
        for rule in RULES:
            for m in rule.pattern.finditer(text):
                if "secret" in (m.groupdict() or {}):
                    start, end = m.span("secret")
                    value = m.group("secret")
                else:
                    start, end = m.span()
                    value = m.group()
                # Allowlist and the credential-likeness gate apply only to the
                # context-based rules; a vendor-prefixed match is high
                # confidence and must never be skipped.
                if not value:
                    continue
                if rule.generic and ALLOWLIST.match(value):
                    continue
                # Only the loose assignment rule needs the entropy gate; a
                # password inside `scheme://user:pass@host` is high confidence
                # from its context regardless of how weak it is.
                if rule.gated and not credential_like(value):
                    continue
                spans.append((start, end, rule, value))

        if not spans:
            return text

        spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
        chosen: list[tuple[int, int, Rule, str]] = []
        cursor = -1
        for start, end, rule, value in spans:
            if start < cursor:
                continue  # overlapped by an earlier, longer match
            chosen.append((start, end, rule, value))
            cursor = end

        out, last = [], 0
        for start, end, rule, value in chosen:
            out.append(text[last:start])
            fake = self.mapping.get(value) or self._replacement(rule, value)
            self.mapping[value] = fake
            out.append(fake)
            self.counts[rule.name] += 1
            self.originals.add(value)
            last = end
        out.append(text[last:])
        return "".join(out)

    def scrub_obj(self, obj):
        """Walk every string leaf of a decoded JSON value."""
        if isinstance(obj, str):
            return self.scrub_text(obj)
        if isinstance(obj, list):
            return [self.scrub_obj(v) for v in obj]
        if isinstance(obj, dict):
            return {k: (v if k in SKIP_KEYS else self.scrub_obj(v)) for k, v in obj.items()}
        return obj


# Structural fields that must survive untouched or the transcript stops
# replaying / stops being identifiable as the session it is.
SKIP_KEYS = {"uuid", "parentUuid", "timestamp", "sessionId", "session_id",
             "id", "requestId", "tool_use_id", "toolUseID", "type", "role"}


def scrub_file(src: Path, dest: Path, salt: bytes) -> dict:
    """Scrub a JSONL transcript line by line. Returns an audit summary."""
    scrubber = Scrubber(salt)
    lines_in = lines_failed = 0
    out_lines: list[str] = []

    with src.open("r", errors="replace") as fh_in:
        for line in fh_in:
            stripped = line.strip()
            if not stripped:
                out_lines.append(line)
                continue
            lines_in += 1
            try:
                obj = json.loads(stripped)
            except json.JSONDecodeError:
                # Never pass through a line we cannot parse: scrub it as raw text.
                lines_failed += 1
                out_lines.append(scrubber.scrub_text(line))
                continue
            out_lines.append(json.dumps(scrubber.scrub_obj(obj), ensure_ascii=False) + "\n")

    # Global sweep: a value detected in one place is rewritten everywhere,
    # including occurrences that carried no detectable context of their own.
    # Short or low-entropy values are excluded — sweeping "pass" across the file
    # would corrupt ordinary prose — so they are replaced only where detected.
    text = "".join(out_lines)
    swept = 0
    guaranteed: set[str] = set()
    for original, fake in sorted(scrubber.mapping.items(), key=lambda kv: -len(kv[0])):
        if len(original) < 12 or shannon(original) < 2.5:
            continue
        guaranteed.add(original)
        if original in text:
            swept += text.count(original)
            text = text.replace(original, fake)
    dest.write_text(text)

    return {
        "swept": swept,
        "lines": lines_in,
        "unparsed_lines": lines_failed,
        "counts": dict(sorted(scrubber.counts.items())),
        "total": sum(scrubber.counts.values()),
        "distinct": len(scrubber.originals),
        "span_only": len(scrubber.originals) - len(guaranteed),
        "originals": guaranteed,
    }


def verify(dest: Path, originals: set[str]) -> list[str]:
    """Confirm no swept secret survived. Returns the values still present.

    Re-running the detectors on the output is useless on its own — the fakes are
    format-preserving, so they match the same rules by design. The real check is
    that none of the globally swept originals appear in the scrubbed file.

    Only swept values are checked. Low-entropy span-only replacements (a
    placeholder like `pass`) legitimately still occur elsewhere as prose.
    """
    if not originals:
        return []
    text = dest.read_text(errors="replace")
    return sorted(v for v in originals if v in text)


def audit_markdown(summary: dict) -> str:
    """Render counts only — never the values."""
    lines = ["# Scrub audit", "",
             f"- **Lines processed:** {summary['lines']:,}",
             f"- **Extra occurrences caught by global sweep:** {summary.get('swept', 0):,}",
             f"- **Replacements:** {summary['total']:,}"
             f" ({summary['distinct']:,} distinct values)",
             f"- **Low-entropy, replaced in place only:** {summary.get('span_only', 0):,}"]
    if summary["unparsed_lines"]:
        lines.append(f"- **Unparsable lines (scrubbed as raw text):** "
                     f"{summary['unparsed_lines']:,}")
    lines += ["", "## By rule", ""]
    if summary["counts"]:
        lines += [f"- `{name}`: {n}" for name, n in summary["counts"].items()]
    else:
        lines.append("- _no secrets detected_")
    lines += ["", "Values are deliberately omitted. Substitution is deterministic and "
              "format-preserving; the HMAC salt is stored outside this repo.", ""]
    return "\n".join(lines)
