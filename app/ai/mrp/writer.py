"""REFINE phase: write one wiki page per plan item (05a §5.5)."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from loguru import logger

from app.services.wiki_write_guard import (
    check_machine_rewrite,
    is_failure_stub,
    make_failure_stub,
    missing_row_identities,
    table_row_identities,
)
from app.config import settings
from app.utils.text import clip_text, parse_json_loose, strip_code_fence

MAX_PARALLEL_PAGES = settings.mrp_write_parallel_pages
LLM_TIMEOUT_S = settings.mrp_llm_timeout_s
COMPLEX_EVIDENCE_COUNT = 8
COMPLEX_EXISTING_CHARS = 3000
AGENT_MAX_STEPS = 10

EXTEND_SHRINK_RATIO = 0.9
POLISH_MIN_BATCHES = 3
POLISH_SHRINK_RATIO = 0.95
RESERVE_RATIO = 0.7
PASS_BUDGET_RATIO = 0.5
EXTEND_RETRIES = 2
TIER_B_PROXIMITY = 5000
PASS_MAX_ROW_LOSS = 0.2

CHARS_PER_TOKEN = 4
CONTEXT_USE_RATIO = 0.85
MAX_SOURCE_BUDGET_CHARS = 2_500_000
DEFAULT_SOURCE_BUDGET_CHARS = 120_000
DEFAULT_EVIDENCE_LEN = 200
MAX_EVIDENCE_LEN = 2000
IMAGE_WINDOW = 1500
PARAGRAPH_BLOCK_CHARS = 3000
EXCERPT_DEFAULT_LEN = 5000
EXCERPT_MAX_LEN = 10000

_IMAGE_MARKER_RE = re.compile(r"image://[0-9a-fA-F-]{36}")
_HEADING_RE = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$", re.MULTILINE)


@dataclass
class PageWriteResult:
    slug: str
    title: str
    page_type: str
    action: str
    content_md: str
    summary: str
    citations: list = field(default_factory=list)
    entity_names: list = field(default_factory=list)
    related_kb_pages: list = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        status = getattr(self, "status", None)
        if status is not None:
            d["status"] = status
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "PageWriteResult":
        obj = cls(
            slug=d.get("slug") or "",
            title=d.get("title") or d.get("slug") or "",
            page_type=d.get("page_type") or "concept",
            action=(d.get("action") or "CREATE").upper(),
            content_md=d.get("content_md") or "",
            summary=d.get("summary") or "",
            citations=list(d.get("citations") or []),
            entity_names=list(d.get("entity_names") or []),
            related_kb_pages=list(d.get("related_kb_pages") or []),
        )
        if d.get("status"):
            obj.status = d["status"]  # type: ignore[attr-defined]
        return obj


def checkpoint_fingerprint(source, plan, full_text: str, kt_slug=None, *, plan_json=None) -> str:
    """Bind drafts to the original extraction and every saved generation input.

    A Wiki-only retry changes wiki_attempt_id, not these inputs. Legacy drafts
    without this provenance are intentionally regenerated once.
    """
    inputs = dict((plan.plan_json if plan_json is None else plan_json) or {})
    inputs.pop("_page_drafts", None)
    inputs.pop("_page_drafts_checkpoint", None)
    payload = {"version": 1, "source_id": str(source.id),
               "attempt_id": str(getattr(source, "attempt_id", None)),
               "source_text": full_text or "", "outline": getattr(source, "outline_json", None),
               "plan_id": str(getattr(plan, "id", None)), "plan": inputs, "knowledge_type": kt_slug}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     default=str).encode("utf-8")).hexdigest()


def reusable_checkpoint_results(source, plan, full_text: str, kt_slug=None) -> dict[str, PageWriteResult]:
    """Return only unique, current, factually valid drafts keyed by planned slug."""
    from app.ai.mrp.verifier import factual_publication_blockers

    saved = plan.plan_json or {}
    marker = saved.get("_page_drafts_checkpoint") or {}
    if not isinstance(marker, dict) or marker.get("fingerprint") != checkpoint_fingerprint(source, plan, full_text, kt_slug):
        return {}
    mapping = marker.get("slugs") or {}
    if not isinstance(mapping, dict):
        return {}
    drafts = [d for d in saved.get("_page_drafts", []) if isinstance(d, dict)]
    counts = Counter(d.get("slug") for d in drafts if isinstance(d.get("slug"), str))
    unique = {d["slug"]: d for d in drafts if isinstance(d.get("slug"), str) and counts[d["slug"]] == 1}
    resolved_counts = Counter(v for v in mapping.values() if isinstance(v, str))
    reusable = {}
    for item in saved.get("pages") or []:
        if not isinstance(item, dict) or not item.get("slug"):
            continue
        original = item["slug"]
        resolved = mapping.get(original)
        if not isinstance(resolved, str) or resolved_counts[resolved] != 1 or resolved not in unique:
            continue
        row = PageWriteResult.from_dict(unique[resolved])
        if not is_failure_stub(row.content_md) and not factual_publication_blockers(row.content_md, full_text or ""):
            reusable[original] = row
    return reusable


def _pass_drops_rows(before: str, after: str) -> bool:
    ids = table_row_identities(before or "")
    if not ids:
        return False
    return len(missing_row_identities(before or "", after or "")) / len(ids) > PASS_MAX_ROW_LOSS


# ---------------------------------------------------------------------------
# Evidence and source selection
# ---------------------------------------------------------------------------


def _ci_word_in(name: str, text: str) -> bool:
    if not name:
        return False
    return re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text or "", re.IGNORECASE) is not None


def assemble_evidence(plan_item: dict, claims: list, full_text: str) -> list[dict]:
    names = [n for n in (plan_item.get("entity_names") or []) if isinstance(n, str) and n.strip()]
    lowered = {n.strip().lower() for n in names}
    out: list[dict] = []
    for c in claims or []:
        if not isinstance(c, dict):
            continue
        subject = (c.get("subject") or "").strip()
        statement = c.get("statement") or ""
        if not (subject.lower() in lowered or any(_ci_word_in(n, statement) for n in names)):
            continue
        try:
            offset = int(c.get("absolute_offset") or 0)
        except (TypeError, ValueError):
            offset = 0
        try:
            ev_len = int(c.get("evidence_length") or DEFAULT_EVIDENCE_LEN)
        except (TypeError, ValueError):
            ev_len = DEFAULT_EVIDENCE_LEN
        ev_len = max(1, min(ev_len, MAX_EVIDENCE_LEN))
        out.append({
            "statement": statement,
            "subject": subject,
            "confidence": c.get("confidence"),
            "source_excerpt": (full_text or "")[offset: offset + ev_len],
            "absolute_offset": offset,
            "evidence_length": ev_len,
        })
    return out


def source_budget_chars(llm) -> int:
    spec = getattr(getattr(llm, "config", None), "spec", None)
    ctx = getattr(spec, "context_window_tokens", None)
    if not ctx:
        return DEFAULT_SOURCE_BUDGET_CHARS
    return int(min(MAX_SOURCE_BUDGET_CHARS, ctx * CHARS_PER_TOKEN * CONTEXT_USE_RATIO))


@dataclass
class _Section:
    title: str
    start: int
    end: int


def _leaf_nodes(nodes: list) -> list[dict]:
    out: list[dict] = []
    for n in nodes or []:
        if not isinstance(n, dict):
            continue
        kids = n.get("children") or []
        if kids:
            out.extend(_leaf_nodes(kids))
        else:
            out.append(n)
    return out


def split_sections(full_text: str, outline_json: Any = None) -> list[_Section]:
    text = full_text or ""
    sections: list[_Section] = []
    for n in _leaf_nodes(outline_json if isinstance(outline_json, list) else []):
        s, e = n.get("char_start"), n.get("char_end")
        if isinstance(s, int) and isinstance(e, int) and e > s:
            sections.append(_Section(n.get("title") or "", s, min(e, len(text))))
    if sections:
        return sorted(sections, key=lambda x: x.start)

    heads = list(_HEADING_RE.finditer(text))
    if heads:
        if heads[0].start() > 0:
            sections.append(_Section("(mở đầu)", 0, heads[0].start()))
        for i, m in enumerate(heads):
            end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
            sections.append(_Section(m.group(2).strip(), m.start(), end))
        return sections

    start = 0
    idx = 1
    while start < len(text):
        end = min(len(text), start + PARAGRAPH_BLOCK_CHARS)
        if end < len(text):
            brk = text.rfind("\n\n", start, end)
            if brk > start:
                end = brk + 2
        sections.append(_Section(f"Đoạn {idx}", start, end))
        start = end
        idx += 1
    return sections


def select_source_context(full_text: str, sections: list[_Section], evidence: list[dict],
                          budget: int) -> tuple[list[_Section], list[_Section]]:
    """Return (included sections in document order, skipped sections)."""
    offsets = [e["absolute_offset"] for e in evidence]
    tier_a: list[int] = []
    for i, s in enumerate(sections):
        if any(s.start <= o < s.end for o in offsets):
            tier_a.append(i)
    chosen = set(tier_a)
    used = sum(sections[i].end - sections[i].start for i in chosen)
    tier_b: list[int] = []
    for i, s in enumerate(sections):
        if i in chosen:
            continue
        adjacent = (i - 1 in chosen) or (i + 1 in chosen)
        near = any(s.start - TIER_B_PROXIMITY <= o < s.end + TIER_B_PROXIMITY for o in offsets)
        if adjacent or near:
            tier_b.append(i)
    for i in tier_b:
        size = sections[i].end - sections[i].start
        if used + size <= budget:
            chosen.add(i)
            used += size
    if not offsets:
        # No evidence anchors: fill from the start of the document within budget.
        for i, s in enumerate(sections):
            size = s.end - s.start
            if used + size > budget:
                break
            chosen.add(i)
            used += size
    included = [sections[i] for i in sorted(chosen)]
    skipped = [s for i, s in enumerate(sections) if i not in chosen]
    return included, skipped


def _skipped_marker(skipped: list[_Section]) -> str:
    if not skipped:
        return ""
    names = ", ".join(s.title or "(không tên)" for s in skipped[:3])
    more = f" và {len(skipped) - 3} phần nữa" if len(skipped) > 3 else ""
    return f"[… đã bỏ qua các phần: {names}{more} …]"


def _render_sections(full_text: str, sections: list[_Section]) -> str:
    return "\n\n".join(full_text[s.start:s.end].strip() for s in sections if s.end > s.start)


def _image_markers_near(full_text: str, evidence: list[dict]) -> list[str]:
    seen: list[str] = []
    for e in evidence:
        o = e["absolute_offset"]
        window = (full_text or "")[max(0, o - IMAGE_WINDOW): o + IMAGE_WINDOW]
        for m in _IMAGE_MARKER_RE.findall(window):
            if m not in seen:
                seen.append(m)
    return seen


def _evidence_catalog(evidence: list[dict]) -> str:
    lines = []
    for e in evidence:
        conf = str(e.get("confidence") or "medium").upper()
        lines.append(f"- [{conf}] {e.get('subject') or ''} / {e.get('statement') or ''}")
    return "\n".join(lines)


def make_summary(content_md: str) -> str:
    parts: list[str] = []
    for line in (content_md or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            if parts:
                break
            continue
        parts.append(s)
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

WRITER_SYSTEM_PROMPT = """You compile pages for an internal knowledge wiki.
Compile, do not summarise: keep figures, rules, procedures and their steps, examples and definitions.
The source material is the authority. Plan titles, slugs and extracted claims may contain mistakes.
Never use outside knowledge to fill gaps. Copy legal document identifiers exactly from the source;
never infer an identifier from a slug or replace it with a more familiar law or decree.
Write in the same language as the source material.
Structure: an opening paragraph, then H2 sections; bold key terms; finish with a "Xem thêm" section of related links.
Do not add a references, citations or footnotes section.
Only link to slugs given in the list of existing pages, using [[slug]] or [[slug|label]].
Keep image markers of the form image://<uuid> exactly as given and never invent new ones.
Write at least 150 words. Output the page Markdown only."""

EXTEND_SYSTEM_PROMPT = """You extend an existing draft of an internal wiki page.
Keep the current draft exactly as it is and only append new sections covering the new material.
Your output must be the complete page: the full draft followed by the new sections, and it must be at least
as long as the draft plus 60% of the new material. Same language as the source. Output Markdown only."""

POLISH_SYSTEM_PROMPT = """You polish an internal wiki page assembled in several passes.
Fix ordering, duplicated headings and transitions without removing any fact, table row, link or image marker.
Output the complete page Markdown only."""

AGENT_SYSTEM_PROMPT = WRITER_SYSTEM_PROMPT + """
You may call tools: read_kb_page to read an existing wiki page in the same scope, read_source_excerpt to
read more of the source document, and finish to submit the final page content and a short summary.
Always end by calling finish."""

AGENT_TOOLS = [
    {
        "name": "read_kb_page",
        "description": "Read the Markdown of an existing wiki page in the same scope.",
        "parameters": {
            "type": "object",
            "properties": {"slug": {"type": "string"}},
            "required": ["slug"],
        },
    },
    {
        "name": "read_source_excerpt",
        "description": "Read part of the source document by character offset.",
        "parameters": {
            "type": "object",
            "properties": {
                "start_char": {"type": "integer"},
                "length": {"type": "integer", "description": "default 5000, max 10000"},
            },
            "required": ["start_char"],
        },
    },
    {
        "name": "finish",
        "description": "Submit the final page.",
        "parameters": {
            "type": "object",
            "properties": {"content_md": {"type": "string"}, "summary": {"type": "string"}},
            "required": ["content_md"],
        },
    },
]


def _page_prompt(item: dict, linkable: list[str], existing: Optional[str], source_ctx: str,
                 evidence: list[dict], images: list[str]) -> str:
    action = (item.get("action") or "CREATE").upper()
    parts = [
        f"Action: {action}",
        f"Slug: {item.get('slug')}",
        f"Title: {item.get('title')}",
        f"Page type: {item.get('page_type') or 'concept'}",
        "Existing pages you may link to: " + (", ".join(linkable) if linkable else "(none)"),
    ]
    if action == "UPDATE" and existing:
        parts.append("=== CURRENT PAGE CONTENT ===\n" + existing)
    parts.append("=== SOURCE CONTEXT ===\n" + (source_ctx or "(none)"))
    parts.append("=== EVIDENCE ===\n" + (_evidence_catalog(evidence) or "(none)"))
    if images:
        parts.append("Image markers available near the evidence: " + ", ".join(images))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


async def _generate(llm, prompt: str, system: str, temperature: float) -> str:
    raw = await asyncio.wait_for(llm.generate(prompt, system=system, temperature=temperature),
                                 timeout=LLM_TIMEOUT_S)
    return strip_code_fence(raw or "").strip()


async def write_simple(llm, item, linkable, existing, source_ctx, evidence, images) -> tuple[str, str]:
    content = await _generate(llm, _page_prompt(item, linkable, existing, source_ctx, evidence, images),
                              WRITER_SYSTEM_PROMPT, 0.15)
    return content, make_summary(content)


async def repair_evidence(llm, content: str, source_ctx: str, full_text: str) -> str:
    """One bounded corrective pass; an unsuccessful correction stays blocked at COMMIT."""
    from app.ai.mrp.verifier import factual_publication_blockers

    blockers = factual_publication_blockers(content, full_text)
    if not blockers or is_failure_stub(content) or "empty_source" in blockers:
        return content
    budget = min(source_budget_chars(llm), DEFAULT_SOURCE_BUDGET_CHARS)
    # Keep both the draft and the source header intact. A huge draft needs
    # regeneration with the normal multipass writer, not a truncated repair.
    if len(content) > budget // 2:
        return content
    available = max(0, budget - len(content) - 2000)
    material = full_text if len(full_text) <= available else full_text[:6000] + "\n\n" + source_ctx
    prompt = (
        "Correct this draft against the source. Validation errors: " + ", ".join(blockers)
        + ". The source overrides the plan, slug and draft. Copy document identifiers exactly. "
        "Correct unsupported references using source evidence; do not simply strip references to pass validation. "
        "Keep supported facts, procedures, numbers, tables and links. Do not invent or silently omit material. "
        "Do not add footnotes. Return the complete corrected Markdown only.\n\n"
        "=== SOURCE MATERIAL ===\n" + material[:available]
        + "\n\n=== DRAFT TO CORRECT ===\n" + content
    )
    candidate = await _generate(llm, prompt, WRITER_SYSTEM_PROMPT, 0.0)
    if (is_failure_stub(candidate) or factual_publication_blockers(candidate, full_text)
            or check_machine_rewrite(content, candidate, max_row_loss=0, min_length_ratio=0.85, min_old_chars=1)):
        logger.warning("Evidence correction did not pass validation; keeping blocked draft")
        return content
    return candidate


async def write_with_agent(llm, session, item, linkable, existing, source_ctx, evidence, images,
                           full_text: str, scope: tuple[str, Any]) -> tuple[str, str]:
    from app.ai.agent_protocol import assistant_message_from_turn, tool_results_message
    from app.services import wiki_service

    messages: list[dict] = [{
        "role": "user",
        "content": _page_prompt(item, linkable, existing, source_ctx, evidence, images),
    }]
    last_text = ""
    for _ in range(AGENT_MAX_STEPS):
        turn = await asyncio.wait_for(
            llm.generate_with_tools(messages, AGENT_TOOLS, system=AGENT_SYSTEM_PROMPT, temperature=0.15),
            timeout=LLM_TIMEOUT_S,
        )
        if turn.text:
            last_text = turn.text
        if not turn.tool_calls:
            break
        messages.append(assistant_message_from_turn(turn))
        results = []
        for call in turn.tool_calls:
            args = call.arguments or {}
            if call.name == "finish":
                content = strip_code_fence(args.get("content_md") or "").strip()
                return content, (args.get("summary") or make_summary(content)).strip()
            if call.name == "read_kb_page":
                page = await wiki_service.get_page_by_slug(
                    session, str(args.get("slug") or ""), scope_type=scope[0], scope_id=scope[1]
                )
                results.append((call.id, call.name, page.content_md if page else "(page not found)"))
            elif call.name == "read_source_excerpt":
                try:
                    start = max(0, int(args.get("start_char") or 0))
                    length = int(args.get("length") or EXCERPT_DEFAULT_LEN)
                except (TypeError, ValueError):
                    start, length = 0, EXCERPT_DEFAULT_LEN
                length = max(1, min(length, EXCERPT_MAX_LEN))
                results.append((call.id, call.name, (full_text or "")[start:start + length]))
            else:
                results.append((call.id, call.name, f"Unknown tool {call.name}"))
        messages.append(tool_results_message(results))

    content = strip_code_fence(last_text or "").strip()
    if not content:
        content = f"# {item.get('title') or item.get('slug')}\n\n(content generation incomplete)\n"
    return content, make_summary(content)


def _batch_sections(sections: list[_Section], budget: int) -> list[list[_Section]]:
    batches: list[list[_Section]] = []
    cur: list[_Section] = []
    size = 0
    for s in sections:
        n = s.end - s.start
        if cur and size + n > budget:
            batches.append(cur)
            cur, size = [], 0
        cur.append(s)
        size += n
    if cur:
        batches.append(cur)
    return batches


async def write_multipass(llm, item, linkable, existing, full_text, sections, evidence, images,
                          pass_budget: int) -> tuple[str, str]:
    batches = _batch_sections(sections, max(1, pass_budget))
    first_ctx = _render_sections(full_text, batches[0]) if batches else ""
    draft = await _generate(llm, _page_prompt(item, linkable, existing, first_ctx, evidence, images),
                            WRITER_SYSTEM_PROMPT, 0.15)
    for batch in batches[1:]:
        new_material = _render_sections(full_text, batch)
        accepted = None
        for _attempt in range(EXTEND_RETRIES + 1):
            prompt = (
                f"Slug: {item.get('slug')}\nTitle: {item.get('title')}\n\n"
                f"=== CURRENT DRAFT ===\n{draft}\n\n=== NEW SOURCE MATERIAL ===\n{new_material}"
            )
            try:
                candidate = await _generate(llm, prompt, EXTEND_SYSTEM_PROMPT, 0.15)
            except Exception as e:
                logger.warning(f"writer[{item.get('slug')}]: extend pass failed: {e}")
                continue
            if len(candidate) >= EXTEND_SHRINK_RATIO * len(draft) and not _pass_drops_rows(draft, candidate):
                accepted = candidate
                break
        if accepted is None:
            appended = [f"## {s.title or 'Bổ sung'}\n\n{full_text[s.start:s.end].strip()}" for s in batch]
            accepted = draft.rstrip() + "\n\n" + "\n\n".join(appended) + "\n"
        draft = accepted

    if len(batches) >= POLISH_MIN_BATCHES or images:
        try:
            polished = await _generate(llm, draft, POLISH_SYSTEM_PROMPT, 0.1)
            if len(polished) >= POLISH_SHRINK_RATIO * len(draft) and not _pass_drops_rows(draft, polished):
                draft = polished
        except Exception as e:
            logger.warning(f"writer[{item.get('slug')}]: polish pass failed: {e}")
    return draft, make_summary(draft)


# ---------------------------------------------------------------------------
# Phase
# ---------------------------------------------------------------------------


def _claims_from_extracts(chunk_extracts: list, plan_json: dict) -> list[dict]:
    claims = plan_json.get("_claims") if isinstance(plan_json, dict) else None
    if isinstance(claims, list) and claims:
        return claims
    out: list[dict] = []
    for row in chunk_extracts or []:
        data = getattr(row, "extract_json", None) if not isinstance(row, dict) else row.get("extract_json")
        for c in (data or {}).get("claims") or []:
            if isinstance(c, dict):
                out.append(c)
    return out


VERBATIM_LEGAL_MARKER = "> **Căn cứ pháp lý**"


def is_verbatim_legal_page(content_md: Optional[str]) -> bool:
    return bool(content_md) and content_md.lstrip().startswith(VERBATIM_LEGAL_MARKER)


async def _drop_verbatim_targets(items: list[dict], scope) -> list[dict]:
    """Article pages written by the legal splitter stay verbatim; the LLM never rewrites them."""
    from app import database
    from app.services import wiki_service

    kept = []
    async with database.async_session_factory() as s:
        for item in items:
            try:
                page = await wiki_service.get_page_by_slug(s, item["slug"], scope_type=scope[0], scope_id=scope[1])
            except Exception:
                page = None
            if page is not None and is_verbatim_legal_page(page.content_md):
                logger.info(f"refine[{item['slug']}]: verbatim legal article, not rewritten")
                continue
            kept.append(item)
    return kept


async def run_refine_phase(session, source, plan, chunk_extracts, full_text, llm, embedding_provider,
                           kt_slug, tracker) -> list[PageWriteResult]:
    from app import database
    from app.config import settings
    from app.services import wiki_service

    plan_json = dict(getattr(plan, "plan_json", None) or {})
    fingerprint = checkpoint_fingerprint(source, plan, full_text, kt_slug)
    completed = reusable_checkpoint_results(source, plan, full_text, kt_slug)
    items = [p for p in (plan_json.get("pages") or []) if isinstance(p, dict) and p.get("slug")]
    items.sort(key=lambda p: p.get("priority") if isinstance(p.get("priority"), (int, float)) else 99)
    claims = _claims_from_extracts(chunk_extracts, plan_json)
    sections = split_sections(full_text or "", getattr(source, "outline_json", None))
    budget = source_budget_chars(llm)
    multipass_enabled = bool(getattr(settings, "mrp_multipass_writer_enabled", True))
    try:
        scopes = await wiki_service.resolve_wiki_scopes(session, source)
    except Exception:
        scopes = [("global", None)]
    scope = scopes[0] if scopes else ("global", None)

    from app.services.wiki_origin_service import resolve_target_slug
    # Plan collisions must be resolved before producing links or loading old content.
    prepared = []
    planned_slugs = {}
    for item in items:
        item = dict(item)
        original = item["slug"]
        item["slug"] = await resolve_target_slug(session, original, "generated", scope[0], scope[1], source.id)
        planned_slugs[original] = item["slug"]
        # A collision/ownership change since the checkpoint also invalidates reuse.
        if original in completed and completed[original].slug != item["slug"]:
            completed.pop(original)
        item["_planned_slug"] = original
        prepared.append(item)
    items = prepared
    linkable_all = [p["slug"] for p in items]

    if tracker is not None:
        await tracker.update(78, f"Writing {len(items)} wiki page(s)...")

    sem = asyncio.Semaphore(MAX_PARALLEL_PAGES)
    checkpoint_lock = asyncio.Lock()

    async def _checkpoint(original: str, result: PageWriteResult) -> None:
        from sqlalchemy import select
        from app.database.models import Source, SourceCompilationPlan
        from app.services.source_quality import lock_current_attempt

        # Per-page LLM work uses separate sessions. Serialize all parent-session
        # writes, and keep attempt/plan locks through the checkpoint commit.
        async with checkpoint_lock:
            try:
                if not await lock_current_attempt(session, source, "wiki"):
                    raise RuntimeError("Stale Wiki attempt cannot save a draft checkpoint")
                current_source = (await session.execute(
                    select(Source.full_text, Source.outline_json).where(Source.id == source.id)
                    .execution_options(autoflush=False)
                )).one_or_none()
                if (current_source is None or current_source.full_text != full_text
                        or current_source.outline_json != getattr(source, "outline_json", None)):
                    raise RuntimeError("Stale Wiki original cannot save a draft checkpoint")
                latest = (await session.execute(
                    select(SourceCompilationPlan.plan_json).where(SourceCompilationPlan.id == plan.id)
                    .with_for_update().execution_options(autoflush=False)
                )).scalar_one_or_none()
                if not isinstance(latest, dict) or checkpoint_fingerprint(
                        source, plan, full_text, kt_slug, plan_json=latest) != fingerprint:
                    raise RuntimeError("Stale Wiki plan cannot save a draft checkpoint")
                completed[original] = result
                latest = dict(latest)
                latest["_page_drafts"] = [completed[key].to_dict() for key in planned_slugs if key in completed]
                latest["_page_drafts_checkpoint"] = {"fingerprint": fingerprint, "slugs": planned_slugs}
                plan.plan_json = latest
                await session.commit()
            except BaseException:
                await session.rollback()
                raise

    async def _one(item: dict) -> PageWriteResult:
        slug = item["slug"]
        original = item["_planned_slug"]
        if original in completed:
            return completed[original]
        title = item.get("title") or slug
        action = (item.get("action") or "CREATE").upper()
        result = PageWriteResult(
            slug=slug, title=title, page_type=item.get("page_type") or "concept", action=action,
            content_md="", summary=title,
            entity_names=list(item.get("entity_names") or []),
            related_kb_pages=list(item.get("related_kb_pages") or []),
        )
        async with sem:
            try:
                async with database.async_session_factory() as page_session:
                    existing_page = await wiki_service.get_page_by_slug(
                        page_session, slug, scope_type=scope[0], scope_id=scope[1]
                    )
                    existing = existing_page.content_md if existing_page is not None and getattr(existing_page, "origin_tag", None) == "generated" and len(scopes) <= 1 else None
                    evidence = assemble_evidence(item, claims, full_text or "")
                    included, skipped = select_source_context(full_text or "", sections, evidence, budget)
                    images = _image_markers_near(full_text or "", evidence)
                    linkable = [s for s in linkable_all if s != slug]
                    related_len = sum(s.end - s.start for s in included)
                    evidence_len = sum(len(e.get("source_excerpt") or "") for e in evidence)
                    total = related_len + evidence_len + len(existing or "")
                    if multipass_enabled and total >= RESERVE_RATIO * budget and len(included) > 1:
                        content, summary = await write_multipass(
                            llm, item, linkable, existing, full_text or "", included, evidence, images,
                            int(PASS_BUDGET_RATIO * budget),
                        )
                    else:
                        ctx = _render_sections(full_text or "", included)
                        marker = _skipped_marker(skipped)
                        if marker:
                            ctx = f"{ctx}\n\n{marker}"
                        complex_mode = (len(evidence) > COMPLEX_EVIDENCE_COUNT
                                        or len(existing or "") > COMPLEX_EXISTING_CHARS)
                        if complex_mode and len(scopes) <= 1 and hasattr(llm, "generate_with_tools"):
                            try:
                                content, summary = await write_with_agent(
                                    llm, page_session, item, linkable, existing, ctx, evidence, images,
                                    full_text or "", scope,
                                )
                            except NotImplementedError:
                                content, summary = await write_simple(
                                    llm, item, linkable, existing, ctx, evidence, images
                                )
                        else:
                            content, summary = await write_simple(
                                llm, item, linkable, existing, ctx, evidence, images
                            )
                corrected = await repair_evidence(llm, content, _render_sections(full_text or "", included), full_text or "")
                result.content_md = corrected
                result.summary = make_summary(corrected) if corrected != content else summary or title
                if existing:
                    reason = check_machine_rewrite(existing, content)
                    if reason:
                        logger.warning(f"refine[{slug}]: write guard will refuse this rewrite: {reason}")
            except Exception as e:
                logger.warning(f"refine[{slug}]: page generation failed: {type(e).__name__}: {e}")
                result.content_md = make_failure_stub(title, f"{type(e).__name__}: {e}")
                result.summary = title
        await _checkpoint(original, result)
        return result

    tasks = [asyncio.create_task(_one(i)) for i in items]
    try:
        return list(await asyncio.gather(*tasks))
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise
