import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_repository import AgentRepository
from app.repositories.course_repository import CourseRepository
from app.services.agents import (
    AgentValidationError,
    LessonGeneratorAgent,
    LessonValidatorAgent,
    PlacementGeneratorAgent,
    PlacementValidatorAgent,
    QAGeneratorAgent,
    QAValidatorAgent,
    SyllabusGeneratorAgent,
    SyllabusValidatorAgent,
)
from app.services.guardrails import run_exam_code_in_sandbox
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService


def _track_to_level(track: str) -> str:
    t = (track or "python").lower().replace(" ", "-")
    if t in ("python", "python-foundations"):
        return "Beginner"
    if t in ("deep-learning", "nlp", "ml"):
        return "Intermediate"
    return "Beginner"


def _score_to_level(pct: int) -> str:
    if pct < 40:
        return "beginner"
    if pct < 75:
        return "intermediate"
    return "advanced"


def _format_placement_question(q: dict, index: int, total: int, track: str) -> dict:
    choices = q.get("choices") or []
    return {
        "id": f"q{index}",
        "order": index + 1,
        "total": total,
        "text": q.get("question", ""),
        "difficulty": "medium",
        "topic": str(q.get("concept") or track),
        "options": choices,
    }


class OrchestratorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.rag = RAGService()
        self.course_repo = CourseRepository(db)
        self.agent_repo = AgentRepository(db)

        self.placement_generator = PlacementGeneratorAgent(self.llm, self.rag)
        self.placement_validator = PlacementValidatorAgent()
        self.syllabus_generator = SyllabusGeneratorAgent(self.llm)
        self.syllabus_validator = SyllabusValidatorAgent()
        self.lesson_generator = LessonGeneratorAgent(self.llm, self.rag)
        self.lesson_validator = LessonValidatorAgent()
        self.qa_generator = QAGeneratorAgent(self.llm, self.rag)
        self.qa_validator = QAValidatorAgent()

    async def create_placement_test(self, user_id: int, level: str, question_count: int) -> dict:
        raw = self.placement_generator.generate(level=level, question_count=question_count)
        await self.agent_repo.log_run(
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={"level": level, "question_count": question_count, "flow": "generate"},
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.placement_validator.validate(raw, level, question_count)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": level, "question_count": question_count},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.placement_validator.name,
            stage="validate",
            input_json={"level": level, "question_count": question_count},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        placement = await self.course_repo.create_placement_test(user_id=user_id, questions_json=generated)
        return {"placement_id": placement.id, "questions": generated["questions"]}

    async def start_placement_session(self, user_id: int, track: str) -> dict:
        level = _track_to_level(track)
        question_count = 5
        raw = self.placement_generator.generate(level=level, question_count=question_count)
        await self.agent_repo.log_run(
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={
                "level": level,
                "question_count": question_count,
                "track": track,
                "flow": "session",
            },
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.placement_validator.validate(raw, level, question_count)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": level, "question_count": question_count, "track": track},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.placement_validator.name,
            stage="validate",
            input_json={"level": level, "question_count": question_count, "track": track},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        full_payload = {
            **generated,
            "placement_session": {
                "track": track,
                "cursor": 0,
                "correct_count": 0,
                "level": level,
                "wrong_concepts": [],
                "strong_concepts": [],
            },
        }
        placement = await self.course_repo.create_placement_test(user_id=user_id, questions_json=full_payload)
        questions = generated["questions"]
        n = len(questions)
        next_q = _format_placement_question(questions[0], 0, n, track)
        return {"status": "ok", "placement_id": placement.id, "next_question": next_q}

    async def answer_placement_step(
        self,
        user_id: int,
        placement_id: int,
        track: str,
        question_id: str,
        answer_index: int,
    ) -> dict:
        from app.models.entities import PlacementTest

        placement = await self.db.get(PlacementTest, placement_id)
        if placement is None or placement.user_id != user_id:
            raise ValueError("Placement test not found")
        data = placement.questions_json
        if not isinstance(data, dict):
            raise ValueError("Invalid placement data")
        questions = data.get("questions") or []
        sess = data.get("placement_session") or {}
        if sess.get("track") != track:
            raise ValueError("Track mismatch")
        if placement.score is not None:
            raise ValueError("Placement test already completed")
        cursor = int(sess.get("cursor", 0))
        correct_count = int(sess.get("correct_count", 0))
        wrong_concepts: list = list(sess.get("wrong_concepts") or [])
        strong_concepts: list = list(sess.get("strong_concepts") or [])

        if not question_id.startswith("q"):
            raise ValueError("Invalid question id")
        try:
            qi = int(question_id[1:])
        except ValueError as exc:
            raise ValueError("Invalid question id") from exc

        # If cursor from saved state is stale, fall back to the submitted question id.
        if qi != cursor:
            cursor = qi

        if cursor >= len(questions):
            raise ValueError("Invalid state")
        q = questions[qi]
        choices = q.get("choices") or []
        if answer_index >= len(choices):
            raise ValueError("Invalid answer index")
        selected = choices[answer_index]
        correct_ans = q.get("correct_answer")
        is_correct = selected == correct_ans
        if is_correct:
            correct_count += 1
            c = q.get("concept")
            if c:
                strong_concepts.append(str(c))
        else:
            c = q.get("concept")
            if c:
                wrong_concepts.append(str(c))

        cursor += 1
        sess["cursor"] = cursor
        sess["correct_count"] = correct_count
        sess["wrong_concepts"] = wrong_concepts
        sess["strong_concepts"] = strong_concepts
        data["placement_session"] = sess
        placement.questions_json = data

        n = len(questions)
        if cursor < n:
            next_q = _format_placement_question(questions[cursor], cursor, n, track)
            await self.db.commit()
            await self.db.refresh(placement)
            return {"status": "ok", "finished": False, "next_question": next_q}

        pct = int(round(correct_count / n * 100)) if n else 0
        level_str = _score_to_level(pct)
        placement.score = pct
        await self.db.commit()
        await self.db.refresh(placement)

        weak_unique = list(dict.fromkeys(wrong_concepts))
        strong_unique = list(dict.fromkeys(strong_concepts))
        recommended = weak_unique[0] if weak_unique else (questions[0].get("concept") if questions else "Python Basics")

        placement_result = {
            "track": track,
            "score": correct_count,
            "percentage": pct,
            "level": level_str,
            "strong_topics": strong_unique[:10],
            "weak_topics": weak_unique[:10],
            "recommended_start_topic": str(recommended),
        }
        return {"status": "ok", "finished": True, "placement_result": placement_result}

    async def build_syllabus(self, user_id: int, placement_id: int, course_title: str) -> dict:
        from app.models.entities import PlacementTest

        placement = await self.db.get(PlacementTest, placement_id)
        if placement is None or placement.user_id != user_id:
            raise ValueError("Placement test not found")
        score = placement.score or 0
        level_str = _score_to_level(score)
        raw_syllabus = self.syllabus_generator.generate(score=score, level=level_str)
        await self.agent_repo.log_run(
            agent_name=self.syllabus_generator.name,
            stage="generate",
            input_json={"placement_id": placement_id, "score": score, "level": level_str, "course_title": course_title},
            output_json=raw_syllabus,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.syllabus_validator.validate(raw_syllabus)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.syllabus_validator.name,
                stage="validate",
                input_json={"placement_id": placement_id, "score": score, "level": level_str},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.syllabus_validator.name,
            stage="validate",
            input_json={"placement_id": placement_id, "score": score, "level": level_str},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )

        # Transform lessons from syllabus format to CourseRepository format
        # Syllabus returns: {"topic": str, "description": str}
        # CourseRepository expects: {"title": str, "topic": str, "prerequisites": [], "markdown_content": str}
        transformed_lessons = []
        for idx, lesson in enumerate(generated.get("lessons", []), start=1):
            transformed_lessons.append({
                "title": lesson.get("topic", ""),
                "topic": lesson.get("topic", "").lower().replace(" ", "_"),
                "prerequisites": lesson.get("prerequisites", []),
                "markdown_content": lesson.get("description", ""),
            })
        
        course = await self.course_repo.create_course_with_lessons(
            user_id=user_id,
            title=course_title,
            level=level_str.capitalize(),
            lessons=transformed_lessons,
        )
        
        # Refresh the course with lessons loaded
        course = await self.course_repo.get_course_with_lessons(course.id)
        if course is None:
            raise ValueError("Failed to retrieve created course with lessons")
        
        # Transform to frontend ModuleDto format with embedded lessons
        # Each lesson becomes a module with one lesson inside
        modules = []
        for idx, lesson in enumerate(course.lessons, start=1):
            modules.append({
                "id": f"module_{idx}",
                "module_id": f"module_{idx}",
                "title": lesson.topic.replace("_", " ").title(),
                "description": f"Learn about {lesson.topic.replace('_', ' ').lower()}",
                "topics": [lesson.topic],
                "duration": "20 min",
                "target_level": level_str,
                "lessons": [
                    {
                        "lesson_id": f"lesson_{lesson.id}",
                        "id": f"lesson_{lesson.id}",
                        "title": lesson.title,
                        "topic": lesson.topic,
                        "topic_name": lesson.topic,
                        "duration_minutes": 20,
                        "order": lesson.order_index,
                    }
                ]
            })
        
        return {
            "status": "success",
            "intent": "syllabus_generation",
            "result": {
                "status": "generated",
                "track": "python",
                "level": level_str,
                "syllabus": modules,
                "validation": {
                    "status": "valid",
                    "is_valid": True,
                    "issues": []
                }
            }
        }

    async def generate_lesson_content(self, user_id: int, lesson_id: int) -> dict:
        from app.models.entities import Lesson

        lesson = await self.db.get(Lesson, lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")
        raw_lesson = self.lesson_generator.generate(topic=lesson.topic)
        await self.agent_repo.log_run(
            agent_name=self.lesson_generator.name,
            stage="generate",
            input_json={"lesson_id": lesson_id, "topic": lesson.topic},
            output_json=raw_lesson,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.lesson_validator.validate(raw_lesson)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.lesson_validator.name,
                stage="validate",
                input_json={"lesson_id": lesson_id, "topic": lesson.topic},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.lesson_validator.name,
            stage="validate",
            input_json={"lesson_id": lesson_id, "topic": lesson.topic},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        updated = await self.course_repo.update_lesson_content(lesson.id, generated["markdown"])
        
        # Format response matching frontend StructuredLesson interface
        return {
            "status": "success",
            "lesson": {
                "lesson_id": f"lesson_{updated.id}",
                "title": updated.title,
                "duration_minutes": 20,
                "sections": [
                    {
                        "type": "explanation",
                        "title": updated.title,
                        "content": updated.markdown_content or "",
                    }
                ]
            },
            "generated_in_ms": 0,
            "llm_used": True,
        }

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

        raw_qa = self.qa_generator.generate(question=question, lesson_markdown=lesson_markdown)
        await self.agent_repo.log_run(
            agent_name=self.qa_generator.name,
            stage="generate",
            input_json={
                "lesson_id": lesson_id,
                "current_topic": current_topic,
                "question": question,
            },
            output_json=raw_qa,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.qa_validator.validate(raw_qa)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.qa_validator.name,
                stage="validate",
                input_json={
                    "lesson_id": lesson_id,
                    "current_topic": current_topic,
                    "question": question,
                },
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.qa_validator.name,
            stage="validate",
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
            "routing": {"steps": ["sanitize", "rag_retrieve", "qa_generator", "qa_validator"]},
        }

    async def run_exam_code(self, code: str) -> dict:
        result = run_exam_code_in_sandbox(code)
        return {"stdout": result.stdout, "stderr": result.stderr, "return_code": result.return_code}
