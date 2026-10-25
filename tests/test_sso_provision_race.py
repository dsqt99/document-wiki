"""Lần đăng nhập SSO đầu: nhiều API song song cùng tạo một tài khoản không được trả 500."""
import unittest
from unittest.mock import AsyncMock, patch

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database.models import AppConfig, Department, Employee, EmployeeDepartment
from app.routers import sso


class _StaleFirstLookup:
    """Phiên mà lần tra external_id đầu tiên không thấy bản ghi (yêu cầu kia chưa commit lúc đọc)."""

    def __init__(self, session):
        self._session = session
        self._missed = False

    def __getattr__(self, name):
        return getattr(self._session, name)

    async def execute(self, stmt, *args, **kwargs):
        result = await self._session.execute(stmt, *args, **kwargs)
        if not self._missed and "external_id" in str(stmt):
            self._missed = True

            class _Empty:
                def scalar_one_or_none(self):
                    return None

            return _Empty()
        return result


class ProvisionRaceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = create_async_engine("sqlite+aiosqlite://")
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda c: Employee.metadata.create_all(c, tables=[
                AppConfig.__table__, Department.__table__, Employee.__table__, EmployeeDepartment.__table__]))
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)
        audit = patch("app.services.audit_chain.record", new_callable=AsyncMock)
        audit.start()
        self.addCleanup(audit.stop)

    async def asyncTearDown(self):
        await self.engine.dispose()

    async def test_concurrent_first_login_reuses_row_created_by_other_request(self):
        async with self.sessions() as other:
            other.add(Employee(name="Quản trị", email="admin@cahy.vn", role="admin", global_role="admin",
                               external_id="kc-admin", auth_provider="oidc", is_active=True))
            await other.commit()

        async with self.sessions() as session:
            claims = {"sub": "kc-admin", "preferred_username": "admin_cahy", "name": "Quản trị"}
            employee = await sso._provision(_StaleFirstLookup(session), claims, ["admin"], [])
            await session.commit()

            self.assertNotIsInstance(employee, str)
            self.assertEqual(employee.external_id, "kc-admin")
            count = await session.scalar(select(func.count()).select_from(Employee))
            self.assertEqual(count, 1)
