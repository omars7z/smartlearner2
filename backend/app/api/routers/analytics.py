from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.security import get_current_user_id

from ._common import get_orchestrator

router = APIRouter(tags=["analytics"])


@router.get("/analytics/summary")
async def analytics_summary(
    user_id: Annotated[int, Depends(get_current_user_id)],
    service=Depends(get_orchestrator),
    track: str | None = Query(default=None),
) -> dict:
    try:
        return await service.build_analytics_summary(user_id=user_id, track=track)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

