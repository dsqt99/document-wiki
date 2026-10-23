"""User-authorized temporary PA08 contributor projection; no administrator grant."""
import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select
from app.database import async_session_factory
from app.database.models import AppConfig, Employee
from app.services.identity_directory import CONFIG_KEY, policy_permissions

ROLE = 'qa-upload-261023-pa08'
SNAPSHOT = Path('/tmp/cahy-qa-wiki-identity-before.json')


async def main():
    async with async_session_factory() as db:
        employee = (await db.execute(select(Employee).where(Employee.email == 'test_pa08_user@conganhungyen.gov.vn').with_for_update())).scalar_one()
        config = (await db.execute(select(AppConfig).where(AppConfig.key == CONFIG_KEY).with_for_update())).scalar_one()
        directory = json.loads(config.value)
        account = directory['accounts'][employee.external_id]
        if sys.argv[1:] == ['apply']:
            assert not SNAPSHOT.exists(), 'Restore previous test grant first'
            assert employee.clearance_level == 'PUBLIC' and employee.role == 'employee'
            assert ROLE not in directory['role_definitions']
            assert len(account.get('unit_external_ids', [])) == 1
            before = {'employee_id': str(employee.id), 'external_id': employee.external_id,
                      'clearance_level': employee.clearance_level, 'role': employee.role,
                      'global_role': employee.global_role, 'global_role_source': employee.global_role_source,
                      'roles': list(account['roles'])}
            SNAPSHOT.write_text(json.dumps(before, ensure_ascii=False, indent=2))
            directory['role_definitions'][ROLE] = {'permissions': [], 'wiki_global_role': 'contributor'}
            account['roles'] = [*account['roles'], ROLE]
            employee.clearance_level = 'INTERNAL'
            projected = policy_permissions(account['roles'], directory['role_definitions'])
            assert 'doc:create:own_dept' in projected and 'doc:create:all' not in projected
            assert not any(permission.endswith(':all') for permission in projected)
        elif sys.argv[1:] == ['reapply_public']:
            assert SNAPSHOT.exists() and employee.role == 'employee'
            directory['role_definitions'][ROLE] = {'permissions': [], 'wiki_global_role': 'contributor'}
            if ROLE not in account['roles']:
                account['roles'].append(ROLE)
            employee.clearance_level = 'PUBLIC'
            projected = policy_permissions(account['roles'], directory['role_definitions'])
            assert 'doc:create:own_dept' in projected and not any(p.endswith(':all') for p in projected)
        elif sys.argv[1:] in (['set_public'], ['set_internal']):
            assert SNAPSHOT.exists() and ROLE in account['roles']
            assert employee.clearance_level in ('PUBLIC', 'INTERNAL')
            employee.clearance_level = 'PUBLIC' if sys.argv[1] == 'set_public' else 'INTERNAL'
        elif sys.argv[1:] == ['restore']:
            before = json.loads(SNAPSHOT.read_text())
            assert str(employee.id) == before['employee_id']
            assert employee.clearance_level in ('INTERNAL', before['clearance_level'])
            employee.clearance_level = before['clearance_level']
            account['roles'] = [role for role in account['roles'] if role != ROLE]
            assert not any(ROLE in value.get('roles', []) for value in directory['accounts'].values())
            directory['role_definitions'].pop(ROLE, None)
            if employee.global_role in ('contributor', before['global_role']):
                employee.global_role = before['global_role']
                employee.global_role_source = before['global_role_source']
        else:
            raise SystemExit('Usage: apply | restore')
        config.value = json.dumps(directory, ensure_ascii=False)
        await db.commit()
        print(json.dumps({'employee_id': str(employee.id), 'action': sys.argv[1],
                          'clearance_level': employee.clearance_level, 'roles': account['roles']}))


asyncio.run(main())
