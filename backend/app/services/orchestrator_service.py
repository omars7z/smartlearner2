import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_repository import AgentRepository
from app.repositories.course_repository import CourseRepository
from app.services.agents import LessonAgent, PlacementAgent, QAAgent, SyllabusAgent
from app.services.guardrails import run_exam_code_in_sandbox
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


class OrchestratorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.rag = RAGService()
        self.course_repo = CourseRepository(db)
        self.agent_repo = AgentRepository(db)

        self.placement_agent = PlacementAgent("placement", self.llm)
        self.syllabus_agent = SyllabusAgent("syllabus", self.llm)
        self.lesson_agent = LessonAgent(self.llm, self.rag)
        self.qa_agent = QAAgent(self.llm, self.rag)

    async def create_placement_test(self, user_id: int, level: str, question_count: int) -> dict:
        generated = self.placement_agent.generate_and_validate(level=level, question_count=question_count)
        placement = await self.course_repo.create_placement_test(user_id=user_id, questions_json=generated)
        await self.agent_repo.log_run(
            agent_name="placement",
            stage="generator-validator",
            input_json={"level": level, "question_count": question_count},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        return {"placement_id": placement.id, "questions": generated["questions"]}

    async def build_syllabus(self, user_id: int, placement_id: int, course_title: str) -> dict:
        from app.models.entities import PlacementTest

        placement = await self.db.get(PlacementTest, placement_id)
        if placement is None or placement.user_id != user_id:
            raise ValueError("Placement test not found")
        score = placement.score or 0
        generated = self.syllabus_agent.generate_and_validate(score=score)
        course = await self.course_repo.create_course_with_lessons(
            user_id=user_id,
            title=course_title,
            level="Beginner",
            lessons=generated["lessons"],
        )
        await self.agent_repo.log_run(
            agent_name="syllabus",
            stage="generator-validator",
            input_json={"placement_id": placement_id, "score": score},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        return {"course_id": course.id, "lessons": generated["lessons"]}

    async def generate_lesson_content(self, user_id: int, lesson_id: int) -> dict:
        from app.models.entities import Lesson

        lesson = await self.db.get(Lesson, lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")
        generated = self.lesson_agent.generate_and_validate(topic=lesson.topic)
        updated = await self.course_repo.update_lesson_content(lesson.id, generated["markdown"])
        await self.agent_repo.log_run(
            agent_name="lesson",
            stage="generator-validator",
            input_json={"lesson_id": lesson_id, "topic": lesson.topic},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        return {"lesson_id": updated.id, "markdown": updated.markdown_content}

    async def answer_question(
        self,
        user_id: int,
        question: str,
        lesson_id: int | None = None,
        current_topic: str | None = None,
        student_context: dict | None = None,
    ) -> dict:
        from app.models.entities import Lesson

        lesson_markdown = ""
        if lesson_id is not None and lesson_id != 0:
            lesson = await self.db.get(Lesson, lesson_id)
            if lesson is None:
                raise ValueError("Lesson not found")
            lesson_markdown = lesson.markdown_content or ""
        if current_topic:
            lesson_markdown = (lesson_markdown + f"\n\nCurrent topic: {current_topic}").strip()
        if student_context:
            lesson_markdown = (
                lesson_markdown + f"\n\nStudent context: {json.dumps(student_context, ensure_ascii=False)}"
            ).strip()
        if not lesson_markdown:
            lesson_markdown = "General Python Foundations (Python Basics)."

        generated = self.qa_agent.generate_and_validate(question=question, lesson_markdown=lesson_markdown)
        await self.agent_repo.log_run(
            agent_name="qa",
            stage="generator-validator",
            input_json={
                "lesson_id": lesson_id,
                "current_topic": current_topic,
                "question": question,
            },
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        return self._qa_envelope(generated)

    def _qa_envelope(self, generated: dict) -> dict:
        """Shape expected by frontend QAResponse (result.explanation.core_explanation + result.rag)."""
        answer = str(generated.get("answer", ""))
        rag = generated.get("rag") or {}
        return {
            "status": "ok",
            "intent": "qa_rag",
            "result": {
                "status": "ok",
                "explanation": {
                    "core_explanation": answer,
                },
                "rag": rag,
            },
            "routing": {"steps": ["sanitize", "rag_retrieve", "llm_json", "validate"]},
        }

    async def run_exam_code(self, code: str) -> dict:
        result = run_exam_code_in_sandbox(code)
        return {"stdout": result.stdout, "stderr": result.stderr, "return_code": result.return_code}
