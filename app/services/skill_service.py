"""Skill catalogue service (06 §2.5).

Content hashes: ``_calculate_zip_content_hash`` hashes ``"<entry>:<md5>\\n"`` for each
file entry sorted by name. That matches ``storage_service.calculate_prefix_hash`` of a
version's ``content/`` prefix (MinIO's single-part etag is the md5), so a ZIP, its
ingested version and a contribution with the same files all share one hash.
"""

from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import uuid
import zipfile
from pathlib import Path
from typing import Any, Iterable, Optional

from fastapi import HTTPException
from sqlalchemy import and_, exists, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.database.models import Department, Skill, SkillContribution, SkillDepartment, SkillVersion
from app.utils.text import slugify

logger = logging.getLogger(__name__)

HIDDEN_STATUSES = ("deleting", "archived")
SKILL_MD = "skill.md"
INGEST_JOB = "ingest_skill_task"
DELETE_JOB = "delete_skill_task"


# ---------------------------------------------------------------- module helpers


def status_value(status) -> str:
    return getattr(status, "value", status) or ""


def version_prefix(skill_id, version: int) -> str:
    return f"skills/{skill_id}/versions/{version}/"


def content_prefix(skill_id, version: int) -> str:
    return version_prefix(skill_id, version) + "content/"


