"""Departments, employees, MCP tokens and the role permission matrix (mounted under /api).

A "managed" department has an ``external_id``: it is synchronised from Keycloak and
cannot be edited here, and its memberships come only from Keycloak.
"""

import json
import math
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.database.models import Department, Employee, EmployeeDepartment
from app.services import audit_service, auth_service, config_service, permissions
from app.services.auth_service import get_current_user, require_permission
from app.services.identity_directory import (
    load_directory, account_for, unit_scope, require_local_management, policy_permissions,
)

router = APIRouter()

MANAGED_DEPARTMENT_MSG = "Phòng ban đồng bộ từ Keycloak — sửa tại trang Quản trị của Trợ lý ảo AI"
SSO_SOURCE_ONLY_MSG = "Chỉ tài khoản đăng nhập qua Keycloak mới để Keycloak quản lý mức quyền"
MIN_EMPLOYEE_PASSWORD = 8
ACCOUNT_ROLES = ("admin", "employee")
ROLE_SOURCES = ("sso", "manual")


async def _audit(db, user, action: str, resource_type: str, resource_id, reason: Optional[str] = None):
    await audit_service.log_audit(db, user, action, resource_type, resource_id, reason=reason)


def _parse_uuid(value, not_found: str) -> uuid.UUID:
    try:
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    except (ValueError, TypeError):
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)


def _global_role_error() -> HTTPException:
    return HTTPException(
        status.HTTP_400_BAD_REQUEST,
        "Global role must be one of: " + ", ".join(permissions.SYSTEM_ROLE_IDS),
    )


# ---------------------------------------------------------------------------
# Departments
# ---------------------------------------------------------------------------


class DepartmentIn(BaseModel):
    name: str
    description: Optional[str] = None


def _department_out(dept: Department, employee_count: int) -> dict:
    return {
        "id": str(dept.id),
        "name": dept.name,
        "description": dept.description,
        "employee_count": int(employee_count or 0),
        "code": dept.code,
        "parent_id": str(dept.parent_id) if dept.parent_id else None,
        "managed": dept.external_id is not None,
        "is_active": bool(dept.is_active),
    }


@router.get("/departments")
async def list_departments(
    include_inactive: bool = False,
    user: Employee = require_permission("org:departments:read"),
    db: AsyncSession = Depends(get_db),
):
    counts = (
        select(EmployeeDepartment.department_id, func.count(EmployeeDepartment.employee_id).label("n"))
        .group_by(EmployeeDepartment.department_id)
        .subquery()
    )
    query = select(Department, func.coalesce(counts.c.n, 0)).outerjoin(counts, counts.c.department_id == Department.id)
    if not include_inactive:
        query = query.where(Department.is_active.is_(True))
    directory = await load_directory(db)
    if directory is not None:
        query = query.where(Department.external_id.is_not(None))
        if user.role != 'admin':
            query = query.where(Department.id.in_(await unit_scope(db, user)))
    query = query.order_by(Department.created_at.asc(), Department.id.asc())
    rows = (await db.execute(query)).all()
    return [_department_out(dept, n) for dept, n in rows]


async def _editable_department(db: AsyncSession, dept_id) -> Department:
    await require_local_management(db)
    dept = await db.get(Department, _parse_uuid(dept_id, "Department not found"))
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    if dept.external_id is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, MANAGED_DEPARTMENT_MSG)
    return dept


async def _name_taken(db: AsyncSession, name: str, exclude_id=None) -> bool:
    query = select(Department.id).where(Department.name == name)
    if exclude_id is not None:
        query = query.where(Department.id != exclude_id)
    return (await db.execute(query)).first() is not None


