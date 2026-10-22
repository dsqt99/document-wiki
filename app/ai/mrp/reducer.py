"""REDUCE phase: merge extracts, reconcile with the KB and plan pages (05a §5.3)."""

from __future__ import annotations

import asyncio
import math
import re
import unicodedata
from collections import Counter
from typing import Any, Optional

from loguru import logger
from sqlalchemy import select

from app.config import settings
from app.utils.text import parse_json_loose, slugify, strip_code_fence

AUTO_MERGE_SIM = 0.90
AMBIGUOUS_SIM = 0.75
KB_UPDATE_SIM = 0.85
KB_MAYBE_SIM = 0.60
MAX_PLAN_CONCEPTS = 300
EMBED_TEXT_MAX = 4000
ARBITRATE_TIMEOUT_S = 60
MAYBE_TIMEOUT_S = 30
PLANNING_TIMEOUT_S = settings.mrp_llm_timeout_s

_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFC", name or "").lower()
    s = _PUNCT_RE.sub(" ", s)
    return _WS_RE.sub(" ", s).strip()


def _extract_data(row) -> dict:
    data = row.get("extract_json") if isinstance(row, dict) else getattr(row, "extract_json", None)
    return data if isinstance(data, dict) else {}


def _dedupe_exact(items: list[dict], name_key: str, def_key: str) -> list[dict]:
    groups: dict[str, dict] = {}
    spellings: dict[str, Counter] = {}
    for it in items:
        name = (it.get(name_key) or "").strip()
        key = normalize_name(name)
        if not key:
            continue
        spellings.setdefault(key, Counter())[name] += 1
        g = groups.get(key)
        if g is None:
            g = {"term": name, "definition": "", "mention_count": 0,
                 "absolute_offset": it.get("absolute_offset")}
            groups[key] = g
        g["mention_count"] += int(it.get("mention_count") or 1)
        d = it.get(def_key) or ""
        if len(d) > len(g["definition"]):
            g["definition"] = d
    for key, g in groups.items():
        g["term"] = spellings[key].most_common(1)[0][0]
    return list(groups.values())


def _cosine(a, b) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _concept_text(c: dict) -> str:
    return f"{c.get('term')}: {(c.get('definition') or '')[:200]}"[:EMBED_TEXT_MAX]


async def _embed_many(embedding_provider, texts: list[str]) -> list:
    if hasattr(embedding_provider, "embed_batch"):
        return list(await embedding_provider.embed_batch(texts))
    return [await embedding_provider.embed(t) for t in texts]


