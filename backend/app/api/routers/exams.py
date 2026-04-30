from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user_id
from app.schemas.contracts import ExamExecutionRequest

from ._common import get_orchestrator

router = APIRouter(tags=["exams"])


@router.post("/exam/run")
async def run_exam(
    payload: ExamExecutionRequest,
    _user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
) -> dict:
    return await service.run_exam_code(payload.code)
