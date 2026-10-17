"""Skill catalogue endpoints (06 §2.3-2.4)."""

from __future__ import annotations

import io
import json
import logging
import re
import uuid
import zipfile
from datetime import datetime
from pathlib import PurePosixPath
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import permission_engine
from app.services import skill_contribution_service as contrib
from app.services.auth_service import get_current_user, require_permission
from app.services.skill_service import (
    department_names,
    skill_service,
    skill_to_dict,
    strip_zip_ext,
    uuid_list,
)
from app.services.storage_service import storage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/skills", tags=["skills"])

TEXT_EXTENSIONS = {
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".sh", ".js", ".ts", ".tsx", ".html", ".css", ".sql",
    ".env", ".cfg", ".ini", ".xml", ".csv", ".bat", ".ps1",
}
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,79}$")
SYSTEM_SKILL_ERROR = "Kỹ năng hệ thống chỉ quản trị viên được sửa hoặc xóa"
OWN_DEPT_ERROR = "You can only assign skills to your own departments"


# ---------------------------------------------------------------- models


class SkillResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    department_ids: list[uuid.UUID] = []
    department_names: list[str] = []
    current_version: int
    version_hash: Optional[str] = None
    status: str
    scope_type: str = "global"
    scope_id: Optional[uuid.UUID] = None
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class SkillVersionResponse(BaseModel):
    version_number: int
    version_hash: Optional[str] = None
    storage_path: Optional[str] = None
    changelog: Optional[str] = None
    created_at: Optional[datetime] = None


class SkillListResponse(BaseModel):
    items: list[SkillResponse]
    total: int


class SkillUpdateRequest(BaseModel):
    name: Optional[str] = None
    department_ids: Optional[list[uuid.UUID]] = None
    scope_type: Optional[str] = None
    scope_id: Optional[uuid.UUID] = None
    increment_version: bool = False


class SkillComposeRequest(BaseModel):
    name: str
    description: str
    body: str = ""
    scope_type: str = "global"
    department_ids: list[uuid.UUID] = []


class SkillContentRequest(BaseModel):
    description: Optional[str] = None
    body: str


# ---------------------------------------------------------------- helpers


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


def _perms(user) -> set:
    return permission_engine._get_user_permissions(user)


def _own_depts(user) -> set:
    return permission_engine._as_uuid_set(permission_engine._user_department_ids(user))


async def _response(db, skill) -> SkillResponse:
    names = await department_names(db, skill.department_ids)
    return SkillResponse(**skill_to_dict(skill, names))


async def _require_access(db, user, skill, action: str, *, need_grant: bool = False) -> None:
    """Access check of 06 §2.2; ``need_grant`` also requires some skill:<action> grant for non-admins."""
    if need_grant and not _is_admin(user):
        if permission_engine.get_scope_level(_perms(user), "skill", action) is None:
            raise HTTPException(status_code=403, detail="Access denied")
    if not await permission_engine.can_access_skill(db, user, skill, action):
        raise HTTPException(status_code=403, detail="Access denied")


def _system_guard(user, skill) -> None:
    if skill.is_system and not _is_admin(user):
        raise HTTPException(status_code=403, detail=SYSTEM_SKILL_ERROR)


def _parse_uuid_field(values) -> list[uuid.UUID]:
    """Form lists may arrive as repeated fields, a JSON array or a comma-separated string."""
    flat: list = []
    for v in values or []:
        if isinstance(v, str):
            s = v.strip()
            if s.startswith("["):
                try:
                    flat.extend(json.loads(s))
                    continue
                except ValueError:
                    pass
            flat.extend(p for p in s.split(",") if p.strip())
        else:
            flat.append(v)
    return uuid_list(flat)


