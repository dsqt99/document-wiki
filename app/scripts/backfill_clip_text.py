"""Backfill after the clip_text fixes: article summaries/titles, cut summaries, relation quotes.

Usage: python -m app.scripts.backfill_clip_text [apply]   (default: dry run with counts and a few samples)
Pages a person edited (editor_edit / rollback / draft_approved) are skipped entirely.
"""
import asyncio
import re
import sys
from types import SimpleNamespace

from sqlalchemy import select

from app.database import async_session_factory
from app.database.models import LegalRelation, LegalRelationType, LegalUnit, LegalUnitType, Source, WikiPage
from app.services import wiki_service
from app.services.doc_metadata_service import get_doc_meta
from app.services.legal_relation_extractor import LegalRelationExtractor
from app.services.legal_service import article_summary, is_body_sentence, split_legal_text_by_articles
from app.utils.text import clip_text

APPLY = len(sys.argv) > 1 and sys.argv[1] == "apply"
_BOUNDARY_END = re.compile(r"[.!?;:…)\]”\"]$")


async def legal_sources(db):
    ids = (await db.execute(select(LegalUnit.source_id).distinct())).scalars().all()
    rows = (await db.execute(select(Source).where(Source.id.in_(ids)))).scalars().all()
    return [s for s in rows if s.wiki_status not in ("processing", "queued")]


async def fix_pages(db, stats, changed):
    for src in await legal_sources(db):
        full_text = src.full_text or ""
        if not full_text.strip():
            continue
        doc_slug = (get_doc_meta(src) or {}).get("doc_slug") or f"doc-{src.id.hex[:8]}"
        parsed = split_legal_text_by_articles(full_text, src.title or "", doc_slug=doc_slug)
        arts = parsed["articles"]
        if not arts:
            continue
        slugs = [a["slug"] for a in arts] + [doc_slug]
        pages = (await db.execute(select(WikiPage).where(WikiPage.slug.in_(slugs)))).scalars().all()
        edited = await wiki_service.human_edited_page_ids(db, [p.id for p in pages])
        by_slug: dict[str, list] = {}
        for p in pages:
            by_slug.setdefault(p.slug, []).append(p)

        toc_fix: dict[str, str] = {}
        slug_count: dict[str, int] = {}
        for a in arts:
            slug_count[a["slug"]] = slug_count.get(a["slug"], 0) + 1
        for a in arts:
            num, title, lead = a["num"], a["title"], a.get("lead")
            if slug_count[a["slug"]] > 1:
                # A quoted article of an amended law repeats the number ("Điều 3" twice): the page
                # cannot tell which one it holds, so leave it rather than mix one's title with the other's body.
                stats["skip_dup_slug"] += 1
                continue
            raw_title = a["heading"].split(". ", 1)[1] if ". " in a["heading"] else None
            if lead and raw_title:
                toc_fix[f"[[{a['slug']}|Điều {num}: {raw_title}]]"] = (
                    f"[[{a['slug']}|Điều {num} — {clip_text(lead, 100)}]]"
                )
            for p in by_slug.get(a["slug"], []):
                if p.id in edited:
                    stats["skip_edited"] += 1
                    continue
                if raw_title and raw_title not in (p.content_md or ""):
                    # The page holds another article under this slug (e.g. a quoted "Điều 3" of an amended law).
                    stats["skip_mismatch"] += 1
                    continue
                new_summary = article_summary(num, title, lead, p.content_md or "")
                new_title = p.title
                old_prefix = f"Điều {num}: {raw_title} - "
                if lead and raw_title and (p.title or "").startswith(old_prefix):
                    new_title = f"Điều {num} - {p.title[len(old_prefix):]}"
                if new_summary != p.summary or new_title != p.title:
                    if new_title != p.title and stats["article_titles"] < 2 or stats["article_pages"] < 2:
                        print("ART", p.slug, "|", p.title[:90], "=>", new_title[:90])
                        print("    OLD:", p.summary)
                        print("    NEW:", new_summary)
                    stats["article_pages"] += 1
                    stats["article_titles"] += new_title != p.title
                    if APPLY:
                        p.summary, p.title = new_summary, new_title
                    changed[p.id] = p

        preamble = parsed["preamble"] or ""
        for p in by_slug.get(doc_slug, []):
            if p.id in edited:
                stats["skip_edited"] += 1
                continue
            content = p.content_md or ""
            for old, new in toc_fix.items():
                content = content.replace(old, new)
            summary = p.summary
            if preamble and summary == " ".join(preamble.split())[:280] or summary == preamble[:280]:
                summary = clip_text(preamble, 280)
            if content != p.content_md or summary != p.summary:
                stats["overview_pages"] += 1
                if APPLY:
                    p.content_md, p.summary = content, summary
                changed[p.id] = p


