from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.errors import LessonLockedError
from app.core.security import get_current_user_id
from app.schemas.contracts import (
    LessonGenerationRequest,
    QuickAssessmentGenerateRequest,
    QuickAssessmentGradeRequest,
    SubmitAssessmentRequest,
)
from app.services.agents import AgentValidationError

from ._common import get_orchestrator, parse_lesson_id

router = APIRouter(tags=["lessons"])


@router.post("/lessons/generate")
async def generate_lesson(
    payload: LessonGenerationRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.generate_lesson_content(user_id, payload.lesson_id)
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.generate_lesson_content(user_id, parse_lesson_id(lesson_id))
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        if "Invalid literal" in str(exc) or "invalid literal" in str(exc):
            raise HTTPException(status_code=400, detail=f"Invalid lesson_id format: {lesson_id}")
        raise HTTPException(status_code=404, detail=str(exc))
    except TypeError:
        raise HTTPException(status_code=400, detail=f"Invalid lesson_id format: {lesson_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating lesson content: {str(exc)}")


@router.post("/lessons/{lesson_id}/assessment")
async def generate_lesson_assessment(
    lesson_id: str,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.generate_lesson_assessment(user_id=user_id, lesson_id=parse_lesson_id(lesson_id))
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/lessons/{lesson_id}/submit-assessment")
async def submit_lesson_assessment(
    lesson_id: str,
    payload: SubmitAssessmentRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.submit_lesson_assessment(
            user_id=user_id,
            lesson_id=parse_lesson_id(lesson_id),
            answers=[a.model_dump() for a in payload.answers],
        )
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/lessons/quick-assessment/generate")
async def quick_assessment_generate(
    payload: QuickAssessmentGenerateRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        data = await service.generate_lesson_assessment(user_id=user_id, lesson_id=parse_lesson_id(payload.lesson_id))
        questions = data.get("questions") or []
        out_q = []
        for i, q in enumerate(questions):
            qid = str(q.get("id") or f"q{i}")
            out_q.append(
                {
                    "id": qid,
                    "text": str(q.get("question") or ""),
                    "options": list(q.get("choices") or []),
                }
            )
        return {
            "status": "ok",
            "lesson_id": payload.lesson_id,
            "topic": payload.topic,
            "questions": out_q,
        }
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/lessons/quick-assessment/grade")
async def quick_assessment_grade(
    payload: QuickAssessmentGradeRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        converted = []
        for a in payload.answers:
            qid = a.question_id
            idx = 0
            if qid.startswith("q"):
                try:
                    idx = int(qid[1:])
                except ValueError:
                    idx = 0
            converted.append({"question_index": idx, "choice_index": a.answer_index})
        result = await service.submit_lesson_assessment(
            user_id=user_id,
            lesson_id=parse_lesson_id(payload.lesson_id),
            answers=converted,
        )
        score = int(result.get("score") or 0)
        if result.get("passed") is True:
            next_action = "advance_to_next_lesson"
        elif result.get("locked") is True:
            next_action = "review_required_locked"
        elif result.get("next_action") == "go_to_sub_lessons":
            next_action = "go_to_sub_lessons"
        elif result.get("next_action") == "retry_after_regeneration":
            next_action = "retry_after_regeneration"
        else:
            next_action = "retry_after_regeneration"
        return {
            "status": "ok",
            "lesson_id": payload.lesson_id,
            "topic": payload.topic,
            "grading": {"correct_count": score, "total": 5, "per_question": []},
            "next_action": next_action,
            "updated_syllabus_modules": result.get("updated_syllabus_modules"),
            "follow_up_explanation": {
                "explanation": {"core_explanation": str(result.get("message") or "Assessment processed.")}
            },
        }
    except LessonLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": LessonLockedError.default_message},
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
