"""Ánh xạ vai trò realm Keycloak sang global_role của wiki (một nơi gán vai trò: Keycloak).

Quyền `admin` vẫn chỉ đến từ SSO_ADMIN_ROLES; bảng ánh xạ không bao giờ cho ra `admin`.
Nguồn của mức (employees.global_role_source) quyết định ai quản lý:
- `sso`: Keycloak là nguồn sự thật, mỗi lần SSO đặt lại đúng mức theo vai trò (nâng và hạ). Hạ mức một
  vai trò hay xóa vai trò trên cổng quản trị thì người đã nhận mức cũ cũng bị hạ.
- `manual`: quản trị wiki cấp tay. Keycloak chỉ được nâng; đã nâng thì từ đó Keycloak quản lý (`sso`).

Bảng ánh xạ do Trợ lý ảo AI đẩy sang qua /internal/org-sync (vai trò tạo trên cổng quản trị) và lưu ở
app_config; chưa từng nhận thì dùng SSO_ROLE_GLOBAL_MAP trong .env.
"""

import json
from typing import Iterable, Optional

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

GLOBAL_ROLE_RANK = {"viewer": 0, "contributor": 1, "knowledge_manager": 2}
ROLE_MAP_CONFIG_KEY = "sso_role_global_map"
SOURCE_SSO = "sso"
SOURCE_MANUAL = "manual"
GLOBAL_ROLE_SOURCES = (SOURCE_SSO, SOURCE_MANUAL)


def parse_role_map(raw: str) -> dict[str, str]:
    """Nhận JSON {"qt-dl": "knowledge_manager"} hoặc "qt-dl:knowledge_manager,qt-nd:viewer"."""
    raw = (raw or "").strip()
    if not raw:
        return {}
    pairs: dict = {}
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            logger.warning("SSO_ROLE_GLOBAL_MAP không phải JSON hợp lệ — bỏ qua")
            return {}
        pairs = data if isinstance(data, dict) else {}
    else:
        for item in raw.split(","):
            role, _, target = item.partition(":")
            pairs[role] = target
    return clean_role_map(pairs)


def clean_role_map(pairs: dict) -> dict[str, str]:
    """Bỏ cặp rỗng hoặc global_role không hợp lệ (gồm `admin`)."""
    result: dict[str, str] = {}
    for role, target in pairs.items():
        role, target = str(role).strip(), str(target).strip()
        if not role:
            continue
        if target not in GLOBAL_ROLE_RANK:
            logger.warning(f"SSO_ROLE_GLOBAL_MAP: bỏ qua '{role}' → '{target}' (global_role không hợp lệ)")
            continue
        result[role] = target
    return result


def derived_global_role(roles: Iterable[str], role_map: dict[str, str]) -> Optional[str]:
    """global_role cao nhất trong các vai trò Keycloak có ánh xạ; None nếu không vai trò nào có."""
    targets = [role_map[r] for r in roles if r in role_map]
    return max(targets, key=GLOBAL_ROLE_RANK.__getitem__) if targets else None


def reconcile_global_role(
    current: Optional[str], source: Optional[str], roles: Iterable[str], role_map: dict[str, str], default: str,
) -> tuple[str, str]:
    """(global_role, nguồn) mới theo vai trò Keycloak (không dùng cho tài khoản admin)."""
    current = current or default
    if current not in GLOBAL_ROLE_RANK:
        return current, source or SOURCE_MANUAL
    target = derived_global_role(roles, role_map)
    if source == SOURCE_MANUAL:
        if target and GLOBAL_ROLE_RANK[target] > GLOBAL_ROLE_RANK[current]:
            return target, SOURCE_SSO
        return current, SOURCE_MANUAL
    return target or default, SOURCE_SSO


def sync_employee_roles(
    employee, roles: Optional[Iterable[str]], is_admin: bool, role_map: dict[str, str],
    default_global_role: str, default_admin_email: str,
) -> tuple[tuple[str, str], tuple[str, str]]:
    """Đặt role/global_role của một nhân viên SSO theo vai trò Keycloak; trả về (trước, sau) = (global_role, nguồn).

    Dùng chung cho lúc đăng nhập SSO và cho lệnh đổi vai trò tức thì từ cổng quản trị.
    Keycloak là nguồn quyền admin; tài khoản admin mặc định giữ làm lối vào dự phòng.
    """
    before = (employee.global_role, employee.global_role_source)
    if is_admin:
        employee.role = "admin"
        employee.global_role = "admin"
        employee.global_role_source = SOURCE_SSO
    elif (employee.role == "admin" or employee.global_role == "admin") and (
        employee.email.lower() != default_admin_email.lower()
    ):
        employee.role = "employee"
        if employee.global_role == "admin":
            employee.global_role = default_global_role
            employee.global_role_source = SOURCE_SSO
    if not is_admin and roles is not None and employee.global_role != "admin":
        employee.global_role, employee.global_role_source = reconcile_global_role(
            employee.global_role, employee.global_role_source, roles, role_map, default_global_role,
        )
    return before, (employee.global_role, employee.global_role_source)


async def load_role_map(db: AsyncSession) -> dict[str, str]:
    """Bảng ánh xạ đang hiệu lực: bản Trợ lý ảo AI đã đẩy sang, không có thì lấy từ .env."""
    from app.config import settings
    from app.database.models import AppConfig

    row = await db.get(AppConfig, ROLE_MAP_CONFIG_KEY)
    if row is not None and row.value is not None:
        return parse_role_map(row.value)
    return settings.sso_role_map
