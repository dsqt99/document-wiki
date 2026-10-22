"""Email/password login and the current user's profile (mounted under /api)."""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.database.models import Employee
from app.services import auth_service, permission_engine

router = APIRouter()

MIN_PASSWORD_LENGTH = 6


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


def department_names(emp) -> list[str]:
    names: list[str] = []
    for link in getattr(emp, "employee_departments", None) or []:
        dept = getattr(link, "department", None)
        if dept is not None:
            names.append(dept.name)
    return names


def user_summary(emp) -> dict:
    return {
        "id": str(emp.id),
        "name": emp.name,
        "email": emp.email,
        "role": emp.role,
        "department_ids": [str(d) for d in emp.department_ids],
        "scope_department_ids": [str(d) for d in permission_engine._user_department_ids(emp)],
        "department_names": department_names(emp),
        "permissions": permission_engine.get_effective_permissions(emp),
        "workspace_memberships": [],
    }


@router.post("/auth/login")
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    employee = await auth_service.authenticate_employee(db, body.email, body.password)
    if employee is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    from app.services.identity_directory import hydrate_identity

    await hydrate_identity(db, employee)
    if (
        settings.sso_enabled
        and not settings.sso_allow_password_login
        and (employee.email or "").lower() != (settings.default_admin_email or "").lower()
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Password login is disabled, use SSO")
    token = auth_service.create_access_token(str(employee.id), employee.role, employee.name)
    return {"access_token": token, "token_type": "bearer", "user": user_summary(employee)}


@router.get("/auth/me")
async def me(user: Employee = Depends(auth_service.get_current_user)):
    data = user_summary(user)
    workspace = data.pop("workspace_memberships")
    data.update(
        {
            "is_active": user.is_active,
            "has_mcp_token": bool(user.mcp_token_hash),
            "auth_provider": user.auth_provider,
            "workspace_memberships": workspace,
        }
    )
    return data


@router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    user: Employee = Depends(auth_service.get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.password_hash:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "No password set. Contact admin.")
    if not auth_service.verify_password(body.current_password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Current password is incorrect")
    if len(body.new_password or "") < MIN_PASSWORD_LENGTH:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be at least 6 characters")
    user.password_hash = auth_service.hash_password(body.new_password)
    await db.commit()
    return {"message": "Password changed successfully"}


@router.get("/auth/status")
async def auth_status():
    return {"auth_required": True}
