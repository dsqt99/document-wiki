"""L2: structural checks (05b §3.3)."""

from __future__ import annotations

import re
from typing import Optional

from sqlalchemy import select

from app.services.ai_review.runner import CheckResult

MIN_CHARS = 100
WARN_CHARS = 45_000
MAX_LINK_MATCHES = 20
MAX_HEADING_MATCHES = 10

_WIKILINK_RE = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
_FENCE_RE = re.compile(r"^(```|~~~)")


def _targets(content_md: str) -> list[str]:
    seen: list[str] = []
    for m in _WIKILINK_RE.finditer(content_md or ""):
        slug = m.group(1).strip()
        if slug and slug not in seen:
            seen.append(slug)
    return seen


async def _existing_slugs(db, slugs: list[str]) -> set[str]:
    from app.database.models import WikiPage

    if not slugs:
        return set()
    rows = (await db.execute(select(WikiPage.slug).where(WikiPage.slug.in_(slugs)))).scalars().all()
    return set(rows)


def _heading_jumps(content_md: str) -> list[dict]:
    jumps: list[dict] = []
    prev: Optional[int] = None
    in_fence = False
    for i, line in enumerate((content_md or "").splitlines()):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if prev is not None and level > prev + 1:
            jumps.append({"line": i + 1, "from": f"H{prev}", "to": f"H{level}"})
        prev = level
    return jumps


async def run(db, content_md: str, self_slug: Optional[str] = None, scope_type: str = "global",
              scope_id=None) -> list[CheckResult]:
    text = content_md or ""
    out: list[CheckResult] = []

    targets = _targets(text)
    others = [t for t in targets if t != self_slug]
    existing = await _existing_slugs(db, others)
    broken = [t for t in others if t not in existing]
    out.append(CheckResult(
        id="links.broken", layer="L2", severity="warn",
        status="warn" if broken else "pass",
        message=f"{len(broken)} wikilink target(s) do not exist in any scope" if broken else None,
        matches=broken[:MAX_LINK_MATCHES],
    ))

    has_self = bool(self_slug) and self_slug in targets
    out.append(CheckResult(
        id="links.self", layer="L2", severity="warn",
        status="warn" if has_self else "pass",
        message="Page links back to itself" if has_self else None,
    ))

    n = len(text)
    if n < MIN_CHARS:
        status, msg = "warn", f"Content is unusually short ({n} chars)"
    elif n > WARN_CHARS:
        status, msg = "warn", f"Content is approaching the 50KB hard cap ({n} chars)"
    else:
        status, msg = "pass", None
    out.append(CheckResult(id="length.sanity", layer="L2", severity="warn", status=status, message=msg,
                           extra={"chars": n}))

    jumps = _heading_jumps(text)
    out.append(CheckResult(
        id="markdown.heading_jump", layer="L2", severity="warn",
        status="warn" if jumps else "pass",
        message=("Heading levels jump non-incrementally: "
                 + ", ".join(f"{j['from']}→{j['to']}" for j in jumps[:5])) if jumps else None,
        matches=jumps[:MAX_HEADING_MATCHES],
    ))

    fences = sum(1 for line in text.splitlines() if _FENCE_RE.match(line))
    unclosed = fences % 2 == 1
    out.append(CheckResult(
        id="markdown.unclosed_fence", layer="L2", severity="warn",
        status="warn" if unclosed else "pass",
        message="Code fence appears to be unclosed" if unclosed else None,
    ))
    return out
