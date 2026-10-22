"""The shared directory must not retain independent Wiki grants."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.database.models import AppConfig, Department, Employee, EmployeeDepartment
from app.routers import org_sync, rbac
from app.services import identity_directory as directory, permission_engine

from app.services.sso_roles import sync_employee_roles


class SharedRoleTests(unittest.TestCase):
    def test_linked_manual_grant_is_revoked_by_central_role(self):
        employee = SimpleNamespace(external_id="kc-1", email="a@example.vn", role="employee",
                                   global_role="knowledge_manager", global_role_source="manual")
        sync_employee_roles(employee, ["user"], False, {}, "viewer", "admin@example.vn")
        self.assertEqual((employee.global_role, employee.global_role_source), ("viewer", "sso"))

    def test_linked_default_admin_cannot_keep_revoked_admin_role(self):
        employee = SimpleNamespace(external_id="kc-1", email="admin@example.vn", role="admin",
                                   global_role="admin", global_role_source="sso")
        sync_employee_roles(employee, ["user"], False, {}, "viewer", "admin@example.vn")
        self.assertEqual((employee.role, employee.global_role), ("employee", "viewer"))


DEFINITIONS = {
    'admin': {'name': 'Quản trị toàn quyền', 'permissions': []},
    'qt-nd': {'name': 'Quản trị người dùng', 'permissions': ['portal.use', 'users.manage', 'org.manage', 'roles.manage'], 'wiki_global_role': 'viewer'},
    'qt-dl': {'name': 'Quản trị dữ liệu', 'permissions': ['portal.use', 'knowledge.manage', 'knowledge.approve'], 'wiki_global_role': 'knowledge_manager'},
    'user': {'name': 'Người dùng nghiệp vụ', 'permissions': ['portal.use']},
}


class DirectoryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine('sqlite+aiosqlite://')
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda c: Employee.metadata.create_all(c, tables=[
                AppConfig.__table__, Department.__table__, Employee.__table__, EmployeeDepartment.__table__]))
        self.db = async_sessionmaker(self.engine, expire_on_commit=False)()
        self.audit = patch('app.services.audit_chain.record', new_callable=AsyncMock)
        self.audit.start()
        self.addCleanup(self.audit.stop)
        self.legacy = Employee(name='Old local demo', email='old@local.vn', role='admin', global_role='admin')
        self.db.add(self.legacy)
        await self.db.flush()
        accounts = [dict(keycloak_id='admin', username='admin', name='Admin', email='admin@shared.vn', enabled=True, roles=['admin'], unit_external_ids=[])]
        members = []
        for unit, role in [('pa08', 'qt-nd'), ('pc06', 'qt-dl')]:
            for index in range(3):
                key = f'{unit}-{index}'
                accounts.append(dict(keycloak_id=key, username=key, name=f'{unit.upper()} {index}',
                                     email=f'{key}@shared.vn', enabled=True, roles=[role if index == 0 else 'user'], unit_external_ids=[unit]))
                members.append(dict(keycloak_id=key, email=f'{key}@shared.vn', unit_external_ids=[unit]))
        self.payload = org_sync.SyncPayload(
            units=[dict(external_id=u, code=u.upper(), name=u.upper()) for u in ['pa08', 'pc06']],
            members=members, accounts=accounts, directory_complete=True, role_definitions=DEFINITIONS,
            role_map={'qt-nd': 'viewer', 'qt-dl': 'knowledge_manager'})
        await org_sync.apply_org_sync(self.db, self.payload)

    async def asyncTearDown(self):
        await self.db.close()
        await self.engine.dispose()

    async def actor(self, key):
        employee = (await self.db.execute(select(Employee).where(Employee.external_id == key))).scalar_one()
        employee = await rbac._load_employee(self.db, employee.id)
        return await directory.hydrate_identity(self.db, employee)

    async def listing(self, actor, **kw):
        return await rbac.list_employees(department_id=None, search=kw.get('search'),
                                         page=kw.get('page', 1), page_size=kw.get('size', 20), user=actor, db=self.db)

    async def test_full_roster_provisions_never_logged_in_and_no_group_users(self):
        result = await self.listing(await self.actor('admin'))
        self.assertEqual(result['total'], 7)
        self.assertEqual({e['email'] for e in result['items']}, {a.email for a in self.payload.accounts})
        self.assertNotIn(self.legacy.email, [e['email'] for e in result['items']])

    async def test_scoped_count_search_and_pagination_match_pa08_roster(self):
        actor = await self.actor('pa08-0')
        result = await self.listing(actor, size=2)
        self.assertEqual((result['total'], len(result['items']), result['total_pages']), (3, 2, 2))
        self.assertTrue(all(e['department_names'] == ['PA08'] for e in result['items']))
        self.assertEqual((await self.listing(actor, search='pc06'))['total'], 0)
        self.assertEqual(len((await self.listing(actor, page=2, size=2))['items']), 1)
        self.assertEqual(result['items'][0]['identity_roles'][0]['name'], 'Quản trị người dùng')

    async def test_child_units_are_inherited_but_other_units_are_not(self):
        parent = (await self.db.execute(select(Department).where(Department.external_id == 'pa08'))).scalar_one()
        child = Department(name='PA08 child', code='CHILD', external_id='child', parent_id=parent.id)
        self.db.add(child)
        await self.db.flush()
        employee = await self.actor('pa08-2')
        employee.employee_departments[0].department_id = child.id
        await self.db.flush()
        result = await self.listing(await self.actor('pa08-0'))
        self.assertEqual(result['total'], 3)

    async def test_central_permissions_ignore_local_global_role_and_matrix_overrides(self):
        actor = await self.actor('pa08-0')
        actor.global_role = 'admin'
        perms = permission_engine._get_user_permissions(actor)
        self.assertIn('org:employees:read', perms)
        self.assertNotIn('org:employees:manage', perms)
        self.assertNotIn('doc:delete:all', perms)
        self.assertNotIn('org:settings:manage', perms)
        data_manager = await self.actor('pc06-0')
        perms = permission_engine._get_user_permissions(data_manager)
        self.assertIn('doc:delete:own_dept', perms)
        self.assertNotIn('doc:delete:all', perms)
        self.assertNotIn('org:employees:manage', perms)

    async def test_removed_legacy_identity_is_not_an_independent_login(self):
        with self.assertRaises(HTTPException) as caught:
            await directory.hydrate_identity(self.db, self.legacy)
        self.assertEqual(caught.exception.status_code, 401)

    async def test_direct_wiki_grant_and_cross_unit_token_management_are_blocked(self):
        actor = await self.actor('pa08-0')
        other = await self.actor('pc06-0')
        with self.assertRaises(HTTPException) as caught:
            await rbac._load_scoped_employee(self.db, actor, other.id)
        self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(HTTPException) as caught:
            await rbac.update_employee(str(actor.id), rbac.EmployeeUpdate(global_role='admin'), actor, self.db)
        self.assertEqual(caught.exception.status_code, 409)

    async def test_role_lock_unlock_and_delete_events_apply_immediately(self):
        actor = await self.actor('pc06-0')
        for changes in [dict(roles=['user'], enabled=True), dict(enabled=False), dict(enabled=True, reactivate=True)]:
            await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(
                accounts=[dict(keycloak_id='pc06-0', **changes)], role_definitions=DEFINITIONS))
        actor = await self.actor('pc06-0')
        self.assertTrue(actor.is_active)
        self.assertNotIn('doc:delete:own_dept', permission_engine._get_user_permissions(actor))
        await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(
            accounts=[dict(keycloak_id='pc06-0', enabled=False, deleted=True)], role_definitions=DEFINITIONS))
        self.assertEqual((await self.listing(await self.actor('admin')))['total'], 6)
        self.assertFalse(actor.is_active)

    async def test_full_roster_repairs_missed_reactivation_and_deletion(self):
        actor = await self.actor('pc06-0')
        actor.is_active = False
        self.payload.accounts = [a for a in self.payload.accounts if a.keycloak_id != 'pa08-2']
        await org_sync.apply_org_sync(self.db, self.payload)
        self.assertTrue(actor.is_active)
        self.assertEqual((await self.listing(await self.actor('admin')))['total'], 6)

    async def test_empty_snapshot_cannot_retire_everyone(self):
        with self.assertRaises(HTTPException) as caught:
            await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(directory_complete=True, accounts=[]))
        self.assertEqual(caught.exception.status_code, 409)

    async def test_old_snapshot_and_event_cannot_restore_revoked_account(self):
        self.payload.observed_at = 100
        await org_sync.apply_org_sync(self.db, self.payload)
        await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(observed_at=300,
            accounts=[dict(keycloak_id='pc06-0', enabled=False, deleted=True)], role_definitions=DEFINITIONS))
        self.payload.observed_at = 200
        self.assertEqual(await org_sync.apply_org_sync(self.db, self.payload), {'ignored': 'stale_snapshot'})
        old = self.payload.accounts[-3].model_copy(update={'keycloak_id': 'pc06-0', 'enabled': True})
        await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(observed_at=250,
            accounts=[old], role_definitions=DEFINITIONS))
        data = await directory.load_directory(self.db)
        self.assertNotIn('pc06-0', data['accounts'])
        self.assertEqual((await self.listing(await self.actor('admin')))['total'], 6)

    async def test_out_of_order_different_account_events_are_merged(self):
        for version, key in [(300, 'pc06-0'), (200, 'pa08-0')]:
            await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(observed_at=version,
                accounts=[dict(keycloak_id=key, enabled=False)], role_definitions=DEFINITIONS))
        data = await directory.load_directory(self.db)
        self.assertFalse(data['accounts']['pc06-0']['enabled'])
        self.assertFalse(data['accounts']['pa08-0']['enabled'])

    async def test_new_account_event_provisions_profile_and_unit_without_login(self):
        await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(observed_at=100,
            accounts=[dict(keycloak_id='new', username='new', name='New officer', email='new@shared.vn',
                           roles=['user'], enabled=True, unit_external_ids=['pa08'])], role_definitions=DEFINITIONS))
        data = await self.listing(await self.actor('pa08-0'))
        self.assertEqual(data['total'], 4)
        self.assertIn('New officer', [e['name'] for e in data['items']])

    async def test_private_wiki_unit_does_not_extend_central_identity_scope(self):
        actor = await self.actor('pa08-0')
        private = Department(name='Legacy private department', external_id=None)
        self.db.add(private)
        await self.db.flush()
        self.db.add(EmployeeDepartment(employee_id=actor.id, department_id=private.id))
        await self.db.flush()
        self.assertNotIn(private.id, await directory.unit_scope(self.db, actor))

    async def test_hydration_removes_stale_admin_and_approval_stays_in_unit(self):
        from app.routers import wiki
        actor = await self.actor('pc06-0')
        actor.role = actor.global_role = 'admin'
        await directory.hydrate_identity(self.db, actor)
        self.assertFalse(wiki._is_admin(actor))
        own = actor.department_ids[0]
        other = (await self.actor('pa08-0')).department_ids[0]
        draft = SimpleNamespace(draft_kind='create', suggested_metadata={'scope_type': 'department', 'scope_id': str(own)})
        self.assertTrue(await wiki._can_review_draft(self.db, actor, draft))
        draft.suggested_metadata['scope_id'] = str(other)
        self.assertFalse(await wiki._can_review_draft(self.db, actor, draft))

    async def test_old_unknown_create_event_cannot_resurrect_after_new_complete_snapshot(self):
        self.payload.observed_at = 300
        await org_sync.apply_org_sync(self.db, self.payload)
        await org_sync.apply_org_sync(self.db, org_sync.SyncPayload(observed_at=200, role_definitions=DEFINITIONS,
            accounts=[dict(keycloak_id='not-seen-before', username='old', name='Old event', enabled=True,
                           roles=['admin'], unit_external_ids=[])]))
        self.assertNotIn('not-seen-before', (await directory.load_directory(self.db))['accounts'])

    async def test_branch_merge_does_not_review_foreign_unit_drafts(self):
        from app.routers import wiki_branches
        actor = await self.actor('pc06-0')
        other = (await self.actor('pa08-0')).department_ids[0]
        draft = SimpleNamespace(status='pending', draft_kind='create',
            suggested_metadata={'scope_type': 'department', 'scope_id': str(other)})
        with patch.object(wiki_branches, '_branch_drafts', AsyncMock(return_value=[draft])):
            with self.assertRaises(HTTPException) as caught:
                await wiki_branches._ensure_shared_branch_reviewable(self.db, actor, SimpleNamespace(id='branch'))
        self.assertEqual(caught.exception.status_code, 403)

    async def test_branch_author_cannot_change_another_officers_draft(self):
        from app.routers import wiki_branches
        actor = await self.actor('pc06-0')
        other = await self.actor('pa08-0')
        draft = SimpleNamespace(author_id=other.id, draft_kind='create',
            suggested_metadata={'scope_type': 'department', 'scope_id': str(other.department_ids[0])})
        with self.assertRaises(HTTPException) as caught:
            await wiki_branches._ensure_shared_author_draft(self.db, actor, draft)
        self.assertEqual(caught.exception.status_code, 403)
        draft.author_id = actor.id
        with self.assertRaises(HTTPException):
            await wiki_branches._ensure_shared_author_draft(self.db, actor, draft)

    async def test_branch_attachment_requires_same_author_and_scope(self):
        from app.routers import wiki_drafts
        actor = await self.actor('pc06-0')
        other = await self.actor('pa08-0')
        branch = SimpleNamespace(author_id=other.id, status='draft', scope_type='department', scope_id=actor.department_ids[0])
        fake = SimpleNamespace(get=AsyncMock(return_value=branch))
        with self.assertRaises(HTTPException):
            await wiki_drafts._validate_shared_branch_attachment(fake, actor, 'branch', 'department', actor.department_ids[0])
        branch.author_id = actor.id
        with self.assertRaises(HTTPException):
            await wiki_drafts._validate_shared_branch_attachment(fake, actor, 'branch', 'department', other.department_ids[0])
        await wiki_drafts._validate_shared_branch_attachment(fake, actor, 'branch', 'department', actor.department_ids[0])


if __name__ == "__main__":
    unittest.main()
