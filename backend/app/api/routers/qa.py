from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import get_current_user_id
from app.schemas.contracts import ChatRequest

from ._common import get_orchestrator

router = APIRouter(tags=["qa"])


@router.post("/chat/ask")
@router.post("/qa/ask")
async def ask_chatbot(
    payload: ChatRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    try:
        return await service.answer_question(
            user_id,
            payload.question,
            lesson_id=payload.lesson_id,
            current_topic=payload.current_topic,
            student_context=payload.student_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
