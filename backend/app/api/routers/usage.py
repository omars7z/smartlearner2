from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.groq_rate_limits import snapshot_json
from app.core.security import get_current_user_id

router = APIRouter(tags=["usage"])


@router.get("/usage/rate-limits")
async def get_groq_rate_limits(_user_id: Annotated[int, Depends(get_current_user_id)]) -> dict:
    return snapshot_json()
