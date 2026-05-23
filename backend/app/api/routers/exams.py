import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.errors import LessonLockedError
from app.core.security import get_current_user_id
from app.schemas.contracts import ExamExecutionRequest, ExamGenerateRequest, ExamGradeRequest
from app.services.agents import AgentValidationError
from app.services.llm_client import LLMClientError

from ._common import get_orchestrator, parse_lesson_id

logger = logging.getLogger(__name__)

router = APIRouter(tags=["exams"])


@router.post("/exams/generate")
async def generate_exam(
    payload: ExamGenerateRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        lesson_id = parse_lesson_id(payload.lesson_id)
        return await service.generate_exam(
            user_id=user_id,
            lesson_id=lesson_id,
            level=payload.level,
            question_count=payload.question_count,
        )
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except LLMClientError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("generate_exam failed user_id=%s lesson_id=%s", user_id, payload.lesson_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Exam generation failed ({type(exc).__name__}).",
        ) from exc


@router.post("/exams/grade")
async def grade_exam(
    payload: ExamGradeRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        lesson_id = parse_lesson_id(payload.lesson_id)
        answers = [{"question_id": a.question_id, "answer_index": a.answer_index} for a in payload.answers]
        return await service.grade_exam(user_id=user_id, lesson_id=lesson_id, answers=answers)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception("grade_exam failed user_id=%s lesson_id=%s", user_id, payload.lesson_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Exam grading failed ({type(exc).__name__}).",
        ) from exc


@router.post("/exam/run")
async def run_exam(
    payload: ExamExecutionRequest,
    _user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    return await service.run_exam_code(payload.code)