def temp_upload_dir() -> Path:
    from app import worker

    path = Path(worker.TEMP_UPLOAD_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def enqueue(job: str, *args) -> None:
    """Push a job onto the skills queue; failures propagate to the caller."""
    from app import worker

    pool = await worker.get_arq_pool()
    try:
        await pool.enqueue_job(job, *args, _queue_name=worker.SKILLS_QUEUE)
    finally:
        closer = getattr(pool, "aclose", None) or getattr(pool, "close", None)
        if closer is not None:
            try:
                res = closer()
                if asyncio.iscoroutine(res):
                    await res
            except Exception:
                pass


def as_uuid(value) -> Optional[uuid.UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


def uuid_list(values) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for v in values or []:
        u = as_uuid(v)
        if u is not None and u not in out:
            out.append(u)
    return out


def sync_departments(skill: Skill, dept_ids: Iterable) -> None:
    """Make skill.skill_departments match ``dept_ids`` (relationship must be loaded or new)."""
    wanted = uuid_list(dept_ids)
    current = list(skill.skill_departments or [])
    keep = [sd for sd in current if sd.department_id in wanted]
    have = {sd.department_id for sd in keep}
    skill.skill_departments = keep + [SkillDepartment(department_id=d) for d in wanted if d not in have]


async def read_upload(file) -> tuple[str, bytes]:
    """(filename, bytes) from an UploadFile-like object or a (name, data) tuple."""
    if isinstance(file, tuple):
        return file[0], file[1]
    data = await file.read()
    return file.filename or "skill.zip", data


def strip_zip_ext(filename: str) -> str:
    name = Path(filename or "").name
    return name[:-4] if name.lower().endswith(".zip") else name


async def department_names(db, ids: Iterable) -> dict:
    ids = uuid_list(ids)
    if not ids:
        return {}
    rows = await db.execute(select(Department.id, Department.name).where(Department.id.in_(ids)))
    return dict(rows.all())


def skill_to_dict(skill: Skill, names: Optional[dict] = None) -> dict:
    ids = list(skill.department_ids)
    names = names or {}
    return {
        "id": skill.id,
        "name": skill.name,
        "slug": skill.slug,
        "department_ids": ids,
        "department_names": [names[d] for d in ids if d in names],
        "current_version": skill.current_version or 0,
        "version_hash": skill.version_hash,
        "status": status_value(skill.status),
        "scope_type": skill.scope_type or "global",
        "scope_id": skill.scope_id,
        "is_system": bool(skill.is_system),
        "created_at": skill.created_at,
        "updated_at": skill.updated_at,
    }


class SkillService:
    # ------------------------------------------------------------ ZIP helpers

    @staticmethod
    def _calculate_zip_content_hash(data: bytes) -> Optional[str]:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                entries = sorted((i for i in zf.infolist() if not i.is_dir()), key=lambda i: i.filename)
                digest = hashlib.sha256()
                for info in entries:
                    md5 = hashlib.md5(zf.read(info)).hexdigest()
                    digest.update(f"{info.filename}:{md5}\n".encode())
                return digest.hexdigest()
        except (zipfile.BadZipFile, OSError, ValueError, RuntimeError):
            return None

    @staticmethod
    def validate_zip_content(data: bytes, zip_name: str) -> tuple[bool, Optional[str]]:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = [n.lower() for n in zf.namelist()]
        except (zipfile.BadZipFile, OSError, ValueError):
            return False, "Invalid or corrupted ZIP file."
        own = f"{(zip_name or '').lower()}/{SKILL_MD}"
        if any(n == SKILL_MD or n == own or n.endswith("/" + SKILL_MD) for n in names):
            return True, None
        return False, "Missing mandatory SKILL.md file in ZIP package."

    @staticmethod
    def _write_temp(data: bytes) -> str:
        path = temp_upload_dir() / f"{uuid.uuid4()}.zip"
        path.write_bytes(data)
        return str(path)

    @staticmethod
    def _remove_temp(path: Optional[str]) -> None:
        if path:
            try:
                Path(path).unlink(missing_ok=True)
            except OSError as e:
                logger.warning("could not remove temp upload %s: %s", path, e)

    # ------------------------------------------------------------ lookups

    @staticmethod
    def _skill_query():
        return select(Skill).options(selectinload(Skill.skill_departments))

    async def _find(self, db, slug_or_id: str, include_hidden: bool = False) -> Optional[Skill]:
        sid = as_uuid(slug_or_id)
        cond = Skill.id == sid if sid else Skill.slug == slug_or_id
        skill = (await db.execute(self._skill_query().where(cond))).scalar_one_or_none()
        if skill is None and sid is not None:
            skill = (await db.execute(self._skill_query().where(Skill.slug == slug_or_id))).scalar_one_or_none()
        if skill is not None and not include_hidden and status_value(skill.status) in HIDDEN_STATUSES:
            return None
        return skill

    async def _require(self, db, slug_or_id: str) -> Skill:
        skill = await self._find(db, slug_or_id)
        if skill is None:
            raise HTTPException(status_code=404, detail="Skill not found")
        return skill

    # ------------------------------------------------------------ upload

    @staticmethod
    def _apply_scope(skill: Skill, department_ids, scope_type, scope_id) -> None:
        depts = uuid_list(department_ids)
        sid = as_uuid(scope_id)
        if scope_type == "department" or depts:
            if sid and sid not in depts:
                depts = [sid] + depts
            skill.scope_type = "department"
            skill.scope_id = sid or (depts[0] if depts else None)
            sync_departments(skill, depts)
        else:
            skill.scope_type = "global"
            skill.scope_id = None
            sync_departments(skill, [])

    async def upload_skills(self, db, files, department_ids=None, scope_type: str = "global", scope_id=None,
                            force: bool = False, current_user_id=None) -> list[dict]:
        results: list[dict] = []
        conflicts: list[str] = []
        jobs: list[tuple] = []
        temps: list[str] = []
        try:
            for f in files or []:
                filename, data = await read_upload(f)
                name = strip_zip_ext(filename)
                content_hash = self._calculate_zip_content_hash(data)
                if content_hash is None:
                    results.append({"name": name, "status": "error", "message": "Invalid ZIP file."})
                    continue
                ok, err = self.validate_zip_content(data, name)
                if not ok:
                    results.append({"name": name, "status": "rejected", "message": err})
                    continue

                skill = (await db.execute(self._skill_query().where(Skill.name == name))).scalar_one_or_none()
                if skill is not None and not force:
                    conflicts.append(name)
                    continue
                if skill is not None:
                    self._apply_scope(skill, department_ids, scope_type, scope_id)
                    if skill.version_hash == content_hash:
                        results.append({"name": name, "status": "updated_metadata",
                                        "message": "Metadata updated, content unchanged."})
                        continue
                    skill.status = "processing"
                    skill.version_hash = content_hash
                    skill.current_version = (skill.current_version or 0) + 1
                else:
                    skill = Skill(id=uuid.uuid4(), name=name, slug=slugify(name) or name, status="processing",
                                  current_version=1, version_hash=content_hash, skill_departments=[])
                    self._apply_scope(skill, department_ids, scope_type, scope_id)
                    db.add(skill)

                version = SkillVersion(
                    id=uuid.uuid4(), skill_id=skill.id, version_number=skill.current_version,
                    version_hash=content_hash, storage_path=content_prefix(skill.id, skill.current_version),
                    created_by=as_uuid(current_user_id),
                )
                db.add(version)
                temp_path = self._write_temp(data)
                temps.append(temp_path)
                jobs.append((str(skill.id), str(version.id), temp_path, filename))
                results.append({"name": name, "status": "processing", "skill_id": str(skill.id),
                                "version": skill.current_version})

            if conflicts:
                await db.rollback()
                for t in temps:
                    self._remove_temp(t)
                raise HTTPException(status_code=409, detail={
                    "message": "Duplicate skill names detected", "conflicts": conflicts,
                })
            await db.commit()
        except HTTPException:
            raise
        except Exception:
            await db.rollback()
            for t in temps:
                self._remove_temp(t)
            raise

        for job in jobs:
            try:
                await enqueue(INGEST_JOB, *job)
            except Exception as e:
                logger.error("could not enqueue skill ingest for %s: %s", job[0], e)
                self._remove_temp(job[2])
        return results

    async def reupload_skill(self, db, slug_or_uuid: str, file, user_id=None) -> dict:
        skill = await self._require(db, slug_or_uuid)
        filename, data = await read_upload(file)
        content_hash = self._calculate_zip_content_hash(data)
        if content_hash is None:
            raise HTTPException(status_code=400, detail="Invalid ZIP file.")
        expected = f"{skill.name}.zip"
        if Path(filename).name != expected:
            raise HTTPException(
                status_code=400, detail=f"Filename mismatch. Expected '{expected}', got '{filename}'."
            )
        if content_hash == skill.version_hash:
            return {"status": "skipped", "message": "Content unchanged. No new version created.",
                    "skill_id": str(skill.id), "version": skill.current_version}
        ok, err = self.validate_zip_content(data, skill.name)
        if not ok:
            raise HTTPException(status_code=400, detail=err)

        skill.current_version = (skill.current_version or 0) + 1
        skill.version_hash = content_hash
        skill.status = "processing"
        version = SkillVersion(
            id=uuid.uuid4(), skill_id=skill.id, version_number=skill.current_version, version_hash=content_hash,
            storage_path=content_prefix(skill.id, skill.current_version), created_by=as_uuid(user_id),
        )
        db.add(version)
        temp_path = self._write_temp(data)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            self._remove_temp(temp_path)
            raise
        try:
            await enqueue(INGEST_JOB, str(skill.id), str(version.id), temp_path, filename)
        except Exception as e:
            logger.error("could not enqueue skill ingest for %s: %s", skill.id, e)
            self._remove_temp(temp_path)
        return {"status": "processing", "skill_id": str(skill.id), "version": skill.current_version}

    # ------------------------------------------------------------ read

    async def list_skills(self, db, allowed_department_ids=None, q: Optional[str] = None, department_id=None,
                          scope_type: Optional[str] = None, scope_id=None, ids=None, cursor: Optional[str] = None,
                          limit: int = 20) -> tuple[list[Skill], int]:
        conds = [Skill.status.not_in(HIDDEN_STATUSES)]
        if allowed_department_ids is not None:
            allowed = uuid_list(allowed_department_ids)
            no_dept = ~exists().where(SkillDepartment.skill_id == Skill.id)
            if allowed:
                in_dept = exists().where(SkillDepartment.skill_id == Skill.id,
                                         SkillDepartment.department_id.in_(allowed))
                conds.append(or_(no_dept, in_dept))
            else:
                conds.append(no_dept)
        if ids:
            conds.append(Skill.id.in_(uuid_list(ids)))
        if q and q.strip():
            conds.append(Skill.name.ilike(f"%{q.strip()}%"))
        if department_id:
            conds.append(exists().where(SkillDepartment.skill_id == Skill.id,
                                        SkillDepartment.department_id == as_uuid(department_id)))
        if scope_type:
            conds.append(Skill.scope_type == scope_type)
            if scope_id:
                conds.append(Skill.scope_id == as_uuid(scope_id))

        total = (await db.execute(select(func.count(func.distinct(Skill.id))).where(*conds))).scalar() or 0
        page_conds = list(conds)
        if cursor:
            anchor = (await db.execute(select(Skill.updated_at, Skill.id).where(Skill.slug == cursor))).first()
            if anchor is not None:
                ts, aid = anchor
                page_conds.append(or_(Skill.updated_at < ts, and_(Skill.updated_at == ts, Skill.id < aid)))
        stmt = (self._skill_query().where(*page_conds)
                .order_by(Skill.updated_at.desc(), Skill.id.desc()).limit(max(1, int(limit or 20))))
        items = list((await db.execute(stmt)).scalars().unique().all())
        return items, int(total)

    async def get_skill(self, db, slug: str, version_number: Optional[int] = None) -> Skill:
        try:
            skill = await self._require(db, slug)
            if version_number is not None and version_number != skill.current_version:
                found = (await db.execute(select(SkillVersion.id).where(
                    SkillVersion.skill_id == skill.id, SkillVersion.version_number == version_number,
                ))).first()
                if found is None:
                    raise HTTPException(status_code=404, detail=f"Version {version_number} not found")
            return skill
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("get_skill(%s) failed: %s", slug, e)
            raise HTTPException(status_code=500, detail="Internal server error while fetching skill")

    async def get_version(self, db, skill: Skill, version_number: Optional[int]) -> Optional[SkillVersion]:
        n = version_number if version_number is not None else skill.current_version
        return (await db.execute(select(SkillVersion).where(
            SkillVersion.skill_id == skill.id, SkillVersion.version_number == n,
        ))).scalar_one_or_none()

    async def list_versions(self, db, slug: str) -> list[SkillVersion]:
        skill = await self._require(db, slug)
        rows = await db.execute(select(SkillVersion).where(SkillVersion.skill_id == skill.id)
                                .order_by(SkillVersion.version_number.desc()))
        return list(rows.scalars().all())

    # ------------------------------------------------------------ write

    async def set_latest_version(self, db, slug: str, version_number: int) -> Skill:
        skill = await self._require(db, slug)
        if version_number == skill.current_version:
            return skill
        version = await self.get_version(db, skill, version_number)
        if version is None:
            raise HTTPException(status_code=404, detail=f"Version {version_number} not found")
        skill.current_version = version.version_number
        skill.version_hash = version.version_hash
        skill.storage_path = version.storage_path
        await db.commit()
        return skill

    async def delete_skill(self, db, slug: str) -> None:
        skill = await self._require(db, slug)
        skill.status = "deleting"
        await db.commit()
        try:
            await enqueue(DELETE_JOB, str(skill.id))
        except Exception as e:
            logger.error("could not enqueue skill delete for %s: %s", skill.id, e)

    async def update_skill(self, db, slug: str, req_data: dict) -> Skill:
        skill = await self._require(db, slug)
        data = dict(req_data or {})
        explicit = set(data.pop("_explicit_fields", None) or [k for k, v in data.items() if v is not None])

        new_name = data.get("name")
        if new_name and new_name != skill.name:
            clash = (await db.execute(select(Skill.id).where(Skill.name == new_name, Skill.id != skill.id))).first()
            if clash is not None:
                raise HTTPException(status_code=409, detail=f"Skill with name '{new_name}' already exists.")
            skill.name = new_name
            skill.slug = slugify(new_name) or new_name

        if "scope_type" in explicit or "department_ids" in explicit:
            sid = as_uuid(data.get("scope_id"))
            depts = uuid_list(list(data.get("department_ids") or []) + ([sid] if sid else []))
            if depts:
                skill.scope_type = "department"
                skill.scope_id = sid or depts[0]
                sync_departments(skill, depts)
            else:
                skill.scope_type = "global"
                skill.scope_id = None
                sync_departments(skill, [])

        if data.get("increment_version"):
            skill.current_version = (skill.current_version or 0) + 1
        await db.commit()
        return await self._require(db, str(skill.id))

    async def bulk_change_scope(self, db, skill_ids, scope_type: str, scope_id=None) -> int:
        ids = uuid_list(skill_ids)
        if not ids:
            return 0
        sid = as_uuid(scope_id) if scope_type == "department" else None
        skills = (await db.execute(self._skill_query().where(Skill.id.in_(ids)))).scalars().all()
        for skill in skills:
            skill.scope_type = "department" if sid else "global"
            skill.scope_id = sid
            sync_departments(skill, [sid] if sid else [])
        await db.commit()
        return len(skills)


skill_service = SkillService()


async def contributions_storage_paths(db, skill_id) -> list[str]:
    rows = await db.execute(select(SkillContribution.storage_path).where(SkillContribution.skill_id == skill_id))
    return [p for p in rows.scalars().all() if p]


async def set_status(db, skill_id, status: str) -> None:
    await db.execute(update(Skill).where(Skill.id == skill_id).values(status=status))