@router.post("/departments", status_code=status.HTTP_201_CREATED)
async def create_department(
    body: DepartmentIn,
    user: Employee = require_permission("org:departments:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department name is required")
    if await _name_taken(db, name):
        raise HTTPException(status.HTTP_409_CONFLICT, "Department name already exists")
    dept = Department(name=name, description=body.description)
    db.add(dept)
    await db.flush()
    await _audit(db, user, "create", "department", dept.id, reason=name)
    await db.commit()
    return {"id": str(dept.id), "name": dept.name}


@router.put("/departments/{dept_id}")
async def update_department(
    dept_id: str,
    body: DepartmentIn,
    user: Employee = require_permission("org:departments:manage"),
    db: AsyncSession = Depends(get_db),
):
    dept = await _editable_department(db, dept_id)
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Department name is required")
    if await _name_taken(db, name, exclude_id=dept.id):
        raise HTTPException(status.HTTP_409_CONFLICT, "Department name already exists")
    dept.name = name
    dept.description = body.description
    await _audit(db, user, "update", "department", dept.id, reason=name)
    await db.commit()
    return {"id": str(dept.id), "name": dept.name}


@router.delete("/departments/{dept_id}")
async def delete_department(
    dept_id: str,
    user: Employee = require_permission("org:departments:manage"),
    db: AsyncSession = Depends(get_db),
):
    dept = await _editable_department(db, dept_id)
    name = dept.name
    await db.delete(dept)
    await _audit(db, user, "delete", "department", dept_id, reason=name)
    await db.commit()
    return {"deleted": True}


# ---------------------------------------------------------------------------
# Employees
# ---------------------------------------------------------------------------


class EmployeeCreate(BaseModel):
    name: str
    email: str
    password: Optional[str] = None
    role: str = "employee"
    global_role: str = "viewer"
    global_role_source: Optional[str] = None
    department_ids: list[str] = Field(default_factory=list)


class EmployeeUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    global_role: Optional[str] = None
    global_role_source: Optional[str] = None
    department_ids: Optional[list[str]] = None


class MembershipIn(BaseModel):
    department_id: str


def _employee_out(emp: Employee) -> dict:
    names = []
    for link in emp.employee_departments or []:
        if link.department is not None:
            names.append(link.department.name)
    return {
        "id": str(emp.id),
        "name": emp.name,
        "email": emp.email,
        "role": emp.role,
        "global_role": emp.global_role,
        "global_role_source": emp.global_role_source,
        "department_ids": [str(d) for d in emp.department_ids],
        "department_names": names,
        "is_active": bool(emp.is_active),
        "has_token": bool(emp.mcp_token_hash),
        "last_connected": emp.last_connected.isoformat() if emp.last_connected else None,
    }


async def _load_employee(db: AsyncSession, emp_id, not_found: str = "Employee not found") -> Employee:
    emp_uuid = _parse_uuid(emp_id, not_found)
    result = await db.execute(
        select(Employee)
        .where(Employee.id == emp_uuid)
        .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
    )
    emp = result.scalar_one_or_none()
    if emp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
    return emp


async def _shared_employee_conditions(db, user, directory):
    if directory is None:
        return []
    conds = [Employee.external_id.in_(directory['accounts'])]
    if user.role != 'admin':
        scope = await unit_scope(db, user)
        conds.append(Employee.id.in_(select(EmployeeDepartment.employee_id).where(
            EmployeeDepartment.department_id.in_(scope))))
    return conds


async def _load_scoped_employee(db, actor, employee_id):
    employee = await _load_employee(db, employee_id)
    directory = await load_directory(db)
    if directory is not None:
        account = account_for(directory, employee)
        if account is None or (actor.role != 'admin' and not (
            set(employee.department_ids) & await unit_scope(db, actor)
        )):
            raise HTTPException(403, 'Account is outside your unit scope')
        if actor.role != 'admin' and 'admin' in account.get('roles', []):
            raise HTTPException(403, 'Only a full administrator can manage an administrator account')
    return employee


async def _resolve_departments(db: AsyncSession, raw_ids) -> list[Department]:
    ids = []
    for raw in raw_ids or []:
        try:
            ids.append(uuid.UUID(str(raw)))
        except (ValueError, TypeError):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more departments not found")
    ids = list(dict.fromkeys(ids))
    if not ids:
        return []
    found = list((await db.execute(select(Department).where(Department.id.in_(ids)))).scalars().all())
    if len(found) != len(ids):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "One or more departments not found")
    return found


def _validate_password(password: Optional[str]) -> None:
    if len(password or "") < MIN_EMPLOYEE_PASSWORD:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password must be at least 8 characters")


