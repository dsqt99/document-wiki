"""
Đồng bộ cây đơn vị từ Trợ lý ảo AI (nguồn gốc: nhóm Keycloak).

  POST /api/internal/org-sync — chatbot gửi toàn bộ cây đơn vị và thành viên nhóm,
                                ký JWT HS256 bằng CHATBOT_WIKI_SSO_SECRET (hạn 60 giây,
                                kèm SHA-256 của body).

Mỗi đơn vị là một phòng ban có external_id = id nhóm Keycloak. Lần đầu, phòng ban cũ trùng
mã hoặc tên được nhận làm phòng ban đồng bộ (giữ nguyên tài liệu đã gán). Đơn vị không còn
trên Keycloak chỉ chuyển sang ngừng hoạt động và gỡ thành viên — không xóa, vì xóa phòng ban
làm tài liệu của nó thành công khai. Thành viên của phòng ban đồng bộ theo đúng nhóm Keycloak;
phòng ban tạo trong wiki (external_id NULL) không bị đụng tới.

role_map (nếu gửi) là bảng vai trò Keycloak → global_role của wiki do cổng quản trị chatbot quản lý;
lưu vào app_config, thay cho SSO_ROLE_GLOBAL_MAP, áp dụng ở lần gọi wiki kế tiếp của từng người.

accounts (nếu gửi) là trạng thái tài khoản Keycloak, có hiệu lực ngay (không chờ lần đăng nhập SSO kế tiếp):
  - enabled=false: ngừng hoạt động tài khoản wiki liên kết và thu hồi mã MCP. Wiki kiểm tra is_active ở
    mọi yêu cầu nên người đó mất quyền ngay. Chỉ khớp theo id Keycloak/"chatbot:<id>", không khớp theo email,
    nên tài khoản cục bộ của wiki không bị đụng tới.
  - enabled=true và reactivate=true (cổng quản trị vừa mở khóa): bật lại. Đồng bộ định kỳ không tự bật lại
    tài khoản mà quản trị wiki đã chủ động ngừng.
  - roles (vai trò realm hiện tại): đặt lại global_role ngay theo role_map.
"""

import hashlib
import json
import secrets
import time
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, Request
from loguru import logger
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import AppConfig, Department, Employee, EmployeeDepartment
from app.routers.sso import CHATBOT_SUB_PREFIX, CHATBOT_TICKET_ISSUER
from app.services.sso_roles import GLOBAL_ROLE_RANK, ROLE_MAP_CONFIG_KEY, load_role_map

router = APIRouter()

SYNC_AUDIENCE = "cahy-wiki-org-sync"
SKILL_SYNC_AUDIENCE = "cahy-wiki-skill-sync"
MIN_SECRET_LENGTH = 32
MAX_BODY_BYTES = 5 * 1024 * 1024
NAME_MAX_LENGTH = 200
JTI_TTL_SECONDS = 120

_seen_jti: dict[str, float] = {}


class SyncUnit(BaseModel):
    external_id: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=NAME_MAX_LENGTH)
    description: Optional[str] = Field(default=None, max_length=4000)
    parent_external_id: Optional[str] = Field(default=None, max_length=64)
    level: int = Field(default=1, ge=1, le=100)


class SyncMember(BaseModel):
    keycloak_id: str = Field(min_length=1, max_length=255)
    chatbot_id: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=200)
    unit_external_ids: list[str] = Field(default_factory=list, max_length=1000)


class SyncClearance(BaseModel):
    keycloak_id: str = Field(min_length=1, max_length=255)
    chatbot_id: Optional[str] = Field(default=None, max_length=255)
    email: Optional[str] = Field(default=None, max_length=200)
    clearance_level: str = Field(max_length=20)


class SyncAccount(BaseModel):
    keycloak_id: str = Field(min_length=1, max_length=255)
    chatbot_id: Optional[str] = Field(default=None, max_length=255)
    enabled: bool
    reactivate: bool = False
    roles: Optional[list[str]] = Field(default=None, max_length=500)


