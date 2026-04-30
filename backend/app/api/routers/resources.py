from fastapi import APIRouter, Depends

from app.repositories.resource_repository import ResourceRepository
from app.schemas.contracts import ResourceCreateRequest, ResourceDto

from ._common import get_db, require_admin

router = APIRouter(tags=["resources"])


@router.get("/resources", response_model=list[ResourceDto])
async def list_resources(
    _admin=Depends(require_admin),
    db=Depends(get_db),
) -> list[ResourceDto]:
    repo = ResourceRepository(db)
    items = await repo.list_resources()
    return [
        ResourceDto(
            id=r.id,
            title=r.title,
            url=r.url,
            description=r.description,
            created_by_user_id=r.created_by_user_id,
        )
        for r in items
    ]


@router.post("/resources", response_model=ResourceDto)
async def create_resource(
    payload: ResourceCreateRequest,
    admin=Depends(require_admin),
    db=Depends(get_db),
) -> ResourceDto:
    repo = ResourceRepository(db)
    r = await repo.create_resource(
        title=payload.title.strip(),
        url=payload.url.strip(),
        description=(payload.description.strip() if payload.description else None),
        created_by_user_id=admin.id,
    )
    return ResourceDto(
        id=r.id,
        title=r.title,
        url=r.url,
        description=r.description,
        created_by_user_id=r.created_by_user_id,
    )
