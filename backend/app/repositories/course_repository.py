from itertools import groupby

from sqlalchemy import select, update
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
                    parent_lesson_id=None,
                    is_sub_lesson=False,
                    title=lesson["title"],
                    topic=lesson["topic"],
                    order_index=index,
                    unit_title=lesson.get("unit_title"),
                    prerequisites_json=lesson.get("prerequisites", []),
                    markdown_content=lesson.get("markdown_content"),
                    metadata_json=lesson.get("metadata_json") or {},
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

    async def get_lesson(self, lesson_id: int) -> Lesson | None:
        return await self.db.get(Lesson, lesson_id)

    async def get_lesson_with_course(self, lesson_id: int) -> Lesson | None:
        q = (
            select(Lesson)
            .options(selectinload(Lesson.course))
            .where(Lesson.id == lesson_id)
        )
        res = await self.db.execute(q)
        return res.scalar_one_or_none()

    async def list_lessons_by_course(self, course_id: int) -> list[Lesson]:
        q = select(Lesson).where(Lesson.course_id == course_id).order_by(Lesson.order_index.asc())
        res = await self.db.execute(q)
        return list(res.scalars().all())

    async def get_child_lessons(self, parent_id: int) -> list[Lesson]:
        q = (
            select(Lesson)
            .where(Lesson.parent_lesson_id == parent_id)
            .order_by(Lesson.order_index.asc())
        )
        res = await self.db.execute(q)
        return list(res.scalars().all())

    async def shift_lesson_orders_from(self, course_id: int, from_order_exclusive: int, delta: int) -> None:
        """
        Bump order_index for lessons strictly after `from_order_exclusive` by `delta`.

        SQLite enforces UNIQUE(course_id, order_index). A single UPDATE order_index = order_index + delta
        can violate that constraint while rows are rewritten, so we use a two-phase bump.
        """
        if delta == 0:
            return
        bump = 1_000_000
        await self.db.execute(
            update(Lesson)
            .where(Lesson.course_id == course_id, Lesson.order_index > from_order_exclusive)
            .values(order_index=Lesson.order_index + bump)
        )
        await self.db.flush()
        await self.db.execute(
            update(Lesson)
            .where(Lesson.course_id == course_id, Lesson.order_index > from_order_exclusive + bump)
            .values(order_index=Lesson.order_index - bump + delta)
        )
        await self.db.flush()

    async def block_end_order_index(self, lesson: Lesson) -> int:
        children = await self.get_child_lessons(lesson.id)
        if not children:
            return lesson.order_index
        return max(lesson.order_index, max(c.order_index for c in children))

    async def get_next_lesson_id(self, lesson: Lesson) -> int | None:
        end_order = await self.block_end_order_index(lesson)
        q = (
            select(Lesson.id)
            .where(
                Lesson.course_id == lesson.course_id,
                Lesson.order_index > end_order,
            )
            .order_by(Lesson.order_index.asc())
            .limit(1)
        )
        res = await self.db.execute(q)
        return res.scalar_one_or_none()

    def build_syllabus_modules_from_lessons(
        self,
        course_title: str,
        lessons: list[Lesson],
        *,
        lesson_duration_minutes: int,
        target_level: str = "beginner",
    ) -> list[dict]:
        """Shape aligned with orchestrator build_syllabus `modules` list (for client refresh)."""

        def _module_key(les: Lesson) -> str:
            ut = (les.unit_title or "").strip()
            return ut or "__single__"

        # Global course order first; groupby only merges *consecutive* same-unit rows.
        sorted_lessons = sorted(lessons, key=lambda L: L.order_index)

        modules: list[dict] = []
        mod_idx = 0
        for unit_label, group in groupby(sorted_lessons, key=_module_key):
            chunk = list(group)
            rows = [r for r in chunk if r.parent_lesson_id is None]
            if not rows:
                continue
            mod_idx += 1
            unit_title = rows[0].unit_title if rows[0].unit_title else None
            if unit_label == "__single__" and len([x for x in sorted_lessons if x.parent_lesson_id is None]) == len(
                rows
            ):
                mod_title = course_title
                mod_desc = f"Unit in {course_title}."
            else:
                mod_title = unit_title or f"Module {mod_idx}"
                mod_desc = f"Unit in {course_title}."

            def _lesson_row(les: Lesson) -> dict:
                base = {
                    "lesson_id": f"lesson_{les.id}",
                    "id": f"lesson_{les.id}",
                    "title": les.title,
                    "topic": les.topic,
                    "topic_name": les.topic,
                    "duration_minutes": lesson_duration_minutes,
                    "order": les.order_index,
                    "course_id": les.course_id,
                    "parent_lesson_id": les.parent_lesson_id,
                    "is_sub_lesson": bool(les.is_sub_lesson),
                }
                return base

            lesson_payloads: list[dict] = []
            for les in rows:
                row = _lesson_row(les)
                kids = sorted([x for x in sorted_lessons if x.parent_lesson_id == les.id], key=lambda x: x.order_index)
                if kids:
                    row["sub_lessons"] = [
                        {**_lesson_row(k), "is_final_sub_lesson": k.id == kids[-1].id} for k in kids
                    ]
                lesson_payloads.append(row)

            modules.append({
                "id": f"module_{mod_idx}",
                "module_id": f"module_{mod_idx}",
                "title": mod_title,
                "description": mod_desc,
                "topics": list(dict.fromkeys([r.topic for r in chunk])),
                "duration": f"{len(chunk) * lesson_duration_minutes} min",
                "target_level": target_level,
                "lessons": lesson_payloads,
            })
        return modules

    async def persist_sub_lesson_split(
        self,
        parent: Lesson,
        *,
        overview_markdown: str,
        children: list[dict],
    ) -> list[Lesson]:
        """
        children: dicts with keys title, topic, markdown_content, metadata_json (optional).
        Inserts sub-lessons immediately after parent and shifts following lesson orders.
        """
        n = len(children)
        if n < 1:
            return []
        await self.shift_lesson_orders_from(parent.course_id, parent.order_index, n)
        created: list[Lesson] = []
        for i, row in enumerate(children):
            les = Lesson(
                course_id=parent.course_id,
                parent_lesson_id=parent.id,
                is_sub_lesson=True,
                title=str(row["title"])[:255],
                topic=str(row["topic"])[:100],
                order_index=parent.order_index + 1 + i,
                unit_title=parent.unit_title,
                markdown_content=str(row.get("markdown_content") or ""),
                prerequisites_json=list(parent.prerequisites_json or []),
                metadata_json=row.get("metadata_json") or {},
            )
            self.db.add(les)
            created.append(les)
        parent.markdown_content = overview_markdown
        meta = dict(parent.metadata_json or {})
        meta["remediation_split"] = True
        parent.metadata_json = meta
        await self.db.commit()
        for les in created:
            await self.db.refresh(les)
        await self.db.refresh(parent)
        return created
