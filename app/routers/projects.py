import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.database.models import Employee, Project
from app.services.auth_service import get_current_user

router = APIRouter(tags=["projects"])


class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    _user: Employee = Depends(get_current_user),
):
    """List all active workspaces / projects."""
    stmt = (
        select(Project)
        .where(Project.status == "active")
        .order_by(Project.name.asc())
    )
    result = await db.execute(stmt)
    return result.scalars().all()


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    body: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Create a new workspace / project."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tên không gian làm việc không được để trống")

    # Check for duplicate active project name
    stmt = select(Project).where(Project.name == name, Project.status == "active")
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail=f"Không gian làm việc '{name}' đã tồn tại")

    project = Project(
        name=name,
        description=body.description,
        status="active",
        created_by_id=user.id,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)
    return project


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Employee = Depends(get_current_user),
):
    """Soft delete or archive a workspace / project."""
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Không tìm thấy không gian làm việc")

    project.status = "archived"
    await db.commit()
    return {"message": "Không gian làm việc đã được lưu trữ", "id": str(project_id)}
