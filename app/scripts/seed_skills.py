"""Seed built-in skills from the project ``skills/`` folder. Run: python -m app.scripts.seed_skills"""

import asyncio
import io
import logging
import mimetypes
import zipfile
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

DEFAULT_SKILLS_ROOT = Path(__file__).resolve().parent.parent.parent / "skills"


def _build_zip(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            zf.write(path, f"{folder.name}/{path.relative_to(folder).as_posix()}")
    return buf.getvalue()


def _content_prefix(skill_id, version: int) -> str:
    return f"skills/{skill_id}/versions/{version}/content/"


async def _upload_zip(data: bytes, prefix: str) -> None:
    from app.services.storage_service import storage_service

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            content_type = mimetypes.guess_type(info.filename)[0] or "application/octet-stream"
            await asyncio.to_thread(
                storage_service.upload_file, prefix + info.filename, zf.read(info), content_type
            )


async def _seed_one(folder: Path) -> None:
    from app import database
    from app.database.models import Skill, SkillVersion
    from app.services.skill_service import SkillService

    slug = folder.name
    data = _build_zip(folder)
    content_hash = SkillService._calculate_zip_content_hash(data)

    async with database.async_session_factory() as session:
        try:
            skill = (await session.execute(select(Skill).where(Skill.slug == slug))).scalar_one_or_none()
            if skill is not None:
                if getattr(skill.status, "value", skill.status) == "archived":
                    return
                current = (
                    await session.execute(
                        select(SkillVersion).where(
                            SkillVersion.skill_id == skill.id,
                            SkillVersion.version_number == skill.current_version,
                        )
                    )
                ).scalar_one_or_none()
                if current is not None and current.created_by is not None:
                    return
                if content_hash and content_hash == skill.version_hash:
                    return
                version = (skill.current_version or 0) + 1
                prefix = _content_prefix(skill.id, version)
                session.add(
                    SkillVersion(
                        skill_id=skill.id,
                        version_number=version,
                        version_hash=content_hash,
                        storage_path=prefix,
                        created_by=None,
                    )
                )
                await _upload_zip(data, prefix)
                skill.current_version = version
                skill.version_hash = content_hash
                skill.storage_path = prefix
                skill.status = "active"
            else:
                skill = Skill(
                    name=slug,
                    slug=slug,
                    scope_type="global",
                    current_version=1,
                    version_hash=content_hash,
                    is_system=True,
                    status="active",
                )
                session.add(skill)
                await session.flush()
                prefix = _content_prefix(skill.id, 1)
                skill.storage_path = prefix
                session.add(
                    SkillVersion(
                        skill_id=skill.id,
                        version_number=1,
                        version_hash=content_hash,
                        storage_path=prefix,
                        created_by=None,
                    )
                )
                await _upload_zip(data, prefix)
            await session.commit()
            logger.info("Seeded built-in skill %s", slug)
        except IntegrityError:
            await session.rollback()
            logger.info("Skill %s was seeded concurrently by another process", slug)


async def seed_builtin_skills(skills_root: Optional[Path] = None) -> None:
    root = Path(skills_root) if skills_root else DEFAULT_SKILLS_ROOT
    if not root.is_dir():
        logger.warning("Skills folder %s does not exist; skipping built-in skill seed", root)
        return
    try:
        from app.services.storage_service import storage_service

        await storage_service.ensure_bucket()
    except Exception as e:
        logger.warning("Storage unavailable; skipping built-in skill seed: %s", e)
        return
    for folder in sorted((p for p in root.iterdir() if p.is_dir() and (p / "SKILL.md").is_file()), key=lambda p: p.name):
        try:
            await _seed_one(folder)
        except Exception as e:
            logger.error("Failed to seed skill %s: %s", folder.name, e)


if __name__ == "__main__":
    asyncio.run(seed_builtin_skills())
