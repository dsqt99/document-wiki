"""Selective recovery of three inspected sources. No document text is saved."""
import asyncio
import hashlib
import json
import uuid
from pathlib import Path

from sqlalchemy import select
from app import worker
from app.database import async_session_factory
from app.database.models import Source, SourceCompilationPlan, WikiPage
from app.routers.sources import _enqueue, get_arq_pool
from app.services import source_retry

TARGETS = [uuid.UUID(value) for value in (
    'd6de6e95-ee4e-4a31-9377-d4eca7fe77c1',
    'b1372cdc-5cc5-423b-8a1b-1c965ba58889',
    '440a3202-400c-48ea-8647-6c0647fcb642',
)]
OUTPUT = Path('/tmp/cahy-selective-recovery.json')


async def snapshot(db, source):
    plan = (await db.execute(select(SourceCompilationPlan).where(SourceCompilationPlan.source_id == source.id))).scalar_one_or_none()
    document = plan.plan_json if plan else {}
    pages = (await db.execute(select(WikiPage.id, WikiPage.slug, WikiPage.content_md).where(WikiPage.source_ids.any(source.id)).order_by(WikiPage.id))).all()
    return {
        'id': str(source.id), 'status': source.status, 'wiki_status': source.wiki_status,
        'chunk_status': source.chunk_status, 'phase': source.pipeline_phase,
        'raw_text_sha256': hashlib.sha256((source.full_text or '').encode()).hexdigest(),
        'plan_pages': len(document.get('pages', [])), 'draft_count': len(document.get('_page_drafts', [])),
        'pages': [{'id': str(page.id), 'slug': page.slug, 'sha256': hashlib.sha256((page.content_md or '').encode()).hexdigest()} for page in pages],
    }


async def main():
    pool = await get_arq_pool()
    result = {'mode': 'selective_wiki_retry', 'targets': [str(sid) for sid in TARGETS], 'results': []}
    try:
        async with async_session_factory() as db:
            available, _ = await source_retry.ai_ready(db)
        result['provider_ready'] = available
        OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
        if not available:
            print(json.dumps({'provider_ready': False, 'requeued': 0}), flush=True)
            return
        for sid in TARGETS:
            async with async_session_factory() as db:
                source = (await db.execute(select(Source).where(Source.id == sid).with_for_update(skip_locked=True))).scalar_one_or_none()
                busy = {str(value) for value in await worker._source_ids_with_pending_jobs(pool)}
                if source is None or source.status not in ('error', 'partial') or source.wiki_status != 'error' or str(sid) in busy:
                    row = {'id': str(sid), 'action': 'skipped_changed_or_busy'}
                else:
                    row = {'id': str(sid), 'before': await snapshot(db, source)}
                    assert source.chunk_status == 'ready' and (source.full_text or '').strip()
                    assert source_retry.pick_branch(source, 'wiki') == 'wiki'
                    row['action'] = 'starting_retry'
                    result['results'].append(row)
                    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
                    job = await source_retry.requeue_source(db, source, _enqueue, 'wiki')
                    row.update(action='wiki_requeued', job_id=job)
                    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
                    await db.refresh(source)
                    row['after'] = await snapshot(db, source)
                    assert row['before']['raw_text_sha256'] == row['after']['raw_text_sha256']
                    assert row['after']['chunk_status'] == 'ready'
                if row not in result['results']:
                    result['results'].append(row)
                OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2))
                print(json.dumps({key: value for key, value in row.items() if key not in ('before', 'after')}, ensure_ascii=False), flush=True)
    finally:
        await pool.aclose()


if __name__ == '__main__':
    asyncio.run(main())