class SyncPayload(BaseModel):
    units: list[SyncUnit] = Field(default_factory=list, max_length=20000)
    members: list[SyncMember] = Field(default_factory=list, max_length=200000)
    # Mức tiếp cận của mọi cán bộ (nguồn gốc: Trợ lý ảo AI). None = không đụng tới mức hiện có.
    clearances: Optional[list[SyncClearance]] = Field(default=None, max_length=200000)
    # Vai trò Keycloak → global_role wiki (viewer/contributor/knowledge_manager). None = giữ bảng hiện có.
    role_map: Optional[dict[str, str]] = Field(default=None, max_length=1000)
    # Trạng thái/vai trò tài khoản cần có hiệu lực ngay. None = không đụng tới.
    accounts: Optional[list[SyncAccount]] = Field(default=None, max_length=200000)
    # Lý do ghi vào nhật ký kiểm toán (ví dụ "Khóa tài khoản").
    reason: Optional[str] = Field(default=None, max_length=200)


def _verify(token: str, body: bytes, audience: str = SYNC_AUDIENCE) -> None:
    secret = settings.chatbot_wiki_sso_secret.strip()
    if len(secret) < MIN_SECRET_LENGTH:
        raise HTTPException(503, "Org sync is not configured (CHATBOT_WIKI_SSO_SECRET)")
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=audience,
            issuer=CHATBOT_TICKET_ISSUER,
            leeway=10,
            options={"require": ["exp", "iat", "jti", "body_sha256"]},
        )
    except jwt.PyJWTError as e:
        logger.info(f"Org sync: token rejected ({type(e).__name__})")
        raise HTTPException(401, "Invalid sync token")
    if not secrets.compare_digest(str(claims["body_sha256"]), hashlib.sha256(body).hexdigest()):
        raise HTTPException(401, "Body does not match sync token")

    now = time.time()
    for jti, expires in list(_seen_jti.items()):
        if expires < now:
            _seen_jti.pop(jti, None)
    jti = str(claims["jti"])
    if jti in _seen_jti:
        raise HTTPException(409, "Sync token already used")
    _seen_jti[jti] = now + JTI_TTL_SECONDS


def _name_candidates(unit: SyncUnit) -> list[str]:
    """Tên phòng ban là duy nhất: tên đơn vị, rồi kèm mã, rồi kèm id nhóm."""
    names = [
        f"{unit.name[: NAME_MAX_LENGTH - len(suffix)]}{suffix}".strip()
        for suffix in ("", f" ({unit.code})", f" ({unit.code} {unit.external_id[:8]})")
    ]
    return names + [f"{unit.code} {unit.external_id}"[:NAME_MAX_LENGTH]]


def _unique_name(unit: SyncUnit, taken: set[str]) -> str:
    candidates = _name_candidates(unit)
    return next((n for n in candidates if n.casefold() not in taken), candidates[-1])


async def _apply_clearances(db: AsyncSession, clearances: list[SyncClearance]) -> int:
    """Đặt Employee.clearance_level theo Trợ lý ảo AI; người không có trong danh sách về INTERNAL.

    Chỉ hạ/giữ mức cho tài khoản liên kết Keycloak; tài khoản không khớp thì không bao giờ được nâng.
    """
    from app.services.security_label import DEFAULT_LEVEL, normalize

    employees = list((await db.execute(select(Employee))).scalars().all())
    by_external = {e.external_id: e for e in employees if e.external_id}
    by_email = {e.email.lower(): e for e in employees}

    wanted: dict = {}
    for item in clearances:
        employee = (
            by_external.get(item.keycloak_id)
            or (by_external.get(f"{CHATBOT_SUB_PREFIX}{item.chatbot_id}") if item.chatbot_id else None)
            or (by_email.get(item.email.strip().lower()) if item.email else None)
        )
        if employee is not None:
            wanted[employee.id] = normalize(item.clearance_level)

    changed = 0
    for employee in employees:
        level = wanted.get(employee.id, DEFAULT_LEVEL)
        if employee.clearance_level != level:
            employee.clearance_level = level
            changed += 1
    await db.flush()
    return changed


