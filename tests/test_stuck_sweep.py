import uuid
from types import SimpleNamespace

import pytest

from app import worker
from app.config import settings


class _FakeRedis:
    def __init__(self, jobs=None, error=None):
        self._jobs = jobs or []
        self._error = error

    async def queued_jobs(self):
        if self._error:
            raise self._error
        return self._jobs


async def test_pending_job_source_ids_collects_args_and_kwargs():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    redis = _FakeRedis([
        SimpleNamespace(args=(str(a), str(uuid.uuid4())), kwargs={}),
        SimpleNamespace(args=(), kwargs={"source_id": str(b), "limit": 500, "mode": "auto"}),
        SimpleNamespace(args=(c,), kwargs=None),
        None,
    ])

    busy = await worker._source_ids_with_pending_jobs(redis)

    assert {a, b, c} <= busy


async def test_sweep_does_nothing_when_queue_unreadable(monkeypatch):
    import app.database as _db

    def _no_db():
        raise AssertionError("sweep must not touch the database when the queue can't be read")

    monkeypatch.setattr(_db, "async_session_factory", _no_db)

    swept = await worker.sweep_stuck_processing_cron({"redis": _FakeRedis(error=ConnectionError("down"))})

    assert swept == 0


@pytest.mark.parametrize("cls", [worker.WorkerSettings, worker.SkillWorkerSettings])
def test_workers_wait_for_running_jobs_on_shutdown(cls):
    assert cls.job_completion_wait == settings.worker_shutdown_wait_s > 0