def _check_create_scope(user, department_ids, scope_type, scope_id) -> None:
    if _is_admin(user):
        return
    perms = _perms(user)
    if "skill:create:all" in perms:
        return
    if "skill:create:own_dept" not in perms:
        raise HTTPException(status_code=403, detail="Permission required: skill:create")
    own = _own_depts(user)
    depts = set(uuid_list(department_ids))
    if scope_type == "department" and scope_id:
        depts |= set(uuid_list([scope_id]))
    if depts - own:
        raise HTTPException(status_code=403, detail=OWN_DEPT_ERROR)
    if scope_type != "department" and not depts:
        raise HTTPException(status_code=403, detail="You do not have permission to create global skills")


async def _do_upload(db, user, files: list, department_ids, scope_type, scope_id, force: bool) -> dict:
    """``files`` holds UploadFile objects or (filename, bytes) tuples."""
    _check_create_scope(user, department_ids, scope_type, scope_id)
    if not _is_admin(user):
        scope_ids = uuid_list(list(department_ids or []) + ([scope_id] if scope_id else []))
        eff_scope = "department" if (scope_type == "department" or scope_ids) else "global"
        results = []
        for f in files:
            name = f[0] if isinstance(f, tuple) else (f.filename or "skill.zip")
            c = await contrib.create_contribution_from_zip(db, f, user, scope_type=eff_scope, scope_ids=scope_ids)
            results.append({"name": name, "status": "contribution_pending", "contribution_id": str(c.id),
                            "message": "Submitted contribution for review"})
            await _notify_submitted(db, c, user)
        return {"results": results, "message": "Skills submitted for review."}
    results = await skill_service.upload_skills(
        db, files, department_ids=department_ids, scope_type=scope_type, scope_id=scope_id, force=force,
        current_user_id=user.id,
    )
    return {"results": results}


async def _notify_submitted(db, c, user) -> None:
    try:
        from app.services import contribution_service as cs

        await cs.notify_submitted(db, cs.skill_contribution_adapter, c, user)
        await db.commit()
    except Exception as e:
        logger.warning("submitted notification for contribution %s failed: %s", c.id, e)


def _is_text(path: str) -> bool:
    p = PurePosixPath(path or "")
    return p.suffix.lower() in TEXT_EXTENSIONS or p.name.lower() in TEXT_EXTENSIONS


async def _storage_prefix(db, skill, version: Optional[int]) -> Optional[str]:
    if version is not None and version != skill.current_version:
        v = await skill_service.get_version(db, skill, version)
        if v is None:
            raise HTTPException(status_code=404, detail=f"Version {version} not found")
        path = v.storage_path
    else:
        path = skill.storage_path
    if not path:
        return None
    return path if path.endswith("/") else path + "/"


def _missing_key(e: Exception) -> bool:
    return getattr(e, "code", None) in ("NoSuchKey", "NoSuchObject", "NotFound")


async def _try_download(key: str) -> Optional[bytes]:
    try:
        return await contrib.run(storage_service.download_file, key)
    except Exception as e:
        if _missing_key(e):
            return None
        raise


async def _skill_files(prefix: str) -> list[tuple[str, object]]:
    return await contrib.list_rel(prefix)


def _skill_md_rel(rels: list[str], name: str) -> Optional[str]:
    own = f"{name}/skill.md".lower()
    for r in rels:
        if r.lower() == own:
            return r
    for r in rels:
        low = r.lower()
        if low == "skill.md" or low.endswith("/skill.md"):
            return r
    return None


def split_frontmatter(text: str) -> tuple[list[str], str]:
    """(frontmatter lines, body). No frontmatter gives ([], stripped text)."""
    stripped = text.lstrip("﻿")
    if stripped.startswith("---"):
        lines = stripped.splitlines()
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[1:i], "\n".join(lines[i + 1:]).strip()
    return [], stripped.strip()


def frontmatter_description(lines: list[str]) -> str:
    for line in lines:
        if line.lower().startswith("description:"):
            raw = line.split(":", 1)[1].strip()
            if raw.startswith('"'):
                try:
                    return str(json.loads(raw))
                except ValueError:
                    return raw.strip('"')
            if len(raw) >= 2 and raw.startswith("'") and raw.endswith("'"):
                return raw[1:-1]
            return raw
    return ""


