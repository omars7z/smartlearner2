from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.entities import Course, Lesson, PlacementTest


class CourseRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_placement_test(self, user_id: int, questions_json: dict) -> PlacementTest:
        placement = PlacementTest(user_id=user_id, questions_json=questions_json)
        self.db.add(placement)
        await self.db.commit()
        await self.db.refresh(placement)
        return placement

    async def update_placement_score(self, placement_id: int, score: int) -> PlacementTest | None:
        placement = await self.db.get(PlacementTest, placement_id)
        if placement is None:
            return None
        placement.score = score
        await self.db.commit()
        await self.db.refresh(placement)
        return placement

    async def create_course_with_lessons(
        self,
        user_id: int,
        title: str,
        level: str,
        lessons: list[dict],
    ) -> Course:
        course = Course(user_id=user_id, title=title, level=level)
        self.db.add(course)
        await self.db.flush()
        for index, lesson in enumerate(lessons, start=1):
            self.db.add(
                Lesson(
                    course_id=course.id,
                    title=lesson["title"],
                    topic=lesson["topic"],
                    order_index=index,
                    prerequisites_json=lesson.get("prerequisites", []),
                    markdown_content=lesson.get("markdown_content"),
                )
            )
        await self.db.commit()
        await self.db.refresh(course)
        return course

    async def get_course_with_lessons(self, course_id: int) -> Course | None:
        query = select(Course).options(selectinload(Course.lessons)).where(Course.id == course_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def update_lesson_content(self, lesson_id: int, markdown_content: str) -> Lesson | None:
        lesson = await self.db.get(Lesson, lesson_id)
        if lesson is None:
            return None
        lesson.markdown_content = markdown_content
        await self.db.commit()
        await self.db.refresh(lesson)
        return lesson
