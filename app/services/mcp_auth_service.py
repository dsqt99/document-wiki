"""MCP identities: ``ark_`` personal tokens, forwarded Keycloak tokens and source scoping.

Tokens are stored only as an HMAC-SHA256 digest keyed with ``settings.mcp_token_pepper``;
the plaintext is returned exactly once when generated.

Methods of :class:`MCPAuthService` accept either the session bound at construction
(``MCPAuthService(db).verify_token(token)``) or an explicit session as the first
argument (``MCPAuthService().verify_token(session, token)``).
"""

import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional

from sqlalchemy import and_, any_, exists, func, not_, or_, select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.services import permission_engine, security_label

logger = logging.getLogger(__name__)

TOKEN_PREFIX = "ark_"
TOKEN_DISPLAY_PREFIX_LEN = 12
LAST_CONNECTED_BUMP_SECONDS = 60


def hash_token(token: str) -> str:
    key = (settings.mcp_token_pepper or "").encode("utf-8")
    return hmac.new(key, (token or "").encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass
class ResolvedIdentity:
    employee_id: uuid.UUID
    employee_name: str
    department_ids: list = field(default_factory=list)
    department_names: list = field(default_factory=list)
    allowed_knowledge_types: Optional[list[str]] = None
    allowed_source_ids: Optional[list] = None
    is_admin: bool = False
    permissions: list[str] = field(default_factory=list)
    delegated_role: Optional[str] = None
    clearance_level: str = security_label.DEFAULT_LEVEL
    bumped_last_connected: bool = False

    @property
    def allowed_labels(self) -> list[str]:
        return security_label.allowed_labels(self.clearance_level)

    def has_permission(self, permission: str) -> bool:
        return bool(self.is_admin) or permission in (self.permissions or [])

    def has_any_permission(self, *perms: str) -> bool:
        if self.is_admin:
            return True
        own = set(self.permissions or [])
        return any(p in own for p in perms)


# ---------------------------------------------------------------------------
# SQL helpers
# ---------------------------------------------------------------------------


def _uuid_list(values) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for v in values or ():
        try:
            out.append(v if isinstance(v, uuid.UUID) else uuid.UUID(str(v)))
        except (ValueError, TypeError, AttributeError):
            continue
    return out


def _scope_clause(allowed_source_ids, allowed_knowledge_types):
    """OR of the provided allow-lists, or None when neither restricts."""
    from app.database.models import KnowledgeType, Source

    if allowed_source_ids is None and allowed_knowledge_types is None:
        return None
    parts = []
    if allowed_source_ids is not None:
        parts.append(Source.id.in_(_uuid_list(allowed_source_ids)))
    if allowed_knowledge_types is not None:
        parts.append(
            and_(
                Source.knowledge_type_id.isnot(None),
                Source.knowledge_type_id.in_(
                    select(KnowledgeType.id).where(KnowledgeType.slug.in_(list(allowed_knowledge_types)))
                ),
            )
        )
    return or_(*parts)


def _identity_scope(identity) -> tuple[Optional[Any], Optional[Any], Optional[str], bool, Optional[uuid.UUID]]:
    is_admin = bool(getattr(identity, "is_admin", False))
    allowed_ids = getattr(identity, "allowed_source_ids", None)
    allowed_kts = getattr(identity, "allowed_knowledge_types", None)
    clearance = getattr(identity, "clearance_level", None)
    employee_id = getattr(identity, "employee_id", None)
    if is_admin:
        allowed_ids = allowed_kts = None
    return allowed_ids, allowed_kts, clearance, is_admin, employee_id


def apply_scope_filter(query, identity):
    """Restrict a query over ``sources`` to what the MCP identity may read.

    The label and personal-document rules always apply, even for admins.
    """
    allowed_ids, allowed_kts, clearance, _is_admin, employee_id = _identity_scope(identity)
    query = query.where(security_label.source_label_clause(clearance))
    query = query.where(permission_engine.personal_visible_clause(employee_id))
    scope = _scope_clause(allowed_ids, allowed_kts)
    if scope is not None:
        query = query.where(scope)
    return query


def page_source_clause(identity):
    """Clause on ``wiki_pages``: hide a page if any of its sources is unreadable for ``identity``."""
    from app.database.models import Source, WikiPage

    allowed_ids, allowed_kts, clearance, _is_admin, employee_id = _identity_scope(identity)

    not_personal = func.coalesce(Source.scope_type, permission_engine._GLOBAL_SCOPE) != permission_engine.PERSONAL_SCOPE
    if employee_id is None:
        personal_ok = not_personal
    else:
        personal_ok = or_(not_personal, and_(Source.scope_id.isnot(None), Source.scope_id == employee_id))

    readable = [
        Source.security_label.isnot(None),
        security_label.source_label_clause(clearance),
        personal_ok,
    ]
    scope = _scope_clause(allowed_ids, allowed_kts)
    if scope is not None:
        readable.append(scope)

    return ~exists(
        select(1).where(
            and_(
                Source.id == any_(WikiPage.source_ids),
                not_(and_(*readable)),
            )
        )
    )


async def source_ids_for_departments(session, department_ids, include_global: bool = True) -> list[uuid.UUID]:
    """Ids of global sources (no department link) plus sources linked to ``department_ids``."""
    from app.database.models import Source, SourceDepartment

    dept_ids = _uuid_list(department_ids)
    conds = []
    if include_global:
        conds.append(~exists(select(1).where(SourceDepartment.source_id == Source.id)))
    if dept_ids:
        conds.append(
            Source.id.in_(
                select(SourceDepartment.source_id).where(SourceDepartment.department_id.in_(dept_ids))
            )
        )
    if not conds:
        return []
    rows = await session.execute(select(Source.id).where(or_(*conds)))
    return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


def _employee_department_names(emp) -> list[str]:
    names: list[str] = []
    try:
        for link in getattr(emp, "employee_departments", None) or []:
            dept = getattr(link, "department", None)
            if dept is not None and getattr(dept, "name", None):
                names.append(dept.name)
    except Exception:
        pass
    return names


class MCPAuthService:
    hash_token = staticmethod(hash_token)

    def __init__(self, db=None):
        self.db = db
        self.bumped_last_connected = False

    # -- argument helpers ------------------------------------------------

    def _session_and(self, args: tuple):
        """Return (session, remaining_arg) for both call styles."""
        if len(args) >= 2:
            return args[0], args[1]
        if len(args) == 1:
            return self.db, args[0]
        raise TypeError("expected an argument")

    async def _get_employee(self, session, employee_or_id):
        from app.database.models import Employee

        if employee_or_id is None:
            return None
        if isinstance(employee_or_id, (uuid.UUID, str)):
            try:
                emp_id = employee_or_id if isinstance(employee_or_id, uuid.UUID) else uuid.UUID(employee_or_id)
            except ValueError:
                return None
            return await session.get(Employee, emp_id)
        return employee_or_id

    async def _load_with_departments(self, session, employee_id):
        from app.database.models import Employee, EmployeeDepartment

        result = await session.execute(
            select(Employee)
            .where(Employee.id == employee_id)
            .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    # -- verification ----------------------------------------------------

    async def verify_token(self, *args) -> Optional[ResolvedIdentity]:
        from app.database.models import Employee, EmployeeDepartment

        session, token = self._session_and(args)
        self.bumped_last_connected = False
        if not token:
            return None
        result = await session.execute(
            select(Employee)
            .where(Employee.mcp_token_hash == hash_token(token), Employee.is_active.is_(True))
            .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
        )
        emp = result.scalar_one_or_none()
        if emp is None:
            return None

        now = datetime.now(timezone.utc)
        last = emp.last_connected
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last is None or now - last > timedelta(seconds=LAST_CONNECTED_BUMP_SECONDS):
            emp.last_connected = now
            self.bumped_last_connected = True

        identity = await self._resolve_scope(emp, session)
        identity.bumped_last_connected = self.bumped_last_connected
        return identity

    async def verify_sso_token(self, *args) -> tuple[Optional[ResolvedIdentity], Optional[str]]:
        import sys

        session, token = self._session_and(args)
        sso = sys.modules.get("app.routers.sso")
        if sso is None:
            from app.routers import sso
        outcome = await sso.employee_from_access_token(session, token)
        if isinstance(outcome, str):
            return None, outcome
        await session.commit()
        emp = await self._load_with_departments(session, outcome.id) or outcome
        if not getattr(emp, "is_active", True):
            return None, "sso_inactive"
        return await self._resolve_scope(emp, session), None

    async def _resolve_scope(self, emp, session=None) -> ResolvedIdentity:
        session = session if session is not None else self.db
        perms = permission_engine.get_effective_permissions(emp)
        identity = ResolvedIdentity(
            employee_id=emp.id,
            employee_name=emp.name,
            department_ids=list(getattr(emp, "department_ids", None) or []),
            department_names=_employee_department_names(emp),
            permissions=perms,
            clearance_level=security_label.normalize(getattr(emp, "clearance_level", None)),
        )
        if getattr(emp, "role", None) == "admin":
            identity.is_admin = True
            return identity
        if "doc:read:all" in perms:
            return identity
        if "doc:read:own_dept" in perms:
            identity.allowed_source_ids = await source_ids_for_departments(session, identity.department_ids)
            return identity
        identity.allowed_source_ids = []
        return identity

    async def resolve_scope(self, emp, session=None) -> ResolvedIdentity:
        return await self._resolve_scope(emp, session)

    # -- forwarded identity (02 §8.2 step 4) -----------------------------

    async def apply_forwarded_identity(
        self, identity: ResolvedIdentity, role: str, headers: Mapping[str, str], session=None
    ) -> ResolvedIdentity:
        """Apply a trusted forwarded role/department to ``identity`` in place and return it.

        Call only when ``forwarded_role(headers, settings.mcp_trust_forwarded_identity)`` is non-empty.
        May create a department (flushes, does not commit).
        """
        from app.database.models import Department

        session = session if session is not None else self.db
        get = (lambda k: (headers.get(k) or "").strip()) if headers is not None else (lambda k: "")
        identity.delegated_role = role
        identity.clearance_level = security_label.normalize(get("x-user-clearance"))
        if role == "admin":
            identity.is_admin = True
            identity.allowed_source_ids = None
            identity.allowed_knowledge_types = None
            return identity

        identity.is_admin = False
        dept_id, dept_code, dept_name = get("x-department-id"), get("x-department-code"), get("x-department-name")
        active = Department.is_active.is_(True)
        found: list = []
        if dept_id:
            found = list((await session.execute(select(Department).where(active, Department.external_id == dept_id))).scalars().all())
        if not found and dept_code:
            found = list(
                (await session.execute(select(Department).where(active, func.upper(Department.code) == dept_code.upper())))
                .scalars().all()
            )
        if not found and dept_name:
            found = list((await session.execute(select(Department).where(active, Department.name == dept_name))).scalars().all())
        if not found and (dept_code or dept_name):
            needles = [n for n in (dept_code, dept_name) if n]
            found = list(
                (
                    await session.execute(
                        select(Department).where(
                            active,
                            Department.external_id.is_(None),
                            or_(*[Department.name.ilike(f"%{n}%") for n in needles]),
                        )
                    )
                ).scalars().all()
            )
        if not found and dept_code:
            existing = (await session.execute(select(Department).where(Department.name == dept_code))).scalars().first()
            if existing is None:
                existing = Department(name=dept_code, description=dept_name or dept_code)
                session.add(existing)
                await session.flush()
            found = [existing]

        if found:
            identity.department_ids = [d.id for d in found]
            identity.department_names = [d.name for d in found]
            identity.allowed_source_ids = await source_ids_for_departments(
                session, identity.department_ids, include_global=False
            )
        else:
            identity.department_ids = []
            identity.department_names = []
            identity.allowed_source_ids = await source_ids_for_departments(session, [], include_global=True)
        return identity

    # -- token lifecycle -------------------------------------------------

    async def generate_token(self, *args) -> str:
        session, target = self._session_and(args)
        emp = await self._get_employee(session, target)
        if emp is None:
            raise ValueError("Employee not found")
        token = TOKEN_PREFIX + secrets.token_urlsafe(32)
        emp.mcp_token = None
        emp.mcp_token_hash = hash_token(token)
        emp.mcp_token_prefix = token[:TOKEN_DISPLAY_PREFIX_LEN]
        emp.mcp_token_rotated_at = datetime.now(timezone.utc)
        await session.flush()
        return token

    async def revoke_token(self, *args) -> bool:
        session, target = self._session_and(args)
        emp = await self._get_employee(session, target)
        if emp is None:
            return False
        had = any(
            getattr(emp, f, None) is not None
            for f in ("mcp_token", "mcp_token_hash", "mcp_token_prefix", "mcp_token_rotated_at")
        )
        emp.mcp_token = None
        emp.mcp_token_hash = None
        emp.mcp_token_prefix = None
        emp.mcp_token_rotated_at = None
        if had:
            await session.flush()
        return had


mcp_auth_service = MCPAuthService()