async def fix_cut_summaries(db, stats, changed):
    """MRP (300) / verbatim (280) summaries ending mid-word: the rest is gone, trim to a boundary."""
    linked = select(LegalUnit.wiki_page_id).where(LegalUnit.wiki_page_id.is_not(None))
    rows = (await db.execute(select(WikiPage).where(WikiPage.id.not_in(linked)))).scalars().all()
    rows = [p for p in rows if p.id not in changed]
    edited = await wiki_service.human_edited_page_ids(db, [p.id for p in rows])
    heading = re.compile(r"^#*\s*\**Điều\s+(\d+[a-zđ]*)\**\.?\s*(.*?)\**\s*$", re.IGNORECASE)
    for p in rows:
        if p.id in edited or not re.match(r"Điều\s+\d", p.title or ""):
            continue
        # Article page under an old slug (no legal unit points at it): rebuild its summary from its text.
        m = next((heading.match(line.strip()) for line in (p.content_md or "").splitlines()
                  if heading.match(line.strip())), None)
        if not m:
            continue
        raw = m.group(2).strip() or None
        lead = raw if is_body_sentence(raw) else None
        new = article_summary(m.group(1), None if lead else raw, lead, p.content_md or "")
        if new != p.summary:
            stats["orphan_articles"] = stats.get("orphan_articles", 0) + 1
            if APPLY:
                p.summary = new
            changed[p.id] = p

    cands = [p for p in rows if p.summary and len(p.summary) in (280, 300) and not _BOUNDARY_END.search(p.summary)
             and p.id not in changed]
    for p in cands:
        if p.id in edited:
            stats["skip_edited"] += 1
            continue
        collapsed = " ".join(p.summary.split())
        new = clip_text(collapsed, len(collapsed) - 1)
        if stats["cut_summaries"] < 2:
            print("CUT", p.slug, "|", p.summary[-60:], "=>", new[-60:])
        stats["cut_summaries"] += 1
        if APPLY:
            p.summary = new
        changed[p.id] = p


