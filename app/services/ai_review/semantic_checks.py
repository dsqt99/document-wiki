"""L3: near-duplicate detection for new-page proposals (05b §3.4)."""

from __future__ import annotations

from app.services.ai_review.runner import CheckResult

EMBED_CHARS = 4000
TOP_K = 6
DUP_SIM = 0.85
MAX_MATCHES = 5


async def run(db, content_md: str, self_page_id=None, scope_type: str = "global", scope_id=None,
              draft_kind: str = "edit") -> list[CheckResult]:
    if draft_kind != "create":
        return [CheckResult(id="semantic.duplicate", layer="L3", severity="warn", status="skipped",
                            message="Only runs for new-page proposals")]
    try:
        import app.ai.registry as registry_mod

        emb = await registry_mod.ProviderRegistry(db).get_embedding(task="document")
        vec = await emb.embed((content_md or "")[:EMBED_CHARS])
    except Exception as e:
        return [CheckResult(id="semantic.duplicate", layer="L3", severity="warn", status="skipped",
                            message=f"Embedding lookup failed: {e}")]

    from app.services import wiki_service

    hits = await wiki_service.search_pages_semantic(db, vec, top_k=TOP_K, scope_type=scope_type,
                                                    scope_id=scope_id)
    similar = []
    for page, score in hits or []:
        if self_page_id is not None and str(page.id) == str(self_page_id):
            continue
        if score >= DUP_SIM:
            similar.append({"slug": page.slug, "title": page.title, "score": round(float(score), 3)})
    if similar:
        return [CheckResult(
            id="semantic.duplicate", layer="L3", severity="warn", status="warn",
            message=f"{len(similar)} existing page(s) look similar — consider editing instead of creating",
            matches=similar[:MAX_MATCHES],
        )]
    return [CheckResult(id="semantic.duplicate", layer="L3", severity="warn", status="pass")]
