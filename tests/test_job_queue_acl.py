"""Worker visibility must not expose Redis metadata beyond document permissions."""
import json
import types
import uuid
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import true


def fixtures(function, args, visible=()):
    job = types.SimpleNamespace(job_id='job-1', function=function, args=args, score=1, enqueue_time=None)
    pipeline = types.SimpleNamespace(exists=Mock(), execute=AsyncMock(return_value=[True]))
    pool = types.SimpleNamespace(queued_jobs=AsyncMock(side_effect=[[job], []]),
        pipeline=Mock(return_value=pipeline),
        mget=AsyncMock(return_value=[json.dumps({'progress': 20, 'message': 'SECRET PAGE TITLE'})]))
    db = types.SimpleNamespace(execute=AsyncMock(return_value=types.SimpleNamespace(
        scalars=lambda: types.SimpleNamespace(all=lambda: list(visible)))))
    return db, pool


@pytest.mark.asyncio
async def test_job_for_filtered_source_exposes_no_title_or_progress():
    from app.services.job_queue import list_jobs
    db, pool = fixtures('ingest_file_task', (str(uuid.uuid4()),))
    result = await list_jobs(db, pool, true())
    assert result == {'running': 0, 'queued': 0, 'jobs': []}
    assert 'SECRET' not in json.dumps(result)


@pytest.mark.asyncio
async def test_unbound_rewrite_job_is_hidden_without_proof_of_access():
    from app.services.job_queue import list_jobs
    db, pool = fixtures('rewrite_pages_after_source_delete_task', ([str(uuid.uuid4())], 'SECRET DOCUMENT'))
    result = await list_jobs(db, pool, true())
    assert result['jobs'] == []


@pytest.mark.asyncio
async def test_authorized_source_job_remains_visible():
    from app.services.job_queue import list_jobs
    sid = uuid.uuid4()
    source = types.SimpleNamespace(id=sid, title='Allowed', file_name=None, wiki_status='ready',
        progress=25, progress_message='Allowed progress')
    db, pool = fixtures('ingest_file_task', (str(sid),), [source])
    result = await list_jobs(db, pool, true())
    assert result['jobs'][0]['source_title'] == 'Allowed'
    assert result['jobs'][0]['message'] == 'Allowed progress'


@pytest.mark.asyncio
async def test_admin_can_inspect_unbound_jobs_explicitly():
    from app.services.job_queue import list_jobs
    db, pool = fixtures('rewrite_pages_after_source_delete_task', ([str(uuid.uuid4())], 'Admin only'))
    result = await list_jobs(db, pool, true(), include_unbound=True)
    assert result['jobs'][0]['message'] == 'SECRET PAGE TITLE'


@pytest.mark.asyncio
async def test_include_unbound_never_reveals_a_filtered_source():
    from app.services.job_queue import list_jobs
    db, pool = fixtures('ingest_file_task', (str(uuid.uuid4()),))
    result = await list_jobs(db, pool, true(), include_unbound=True)
    assert result['jobs'] == []
