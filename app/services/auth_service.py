"""Password hashing, wiki JWT sessions and bearer-token resolution."""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.database.models import Employee, EmployeeDepartment

logger = logging.getLogger(__name__)

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24
SOURCE_FILE_AUDIENCE = "arkon-source-file"
SOURCE_FILE_TOKEN_MINUTES = 15

_bearer = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def create_access_token(employee_id: str, role: str, name: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(employee_id),
        "role": role,
        "name": name,
        "exp": now + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": now,
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None
    except Exception:
        return None


def create_source_file_token(employee_id: str, source_id: str) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(employee_id),
        "src": str(source_id),
        "aud": SOURCE_FILE_AUDIENCE,
        "exp": now + timedelta(minutes=SOURCE_FILE_TOKEN_MINUTES),
        "iat": now,
    }
    return jwt.encode(claims, settings.secret_key, algorithm=JWT_ALGORITHM)


def decode_source_file_token(token: str, source_id: str) -> Optional[str]:
    try:
        claims = jwt.decode(
            token, settings.secret_key, algorithms=[JWT_ALGORITHM], audience=SOURCE_FILE_AUDIENCE
        )
    except Exception:
        return None
    if str(claims.get("src")) != str(source_id):
        return None
    sub = claims.get("sub")
    return sub or None


async def authenticate_employee(db: AsyncSession, email: str, password: str) -> Optional[Employee]:
    result = await db.execute(
        select(Employee)
        .where(Employee.email == email, Employee.is_active.is_(True))
        .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
    )
    employee = result.scalar_one_or_none()
    if employee is None or not employee.password_hash:
        return None
    if not verify_password(password, employee.password_hash):
        return None
    return employee


def is_keycloak_token(token: str) -> bool:
    from app.routers import sso

    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return False
    return header.get("alg") in sso.SIGNING_ALGORITHMS


async def _load_employee(db: AsyncSession, employee_id: uuid.UUID) -> Optional[Employee]:
    result = await db.execute(
        select(Employee)
        .where(Employee.id == employee_id)
        .options(selectinload(Employee.employee_departments).selectinload(EmployeeDepartment.department))
        .execution_options(populate_existing=True)
    )
    return result.scalar_one_or_none()


async def employee_from_bearer(db: AsyncSession, token: str) -> Employee:
    import sys

    this = sys.modules[__name__]
    employee = None
    claims = decode_access_token(token)
    if claims is not None:
        try:
            emp_id = uuid.UUID(str(claims.get("sub")))
        except (ValueError, TypeError):
            emp_id = None
        if emp_id is not None:
            employee = await this._load_employee(db, emp_id)
    elif this.is_keycloak_token(token):
        from app.routers import sso

        outcome = await sso.employee_from_access_token(db, token)
        if isinstance(outcome, str):
            await db.rollback()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, f"Keycloak token rejected ({outcome})")
        await db.commit()
        employee = await this._load_employee(db, outcome.id)
    else:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if employee is None or not employee.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Account not found or deactivated")
    return employee


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> Employee:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    employee = await employee_from_bearer(db, credentials.credentials)
    if not employee.global_role:
        employee.global_role = "viewer"
    return employee


async def require_admin(user: Employee = Depends(get_current_user)) -> Employee:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin access required")
    return user


def _permission_granted(permission: str, perms: set) -> bool:
    if permission in perms:
        return True
    parts = permission.split(":")
    if len(parts) == 2:
        return f"{permission}:own_dept" in perms or f"{permission}:all" in perms
    if parts[-1] == "own_dept":
        return ":".join(parts[:-1] + ["all"]) in perms
    return False


def require_permission(permission: str):
    async def _check(user: Employee = Depends(get_current_user)) -> Employee:
        if user.role == "admin":
            return user
        from app.services import permission_engine

        perms = permission_engine._get_user_permissions(user)
        if _permission_granted(permission, perms):
            return user
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Permission required: {permission}")

    return Depends(_check)
