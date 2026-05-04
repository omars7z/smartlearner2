from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entities import LessonProgress


class LessonProgressRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, *, user_id: int, lesson_id: int) -> LessonProgress:
        q = select(LessonProgress).where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id == lesson_id,
        )
        res = await self.db.execute(q)
        row = res.scalar_one_or_none()
        if row is not None:
            return row
        row = LessonProgress(user_id=user_id, lesson_id=lesson_id)
        self.db.add(row)
        await self.db.flush()
        return row

    async def save(self, row: LessonProgress) -> LessonProgress:
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def get_passed_map(self, user_id: int, lesson_ids: list[int]) -> dict[int, bool]:
        if not lesson_ids:
            return {}
        q = select(LessonProgress.lesson_id, LessonProgress.passed).where(
            LessonProgress.user_id == user_id,
            LessonProgress.lesson_id.in_(lesson_ids),
        )
        res = await self.db.execute(q)
        return {int(r[0]): bool(r[1]) for r in res.all()}

