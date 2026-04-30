from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user_id
from app.repositories.course_repository import CourseRepository
from app.schemas.contracts import (
    PlacementAnswerRequest,
    PlacementGenerationRequest,
    PlacementStartRequest,
    PlacementSubmissionRequest,
)
from app.services.agents import AgentValidationError
from app.services.llm_client import LLMClientError

from ._common import get_db, get_orchestrator

router = APIRouter(tags=["placement"])


@router.post("/placement/start")
@router.post("/placements/sessions")
async def placement_start(
    payload: PlacementStartRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.start_placement_session(user_id, payload.track)
    except LLMClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/placement/answer")
@router.post("/placements/sessions/{placement_id}/answers")
async def placement_answer(
    payload: PlacementAnswerRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.answer_placement_step(
            user_id,
            payload.placement_id,
            payload.track,
            payload.question_id,
            payload.answer_index,
        )
    except LLMClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/placement/generate")
@router.post("/placements")
async def generate_placement(
    payload: PlacementGenerationRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.create_placement_test(
            user_id,
            payload.level,
            payload.question_count,
            track=payload.track,
        )
    except LLMClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/placement/submit")
async def submit_placement(
    payload: PlacementSubmissionRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db=Depends(get_db),
) -> dict:
    repo = CourseRepository(db)
    placement = await repo.update_placement_score(payload.placement_id, payload.score)
    if placement is None or placement.user_id != user_id:
        raise HTTPException(status_code=404, detail="Placement test not found")
    return {"placement_id": placement.id, "score": placement.score}