async def fix_units_and_relations(db, stats):
    busy = select(Source.id).where(Source.wiki_status.in_(("processing", "queued")))
    units = (await db.execute(select(LegalUnit).where(
        LegalUnit.unit_type == LegalUnitType.ARTICLE, LegalUnit.source_id.not_in(busy)))).scalars().all()
    for u in units:
        if u.title and is_body_sentence(u.title):
            old_prefix = f"Điều {u.unit_number}: {u.title}"
            stats["unit_titles"] += 1
            if APPLY:
                kids = (await db.execute(select(LegalUnit).where(
                    LegalUnit.source_id == u.source_id, LegalUnit.full_path.like(old_prefix[:200] + "%"),
                    LegalUnit.id != u.id))).scalars().all()
                for k in kids:
                    if k.full_path.startswith(old_prefix):
                        k.full_path = f"Điều {u.unit_number}" + k.full_path[len(old_prefix):]
                u.title, u.full_path = None, f"Điều {u.unit_number}"

    ex = LegalRelationExtractor()
    unit_by_id = {u.id: u for u in units}
    rels = (await db.execute(select(LegalRelation))).scalars().all()
    groups: dict = {}
    for r in rels:
        groups.setdefault(r.source_unit_id, []).append(r)
    preambles: dict = {}
    from sqlalchemy import text as sql
    original = dict((await db.execute(sql("select id, quote_context from bak_clip_20261018_rels"))).all())
    for unit_id, rs in groups.items():
        unit = unit_by_id.get(unit_id)  # article units of sources not being processed
        if unit is None:
            continue
        fresh = ex.extract_from_text(unit.content or "", default_doc_number=unit.doc_number)
        if any(r.relation_type == LegalRelationType.CAN_CU for r in rs):
            if unit.source_id not in preambles:
                src = await db.get(Source, unit.source_id)
                preambles[unit.source_id] = split_legal_text_by_articles(src.full_text or "", "")["preamble"] or ""
            fresh += ex.extract_preamble_basis(preambles[unit.source_id])
        pool: dict = {}
        for f in fresh:
            key = (f.relation_type, f.target_doc_number, getattr(f, "target_article_number", None),
                   getattr(f, "target_clause_number", None))
            pool.setdefault(key, []).append(f.quote_context)
        for r in rs:
            key = (r.relation_type, r.target_doc_number, r.target_article_number, r.target_clause_number)
            quotes = pool.get(key)
            if not quotes:
                stats["rel_unmatched"] += 1
                continue
            # Same key twice in one article: pick the fresh quote that continues this relation's original text.
            # A relation already holding one of the fresh quotes keeps it, so re-runs do not swap them.
            orig = (original.get(r.id) or r.quote_context or "").lstrip("…")[:120]
            if r.quote_context in quotes:
                q = r.quote_context
            else:
                q = next((x for x in quotes if orig and orig in x), quotes[0])
            quotes.remove(q)
            if q != r.quote_context:
                if stats["rel_quotes"] < 2:
                    print("REL", r.target_doc_number, "| OLD:", r.quote_context)
                    print("    NEW:", q)
                stats["rel_quotes"] += 1
                if APPLY:
                    r.quote_context = q


async def reembed(db, pages):
    from app.ai.embedding_catalog import get_spec
    from app.ai.registry import ProviderRegistry
    from app.services.embedding_storage import upsert_page_embedding, wiki_chunk_content_hash

    registry = ProviderRegistry(db)
    spec_id = await registry.get_active_embedding_spec_id()
    spec = get_spec(spec_id) if spec_id else None
    if not spec:
        print("no embedding spec, skip re-embed")
        return 0
    provider = await registry.get_embedding(task="document", spec_id=spec.id)
    done = 0
    for i in range(0, len(pages), 16):
        batch = pages[i:i + 16]
        vecs = await provider.embed_batch([f"{p.title}\n\n{p.summary}\n\n{(p.content_md or '')[:4000]}" for p in batch])
        for p, v in zip(batch, vecs):
            await upsert_page_embedding(db, page_id=p.id, spec=spec, vector=list(v),
                                        content_hash=wiki_chunk_content_hash("", p.content_md or ""),
                                        title=p.title, summary=p.summary, content_md=p.content_md)
        await db.commit()
        done += len(batch)
    return done


async def main():
    stats = {k: 0 for k in ("article_pages", "article_titles", "overview_pages", "cut_summaries",
                            "unit_titles", "rel_quotes", "rel_unmatched", "skip_edited", "skip_dup_slug", "skip_mismatch")}
    changed: dict = {}
    async with async_session_factory() as db:
        await fix_pages(db, stats, changed)
        await fix_cut_summaries(db, stats, changed)
        await fix_units_and_relations(db, stats)
        print("APPLY" if APPLY else "DRY RUN", stats)
        if APPLY:
            await db.commit()
            n = await reembed(db, list(changed.values()))
            print("re-embedded pages:", n)
        else:
            await db.rollback()


asyncio.run(main())
