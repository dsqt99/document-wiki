"""Signed portal directory and policy. AppConfig keeps the replica schema independent."""
import json

from fastapi import HTTPException
from sqlalchemy import select

from app.config import settings
from app.database.models import AppConfig, Department, Employee, EmployeeDepartment
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


async def apply_directory(db, payload):
    """Upsert a complete roster or an account event, never delete document ownership."""
    if not payload.directory_complete and payload.role_definitions is None and payload.observed_at is None:
        return
    previous = await load_directory(db)
    if previous is None and not payload.directory_complete:
        # A partial event cannot establish the authoritative universe of accounts.
        return
    directory = previous or {'accounts': {}, 'role_definitions': {}}
    tombstones = directory.setdefault('tombstones', {})
    accounts = {} if payload.directory_complete else dict(directory['accounts'])
    if payload.directory_complete and not payload.accounts and directory['accounts']:
        raise HTTPException(409, 'Empty shared roster; refusing to remove every account')
    if payload.directory_complete:
        keys = [a.keycloak_id for a in payload.accounts or []]
        if payload.accounts is None or len(keys) != len(set(keys)) or any(
            not a.username or not a.name or a.roles is None or a.unit_external_ids is None
            for a in payload.accounts
        ):
            raise HTTPException(422, 'Incomplete shared identity roster')
    if payload.role_definitions is not None:
        directory['role_definitions'] = payload.role_definitions
    employees = list((await db.execute(select(Employee))).scalars().all())
    by_external = {e.external_id: e for e in employees if e.external_id}
    by_email = {e.email.lower(): e for e in employees}
    for item in payload.accounts or []:
        old = accounts.get(item.keycloak_id, {})
        profile = {**old, **item.model_dump(exclude_unset=True)}
        profile['observed_at'] = payload.observed_at or 0
        employee = by_external.get(item.keycloak_id)
        if employee is None and item.chatbot_id:
            employee = by_external.get(f'chatbot:{item.chatbot_id}')
        if employee is None and item.email:
            candidate = by_email.get(item.email.lower())
            if candidate and candidate.external_id and not candidate.external_id.startswith('chatbot:'):
                raise HTTPException(409, 'Shared identity email belongs to another identity')
            employee = candidate
        if item.deleted:
            accounts.pop(item.keycloak_id, None)
            tombstones[item.keycloak_id] = payload.observed_at or 0
            if employee:
                employee.is_active = False
                employee.mcp_token = employee.mcp_token_hash = employee.mcp_token_prefix = None
            continue
        if employee is None and item.name and item.username:
            email = item.email or f'{item.keycloak_id}@sso.invalid'
            employee = Employee(name=item.name[:200], email=email, password_hash=None,
                                external_id=item.keycloak_id, auth_provider='keycloak',
                                role='employee', global_role='viewer', global_role_source='sso',
                                is_active=item.enabled)
            db.add(employee)
            await db.flush()
            by_email[email.lower()] = employee
        if employee is not None:
            employee.external_id = item.keycloak_id
            employee.auth_provider = 'keycloak'
            by_external[item.keycloak_id] = employee
            if item.name:
                employee.name = item.name[:200]
            if item.email and item.email.lower() != employee.email.lower():
                conflict = by_email.get(item.email.lower())
                if conflict and conflict.id != employee.id:
                    raise HTTPException(409, 'Shared identity email conflict')
                by_email.pop(employee.email.lower(), None)
                employee.email = item.email.lower()
                by_email[employee.email] = employee
            if payload.directory_complete or item.reactivate:
                employee.is_active = item.enabled
            if not payload.directory_complete and item.unit_external_ids is not None:
                departments = list((await db.execute(select(Department))).scalars().all())
                wanted = {d.id for d in departments if d.external_id in item.unit_external_ids and d.is_active}
                managed = {d.id for d in departments}
                links = list((await db.execute(select(EmployeeDepartment).where(
                    EmployeeDepartment.employee_id == employee.id,
                    EmployeeDepartment.department_id.in_(managed),
                ))).scalars().all())
                existing = {link.department_id for link in links}
                for link in links:
                    if link.department_id not in wanted:
                        await db.delete(link)
                for department_id in wanted - existing:
                    db.add(EmployeeDepartment(employee_id=employee.id, department_id=department_id))
        if profile.get('username'):
            accounts[item.keycloak_id] = profile
    if payload.directory_complete:
        for key in set(directory['accounts']) - set(accounts):
            tombstones[key] = payload.observed_at or 0
            employee = by_external.get(key)
            if employee:
                employee.is_active = False
                employee.mcp_token = employee.mcp_token_hash = employee.mcp_token_prefix = None
    directory['accounts'] = accounts
    directory['observed_at'] = max(directory.get('observed_at', 0), payload.observed_at or 0)
    if payload.directory_complete:
        directory['last_complete_observed_at'] = payload.observed_at or 0
    row = await db.get(AppConfig, CONFIG_KEY)
    value = json.dumps(directory, ensure_ascii=False)
    if row is None:
        db.add(AppConfig(key=CONFIG_KEY, value=value))
    else:
        row.value = value
    await db.flush()
