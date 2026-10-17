"""Background jobs for the skill catalogue and the daily statistics rollup (06 §2.5, §8.3)."""

from __future__ import annotations

import asyncio
import io
import logging
import mimetypes
import zipfile
from pathlib import Path

from sqlalchemy import delete, select, update

logger = logging.getLogger(__name__)

MAX_FILES = 100
MAX_UNCOMPRESSED_BYTES = 10 * 1024 * 1024
FAILED_STATUS = "error"
FAILED_STATUS_FALLBACK = "deprecated"  # the skill_status DB enum has no "error" value


class SkillZipError(ValueError):
    pass


def read_members(data: bytes) -> list[tuple[str, bytes]]:
    from app.services.skill_contribution_service import is_safe_member

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > MAX_FILES:
            raise SkillZipError(f"ZIP has {len(infos)} files (max {MAX_FILES})")
        for i in infos:
            if not is_safe_member(i.filename):
                raise SkillZipError(f"Unsafe path in ZIP: {i.filename}")
        if sum(i.file_size for i in infos) > MAX_UNCOMPRESSED_BYTES:
            raise SkillZipError("ZIP content exceeds 10 MB")
        out, total = [], 0
        for i in infos:
            blob = zf.read(i)
            total += len(blob)
            if total > MAX_UNCOMPRESSED_BYTES:
                raise SkillZipError("ZIP content exceeds 10 MB")
            out.append((i.filename, blob))
        return out


async def _mark_failed(skill_id) -> None:
    from app import database
    from app.database.models import Skill

    for status in (FAILED_STATUS, FAILED_STATUS_FALLBACK):
        try:
            async with database.async_session_factory() as session:
                await session.execute(update(Skill).where(Skill.id == skill_id).values(status=status))
                await session.commit()
            return
        except Exception as e:
            logger.warning("could not set skill %s status to %s: %s", skill_id, status, e)


async def ingest_skill_task(ctx, skill_id, version_id, temp_path, filename=None):
    from app import database
    from app.database.models import Skill, SkillVersion
    from app.services.skill_service import as_uuid, content_prefix
    from app.services.storage_service import storage_service

    sid, vid = as_uuid(skill_id), as_uuid(version_id)
    try:
        data = await asyncio.to_thread(Path(temp_path).read_bytes)
        members = read_members(data)
        async with database.async_session_factory() as session:
            skill = await session.get(Skill, sid)
            version = await session.get(SkillVersion, vid)
            if skill is None or version is None:
                logger.warning("ingest_skill_task: skill %s / version %s gone", skill_id, version_id)
                return {"status": "missing"}
            prefix = content_prefix(skill.id, version.version_number)
            await asyncio.to_thread(storage_service.delete_prefix, prefix)
            for name, blob in members:
                ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
                await asyncio.to_thread(storage_service.upload_file, prefix + name, blob, ctype)
            prefix_hash = await asyncio.to_thread(storage_service.calculate_prefix_hash, prefix)

            version.storage_path = prefix
            version.version_hash = prefix_hash
            if (skill.current_version or 0) <= version.version_number:
                skill.current_version = version.version_number
                skill.storage_path = prefix
                skill.version_hash = prefix_hash
            skill.status = "active"
            await session.commit()
        logger.info("ingested skill %s v%s (%d files)", skill_id, version.version_number, len(members))
        return {"status": "active", "files": len(members)}
    except Exception as e:
        logger.error("ingest_skill_task failed for skill %s (%s): %s", skill_id, filename, e)
        await _mark_failed(sid)
        return {"status": FAILED_STATUS, "error": str(e)}
    finally:
        try:
            Path(temp_path).unlink(missing_ok=True)
        except OSError as e:
            logger.warning("could not remove temp upload %s: %s", temp_path, e)


async def delete_skill_task(ctx, skill_id):
    from app import database
    from app.database.models import Skill, SkillContribution
    from app.services.skill_service import as_uuid
    from app.services.storage_service import storage_service

    sid = as_uuid(skill_id)
    async with database.async_session_factory() as session:
        paths = (await session.execute(
            select(SkillContribution.storage_path).where(SkillContribution.skill_id == sid)
        )).scalars().all()
        for prefix in [f"skills/{sid}/"] + [p for p in paths if p]:
            try:
                await asyncio.to_thread(storage_service.delete_prefix, prefix)
            except Exception as e:
                logger.warning("delete_skill_task: could not delete %s: %s", prefix, e)
        await session.execute(delete(SkillContribution).where(SkillContribution.skill_id == sid))
        await session.execute(delete(Skill).where(Skill.id == sid))
        await session.commit()
    logger.info("deleted skill %s", skill_id)
    return {"status": "deleted"}


async def daily_stats_rollup_cron(ctx):
    from app.services import stats_aggregator

    target = stats_aggregator.yesterday_utc()
    written = await stats_aggregator.run_daily_rollup(target)
    return {"target_date": target.isoformat(), "sections_written": written}