@router.get("/employees")
async def list_employees(
    department_id: Optional[str] = None,
    search: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    user: Employee = require_permission("org:employees:read"),
    db: AsyncSession = Depends(get_db),
):
    directory = await load_directory(db)
    conds = await _shared_employee_conditions(db, user, directory)
    if department_id:
        dept_uuid = _parse_uuid(department_id, "Department not found")
        conds.append(
            Employee.id.in_(
                select(EmployeeDepartment.employee_id).where(EmployeeDepartment.department_id == dept_uuid)
            )
        )
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        username_matches = [key for key, value in (directory or {}).get('accounts', {}).items()
                            if search.strip().lower() in value.get('username', '').lower()]
        conds.append(or_(Employee.name.ilike(pattern), Employee.email.ilike(pattern),
                         Employee.external_id.in_(username_matches)))

    total = (await db.execute(select(func.count()).select_from(Employee).where(*conds))).scalar_one()
    rows = await db.execute(
        select(Employee)
        .where(*conds)
        .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
        .order_by(Employee.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    items = []
    for employee in rows.scalars().all():
        item = _employee_out(employee)
        account = account_for(directory, employee)
        if account:
            item['identity_roles'] = [{'id': role, 'name': directory.get('role_definitions', {}).get(role, {}).get('name', role)}
                                      for role in account.get('roles', [])]
            item['username'] = account.get('username')
        items.append(item)
    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, math.ceil(total / page_size)),
        "managed": directory is not None,
    }


@router.post("/employees", status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    if not body.password:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Password is required")
    _validate_password(body.password)
    if body.role not in ACCOUNT_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be 'admin' or 'employee'")
    if body.global_role not in permissions.SYSTEM_ROLE_IDS:
        raise _global_role_error()
    if body.global_role_source is not None and body.global_role_source not in ROLE_SOURCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "global_role_source must be 'sso' or 'manual'")
    if body.global_role_source == "sso":
        # A new local account has no external_id, so Keycloak cannot manage it.
        raise HTTPException(status.HTTP_400_BAD_REQUEST, SSO_SOURCE_ONLY_MSG)
    email = (body.email or "").strip()
    if not email or not (body.name or "").strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Name and email are required")
    exists = await db.execute(select(Employee.id).where(func.lower(Employee.email) == email.lower()))
    if exists.first() is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
    departments = await _resolve_departments(db, body.department_ids)

    emp = Employee(
        name=body.name.strip(),
        email=email,
        password_hash=auth_service.hash_password(body.password),
        role=body.role,
        global_role=body.global_role,
        global_role_source="manual",
        is_active=True,
    )
    db.add(emp)
    await db.flush()
    for dept in departments:
        if dept.external_id is None:
            db.add(EmployeeDepartment(employee_id=emp.id, department_id=dept.id))
    await _audit(db, user, "create", "employee", emp.id, reason=email)
    await db.commit()
    return {"id": str(emp.id), "name": emp.name, "email": emp.email}


