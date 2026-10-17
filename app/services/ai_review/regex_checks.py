"""L1: sensitive pattern detection (05b §3.2)."""

from __future__ import annotations

import re

from app.services.ai_review.runner import CheckResult

MAX_MATCHES = 10
ALLOW_LOOKAHEAD = 3

# (id, label, pattern) in the fixed reporting order.
PATTERNS: list[tuple[str, str, re.Pattern]] = [
    ("pii.email", "Email address", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("pii.phone_vn", "Vietnamese phone number", re.compile(r"(?<![\w+])(?:\+84|0)\d{9,10}\b")),
    ("pii.cccd_vn", "12-digit national ID", re.compile(r"(?<!\d)\d{12}(?!\d)")),
    ("secret.api_key_sk", "API key (sk-...)", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("secret.anthropic", "Anthropic key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("secret.aws_access", "AWS access key", re.compile(r"\bAKIA[A-Z0-9]{16}\b")),
    ("secret.github_pat", "GitHub PAT", re.compile(r"\bghp_[A-Za-z0-9]{36}\b")),
    ("secret.google_api", "Google API key", re.compile(r"\bAIza[A-Za-z0-9_-]{35}")),
    ("secret.jwt", "JWT", re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")),
    ("secret.private_key", "Private key block",
     re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]

_ALLOW_RE = re.compile(r"<!--\s*pii-allow:[^>]*-->", re.IGNORECASE)


def _allowed_lines(lines: list[str]) -> set[int]:
    allowed: set[int] = set()
    for i, line in enumerate(lines):
        if not _ALLOW_RE.search(line):
            continue
        allowed.add(i)
        for j in range(i + 1, min(len(lines), i + 1 + ALLOW_LOOKAHEAD)):
            nxt = lines[j]
            if not nxt.strip() or _ALLOW_RE.search(nxt):
                continue
            allowed.add(j)
            break
    return allowed


def _mask(value: str) -> str:
    if len(value) <= 6:
        return "*" * len(value)
    return value[:3] + "*" * (len(value) - 5) + value[-2:]


def run(content_md: str) -> list[CheckResult]:
    lines = (content_md or "").splitlines()
    allowed = _allowed_lines(lines)
    out: list[CheckResult] = []
    for check_id, label, rx in PATTERNS:
        is_secret = check_id.startswith("secret.")
        severity = "block" if is_secret else "warn"
        hits: list[dict] = []
        suppressed = 0
        for idx, line in enumerate(lines):
            for m in rx.finditer(line):
                if idx in allowed:
                    suppressed += 1
                    continue
                hits.append({"line": idx + 1, "snippet": _mask(m.group(0))})
        if hits:
            out.append(CheckResult(
                id=check_id, layer="L1", severity=severity,
                status="fail" if is_secret else "warn",
                message=f"Found {len(hits)} occurrence(s) of {label}",
                matches=hits[:MAX_MATCHES],
                extra={"suppressed": suppressed},
            ))
        else:
            out.append(CheckResult(
                id=check_id, layer="L1", severity=severity, status="pass",
                message=f"{suppressed} suppressed by pii-allow marker" if suppressed else None,
                extra={"suppressed": suppressed},
            ))
    return out
