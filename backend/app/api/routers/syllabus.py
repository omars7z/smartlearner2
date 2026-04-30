from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user_id
from app.schemas.contracts import SyllabusRequest
from app.services.agents import AgentValidationError

from ._common import get_orchestrator

router = APIRouter(tags=["syllabus"])


@router.post("/syllabus/generate")
@router.post("/syllabi")
async def generate_syllabus(
    payload: SyllabusRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.build_syllabus(user_id, payload.placement_id, payload.course_title)
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
