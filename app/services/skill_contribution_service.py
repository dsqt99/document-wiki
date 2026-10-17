"""Skill contributions: storage-backed drafts of a skill that reviewers approve into versions (06 §3.1)."""

from __future__ import annotations

import asyncio
import io
import logging
import re
import uuid
import zipfile
from pathlib import PurePosixPath
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.models import Skill, SkillContribution, SkillVersion
from app.services.skill_service import (
    as_uuid,
    read_upload,
    strip_zip_ext,
    sync_departments,
    uuid_list,
    version_prefix,
)
from app.services.storage_service import storage_service
from app.utils.text import slugify

logger = logging.getLogger(__name__)

CONTRIB_ROOT = "skill-contributions"
UPLOAD_TITLE_PREFIX = "Upload: "
EDITABLE_STATUSES = ("draft", "needs_revision")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def contribution_prefix(contribution_id) -> str:
    return f"{CONTRIB_ROOT}/{contribution_id}/"


def title_root(title: str) -> str:
    root = _NON_WORD.sub("-", (title or "").lower()).replace("_", "-").strip("-")
    return root or "skill"


def is_safe_member(name: str) -> bool:
    return bool(name) and not name.startswith("/") and "\\" not in name and ".." not in PurePosixPath(name).parts


async def run(fn, *args):
    return await asyncio.to_thread(fn, *args)


async def list_rel(prefix: str) -> list:
    """[(relative path, object)] under ``prefix`` sorted by path."""
    objs = await run(storage_service.list_objects, prefix, True)
    out = [(o.object_name[len(prefix):], o) for o in objs if o.object_name.startswith(prefix)]
    return sorted([x for x in out if x[0]], key=lambda x: x[0])


async def get_contribution(db, contribution_id) -> Optional[SkillContribution]:
    cid = as_uuid(contribution_id)
    if cid is None:
        return None
    stmt = (select(SkillContribution)
            .options(selectinload(SkillContribution.contributor), selectinload(SkillContribution.skill))
            .where(SkillContribution.id == cid))
    return (await db.execute(stmt)).scalar_one_or_none()