def build_skill_md(name: str, description: str, body: str, extra_lines: Optional[list[str]] = None) -> str:
    head = [f"name: {name}", f"description: {json.dumps(description or '', ensure_ascii=False)}"]
    head += [ln for ln in (extra_lines or []) if not ln.lower().startswith(("name:", "description:"))]
    return "---\n" + "\n".join(head) + "\n---\n\n" + (body or "").strip() + "\n"


def _zip_bytes(entries: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries:
            zf.writestr(name, data)
    return buf.getvalue()


# ---------------------------------------------------------------- static routes


@router.post("/compose")
async def compose_skill(body: SkillComposeRequest, db: AsyncSession = Depends(get_db),
                        user=Depends(get_current_user)):
    name = (body.name or "").strip().lower()
    if not NAME_RE.match(name):
        raise HTTPException(status_code=400,
                            detail="Tên kỹ năng chỉ gồm chữ thường không dấu, số và '-' (2–80 ký tự)")
    description = (body.description or "").strip()
    if not description:
        raise HTTPException(status_code=400, detail="Cần mô tả khi nào dùng kỹ năng")
    if await skill_service._find(db, name, include_hidden=True) is not None:
        raise HTTPException(status_code=409, detail=f"Đã có kỹ năng '{name}'")
    depts = uuid_list(body.department_ids)
    scope_type = body.scope_type or "global"
    if scope_type == "department" and not depts:
        raise HTTPException(status_code=400, detail="Chọn ít nhất một phòng ban")
    data = _zip_bytes([(f"{name}/SKILL.md", build_skill_md(name, description, body.body).encode("utf-8"))])
    scope_id = depts[0] if scope_type == "department" else None
    return await _do_upload(db, user, [(f"{name}.zip", data)], depts if scope_type == "department" else [],
                            scope_type, scope_id, False)


@router.post("/inspect-zip")
async def inspect_zip(file: UploadFile = File(...), user=require_permission("skill:create")):
    data = await file.read()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            names = [n for n in zf.namelist() if not n.endswith("/")]
            name = strip_zip_ext(file.filename or "")
            rel = _skill_md_rel(names, name)
            text = zf.read(rel).decode("utf-8", errors="replace") if rel else ""
    except (zipfile.BadZipFile, OSError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid ZIP file.")
    return {"name": name, "description": text}


@router.post("/upload")
async def upload_skills(
    files: list[UploadFile] = File(...),
    department_ids: list[str] = Form(default=[]),
    scope_type: str = Form("global"),
    scope_id: Optional[str] = Form(None),
    force: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    depts = _parse_uuid_field(department_ids)
    sid = (uuid_list([scope_id]) or [None])[0]
    return await _do_upload(db, user, files, depts, scope_type or "global", sid, force)


@router.get("", response_model=SkillListResponse)
async def list_skills(
    q: Optional[str] = None,
    department_id: Optional[uuid.UUID] = None,
    scope_type: Optional[str] = None,
    scope_id: Optional[uuid.UUID] = None,
    ids: Optional[list[uuid.UUID]] = Query(None),
    cursor: Optional[str] = None,
    limit: int = Query(20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_user),
):
    needs_filter, allowed = permission_engine.build_skill_filter(user, "read")
    if needs_filter and allowed is None:
        return SkillListResponse(items=[], total=0)
    items, total = await skill_service.list_skills(
        db, allowed_department_ids=allowed if needs_filter else None, q=q, department_id=department_id,
        scope_type=scope_type, scope_id=scope_id, ids=ids, cursor=cursor, limit=limit,
    )
    names = await department_names(db, {d for s in items for d in s.department_ids})
    out = []
    for s in items:
        try:
            out.append(SkillResponse(**skill_to_dict(s, names)))
        except Exception as e:
            logger.warning("skipping unserializable skill %s: %s", getattr(s, "id", "?"), e)
    return SkillListResponse(items=out, total=total)


# ---------------------------------------------------------------- files


@router.get("/{skill_id}/files")
async def list_skill_files(skill_id: str, version: Optional[int] = None, db: AsyncSession = Depends(get_db),
                           user=Depends(get_current_user)):
    skill = await skill_service._find(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    await _require_access(db, user, skill, "read")
    prefix = await _storage_prefix(db, skill, version)
    if not prefix:
        return []
    out = []
    for rel, obj in await _skill_files(prefix):
        lm = getattr(obj, "last_modified", None)
        out.append({"path": rel, "size": getattr(obj, "size", 0) or 0,
                    "last_modified": lm.isoformat() if lm else None, "is_text": _is_text(rel)})
    return out


@router.get("/{skill_id}/files/content")
async def read_skill_file(skill_id: str, path: str, version: Optional[int] = None,
                          db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    skill = await skill_service._find(db, skill_id)
    if skill is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    await _require_access(db, user, skill, "read")
    prefix = await _storage_prefix(db, skill, version)
    if not prefix:
        raise HTTPException(status_code=404, detail="Skill storage path not found")
    if not _is_text(path):
        raise HTTPException(status_code=400, detail="Only text-based files can be viewed.")
    clean = path.strip().lstrip("/")
    try:
        candidates = [clean]
        if "/" in clean:
            candidates.append(clean.split("/", 1)[1])
        for base in (prefix, prefix + "content/"):
            for cand in candidates:
                data = await _try_download(base + cand)
                if data is not None:
                    return {"content": data.decode("utf-8", errors="replace")}
        for rel, obj in await _skill_files(prefix):
            if any(rel == c or rel.endswith("/" + c) for c in candidates):
                data = await contrib.run(storage_service.download_file, obj.object_name)
                return {"content": data.decode("utf-8", errors="replace")}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read file content: {e}")
    raise HTTPException(status_code=404, detail=f"File {path} not found in skill storage.")


# ---------------------------------------------------------------- SKILL.md content


async def _read_skill_md(skill) -> tuple[Optional[str], str, list]:
    prefix = skill.storage_path if skill.storage_path.endswith("/") else skill.storage_path + "/"
    files = await _skill_files(prefix)
    rel = _skill_md_rel([r for r, _ in files], skill.name)
    text = ""
    if rel:
        obj = dict(files)[rel]
        text = (await contrib.run(storage_service.download_file, obj.object_name)).decode("utf-8", errors="replace")
    return rel, text, files


@router.get("/{slug}/content")
async def get_skill_content(slug: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "read")
    if not skill.storage_path:
        raise HTTPException(status_code=404, detail="Kỹ năng chưa có nội dung")
    _, text, _ = await _read_skill_md(skill)
    lines, body = split_frontmatter(text)
    return {"name": skill.name, "description": frontmatter_description(lines), "body": body,
            "is_system": bool(skill.is_system)}


@router.put("/{slug}/content")
async def put_skill_content(slug: str, req: SkillContentRequest, db: AsyncSession = Depends(get_db),
                            user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "edit")
    _system_guard(user, skill)

    entries: list[tuple[str, bytes]] = []
    md_rel, old_text, extra = None, "", []
    if skill.storage_path:
        md_rel, old_text, files = await _read_skill_md(skill)
        for rel, obj in files:
            if rel != md_rel:
                entries.append((rel, await contrib.run(storage_service.download_file, obj.object_name)))
    old_lines, _ = split_frontmatter(old_text)
    description = req.description if req.description is not None else frontmatter_description(old_lines)
    entries.append((md_rel or f"{skill.name}/SKILL.md",
                    build_skill_md(skill.name, description, req.body, old_lines).encode("utf-8")))
    data = _zip_bytes(entries)
    filename = f"{skill.name}.zip"

    if not _is_admin(user):
        c = await contrib.create_contribution_from_zip(
            db, (filename, data), user, skill_id=skill.id, base_version=skill.current_version,
            scope_type=skill.scope_type or "global", scope_ids=skill.department_ids,
        )
        await _notify_submitted(db, c, user)
        return {"status": "contribution_pending", "contribution_id": str(c.id),
                "message": "Đã gửi bản sửa, chờ duyệt"}
    return await skill_service.reupload_skill(db, str(skill.id), (filename, data), user.id)


@router.post("/{slug}/reupload")
async def reupload_skill(slug: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                         user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "create")
    _system_guard(user, skill)
    if not _is_admin(user):
        c = await contrib.create_contribution_from_zip(
            db, file, user, skill_id=skill.id, base_version=skill.current_version,
            scope_type=skill.scope_type or "global", scope_ids=skill.department_ids,
        )
        await _notify_submitted(db, c, user)
        return {"status": "contribution_pending", "contribution_id": str(c.id),
                "message": "Update submitted for review."}
    return await skill_service.reupload_skill(db, str(skill.id), file, user.id)


# ---------------------------------------------------------------- versions


@router.get("/{slug}/versions", response_model=list[SkillVersionResponse])
async def list_versions(slug: str, db: AsyncSession = Depends(get_db), user=require_permission("skill:read")):
    versions = await skill_service.list_versions(db, slug)
    return [SkillVersionResponse(version_number=v.version_number, version_hash=v.version_hash,
                                 storage_path=v.storage_path, changelog=v.changelog, created_at=v.created_at)
            for v in versions]


@router.post("/{slug}/set-latest")
async def set_latest(slug: str, version: int = Query(...), db: AsyncSession = Depends(get_db),
                     user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "edit", need_grant=True)
    _system_guard(user, skill)
    skill = await skill_service.set_latest_version(db, slug, version)
    return {"message": f"Version {version} set as latest", "current_version": skill.current_version}


# ---------------------------------------------------------------- single skill


@router.get("/{slug}", response_model=SkillResponse)
async def get_skill(slug: str, version: Optional[int] = None, db: AsyncSession = Depends(get_db),
                    user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug, version)
    await _require_access(db, user, skill, "read")
    return await _response(db, skill)


@router.delete("/{slug}")
async def delete_skill(slug: str, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "delete", need_grant=True)
    _system_guard(user, skill)
    if skill.is_system:
        skill.status = "archived"
        await db.commit()
        return {"message": "Skill archived"}
    await skill_service.delete_skill(db, slug)
    return {"message": "Skill marked for deletion"}


@router.patch("/{slug}", response_model=SkillResponse)
async def update_skill(slug: str, req: SkillUpdateRequest, db: AsyncSession = Depends(get_db),
                       user=Depends(get_current_user)):
    skill = await skill_service.get_skill(db, slug)
    await _require_access(db, user, skill, "edit", need_grant=True)
    _system_guard(user, skill)
    explicit = set(req.model_fields_set)
    if skill.is_system and "name" in explicit and req.name and req.name != skill.name:
        raise HTTPException(
            status_code=400,
            detail="Không đổi tên kỹ năng hệ thống (tên gắn với thư mục nguồn); hãy nhân bản để tạo kỹ năng mới",
        )
    if not _is_admin(user) and "skill:edit:all" not in _perms(user):
        if "scope_type" in explicit or "department_ids" in explicit:
            wanted = set(uuid_list(list(req.department_ids or []) + ([req.scope_id] if req.scope_id else [])))
            if wanted - _own_depts(user):
                raise HTTPException(status_code=403, detail=OWN_DEPT_ERROR)
            if req.scope_type == "global" or not wanted:
                raise HTTPException(status_code=403, detail="You do not have permission to make skills global")
    data = req.model_dump()
    data["_explicit_fields"] = sorted(explicit)
    updated = await skill_service.update_skill(db, str(skill.id), data)
    return await _response(db, updated)