async def _apply_role_map(db: AsyncSession, role_map: dict[str, str]) -> bool:
    """Lưu bảng ánh xạ vai trò; không bao giờ nhận `admin` (quyền admin chỉ từ SSO_ADMIN_ROLES)."""
    from app.services import audit_chain

    wanted: dict[str, str] = {}
    for role, target in role_map.items():
        role = role.strip()
        if not role or len(role) > 255 or target not in GLOBAL_ROLE_RANK:
            raise HTTPException(422, f"Invalid role_map entry for '{role[:64]}'")
        if role in settings.sso_admin_role_set:
            raise HTTPException(422, f"Admin role '{role}' cannot be mapped")
        wanted[role] = target
    before = await load_role_map(db)
    row = await db.get(AppConfig, ROLE_MAP_CONFIG_KEY)
    stored = row is not None and row.value is not None
    if stored and before == wanted:
        return False
    value = json.dumps(wanted, sort_keys=True, ensure_ascii=False)
    if row is None:
        db.add(AppConfig(key=ROLE_MAP_CONFIG_KEY, value=value))
    else:
        row.value = value
    await db.flush()
    if before != wanted:
        await audit_chain.record(
            principal_id=audit_chain.NIL_UUID,
            principal_type="system",
            action="SSO_ROLE_MAP_UPDATE",
            resource_type="config",
            resource_id=ROLE_MAP_CONFIG_KEY,
            reason="org-sync from chatbot",
            metadata={"before": before, "after": wanted},
        )
    return before != wanted


async def _apply_accounts(db: AsyncSession, accounts: list[SyncAccount], reason: Optional[str]) -> dict:
    """Ngừng/bật lại tài khoản và đặt lại global_role theo Keycloak; mỗi thay đổi ghi nhật ký kiểm toán."""
    from app.services import audit_chain
    from app.services.sso_roles import sync_employee_roles

    keys: set[str] = set()
    for item in accounts:
        keys.add(item.keycloak_id)
        if item.chatbot_id:
            keys.add(f"{CHATBOT_SUB_PREFIX}{item.chatbot_id}")
    employees = (
        (await db.execute(select(Employee).where(Employee.external_id.in_(keys)))).scalars().all()
        if keys else []
    )
    by_external = {e.external_id: e for e in employees}
    role_map = await load_role_map(db)

    deactivated = reactivated = roles_changed = 0
    for item in accounts:
        employee = by_external.get(item.keycloak_id) or (
            by_external.get(f"{CHATBOT_SUB_PREFIX}{item.chatbot_id}") if item.chatbot_id else None
        )
        if employee is None:
            continue
        why = reason or "đồng bộ từ cổng quản trị"
        if not item.enabled:
            if employee.is_active:
                employee.is_active = False
                deactivated += 1
                await audit_chain.record(
                    principal_id=employee.id, principal_type="system", action="SSO_ACCOUNT_DEACTIVATED",
                    resource_type="employee", resource_id=str(employee.id), reason=why,
                    metadata={"email": employee.email},
                )
            # Mã MCP là khóa dài hạn: khóa tài khoản phải làm mã đó vô hiệu ngay.
            employee.mcp_token = None
            employee.mcp_token_hash = None
            employee.mcp_token_prefix = None
            continue
        if item.reactivate and not employee.is_active:
            employee.is_active = True
            reactivated += 1
            await audit_chain.record(
                principal_id=employee.id, principal_type="system", action="SSO_ACCOUNT_REACTIVATED",
                resource_type="employee", resource_id=str(employee.id), reason=why,
                metadata={"email": employee.email},
            )
        if item.roles is not None:
            is_admin = bool(set(item.roles) & settings.sso_admin_role_set)
            before, after = sync_employee_roles(
                employee, item.roles, is_admin, role_map,
                settings.sso_default_global_role, settings.default_admin_email,
            )
            if before != after:
                roles_changed += 1
                await audit_chain.record(
                    principal_id=employee.id, principal_type="system", action="SSO_GLOBAL_ROLE_SYNC",
                    resource_type="employee", resource_id=str(employee.id), reason=why,
                    metadata={
                        "before": {"global_role": before[0], "source": before[1]},
                        "after": {"global_role": after[0], "source": after[1]},
                        "realm_roles": sorted(set(item.roles)),
                    },
                )
    await db.flush()
    return {"deactivated": deactivated, "reactivated": reactivated, "roles_changed": roles_changed}


