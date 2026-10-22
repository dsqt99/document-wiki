"""Permission checks for documents and skills.

"own_dept" scope means the union of every department the user belongs to, plus
global resources (no department link). Shared portal identities use their centrally
assigned units and descendants; standalone local identities retain direct memberships.
"""

import uuid
from typing import Iterable, Optional

from sqlalchemy import func, or_, select

from app.services import permissions as _permissions
from app.services import security_label

PERSONAL_SCOPE = "personal"
_GLOBAL_SCOPE = "global"


def parse_permission(p: str) -> tuple[str, str, Optional[str]]:
    parts = (p or "").split(":")
    resource = parts[0] if parts else ""
    action = parts[1] if len(parts) > 1 else ""
    scope = ":".join(parts[2:]) if len(parts) > 2 else None
    return resource, action, scope


def has_permission(perms: Iterable[str], resource: str, action: str, scope: str = "any") -> bool:
    perms = set(perms or ())
    full_all = f"{resource}:{action}:all"
    if scope == "all":
        return full_all in perms
    if scope in ("own_dept", "any"):
        return full_all in perms or f"{resource}:{action}:own_dept" in perms
    return f"{resource}:{action}:{scope}" in perms


def has_any_permission(perms: Iterable[str], *checks) -> bool:
    perms = set(perms or ())
    for check in checks:
        if isinstance(check, str):
            resource, action, scope = parse_permission(check)
            check = (resource, action, scope or "any")
        if has_permission(perms, *check):
            return True
    return False


def get_scope_level(perms: Iterable[str], resource: str, action: str) -> Optional[str]:
    perms = set(perms or ())
    if f"{resource}:{action}:all" in perms:
        return "all"
    if f"{resource}:{action}:own_dept" in perms:
        return "own_dept"
    return None


def is_personal(source) -> bool:
    return (getattr(source, "scope_type", None) or _GLOBAL_SCOPE) == PERSONAL_SCOPE


def personal_visible_clause(employee_id):
    """Personal documents are visible only to their owner (scope_id)."""
    from app.database.models import Source

    not_personal = func.coalesce(Source.scope_type, _GLOBAL_SCOPE) != PERSONAL_SCOPE
    if employee_id is None:
        return not_personal
    return or_(not_personal, Source.scope_id == employee_id)


def _is_admin(user) -> bool:
    return getattr(user, "role", None) == "admin"


def _get_user_permissions(user) -> set[str]:
    central = getattr(user, '_central_permissions', None)
    if central is not None:
        return set(central)
    if getattr(user, "role", None) == "admin" or getattr(user, "global_role", None) == "admin":
        return set(_permissions.ALL_PERMISSIONS)
    effective = _permissions.get_effective_role_permissions()
    role = getattr(user, "global_role", None) or "viewer"
    if role not in effective:
        role = "viewer"
    return set(effective.get(role, []))


def get_effective_permissions(user) -> list[str]:
    return sorted(_get_user_permissions(user))


def _user_department_ids(user) -> list:
    central = getattr(user, '_central_department_ids', None)
    if central is not None:
        return list(central)
    try:
        ids = getattr(user, "department_ids", None)
    except Exception:
        ids = None
    return list(ids or [])


def _as_uuid_set(values) -> set:
    out = set()
    for v in values or ():
        try:
            out.add(v if isinstance(v, uuid.UUID) else uuid.UUID(str(v)))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


async def _source_department_ids(db, source) -> set:
    from app.database.models import SourceDepartment

    sid = getattr(source, "id", None)
    if sid is None:
        return set()
    rows = await db.execute(select(SourceDepartment.department_id).where(SourceDepartment.source_id == sid))
    return _as_uuid_set(rows.scalars().all())


async def can_access_document(db, user, source, action: str = "read") -> bool:
    if _is_admin(user):
        return True
    if is_personal(source) and getattr(source, "scope_id", None) != getattr(user, "id", None):
        return False
    label = security_label.normalize(getattr(source, "security_label", None))
    if label not in security_label.allowed_labels(getattr(user, "clearance_level", None)):
        return False
    perms = _get_user_permissions(user)
    if f"doc:{action}:all" in perms:
        return True
    if f"doc:{action}:own_dept" not in perms:
        return False
    source_depts = await _source_department_ids(db, source)
    if not source_depts:
        return True
    return bool(source_depts & _as_uuid_set(_user_department_ids(user)))


def build_document_filter(user, action: str = "read") -> tuple[bool, Optional[list]]:
    if _is_admin(user):
        return False, None
    level = get_scope_level(_get_user_permissions(user), "doc", action)
    if level == "all":
        return False, None
    if level == "own_dept":
        return True, _user_department_ids(user)
    return True, []


async def can_access_skill(db, user, skill, action: str = "read") -> bool:
    if _is_admin(user):
        return True
    if f"skill:{action}:all" in _get_user_permissions(user):
        return True
    try:
        skill_depts = _as_uuid_set(getattr(skill, "department_ids", None))
    except Exception:
        skill_depts = set()
    if not skill_depts:
        return True
    return bool(skill_depts & _as_uuid_set(_user_department_ids(user)))


def build_skill_filter(user, action: str = "read") -> tuple[bool, Optional[list]]:
    """(needs_filter, department_ids). (True, None) means the user sees nothing (see 06 §2.2)."""
    if _is_admin(user):
        return False, []
    level = get_scope_level(_get_user_permissions(user), "skill", action)
    if level == "all":
        return False, []
    if level == "own_dept":
        return True, _user_department_ids(user)
    return True, None
