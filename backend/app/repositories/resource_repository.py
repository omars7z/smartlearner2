from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import Resource


class ResourceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_resources(self) -> list[Resource]:
        res = await self.db.execute(select(Resource).order_by(Resource.id.desc()))
        return list(res.scalars().all())

    async def create_resource(
        self,
        *,
        title: str,
        url: str,
        description: str | None,
        created_by_user_id: int | None,
    ) -> Resource:
        r = Resource(
            title=title,
            url=url,
            description=description,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(r)
        await self.db.commit()
        await self.db.refresh(r)
        return r