async def apply_org_sync(db: AsyncSession, payload: SyncPayload) -> dict:
    if payload.accounts is not None and not payload.units and not payload.members and payload.clearances is None:
        # Sự kiện tài khoản (khóa, mở khóa, đổi vai trò): không đụng tới cây đơn vị.
        role_map_changed = await _apply_role_map(db, payload.role_map) if payload.role_map is not None else False
        result = await _apply_accounts(db, payload.accounts, payload.reason)
        return {**{f"accounts_{k}": v for k, v in result.items()}, "role_map_changed": role_map_changed}

    units: dict[str, SyncUnit] = {}
    for unit in payload.units:
        units.setdefault(unit.external_id, unit)
    codes = [unit.code.upper() for unit in units.values()]
    if len(set(codes)) != len(codes):
        raise HTTPException(422, "Duplicate unit codes in payload")

    departments = list((await db.execute(select(Department))).scalars().all())
    if not units and any(d.external_id and d.is_active for d in departments):
        raise HTTPException(409, "Empty unit tree; refusing to deactivate all synced departments")
    assigned: dict[str, Department] = {
        d.external_id: d for d in departments if d.external_id and d.external_id in units
    }

    # Lần đầu: nhận phòng ban cũ trùng mã, tên = mã, hoặc tên = tên đơn vị.
    adopted: set[str] = set()
    free = [d for d in departments if not d.external_id]
    for dept_key, unit_key in (
        (lambda d: (d.code or "").strip().upper(), lambda u: u.code.upper()),
        (lambda d: d.name.strip().upper(), lambda u: u.code.upper()),
        (lambda d: d.name.strip().casefold(), lambda u: u.name.strip().casefold()),
    ):
        index: dict[str, SyncUnit] = {}
        for unit in units.values():
            if unit.external_id not in assigned:
                index.setdefault(unit_key(unit), unit)
        for dept in free:
            key = dept_key(dept)
            unit = index.get(key) if key else None
            if unit is None or unit.external_id in assigned or dept.external_id:
                continue
            dept.external_id = unit.external_id
            assigned[unit.external_id] = dept
            adopted.add(unit.external_id)

    # Nhả tên/mã sắp đổi trước (tránh đụng ràng buộc unique khi hai đơn vị đổi chéo tên).
    target_ids = {d.id for d in assigned.values()}
    snapshot_codes = set(codes)
    renamed: set = set()
    released = False
    for dept in departments:
        if dept.id in target_ids:
            unit = units[dept.external_id]
            if dept.name not in _name_candidates(unit) or dept.code != unit.code.upper():
                dept.name = f"~{dept.id}"
                dept.code = None
                renamed.add(dept.id)
                released = True
        elif dept.code and dept.code.upper() in snapshot_codes:
            dept.code = None
            released = True
    if released:
        await db.flush()

    taken = {d.name.casefold() for d in departments}
    created = updated = 0
    for unit in units.values():
        dept = assigned.get(unit.external_id)
        if dept is None:
            dept = Department(
                name=_unique_name(unit, taken),
                external_id=unit.external_id,
                description=unit.description,
            )
            db.add(dept)
            assigned[unit.external_id] = dept
            created += 1
        else:
            before = (dept.name, dept.code, dept.description, dept.is_active)
            if dept.id in renamed:
                taken.discard(dept.name.casefold())
                dept.name = _unique_name(unit, taken)
            # Mô tả trống trên Keycloak không xóa mô tả sẵn có của phòng ban wiki.
            if unit.description:
                dept.description = unit.description
            if before != (dept.name, unit.code.upper(), dept.description, True):
                updated += 1
        taken.add(dept.name.casefold())
        dept.code = unit.code.upper()
        dept.is_active = True
    await db.flush()

    for unit in units.values():
        parent = assigned.get(unit.parent_external_id) if unit.parent_external_id else None
        assigned[unit.external_id].parent_id = parent.id if parent is not None else None

    # Đơn vị đã xóa trên Keycloak: ngừng hoạt động, gỡ thành viên, giữ nguyên tài liệu.
    gone = [d for d in departments if d.external_id and d.external_id not in units]
    deactivated = 0
    for dept in gone:
        if dept.is_active:
            dept.is_active = False
            deactivated += 1
    if gone:
        await db.execute(
            delete(EmployeeDepartment).where(
                EmployeeDepartment.department_id.in_([d.id for d in gone])
            )
        )

    # Thành viên: khớp nhân viên wiki theo id Keycloak, "chatbot:<id>", rồi email.
    keys: set[str] = set()
    emails: set[str] = set()
    for member in payload.members:
        keys.add(member.keycloak_id)
        if member.chatbot_id:
            keys.add(f"{CHATBOT_SUB_PREFIX}{member.chatbot_id}")
        if member.email:
            emails.add(member.email.strip().lower())
    conds = []
    if keys:
        conds.append(Employee.external_id.in_(keys))
    if emails:
        conds.append(func.lower(Employee.email).in_(emails))
    employees = (
        (await db.execute(select(Employee).where(or_(*conds)))).scalars().all() if conds else []
    )
    by_external = {e.external_id: e for e in employees if e.external_id}
    by_email = {e.email.lower(): e for e in employees}

    desired: dict = {}
    matched = 0
    for member in payload.members:
        employee = (
            by_external.get(member.keycloak_id)
            or (by_external.get(f"{CHATBOT_SUB_PREFIX}{member.chatbot_id}") if member.chatbot_id else None)
            or (by_email.get(member.email.strip().lower()) if member.email else None)
        )
        if employee is None:
            continue
        matched += 1
        desired.setdefault(employee.id, set()).update(
            assigned[ext].id for ext in member.unit_external_ids if ext in assigned
        )

    managed_ids = {d.id for d in assigned.values()}
    current = (
        await db.execute(
            select(EmployeeDepartment).where(EmployeeDepartment.department_id.in_(managed_ids))
        )
    ).scalars().all() if managed_ids else []
    existing = set()
    removed = 0
    for row in current:
        if row.department_id in desired.get(row.employee_id, ()):
            existing.add((row.employee_id, row.department_id))
        else:
            await db.delete(row)
            removed += 1
    added = 0
    for employee_id, dept_ids in desired.items():
        for dept_id in dept_ids:
            if (employee_id, dept_id) not in existing:
                db.add(EmployeeDepartment(employee_id=employee_id, department_id=dept_id))
                added += 1
    await db.flush()

    clearances_set = 0
    if payload.clearances is not None:
        clearances_set = await _apply_clearances(db, payload.clearances)

    role_map_changed = False
    if payload.role_map is not None:
        role_map_changed = await _apply_role_map(db, payload.role_map)

    accounts_result = {}
    if payload.accounts is not None:
        accounts_result = await _apply_accounts(db, payload.accounts, payload.reason)

    return {
        **{f"accounts_{k}": v for k, v in accounts_result.items()},
        "departments": len(units),
        "created": created,
        "updated": updated,
        "adopted": len(adopted),
        "deactivated": deactivated,
        "members_matched": matched,
        "members_pending": len(payload.members) - matched,
        "memberships_added": added,
        "memberships_removed": removed,
        "clearances_set": clearances_set,
        "role_map_changed": role_map_changed,
    }


