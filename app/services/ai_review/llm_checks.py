"""L4: LLM judgment of tone, factual claims and page-type fit (05b §3.5)."""

from __future__ import annotations

from app.services.ai_review.runner import CheckResult
from app.utils.text import parse_json_loose

CONTENT_CHARS = 8000
MAX_TOKENS = 400
MAX_CONCERNS = 5

_SYSTEM = "You review draft pages for an internal knowledge wiki. Return JSON only."

_PROMPT = """Review this draft wiki page.
Assess (1) whether the tone is consistent and suitable for an internal wiki, (2) statements that should be
fact-checked, and (3) whether the content fits the declared page type.
Return only JSON: {{"tone_consistent": bool, "tone_notes": str, "factual_concerns": [str],
"scope_fit": bool, "scope_notes": str}}

Title: {title}
Page type: {page_type}

=== CONTENT ===
{content}
"""


def _skipped(msg: str) -> list[CheckResult]:
    return [CheckResult(id="llm.judgment", layer="L4", severity="warn", status="skipped", message=msg)]


async def run(db, content_md: str, title: str, page_type: str) -> list[CheckResult]:
    try:
        import app.ai.registry as registry_mod

        llm = await registry_mod.ProviderRegistry(db).get_llm()
    except Exception as e:
        return _skipped(f"LLM provider unavailable: {e}")
    try:
        raw = await llm.generate(
            _PROMPT.format(title=title or "", page_type=page_type or "concept",
                           content=(content_md or "")[:CONTENT_CHARS]),
            system=_SYSTEM, max_tokens=MAX_TOKENS, temperature=0,
        )
    except Exception as e:
        return _skipped(f"LLM call failed: {e}")
    try:
        data = parse_json_loose(raw or "")
        if not isinstance(data, dict):
            raise ValueError("not an object")
    except Exception:
        return _skipped("LLM returned unparseable response")

    tone_ok = data.get("tone_consistent", True) is not False
    tone_notes = str(data.get("tone_notes") or "")
    scope_ok = data.get("scope_fit", True) is not False
    scope_notes = str(data.get("scope_notes") or "")
    concerns = [str(c) for c in (data.get("factual_concerns") or []) if c]

    scope_msg = None
    if not scope_ok:
        scope_msg = f"Content may not fit page_type='{page_type}'" + (f": {scope_notes}" if scope_notes else "")
    elif scope_notes:
        scope_msg = scope_notes
    return [
        CheckResult(id="llm.tone", layer="L4", severity="warn", status="pass" if tone_ok else "warn",
                    message=(tone_notes or None) if tone_ok else f"Tone may be off: {tone_notes}"),
        CheckResult(id="llm.scope_fit", layer="L4", severity="warn", status="pass" if scope_ok else "warn",
                    message=scope_msg),
        CheckResult(id="llm.factual", layer="L4", severity="warn", status="warn" if concerns else "pass",
                    message=f"{len(concerns)} claim(s) flagged for verification" if concerns else None,
                    matches=concerns[:MAX_CONCERNS]),
    ]
