"""Redaction (best-effort lint, not a guarantee) and sanitising of text that enters agent context."""
from __future__ import annotations

import math
import re

_SECRETS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)")),
    ("aws-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("gh-token", re.compile(r"\b(?:ghp|gho|ghs|github_pat)_[A-Za-z0-9_]{20,}\b")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    ("conn-string", re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s/:@]+:[^\s/@]+@\S+", re.I)),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")),
    ("long-number", re.compile(r"\b\d{9,}\b")),
]
_ASSIGN = re.compile(r"(?i)\b(api[_-]?key|secret|token|passwd|password|pwd|private[_-]?key)\b(\s*[:=]\s*)(\S+)")
_TOKENISH = re.compile(r"[A-Za-z0-9+/=_-]{24,}")


def _entropy(s):
    return -sum(c / len(s) * math.log2(c / len(s)) for c in (s.count(x) for x in set(s)))


def redact(text, deny=()):
    """Return (text, findings). Findings are kinds only, never the secret itself."""
    found = []

    def sub(kind, pat, repl):
        nonlocal text
        text, n = pat.subn(repl, text)
        found.extend([kind] * n)

    for kind, pat in _SECRETS:
        sub(kind, pat, f"[REDACTED:{kind}]")
    sub("assignment", _ASSIGN, lambda m: f"{m.group(1)}{m.group(2)}[REDACTED:assignment]")
    for m in list(_TOKENISH.finditer(text)):
        t = m.group(0)
        if any(c.isdigit() for c in t) and any(c.isalpha() for c in t) and _entropy(t) > 3.8:
            text = text.replace(t, "[REDACTED:high-entropy]")
            found.append("high-entropy")
    for d in deny:
        if d and re.search(re.escape(d), text, re.I):
            text = re.sub(re.escape(d), "[REDACTED:deny-list]", text, flags=re.I)
            found.append("deny-list")
    return text, found


def looks_tabular(text, run=3):
    """True if >= `run` consecutive lines look like data rows (a pasted query result)."""
    streak = best = 0
    for line in text.splitlines():
        row = any(ch.isdigit() for ch in line) and (line.count("|") >= 2 or line.count("\t") >= 2 or line.count(",") >= 3)
        streak = streak + 1 if row else 0
        best = max(best, streak)
    return best >= run