@router.post("/internal/org-sync")
async def org_sync(request: Request, db: AsyncSession = Depends(get_db)):
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing sync token")
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
        raise HTTPException(413, "Payload too large")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(413, "Payload too large")
    _verify(auth[7:].strip(), body)

    try:
        payload = SyncPayload.model_validate_json(body)
    except ValidationError as e:
        raise HTTPException(422, f"Invalid payload: {e.error_count()} error(s)")

    result = await apply_org_sync(db, payload)
    await db.commit()
    logger.info(f"Org sync from chatbot: {result}")
    return result


@router.post("/internal/skill-sync")
async def skill_sync(request: Request, db: AsyncSession = Depends(get_db)):
    """Danh sách kỹ năng phạm vi toàn hệ thống (kèm SKILL.md) để Trợ lý ảo AI nạp vào menu kỹ năng của chat.

    Ký như org-sync (audience riêng). Chỉ trả kỹ năng global đang hoạt động: kỹ năng phòng ban/cá nhân
    không đưa sang vì bên chatbot mọi người đều đọc được.
    """
    from app.database.models import Skill
    from app.routers.skills import _read_skill_files, _split_skill_md

    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        raise HTTPException(401, "Missing sync token")
    body = await request.body()
    if len(body) > 4096:
        raise HTTPException(413, "Payload too large")
    _verify(auth[7:].strip(), body, audience=SKILL_SYNC_AUDIENCE)

    rows = (
        await db.execute(
            select(Skill).where(Skill.status == "active", Skill.scope_type == "global").order_by(Skill.name)
        )
    ).scalars().all()
    items = []
    for skill in rows:
        try:
            _, text = await _read_skill_files(skill, only_skill_md=True)
        except Exception as e:
            logger.warning(f"Skill sync: bỏ qua {skill.slug} ({type(e).__name__})")
            continue
        description, content = _split_skill_md(text)
        if not content:
            continue
        items.append(
            {
                "slug": skill.slug,
                "name": skill.name,
                "description": description,
                "content": content,
                "is_system": skill.is_system,
                "version": skill.current_version,
                "updated_at": skill.updated_at.isoformat() if skill.updated_at else None,
            }
        )
    return {"items": items}
