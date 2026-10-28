"""Signed portal directory and policy. AppConfig keeps the replica schema independent."""
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.database.models import AppConfig, Department
from app.services import permissions

CONFIG_KEY = 'portal_identity_directory'
MANAGED_MESSAGE = 'Tài khoản, đơn vị và quyền dùng chung; quản lý tại Cán bộ & đơn vị của Trợ lý ảo AI.'


async def load_directory(db):
    row = await db.get(AppConfig, CONFIG_KEY)
    return json.loads(row.value) if row is not None and row.value else None


def account_for(directory, employee):
    return (directory or {}).get('accounts', {}).get(employee.external_id)


def policy_permissions(roles, definitions):
    """Project the portal's capabilities into Wiki actions without granting global scope.

    Local Wiki role presets/overrides never add grants to a managed identity.
    """
    if 'admin' in roles:
        return set(permissions.ALL_PERMISSIONS)
    portal = set()
    targets = set()
    for role in roles:
        definition = definitions.get(role, {})
        portal.update(definition.get('permissions', []))
        target = definition.get('wiki_global_role')
        if target in ('viewer', 'contributor', 'knowledge_manager'):
            targets.add(target)
    granted = set()
    if 'portal.use' in portal:
        granted.update(('doc:read:own_dept', 'wiki:read:own_dept', 'skill:read:own_dept', 'org:departments:read'))
    # Preserve the centrally chosen knowledge level, scoped to the actor's units.
    for target in targets:
        for permission in permissions.ROLE_PRESETS[target]:
            if permission.startswith(('doc:', 'wiki:', 'skill:')) and permission != 'skill:contribution:review':
                granted.add(permission.replace(':all', ':own_dept'))
    if 'knowledge.manage' in portal:
        granted.update(f'doc:{a}:own_dept' for a in ('read', 'create', 'edit', 'delete'))
        granted.update(f'wiki:{a}:own_dept' for a in ('read', 'write', 'delete'))
    if 'knowledge.approve' in portal:
        granted.add('skill:contribution:review')
    if 'users.manage' in portal:
        granted.update(('org:employees:read', 'org:departments:read'))
    if 'org.manage' in portal:
        granted.add('org:departments:read')
    if 'roles.manage' in portal:
        granted.add('org:roles:read')
    if 'audit.read' in portal:
        granted.add('org:audit:read')
    return granted


async def unit_scope(db, employee):
    """Same own units + descendants rule as the portal's unit_scope.actor_unit_ids."""
    departments = list((await db.execute(select(Department))).scalars().all())
    directory = await load_directory(db)
    account = account_for(directory, employee)
    scope = {d.id for d in departments if d.is_active and d.external_id in account.get('unit_external_ids', [])} if account else set(employee.department_ids)
    changed = True
    while changed:
        added = {d.id for d in departments if d.is_active and d.parent_id in scope} - scope
        changed = bool(added)
        scope.update(added)
    return scope


async def hydrate_identity(db, employee):
    directory = await load_directory(db)
    if directory is None:
        return employee
    account = account_for(directory, employee)
    if account is None:
        # Retain the explicitly configured LOCAL recovery account, never an SSO admin by email.
        if not employee.external_id and employee.email.lower() == settings.default_admin_email.lower():
            return employee
        raise HTTPException(401, 'Account is not in the shared identity directory')
    if not account.get('enabled'):
        raise HTTPException(401, 'Account deactivated')
    roles = account.get('roles', [])
    employee.role = 'admin' if 'admin' in roles else 'employee'
    from app.services.sso_roles import derived_global_role

    role_map = {key: value['wiki_global_role'] for key, value in directory.get('role_definitions', {}).items()
                if value.get('wiki_global_role') in ('viewer', 'contributor', 'knowledge_manager')}
    employee.global_role = 'admin' if employee.role == 'admin' else (derived_global_role(roles, role_map) or 'viewer')
    employee.global_role_source = 'sso'
    employee._central_permissions = policy_permissions(roles, directory.get('role_definitions', {}))
    employee._central_roles = roles
    employee._central_department_ids = list(await unit_scope(db, employee))
    return employee


async def require_local_management(db):
    if await load_directory(db) is not None:
        raise HTTPException(409, MANAGED_MESSAGE)
