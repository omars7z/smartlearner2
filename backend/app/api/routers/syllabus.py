import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.security import get_current_user_id
from app.schemas.contracts import SyllabusRequest
from app.services.agents import AgentValidationError
from app.services.llm_client import LLMClientError

from ._common import get_orchestrator

logger = logging.getLogger(__name__)

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
    except LLMClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception(
            "build_syllabus failed user_id=%s placement_id=%s",
            user_id,
            payload.placement_id,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Syllabus generation failed ({type(exc).__name__}). See backend terminal for the full traceback.",
        ) from exc