async def require_contribution(db, contribution_id) -> SkillContribution:
    c = await get_contribution(db, contribution_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Contribution not found")
    return c


async def _skill_slug(db, skill_id) -> Optional[str]:
    if skill_id is None:
        return None
    return (await db.execute(select(Skill.slug).where(Skill.id == skill_id))).scalar_one_or_none()


# ---------------------------------------------------------------- create


async def create_contribution(db, skill_id, base_version, user_id, title: str, scope_type: str = "global",
                              scope_ids=None) -> SkillContribution:
    cid = uuid.uuid4()
    skill_uuid = as_uuid(skill_id)
    contribution = SkillContribution(
        id=cid, skill_id=skill_uuid, contributor_id=as_uuid(user_id), base_version=base_version,
        status="draft", revision_round=0, scope_type=scope_type or "global",
        scope_ids=[str(x) for x in uuid_list(scope_ids)] or None, title=title,
        storage_path=contribution_prefix(cid),
    )
    db.add(contribution)
    slug = await _skill_slug(db, skill_uuid)
    root = slug or title_root(title)
    dest = contribution.storage_path + root + "/"

    copied = False
    if skill_uuid is not None and base_version is not None:
        version = (await db.execute(select(SkillVersion).where(
            SkillVersion.skill_id == skill_uuid, SkillVersion.version_number == base_version,
        ))).scalar_one_or_none()
        if version is None or not version.storage_path:
            logger.warning("contribution %s: base version %s of skill %s not found", cid, base_version, skill_uuid)
        else:
            base = version.storage_path if version.storage_path.endswith("/") else version.storage_path + "/"
            rels = await list_rel(base)
            if base.endswith("/versions/%s/" % base_version):
                rels = [(r[len("content/"):] if r.startswith("content/") else r, o) for r, o in rels]
            # Keep the version's own root folder when it has one; otherwise wrap files in <root>/.
            wrap = "" if _common_root([r for r, _ in rels]) else root + "/"
            for rel, obj in rels:
                await run(storage_service.copy_object, obj.object_name, contribution.storage_path + wrap + rel)
            copied = bool(rels)
    if not copied and not (skill_uuid is not None and base_version is not None):
        body = f"# {title}\n\nDescribe what this skill does and when to use it.\n"
        await run(storage_service.upload_file, dest + "SKILL.md", body.encode("utf-8"), "text/markdown")
    await db.commit()
    return await require_contribution(db, cid)


async def create_contribution_from_zip(db, file, user, skill_id=None, base_version=None,
                                       scope_type: str = "global", scope_ids=None) -> SkillContribution:
    filename, data = await read_upload(file)
    zip_name = PurePosixPath(filename or "skill.zip").name
    skill_uuid = as_uuid(skill_id)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            members = [(i.filename, zf.read(i)) for i in zf.infolist() if not i.is_dir()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ZIP extraction failed: {e}")
    members = [(n, b) for n, b in members if is_safe_member(n)]
    if not members:
        raise HTTPException(status_code=400, detail="ZIP file contains no files.")

    firsts = {n.split("/", 1)[0] for n, _ in members}
    shared_root = len(firsts) == 1 and all("/" in n for n, _ in members)
    if not shared_root:
        root = await _skill_slug(db, skill_uuid) or slugify(strip_zip_ext(zip_name)) or "skill"
        members = [(f"{root}/{n}", b) for n, b in members]

    cid = uuid.uuid4()
    prefix = contribution_prefix(cid)
    contribution = SkillContribution(
        id=cid, skill_id=skill_uuid, contributor_id=getattr(user, "id", None), base_version=base_version,
        status="pending", revision_round=0, scope_type=scope_type or "global",
        scope_ids=[str(x) for x in uuid_list(scope_ids)] or None,
        title=f"{UPLOAD_TITLE_PREFIX}{zip_name}"[:200], storage_path=prefix,
    )
    try:
        for name, blob in members:
            await run(storage_service.upload_file, prefix + name, blob, "application/octet-stream")
    except Exception as e:
        try:
            await run(storage_service.delete_prefix, prefix)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"ZIP extraction failed: {e}")
    db.add(contribution)
    await db.commit()
    return await require_contribution(db, cid)


# ---------------------------------------------------------------- transitions


async def submit_contribution(db, contribution_id) -> SkillContribution:
    c = await require_contribution(db, contribution_id)
    c.status = "pending"
    await db.commit()
    return c


async def reject_contribution(db, contribution_id) -> SkillContribution:
    c = await require_contribution(db, contribution_id)
    c.status = "draft"
    await db.commit()
    return c


def _new_skill_name(title: str) -> str:
    name = title or "skill"
    if name.startswith(UPLOAD_TITLE_PREFIX):
        name = strip_zip_ext(name[len(UPLOAD_TITLE_PREFIX):])
    return name.strip() or "skill"


async def approve_contribution(db, contribution_id, admin_id, final_scope_type: Optional[str] = None,
                               final_scope_ids=None) -> Skill:
    c = await require_contribution(db, contribution_id)
    prefix = c.storage_path or contribution_prefix(c.id)
    content_hash = await run(storage_service.calculate_prefix_hash, prefix)

    if c.skill_id is not None:
        same = (await db.execute(select(SkillVersion.id).where(
            SkillVersion.skill_id == c.skill_id, SkillVersion.version_hash == content_hash,
        ).limit(1))).first()
        if same is not None:
            c.status = "rejected"
            await db.commit()
            raise HTTPException(status_code=400,
                                detail="This contribution is identical to an existing version of the skill.")

    scope_type = final_scope_type or c.scope_type or "global"
    scope_ids = uuid_list(final_scope_ids if final_scope_ids is not None else c.scope_ids)

    skill = None
    if c.skill_id is not None:
        skill = (await db.execute(select(Skill).options(selectinload(Skill.skill_departments))
                                  .where(Skill.id == c.skill_id))).scalar_one_or_none()
    if skill is None:
        name = _new_skill_name(c.title)
        skill = (await db.execute(select(Skill).options(selectinload(Skill.skill_departments))
                                  .where(Skill.name == name))).scalar_one_or_none()
        if skill is None:
            skill = Skill(id=uuid.uuid4(), name=name, slug=slugify(name) or name, current_version=0,
                          status="processing", scope_type=scope_type, skill_departments=[])
            db.add(skill)
            await db.flush()
    elif final_scope_type:
        skill.scope_type = final_scope_type

    if scope_type == "department" and scope_ids:
        skill.scope_type = "department"
        skill.scope_id = scope_ids[0]
        sync_departments(skill, scope_ids)
    elif scope_type == "global":
        skill.scope_type = "global"
        skill.scope_id = None
        sync_departments(skill, [])

    n = (skill.current_version or 0) + 1
    dest = version_prefix(skill.id, n)
    await run(storage_service.copy_prefix, prefix, dest)

    db.add(SkillVersion(
        id=uuid.uuid4(), skill_id=skill.id, version_number=n, version_hash=content_hash, storage_path=dest,
        changelog=f"Approved contribution: {c.title}", created_by=c.contributor_id,
    ))
    skill.current_version = n
    skill.storage_path = dest
    skill.version_hash = content_hash
    skill.status = "active"
    c.status = "approved"
    c.skill_id = skill.id
    await db.commit()
    return skill


# ---------------------------------------------------------------- file helpers


async def contribution_root(db, c: SkillContribution) -> str:
    rels = await list_rel(c.storage_path or contribution_prefix(c.id))
    if rels:
        return rels[0][0].split("/", 1)[0]
    slug = await _skill_slug(db, c.skill_id)
    if slug:
        return slug
    title = c.title or ""
    if title.startswith(UPLOAD_TITLE_PREFIX):
        title = strip_zip_ext(title[len(UPLOAD_TITLE_PREFIX):])
    return slugify(title) or "skill"


def under_root(root: str, path: str) -> str:
    path = (path or "").strip().lstrip("/")
    return path if path.startswith(root + "/") else f"{root}/{path}"


def _common_root(paths: list[str]) -> Optional[str]:
    if not paths or not all("/" in p for p in paths):
        return None
    firsts = {p.split("/", 1)[0] for p in paths}
    return firsts.pop() if len(firsts) == 1 else None


async def diff_status(db, c: SkillContribution) -> dict:
    ours = {rel: (o.size, (o.etag or "").strip('"')) for rel, o in await list_rel(c.storage_path or "")}
    theirs: dict = {}
    if c.skill_id is not None:
        latest = (await db.execute(select(SkillVersion).where(SkillVersion.skill_id == c.skill_id)
                                   .order_by(SkillVersion.version_number.desc()).limit(1))).scalar_one_or_none()
        base = latest.storage_path if latest is not None else None
        if base:
            base = base if base.endswith("/") else base + "/"
            if base.endswith("/content/"):
                base = base[: -len("content/")]
            for rel, o in await list_rel(base):
                if rel.startswith("content/"):
                    rel = rel[len("content/"):]
                theirs[rel] = (o.size, (o.etag or "").strip('"'))

    our_root, their_root = _common_root(list(ours)), _common_root(list(theirs))
    if our_root and their_root:
        def strip(p, r):
            return p[len(r) + 1:]
        a = {strip(p, our_root): v for p, v in ours.items()}
        b = {strip(p, their_root): v for p, v in theirs.items()}

        def key(p):
            return f"{our_root}/{p}"
    else:
        a, b = ours, theirs

        def key(p):
            return p

    out: dict[str, str] = {}
    for p, v in a.items():
        if p not in b:
            out[key(p)] = "A"
        elif b[p] != v:
            out[key(p)] = "M"
    for p in b:
        if p not in a:
            out[key(p)] = "D"
    return out