@router.put("/employees/{emp_id}")
async def update_employee(
    emp_id: str,
    body: EmployeeUpdate,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    emp = await _load_employee(db, emp_id)
    if body.global_role is not None and body.global_role not in permissions.SYSTEM_ROLE_IDS:
        raise _global_role_error()
    if body.global_role_source is not None and body.global_role_source not in ROLE_SOURCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "global_role_source must be 'sso' or 'manual'")
    if body.global_role_source == "sso" and not emp.external_id:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, SSO_SOURCE_ONLY_MSG)
    if body.role is not None and body.role not in ACCOUNT_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be 'admin' or 'employee'")
    if body.password:
        _validate_password(body.password)

    changes: list[str] = []
    if body.name is not None and body.name.strip() and body.name.strip() != emp.name:
        emp.name = body.name.strip()
        changes.append("name")
    if body.email is not None and body.email.strip() and body.email.strip() != emp.email:
        new_email = body.email.strip()
        clash = await db.execute(
            select(Employee.id).where(func.lower(Employee.email) == new_email.lower(), Employee.id != emp.id)
        )
        if clash.first() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, "Email already exists")
        emp.email = new_email
        changes.append("email")
    if body.role is not None and body.role != emp.role:
        emp.role = body.role
        changes.append("role")

    if body.global_role_source == "sso":
        emp.global_role_source = "sso"
        if body.global_role is not None:
            emp.global_role = body.global_role
        changes.append("global_role_source=sso")
    else:
        if body.global_role is not None and body.global_role != emp.global_role:
            emp.global_role = body.global_role
            emp.global_role_source = "manual"
            changes.append(f"global_role={body.global_role}")
        elif body.global_role_source == "manual":
            emp.global_role_source = "manual"
            changes.append("global_role_source=manual")

    if body.password:
        emp.password_hash = auth_service.hash_password(body.password)
        changes.append("password")

    if body.department_ids is not None:
        wanted = {d.id for d in await _resolve_departments(db, body.department_ids) if d.external_id is None}
        for link in list(emp.employee_departments or []):
            dept = link.department
            if dept is not None and dept.external_id is not None:
                continue  # managed membership: owned by Keycloak
            if link.department_id not in wanted:
                emp.employee_departments.remove(link)
        current = {link.department_id for link in emp.employee_departments}
        for dept_id in wanted - current:
            emp.employee_departments.append(EmployeeDepartment(employee_id=emp.id, department_id=dept_id))
        changes.append("departments")

    await _audit(db, user, "update", "employee", emp.id, reason=", ".join(changes) or None)
    await db.commit()
    return {"id": str(emp.id), "name": emp.name}