def _bool_list(raw: str, n: int) -> Optional[list[bool]]:
    data = parse_json_loose(strip_code_fence(raw or ""))
    if isinstance(data, dict):
        for k in ("answers", "results", "same", "decisions"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    if not isinstance(data, list) or len(data) != n:
        return None
    return [bool(x) for x in data]


async def _dedupe_embedding(concepts: list[dict], llm, embedding_provider) -> list[dict]:
    if len(concepts) <= 1 or embedding_provider is None:
        return concepts
    try:
        vecs = await _embed_many(embedding_provider, [_concept_text(c) for c in concepts])
        parent = list(range(len(concepts)))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(i, j):
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[rj] = ri

        ambiguous: list[tuple[int, int]] = []
        for i in range(len(concepts)):
            for j in range(i + 1, len(concepts)):
                sim = _cosine(vecs[i], vecs[j])
                if sim >= AUTO_MERGE_SIM:
                    union(i, j)
                elif sim >= AMBIGUOUS_SIM:
                    ambiguous.append((i, j))
        if ambiguous and llm is not None:
            lines = "\n".join(
                f"{k + 1}. \"{concepts[i]['term']}\" vs \"{concepts[j]['term']}\""
                for k, (i, j) in enumerate(ambiguous)
            )
            prompt = ("For each numbered pair, answer whether the two terms denote the same concept. "
                      "Return only a JSON array of booleans in the same order.\n\n" + lines)
            try:
                raw = await asyncio.wait_for(llm.generate(prompt, temperature=0.0), timeout=ARBITRATE_TIMEOUT_S)
                answers = _bool_list(raw, len(ambiguous))
                if answers:
                    for (i, j), same in zip(ambiguous, answers):
                        if same:
                            union(i, j)
            except Exception as e:
                logger.warning(f"reduce: dedupe arbitration failed: {e}")
        merged: dict[int, dict] = {}
        best_count: dict[int, int] = {}
        for i, c in enumerate(concepts):
            r = find(i)
            g = merged.get(r)
            if g is None:
                merged[r] = dict(c)
                best_count[r] = c["mention_count"]
                continue
            g["mention_count"] += c["mention_count"]
            if c["mention_count"] > best_count[r]:
                g["term"] = c["term"]
                best_count[r] = c["mention_count"]
            if len(c.get("definition") or "") > len(g.get("definition") or ""):
                g["definition"] = c["definition"]
        return list(merged.values())
    except Exception as e:
        logger.warning(f"reduce: embedding dedupe failed, keeping exact dedupe: {e}")
        return concepts


async def reconcile_with_kb(session, source, items: list[dict], llm, embedding_provider) -> list[dict]:
    """Attach a KB decision (CREATE / UPDATE <slug>) to each item."""
    from app.ai.mrp import pipeline
    from app.services import wiki_service
    from app.database.models import WikiPage

    for it in items:
        it["kb_action"] = "CREATE"
        it["kb_slug"] = None
        it["kb_score"] = 0.0
    if not items or embedding_provider is None:
        return items
    try:
        scopes = await pipeline._resolve_wiki_scopes(session, source)
    except Exception:
        scopes = [("global", None)]
    try:
        vecs = await _embed_many(embedding_provider, [_concept_text(it) for it in items])
    except Exception as e:
        logger.warning(f"reduce: KB reconciliation embedding failed, all CREATE: {e}")
        return items

    maybe: list[dict] = []
    for it, vec in zip(items, vecs):
        best_page, best_score = None, 0.0
        for scope_type, scope_id in scopes or [("global", None)]:
            try:
                hits = await wiki_service.search_pages_semantic(
                    session, vec, top_k=3, scope_type=scope_type, scope_id=scope_id,
                    page_filter=WikiPage.origin_tag == "generated",
                )
            except Exception as e:
                logger.debug(f"reduce: semantic search failed: {e}")
                hits = []
            for page, score in hits or []:
                if (getattr(page, "origin_tag", None) != "generated"
                    or (page.scope_type or "global") != scope_type
                    or str(page.scope_id or "") != str(scope_id or "")):
                    continue
                if score > best_score:
                    best_page, best_score = page, float(score)
        it["kb_score"] = best_score
        if best_page is None:
            continue
        if best_score >= KB_UPDATE_SIM:
            it["kb_action"], it["kb_slug"] = "UPDATE", best_page.slug
        elif best_score >= KB_MAYBE_SIM:
            it["kb_slug"] = best_page.slug
            it["_kb_title"] = getattr(best_page, "title", best_page.slug)
            maybe.append(it)

    if maybe:
        answers = None
        if llm is not None:
            lines = "\n".join(
                f"{k + 1}. concept \"{it['term']}\" vs existing page \"{it.get('_kb_title')}\" ({it['kb_slug']})"
                for k, it in enumerate(maybe)
            )
            prompt = ("For each numbered line, answer whether the new concept should update the existing "
                      "wiki page (true) or get its own page (false). Return only a JSON array of booleans.\n\n"
                      + lines)
            try:
                raw = await asyncio.wait_for(llm.generate(prompt, temperature=0.0), timeout=MAYBE_TIMEOUT_S)
                answers = _bool_list(raw, len(maybe))
            except Exception as e:
                logger.warning(f"reduce: MAYBE arbitration failed: {e}")
        for k, it in enumerate(maybe):
            if answers and answers[k]:
                it["kb_action"] = "UPDATE"
            else:
                it["kb_action"], it["kb_slug"] = "CREATE", None
            it.pop("_kb_title", None)
    return items


def target_page_count(strategy: str, n: int) -> int:
    if strategy == "single_pass":
        return max(3, min(30, n // 2))
    if strategy == "standard":
        return max(8, min(80, n // 3))
    return max(15, min(200, n // 3))


PLANNING_SYSTEM_PROMPT = (
    "You plan the pages of an internal knowledge wiki compiled from one source document. "
    "Return JSON only."
)


async def run_planning_call(llm, source, strategy, canonical_entities, canonical_concepts, reconciliation,
                            kt_name=None, kt_desc=None, user_note=None) -> dict:
    concepts = sorted(canonical_concepts or [], key=lambda c: -(c.get("mention_count") or 0))[:MAX_PLAN_CONCEPTS]
    recon = {normalize_name(r.get("term") or ""): r for r in (reconciliation or [])}
    lines = []
    for c in concepts:
        r = recon.get(normalize_name(c.get("term") or ""), c)
        decision = r.get("kb_action") or "CREATE"
        if decision == "UPDATE" and r.get("kb_slug"):
            decision = f"UPDATE {r['kb_slug']}"
        lines.append(f"- {c.get('term')} (x{c.get('mention_count') or 1}) [{decision}]: "
                     f"{(c.get('definition') or '')[:200]}")
    updates = sorted({r["kb_slug"] for r in (reconciliation or []) if r.get("kb_action") == "UPDATE" and r.get("kb_slug")})
    target = target_page_count(strategy, len(canonical_concepts or []))
    name = getattr(source, "title", None) or getattr(source, "file_name", None) or str(getattr(source, "id", ""))
    parts = [
        f"Source: {name}",
        f"Knowledge type: {kt_name or '-'}" + (f" — {kt_desc}" if kt_desc else ""),
        f"Strategy: {strategy}",
        f"Target page count: about {target}",
        "Concepts (with KB reconciliation decision):\n" + ("\n".join(lines) or "(none)"),
        "Existing pages to UPDATE: " + (", ".join(updates) or "(none)"),
    ]
    if user_note:
        parts.append(f"Reviewer note: {user_note}")
    parts.append(
        "Slugs must be flat, lowercase, words joined with hyphens. Return ONLY JSON: "
        '{"pages": [{"action": "CREATE|UPDATE", "slug", "title", "page_type", "entity_names": [], '
        '"related_kb_pages": [], "priority"}], "estimated_page_count", "compilation_notes"}'
    )
    raw = await asyncio.wait_for(
        llm.generate("\n\n".join(parts), system=PLANNING_SYSTEM_PROMPT, temperature=0.1),
        timeout=PLANNING_TIMEOUT_S,
    )
    try:
        data = parse_json_loose(strip_code_fence(raw or ""))
    except (ValueError, TypeError) as e:
        raise ValueError(f"planning call returned invalid JSON: {e}") from e
    if not isinstance(data, dict):
        data = {"pages": data if isinstance(data, list) else []}
    pages = []
    for p in data.get("pages") or []:
        if not isinstance(p, dict):
            continue
        slug = slugify(str(p.get("slug") or p.get("title") or "")).replace("/", "-")
        if not slug:
            continue
        action = str(p.get("action") or "CREATE").upper()
        pages.append({
            "action": action if action in ("CREATE", "UPDATE") else "CREATE",
            "slug": slug,
            "title": p.get("title") or slug,
            "page_type": p.get("page_type") or "concept",
            "entity_names": [x for x in (p.get("entity_names") or []) if isinstance(x, str)],
            "related_kb_pages": [x for x in (p.get("related_kb_pages") or []) if isinstance(x, str)],
            "priority": p.get("priority") if isinstance(p.get("priority"), (int, float)) else 99,
        })
    data["pages"] = pages
    data.setdefault("estimated_page_count", len(pages))
    data.setdefault("compilation_notes", "")
    return data


async def run_reduce_phase(session, source, chunk_extracts, llm, embedding_provider, kt_name, kt_desc,
                           tracker, user_note: Optional[str] = None):
    from app.database.models import SourceCompilationPlan
    from app.models.concept_relation import collect_concept_relations, persist_concept_relations

    async def _progress(p, msg):
        if tracker is not None:
            try:
                await tracker.update(p, msg)
            except Exception:
                pass

    await _progress(66, "Merging extracted knowledge...")
    raw_concepts, raw_entities, claims = [], [], []
    for row in chunk_extracts or []:
        data = _extract_data(row)
        raw_concepts.extend(c for c in data.get("concepts") or [] if isinstance(c, dict))
        raw_entities.extend(e for e in data.get("entities") or [] if isinstance(e, dict))
        claims.extend(c for c in data.get("claims") or [] if isinstance(c, dict))

    concepts = _dedupe_exact(raw_concepts, "term", "definition_excerpt")
    entities = _dedupe_exact(raw_entities, "name", "description")

    await _progress(68, "Deduplicating concepts...")
    concepts = await _dedupe_embedding(concepts, llm, embedding_provider)

    await _progress(72, "Reconciling with the knowledge base...")
    reconciliation = await reconcile_with_kb(session, source, [dict(c) for c in concepts], llm,
                                             embedding_provider)

    await _progress(76, "Planning wiki pages...")
    strategy = getattr(source, "pipeline_strategy", None) or "standard"
    plan_json = await run_planning_call(llm, source, strategy, entities, concepts, reconciliation,
                                        kt_name, kt_desc, user_note)
    plan_json["_claims"] = claims
    plan_json["_entities"] = entities
    plan_json["_concepts"] = concepts

    plan = (await session.execute(
        select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id)
    )).scalar_one_or_none()
    if plan is None:
        plan = SourceCompilationPlan(source_id=source.id, plan_json=plan_json, status="pending_review")
        session.add(plan)
    else:
        plan.plan_json = plan_json
        plan.status = "pending_review"
        plan.reviewed_by = None
        plan.review_note = None
        plan.reviewed_at = None
    source.pipeline_phase = "plan_review"
    await session.flush()

    try:
        relations = collect_concept_relations(list(chunk_extracts or []))
        await persist_concept_relations(session, source.id, relations)
    except Exception as e:
        logger.warning(f"reduce[{source.id}]: concept relations not stored: {e}")
    await session.commit()
    return plan
