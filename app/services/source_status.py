"""Dual-pipeline status for a Source.

A source runs two independent branches after extraction:
  - Branch A (chunk_*): chunk + embed raw text into source_chunk_embeddings_<dim>.
  - Branch B (wiki_*):  MRP / legal compilation into wiki pages.

`source.status/progress/progress_message` is an aggregate derived from both
branches. Each branch writes only its own fields, then recomputes the aggregate
under a row lock so two workers finishing at the same time never overwrite
each other's branch state.
"""

import uuid
from typing import Optional

from loguru import logger
from sqlalchemy import select

CHUNK_ACTIVE = {"queued", "processing", "extracting", "chunking", "embedding"}
WIKI_GATES = {"awaiting_approval", "plan_ready"}


def compute_source_dual_status(source) -> tuple[str, int, str]:
    """Derive aggregate (status, progress, progress_message) from both branches."""
    chunk_st = getattr(source, "chunk_status", None) or "pending"
    wiki_st = getattr(source, "wiki_status", None) or "pending"
    chunk_prog = getattr(source, "chunk_progress", None) or 0
    wiki_prog = getattr(source, "wiki_progress", None) or 0
    chunk_msg = getattr(source, "chunk_progress_message", None)
    wiki_msg = getattr(source, "wiki_progress_message", None)
    chunk_err = getattr(source, "chunk_error_message", None) or ""
    wiki_err = getattr(source, "wiki_error_message", None) or ""

    # A branch still 'pending' never started. The dispatcher always moves both
    # branches off 'pending' before either runs, so this only happens for sources
    # ingested before the dual pipeline: the aggregate follows the other branch.
    if chunk_st == "pending" and wiki_st not in ("pending", "skipped"):
        if wiki_st == "ready":
            return "ready", 100, wiki_msg or "Ready"
        if wiki_st == "error":
            return "error", 0, wiki_err or "Wiki compilation failed"
        if wiki_st in WIKI_GATES:
            return wiki_st, 55 if wiki_st == "awaiting_approval" else 80, wiki_msg or wiki_st
        return "processing", wiki_prog or 50, wiki_msg or "Compiling wiki..."

    # Verbatim sources have no wiki branch: aggregate == chunk branch.
    if getattr(source, "preserve_verbatim", False) or wiki_st in ("skipped", "pending"):
        if chunk_st == "ready":
            return "ready", 100, chunk_msg or "Verbatim: indexed, ready"
        if chunk_st == "error":
            return "error", 0, chunk_err or "Chunk indexing failed"
        return "processing", chunk_prog or 50, chunk_msg or "Indexing chunks..."

    if chunk_st == "ready" and wiki_st == "ready":
        return "ready", 100, "Ready (chunks & wiki compiled)"

    if chunk_st == "error" and wiki_st == "error":
        return "error", 0, f"Chunk error: {chunk_err}; Wiki error: {wiki_err}"

    # Human gates on branch B keep their status so the approval UI/API work.
    if wiki_st in WIKI_GATES:
        if wiki_st == "awaiting_approval":
            prog, default = 55, "Awaiting approval for wiki compilation"
        else:
            prog, default = 80, "Compilation plan ready — awaiting review"
        msg = wiki_msg or default
        if chunk_st == "ready":
            msg += " (Raw chunks already searchable)"
        elif chunk_st == "error":
            msg += f" (Chunk error: {chunk_err})"
        return wiki_st, prog, msg

    # Exactly one branch ready, the other failed -> partial.
    if chunk_st == "ready" and wiki_st == "error":
        return "partial", 100, f"Raw chunks searchable. Wiki compilation failed: {wiki_err}"
    if wiki_st == "ready" and chunk_st == "error":
        return "partial", 100, f"Wiki ready. Raw chunk indexing failed: {chunk_err}"

    if chunk_st == "ready":
        overall = int(0.3 * 100 + 0.7 * (wiki_prog or 50))
        return "processing", overall, (wiki_msg or "Wiki compilation in progress...") + " (Raw chunks searchable)"

    if wiki_st == "ready":
        # Wiki is already searchable; a (re)index of raw chunks — e.g. the legacy
        # backfill — must not take a ready source out of 'ready'.
        return "ready", 100, "Wiki ready. Indexing raw chunks..."

    if chunk_st == "error":
        return "processing", wiki_prog or 50, f"Chunk error: {chunk_err}; compiling wiki..."
    if wiki_st == "error":
        return "processing", chunk_prog or 50, f"Wiki error: {wiki_err}; indexing chunks..."

    overall = int(0.3 * chunk_prog + 0.7 * wiki_prog)
    return "processing", max(5, overall), wiki_msg or chunk_msg or "Processing..."


