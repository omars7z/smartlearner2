from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.session import get_db
from app.services.orchestrator import OrchestratorService


def get_orchestrator(db: Annotated[AsyncSession, Depends(get_db)]) -> OrchestratorService:
    return OrchestratorService(db)


def parse_lesson_id(lesson_id: str) -> int:
    return int(lesson_id.replace("lesson_", "")) if lesson_id.startswith("lesson_") else int(lesson_id)


def require_admin(user=Depends(get_current_user)):
    if getattr(user, "role", "student") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user