@router.delete("/employees/{emp_id}")
async def delete_employee(
    emp_id: str,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    emp = await _load_employee(db, emp_id)
    if emp.role == "admin":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot delete an admin account")
    email = emp.email
    await db.delete(emp)
    await _audit(db, user, "delete", "employee", emp_id, reason=email)
    await db.commit()
    return {"deleted": True}


@router.post("/employees/{emp_id}/departments", status_code=status.HTTP_201_CREATED)
async def add_employee_department(
    emp_id: str,
    body: MembershipIn,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    emp = await _load_employee(db, emp_id)
    dept = await db.get(Department, _parse_uuid(body.department_id, "Department not found"))
    if dept is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Department not found")
    if any(link.department_id == dept.id for link in emp.employee_departments or []):
        raise HTTPException(status.HTTP_409_CONFLICT, "Employee already belongs to this department")
    db.add(EmployeeDepartment(employee_id=emp.id, department_id=dept.id))
    await _audit(db, user, "update", "employee", emp.id, reason=f"add department {dept.name}")
    await db.commit()
    return {"employee_id": str(emp.id), "department_id": str(dept.id)}


@router.delete("/employees/{emp_id}/departments/{dept_id}")
async def remove_employee_department(
    emp_id: str,
    dept_id: str,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    try:
        emp_uuid, dept_uuid = uuid.UUID(emp_id), uuid.UUID(dept_id)
    except ValueError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    result = await db.execute(
        select(EmployeeDepartment).where(
            EmployeeDepartment.employee_id == emp_uuid, EmployeeDepartment.department_id == dept_uuid
        )
    )
    link = result.scalar_one_or_none()
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Membership not found")
    await db.delete(link)
    await _audit(db, user, "update", "employee", emp_uuid, reason=f"remove department {dept_uuid}")
    await db.commit()
    return {"removed": True}


@router.patch("/employees/{emp_id}/toggle")
async def toggle_employee(
    emp_id: str,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    emp = await _load_employee(db, emp_id)
    emp.is_active = not emp.is_active
    await _audit(db, user, "update", "employee", emp.id, reason=f"is_active={emp.is_active}")
    await db.commit()
    return {"id": str(emp.id), "is_active": emp.is_active}


# ---------------------------------------------------------------------------
# MCP tokens
# ---------------------------------------------------------------------------


def _mcp_instructions(base: str, token: str) -> str:
    config = {
        "mcpServers": {
            "arkon": {
                "url": f"{base}/mcp",
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
    }
    return (
        "Add this server to Claude Desktop (Settings > Developer > Edit Config, file "
        "claude_desktop_config.json) or to any MCP client that supports HTTP servers. "
        "The token is shown only once; generating a new one revokes the previous token.\n\n"
        + json.dumps(config, indent=2)
    )


def _base(request: Request) -> str:
    from app.routers import sso

    return sso._public_base(request)


def _mcp_service(db):
    from app.services import mcp_auth_service

    return mcp_auth_service.MCPAuthService(db)


async def _issue_token(db: AsyncSession, request: Request, actor: Employee, emp: Employee) -> dict:
    token = await _mcp_service(db).generate_token(emp)
    await _audit(db, actor, "create", "mcp_token", emp.id, reason=f"prefix={emp.mcp_token_prefix}")
    await db.commit()
    return {"token": token, "employee_name": emp.name, "instructions": _mcp_instructions(_base(request), token)}


@router.post("/employees/{emp_id}/token")
async def generate_employee_token(
    emp_id: str,
    request: Request,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    emp = await _load_scoped_employee(db, user, emp_id)
    return await _issue_token(db, request, user, emp)


@router.delete("/employees/{emp_id}/token")
async def revoke_employee_token(
    emp_id: str,
    user: Employee = require_permission("org:employees:manage"),
    db: AsyncSession = Depends(get_db),
):
    not_found = "Employee not found or has no token"
    emp = await _load_scoped_employee(db, user, emp_id)
    if not await _mcp_service(db).revoke_token(emp):
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
    await _audit(db, user, "delete", "mcp_token", emp.id)
    await db.commit()
    return {"revoked": True}


@router.post("/my/mcp-token")
async def rotate_my_token(
    request: Request,
    user: Employee = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _issue_token(db, request, user, user)


@router.delete("/my/mcp-token")
async def revoke_my_token(user: Employee = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    if not await _mcp_service(db).revoke_token(user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Employee not found or has no token")
    await _audit(db, user, "delete", "mcp_token", user.id)
    await db.commit()
    return {"revoked": True}


@router.get("/my/mcp-token/status")
async def my_token_status(user: Employee = Depends(get_current_user)):
    return {"has_token": bool(user.mcp_token_hash)}


# ---------------------------------------------------------------------------
# Role permission matrix
# ---------------------------------------------------------------------------


class MatrixUpdate(BaseModel):
    role_permissions: dict[str, list[str]] = Field(default_factory=dict)


def _matrix() -> dict:
    return {
        "roles": permissions.SYSTEM_ROLES,
        "groups": permissions.PERMISSION_GROUPS,
        "labels": permissions.PERMISSION_LABELS,
        "descriptions": permissions.PERMISSION_DESCRIPTIONS,
        "all_permissions": permissions.ALL_PERMISSIONS,
        "role_permissions": permissions.get_effective_role_permissions(),
    }


@router.get("/rbac/matrix")
async def get_matrix(user: Employee = require_permission("org:roles:read"), db: AsyncSession = Depends(get_db)):
    directory = await load_directory(db)
    if directory is not None:
        definitions = directory.get('role_definitions', {})
        return {**_matrix(), 'managed': True,
                'roles': [{'id': key, 'name': value.get('name', key), 'description': value.get('description', '')}
                          for key, value in definitions.items()],
                'role_permissions': {key: sorted(policy_permissions([key], definitions)) for key in definitions},
                'portal_role_permissions': {key: value.get('permissions', []) for key, value in definitions.items()}}
    return _matrix()


@router.put("/rbac/matrix")
async def update_matrix(
    body: MatrixUpdate,
    user: Employee = require_permission("org:roles:manage"),
    db: AsyncSession = Depends(get_db),
):
    await require_local_management(db)
    cleaned = permissions.sanitize_role_permissions(body.role_permissions)
    payload = json.dumps(cleaned, ensure_ascii=False)
    await config_service.ConfigService(db).set("role_permissions_custom", payload)
    permissions.load_role_permissions_override(payload)
    await _audit(db, user, "update", "rbac_matrix", "role_permissions",
                 reason="roles: " + (", ".join(sorted(cleaned)) or "(none)"))
    await db.commit()
    return {"success": True, "role_permissions": permissions.get_effective_role_permissions()}