async def update_source_dual_status(session, source) -> None:
    """Recompute the aggregate status of `source` inside the caller's transaction.

    Flushes the caller's own branch fields, then re-reads the row with FOR UPDATE
    so the other branch's latest committed state is used. The caller commits.
    """
    from app.database.models import Source

    await session.flush()
    await session.execute(
        select(Source)
        .where(Source.id == source.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    st, prog, msg = compute_source_dual_status(source)
    source.status = st
    source.progress = prog
    source.progress_message = msg


_BRANCH_FIELDS = {
    "chunk": ("chunk_status", "chunk_progress", "chunk_progress_message", "chunk_error_message"),
    "wiki": ("wiki_status", "wiki_progress", "wiki_progress_message", "wiki_error_message"),
}


async def set_branch_state(
    source_id: uuid.UUID,
    branch: str,
    status: Optional[str] = None,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    error: Optional[str] = None,
    session=None,
) -> Optional[str]:
    """Atomically update one branch's fields and the aggregate; commits.

    Uses its own session unless one is given. Returns the new aggregate status,
    or None if the source no longer exists.
    """
    from app.database import async_session_factory
    from app.database.models import Source

    st_f, prog_f, msg_f, err_f = _BRANCH_FIELDS[branch]

    async def _apply(s) -> Optional[str]:
        await s.flush()
        src = (await s.execute(
            select(Source)
            .where(Source.id == source_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if not src:
            return None
        if status is not None:
            setattr(src, st_f, status)
        if progress is not None:
            setattr(src, prog_f, progress)
        if message is not None:
            setattr(src, msg_f, message)
        if error is not None:
            setattr(src, err_f, error)
            src.error_message = error
        agg, agg_prog, agg_msg = compute_source_dual_status(src)
        src.status, src.progress, src.progress_message = agg, agg_prog, agg_msg
        await s.commit()
        return agg

    if session is not None:
        return await _apply(session)
    async with async_session_factory() as s:
        try:
            return await _apply(s)
        except Exception as e:
            logger.warning(f"set_branch_state({source_id}, {branch}) failed: {e}")
            raise


def wiki_attempt_of(source) -> Optional[str]:
    """Attempt id that branch-B jobs of `source` must carry.

    Falls back to the global attempt_id for sources whose branch B started
    before wiki_attempt_id existed.
    """
    attempt = getattr(source, "wiki_attempt_id", None) or getattr(source, "attempt_id", None)
    return str(attempt) if attempt else None


def start_wiki_attempt(source) -> str:
    """Begin a new branch-B run: jobs from any earlier wiki run become stale.

    The global attempt_id and chunk_attempt_id are untouched, so a running
    branch A keeps going. The caller commits before enqueueing.
    """
    source.wiki_attempt_id = uuid.uuid4()
    return str(source.wiki_attempt_id)


def reset_branches(source, wiki_skipped: bool = False) -> None:
    """Reset both branches to pending at the start of a fresh ingest attempt."""
    source.chunk_status = "pending"
    source.chunk_progress = 0
    source.chunk_progress_message = None
    source.chunk_error_message = None
    source.wiki_status = "skipped" if wiki_skipped else "pending"
    source.wiki_progress = 100 if wiki_skipped else 0
    source.wiki_progress_message = "Skipped (verbatim source)" if wiki_skipped else None
    source.wiki_error_message = None
