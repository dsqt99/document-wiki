"""Read-only status of the already queued recovery jobs. Never enqueue work."""
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from arq.jobs import Job
from sqlalchemy import select
from app.database import async_session_factory
from app.database.models import Source, SourceCompilationPlan
from app.routers.sources import get_arq_pool


async def main():
    journal = json.loads(Path('/tmp/cahy-selective-recovery.json').read_text(encoding='utf-8'))
    pool = await get_arq_pool()
    try:
        jobs = {}
        for item in journal['results']:
            if item.get('job_id'):
                jobs[item['id']] = {
                    'job_id': item['job_id'],
                    'job_status': await Job(item['job_id'], pool).status(),
                    'live_lease_seconds': await pool.ttl('arq:in-progress:' + item['job_id']),
                }
        async with async_session_factory() as db:
            rows = (await db.execute(select(Source, SourceCompilationPlan).outerjoin(
                SourceCompilationPlan, SourceCompilationPlan.source_id == Source.id
            ).where(Source.status != 'ready'))).all()
            result = {'at_utc': datetime.now(timezone.utc).isoformat(), 'read_only': True,
                'sources': [{
                    'id': str(source.id), 'status': source.status,
                    'wiki_status': source.wiki_status, 'phase': source.pipeline_phase,
                    'progress': source.wiki_progress,
                    'draft_count': len((plan.plan_json or {}).get('_page_drafts', {})) if plan else 0,
                    'planned_pages': len((plan.plan_json or {}).get('pages', [])) if plan else 0,
                    **jobs.get(str(source.id), {}),
                } for source, plan in rows]}
        Path('/tmp/cahy-recovery-current.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
    finally:
        await pool.aclose()


asyncio.run(main())
