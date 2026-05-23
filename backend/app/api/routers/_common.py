from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exam_constants import parse_exam_lesson_ref, parse_lesson_id

__all__ = ["get_orchestrator", "parse_lesson_id", "parse_exam_lesson_ref", "require_admin"]
from app.core.security import get_current_user
from app.db.session import get_db
from app.services.orchestrator import OrchestratorService


def get_orchestrator(db: Annotated[AsyncSession, Depends(get_db)]) -> OrchestratorService:
    return OrchestratorService(db)


def require_admin(user=Depends(get_current_user)):
    if getattr(user, "role", "student") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
