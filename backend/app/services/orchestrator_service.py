import json
import re
from itertools import groupby

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

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
from app.services.agents.syllabus_common import (
    syllabus_allowed_topics_ordered,
    syllabus_rubric_concepts_for_level,
)
from app.services.guardrails import run_exam_code_in_sandbox, sanitize_prompt
from app.services.llm_client import LLMClient
from app.services.rag_service import RAGService
from app.services.assessment_service import AssessmentService
from app.repositories.lesson_progress_repository import LessonProgressRepository

from app.core.placement_rubric import (
    LEVEL_LABELS,
    LEVEL_ORDER,
    LEVEL_TO_SCORE_PCT,
    PASS_THRESHOLD,
    QUESTIONS_PER_LEVEL,
    normalize_level,
)


def _topic_slug(topic: str) -> str:
    """Stable slug for Lesson.topic (search / RAG key)."""
    s = (topic or "").lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "topic"


def _placement_answer_matches(selected, correct) -> bool:
    """LLM/JSON may mix ints, floats, and strings for the same MCQ choice."""
    if selected is None or correct is None:
        return False
    a, b = str(selected).strip(), str(correct).strip()
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def _set_placement_questions_json(placement, data: dict) -> None:
    """Assign JSON so the ORM always persists (in-place dict edits are often ignored)."""
    placement.questions_json = json.loads(json.dumps(data))
    flag_modified(placement, "questions_json")


def _score_to_level(pct: int) -> str:
    """Legacy mapping when only a percentage is known (no multi-tier session)."""
    if pct < 40:
        return "beginner"
    if pct < 75:
        return "intermediate"
    return "advanced"


def _format_placement_question(
    q: dict,
    index_in_level: int,
    track: str,
    level_key: str,
    level_index: int,
) -> dict:
    choices = q.get("choices") or []
    return {
        "id": f"q{index_in_level}",
        "order": index_in_level + 1,
        "total": QUESTIONS_PER_LEVEL,
        "text": q.get("question", ""),
        "difficulty": level_key,
        "topic": str(q.get("concept") or track),
        "options": choices,
        "level": level_key,
        "level_label": LEVEL_LABELS.get(level_key, level_key),
        "level_index": level_index,
        "level_stage": level_index + 1,
        "levels_total": len(LEVEL_ORDER),
    }


def _build_local_syllabus_payload(level: str) -> dict:
    """Deterministic syllabus fallback when LLM output is missing/invalid."""
    lvl = normalize_level(level)
    topics = syllabus_allowed_topics_ordered(lvl)
    concepts = syllabus_rubric_concepts_for_level(lvl)
    concept_by_topic = {topics[i]: concepts[i] for i in range(min(len(topics), len(concepts)))}
    if concepts:
        concept_fallback = concepts[-1]
    else:
        concept_fallback = "Python fundamentals"

    chapter_map = {
        "beginner": [1, 2, 3, 6],
        "intermediate": [4, 5, 7, 8, 9, 10],
        "advanced": [11, 12, 13, 14],
        "very_advanced": [15, 16],
    }
    chapter_titles = {
        1: "Why we program",
        2: "Variables, Expressions and Statements",
        3: "Conditional execution",
        4: "Functions",
        5: "Iteration",
        6: "Strings",
        7: "Files",
        8: "Lists",
        9: "Dictionaries",
        10: "Tuples",
        11: "Regular Expressions",
        12: "Networked Programs",
        13: "Web Services",
        14: "Object-Oriented Programming",
        15: "Databases and SQL",
        16: "Visualizing Data",
    }
    allowed_chapters = chapter_map.get(lvl, chapter_map["beginner"])
    chunk = max(1, (len(topics) + len(allowed_chapters) - 1) // len(allowed_chapters))

    units: list[dict] = []
    idx = 0
    for ch in allowed_chapters:
        part = topics[idx : idx + chunk]
        idx += chunk
        if not part:
            break
        lessons: list[dict] = []
        for t in part:
            lessons.append(
                {
                    "topic": t,
                    "lesson_title": f"Practical {t}",
                    "description": (
                        f"Learn {t} through practical Python exercises and small examples. "
                        "Practice predictable coding patterns and explain your reasoning clearly."
                    ),
                    "learning_objectives": [
                        f"Identify key ideas behind {t}.",
                        f"Write a short Python example using {t}.",
                        f"Debug common mistakes related to {t}.",
                    ],
                    "rubric_concept": concept_by_topic.get(t, concept_fallback),
                    "chapter_ref": ch,
                }
            )
        units.append(
            {
                "chapter": ch,
                "title": chapter_titles.get(ch, f"Chapter {ch}"),
                "summary": f"Core learning outcomes for {chapter_titles.get(ch, f'Chapter {ch}')}.",
                "lessons": lessons,
            }
        )
    return {"units": units}


class OrchestratorService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm = LLMClient()
        self.llm_validators = LLMClient(use_validator_key=True)
        self.rag = RAGService()
        self.course_repo = CourseRepository(db)
        self.agent_repo = AgentRepository(db)

        self.placement_generator = PlacementGeneratorAgent(self.llm, self.rag)
        self.placement_validator = PlacementValidatorAgent(self.llm_validators)
        self.syllabus_generator = SyllabusGeneratorAgent(self.llm, self.rag)
        self.syllabus_validator = SyllabusValidatorAgent(self.llm_validators)
        self.lesson_generator = LessonGeneratorAgent(self.llm, self.rag)
        self.lesson_validator = LessonValidatorAgent()
        self.qa_generator = QAGeneratorAgent(self.llm, self.rag)
        self.qa_validator = QAValidatorAgent()
        self.assessment_service = AssessmentService(self.llm)
        self.lesson_progress_repo = LessonProgressRepository(db)

    async def create_placement_test(self, user_id: int, level: str, question_count: int) -> dict:
        if question_count != QUESTIONS_PER_LEVEL:
            raise ValueError(
                f"Placement must use exactly {QUESTIONS_PER_LEVEL} questions per rubric tier (got {question_count})."
            )
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
        first_level = LEVEL_ORDER[0]
        raw = self.placement_generator.generate(level=first_level, question_count=QUESTIONS_PER_LEVEL)
        await self.agent_repo.log_run(
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={
                "level": first_level,
                "question_count": QUESTIONS_PER_LEVEL,
                "track": track,
                "flow": "session",
            },
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.placement_validator.validate(raw, first_level, QUESTIONS_PER_LEVEL)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": first_level, "question_count": QUESTIONS_PER_LEVEL, "track": track},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.placement_validator.name,
            stage="validate",
            input_json={"level": first_level, "question_count": QUESTIONS_PER_LEVEL, "track": track},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        full_payload = {
            **generated,
            "placement_session": {
                "track": track,
                "level_index": 0,
                "current_level": first_level,
                "cursor_in_level": 0,
                "correct_in_level": 0,
                "correct_total": 0,
                "answered_total": 0,
                "levels_passed": [],
                "wrong_concepts": [],
                "strong_concepts": [],
            },
        }
        placement = await self.course_repo.create_placement_test(user_id=user_id, questions_json=full_payload)
        questions = generated["questions"]
        next_q = _format_placement_question(questions[0], 0, track, first_level, 0)
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
        wrong_concepts: list = list(sess.get("wrong_concepts") or [])
        strong_concepts: list = list(sess.get("strong_concepts") or [])

        if not question_id.startswith("q"):
            raise ValueError("Invalid question id")
        try:
            qi = int(question_id[1:])
        except ValueError as exc:
            raise ValueError("Invalid question id") from exc

        cursor_in_level = int(sess.get("cursor_in_level", sess.get("cursor", 0)))
        if qi != cursor_in_level:
            cursor_in_level = qi

        if cursor_in_level >= len(questions) or cursor_in_level >= QUESTIONS_PER_LEVEL:
            raise ValueError("Invalid state")

        level_index = int(sess.get("level_index", 0))
        current_level = str(sess.get("current_level") or LEVEL_ORDER[0])
        q = questions[cursor_in_level]
        choices = q.get("choices") or []
        if answer_index >= len(choices):
            raise ValueError("Invalid answer index")
        selected = choices[answer_index]
        correct_ans = q.get("correct_answer")
        is_correct = _placement_answer_matches(selected, correct_ans)

        correct_in_level = int(sess.get("correct_in_level", 0))
        correct_total = int(sess.get("correct_total", 0))
        answered_total = int(sess.get("answered_total", 0))

        if is_correct:
            correct_in_level += 1
            correct_total += 1
            c = q.get("concept")
            if c:
                strong_concepts.append(str(c))
        else:
            c = q.get("concept")
            if c:
                wrong_concepts.append(str(c))
        answered_total += 1

        cursor_in_level += 1
        sess["cursor_in_level"] = cursor_in_level
        sess["correct_in_level"] = correct_in_level
        sess["correct_total"] = correct_total
        sess["answered_total"] = answered_total
        sess["wrong_concepts"] = wrong_concepts
        sess["strong_concepts"] = strong_concepts
        sess["level_index"] = level_index
        sess["current_level"] = current_level
        data["placement_session"] = sess
        _set_placement_questions_json(placement, data)

        if cursor_in_level < QUESTIONS_PER_LEVEL:
            next_q = _format_placement_question(
                questions[cursor_in_level], cursor_in_level, track, current_level, level_index
            )
            await self.db.commit()
            await self.db.refresh(placement)
            return {"status": "ok", "finished": False, "next_question": next_q}

        passed = correct_in_level >= PASS_THRESHOLD
        levels_passed: list = list(sess.get("levels_passed") or [])

        if not passed:
            final_level = normalize_level(current_level)
            sess["final_level"] = final_level
            sess["stopped_reason"] = "failed_level"
            data["placement_session"] = sess
            _set_placement_questions_json(placement, data)
            placement.score = LEVEL_TO_SCORE_PCT.get(final_level, 25)
            weak_unique = list(dict.fromkeys(wrong_concepts))
            strong_unique = list(dict.fromkeys(strong_concepts))
            recommended = weak_unique[0] if weak_unique else str(questions[0].get("concept") or "Python Basics")
            pct = int(round(100 * correct_total / answered_total)) if answered_total else 0
            placement_result = {
                "track": track,
                "score": correct_total,
                "percentage": pct,
                "level": final_level,
                "final_level": final_level,
                "strong_topics": strong_unique[:10],
                "weak_topics": weak_unique[:10],
                "recommended_start_topic": str(recommended),
                "levels_passed": levels_passed,
                "stopped_reason": "failed_level",
                "passed_all_tiers": False,
                "last_block_correct": correct_in_level,
                "last_block_total": QUESTIONS_PER_LEVEL,
                "total_answered": answered_total,
            }
            await self.db.commit()
            await self.db.refresh(placement)
            return {"status": "ok", "finished": True, "placement_result": placement_result}

        levels_passed = levels_passed + [current_level]
        sess["levels_passed"] = levels_passed

        if level_index >= len(LEVEL_ORDER) - 1:
            final_level = "very_advanced"
            sess["final_level"] = final_level
            sess["stopped_reason"] = "completed_all"
            data["placement_session"] = sess
            _set_placement_questions_json(placement, data)
            placement.score = LEVEL_TO_SCORE_PCT["very_advanced"]
            weak_unique = list(dict.fromkeys(wrong_concepts))
            strong_unique = list(dict.fromkeys(strong_concepts))
            recommended = weak_unique[0] if weak_unique else "Architecture and Best Practices"
            pct = int(round(100 * correct_total / answered_total)) if answered_total else 0
            placement_result = {
                "track": track,
                "score": correct_total,
                "percentage": pct,
                "level": final_level,
                "final_level": final_level,
                "strong_topics": strong_unique[:10],
                "weak_topics": weak_unique[:10],
                "recommended_start_topic": str(recommended),
                "levels_passed": levels_passed,
                "stopped_reason": "completed_all",
                "passed_all_tiers": True,
                "last_block_correct": correct_in_level,
                "last_block_total": QUESTIONS_PER_LEVEL,
                "total_answered": answered_total,
            }
            await self.db.commit()
            await self.db.refresh(placement)
            return {"status": "ok", "finished": True, "placement_result": placement_result}

        next_level = LEVEL_ORDER[level_index + 1]
        raw = self.placement_generator.generate(level=next_level, question_count=QUESTIONS_PER_LEVEL)
        await self.agent_repo.log_run(
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={
                "level": next_level,
                "question_count": QUESTIONS_PER_LEVEL,
                "track": track,
                "flow": "session_advance",
            },
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.placement_validator.validate(raw, next_level, QUESTIONS_PER_LEVEL)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": next_level, "question_count": QUESTIONS_PER_LEVEL, "track": track},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.placement_validator.name,
            stage="validate",
            input_json={"level": next_level, "question_count": QUESTIONS_PER_LEVEL, "track": track},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )

        data["questions"] = generated["questions"]
        sess["level_index"] = level_index + 1
        sess["current_level"] = next_level
        sess["cursor_in_level"] = 0
        sess["correct_in_level"] = 0
        data["placement_session"] = sess
        _set_placement_questions_json(placement, data)

        nq = generated["questions"][0]
        next_q = _format_placement_question(nq, 0, track, next_level, level_index + 1)
        await self.db.commit()
        await self.db.refresh(placement)
        return {"status": "ok", "finished": False, "next_question": next_q, "advanced_level": True}

    async def build_syllabus(self, user_id: int, placement_id: int, course_title: str) -> dict:
        from app.models.entities import PlacementTest

        placement = await self.db.get(PlacementTest, placement_id)
        if placement is None or placement.user_id != user_id:
            raise ValueError("Placement test not found")
        score = placement.score or 0
        pj = placement.questions_json
        sess = pj.get("placement_session") if isinstance(pj, dict) else {}
        fl = sess.get("final_level") if isinstance(sess, dict) else None
        if fl:
            level_str = normalize_level(str(fl))
        else:
            level_str = _score_to_level(int(score) if score is not None else 0)

        weak_topics: list[str] = []
        strong_topics: list[str] = []
        if isinstance(sess, dict):
            raw_weak = sess.get("wrong_concepts") or []
            raw_strong = sess.get("strong_concepts") or []
            weak_topics = list(dict.fromkeys(str(t).strip() for t in raw_weak if str(t).strip()))
            strong_topics = list(dict.fromkeys(str(t).strip() for t in raw_strong if str(t).strip()))

        raw_syllabus = self.syllabus_generator.generate(
            score=int(score) if score is not None else 0,
            level=level_str,
            weak_topics=weak_topics,
            strong_topics=strong_topics,
        )
        if not isinstance(raw_syllabus, dict) or (
            not raw_syllabus.get("units") and not raw_syllabus.get("lessons")
        ):
            raw_syllabus = _build_local_syllabus_payload(level_str)
        await self.agent_repo.log_run(
            agent_name=self.syllabus_generator.name,
            stage="generate",
            input_json={
                "placement_id": placement_id,
                "score": score,
                "level": level_str,
                "course_title": course_title,
                "weak_topics": weak_topics,
                "strong_topics": strong_topics,
            },
            output_json=raw_syllabus,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.syllabus_validator.validate(raw_syllabus, placement_level=level_str)
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
        transformed_lessons = []
        for lesson in generated.get("lessons", []):
            rubric_topic = str(lesson.get("topic") or "").strip()
            display_title = str(lesson.get("title") or rubric_topic).strip()
            ch_ref = lesson.get("chapter_ref")
            transformed_lessons.append({
                "title": display_title,
                "topic": _topic_slug(rubric_topic),
                "prerequisites": lesson.get("prerequisites", []),
                "markdown_content": str(lesson.get("description") or ""),
                "unit_title": (str(lesson.get("unit_title")).strip() if lesson.get("unit_title") else None),
                "metadata_json": {"chapter_ref": int(ch_ref)} if ch_ref is not None else {},
            })

        course = await self.course_repo.create_course_with_lessons(
            user_id=user_id,
            title=course_title,
            level=level_str.replace("_", " ").title(),
            lessons=transformed_lessons,
        )

        course = await self.course_repo.get_course_with_lessons(course.id)
        if course is None:
            raise ValueError("Failed to retrieve created course with lessons")

        sorted_lessons = sorted(course.lessons, key=lambda L: L.order_index)
        modules: list[dict] = []
        mod_idx = 0

        def _module_key(les) -> str:
            ut = (les.unit_title or "").strip()
            return ut or "__single__"

        for unit_label, group in groupby(sorted_lessons, key=_module_key):
            rows = list(group)
            mod_idx += 1
            unit_title = rows[0].unit_title if rows[0].unit_title else None
            if unit_label == "__single__" and len(sorted_lessons) == len(rows):
                mod_title = course.title
                mod_desc = f"{level_str.replace('_', ' ').title()} track — Python for Everybody scope."
            else:
                mod_title = unit_title or f"Module {mod_idx}"
                mod_desc = f"Unit in {course.title}."

            modules.append({
                "id": f"module_{mod_idx}",
                "module_id": f"module_{mod_idx}",
                "title": mod_title,
                "description": mod_desc,
                "topics": list({r.topic for r in rows}),
                "duration": f"{len(rows) * 20} min",
                "target_level": level_str,
                "lessons": [
                    {
                        "lesson_id": f"lesson_{les.id}",
                        "id": f"lesson_{les.id}",
                        "title": les.title,
                        "topic": les.topic,
                        "topic_name": les.topic,
                        "duration_minutes": 20,
                        "order": les.order_index,
                    }
                    for les in rows
                ],
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
        from app.models.entities import Course, Lesson

        lesson = await self.db.get(Lesson, lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")

        # Get level from parent course
        level: str = "beginner"
        chapter_ref: int | None = None
        try:
            if lesson.course_id:
                course = await self.db.get(Course, lesson.course_id)
                if course and course.level:
                    raw_level = str(course.level).lower().replace(" ", "_")
                    level = normalize_level(raw_level)
        except Exception:
            pass

        # Get chapter_ref from lesson metadata if available
        try:
            meta = lesson.metadata_json if hasattr(lesson, "metadata_json") else None
            if isinstance(meta, dict):
                cr = meta.get("chapter_ref")
                if cr is not None:
                    chapter_ref = int(cr)
        except Exception:
            pass

        raw_lesson = self.lesson_generator.generate(
            topic=lesson.topic,
            lesson_title=lesson.title,
            level=level,
            chapter_ref=chapter_ref,
        )
        await self.agent_repo.log_run(
            agent_name=self.lesson_generator.name,
            stage="generate",
            input_json={
                "lesson_id": lesson_id,
                "topic": lesson.topic,
                "level": level,
                "chapter_ref": chapter_ref,
            },
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

        md = (updated.markdown_content or "").strip()
        if not md:
            md = f"## {updated.title}\n\n_Content could not be loaded. Try refreshing or regenerating this lesson._"
        return {
            "status": "success",
            "lesson": {
                "lesson_id": f"lesson_{updated.id}",
                "title": updated.title,
                "duration_minutes": 25,
                "sections": [{"type": "markdown", "content": md}],
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

        safe_q = sanitize_prompt(question)
        if not self.rag.is_likely_book_related_question(safe_q):
            return self._qa_py4e_only_envelope()

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

    def _qa_py4e_only_envelope(self) -> dict:
        """No LLM call: question looks unrelated to PY4E book chunks (saves tokens)."""
        msg = (
            "I'm only the **Python for Everybody (PY4E)** chatbot for this course—I help with the book material "
            "and your lessons. Ask something about PY4E or the topics in your course."
        )
        return {
            "status": "ok",
            "intent": "qa_py4e_scope",
            "result": {
                "status": "ok",
                "explanation": {
                    "core_explanation": msg,
                },
                "rag": {
                    "chunks_used": 0,
                    "selected_chunks": [],
                    "skipped_llm": True,
                },
            },
            "routing": {"steps": ["sanitize", "book_relevance_gate"]},
        }

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

    async def generate_lesson_assessment(self, user_id: int, lesson_id: int) -> dict:
        lesson = await self.course_repo.get_lesson_with_course(lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")
        if lesson.course is None or lesson.course.user_id != user_id:
            raise ValueError("Lesson not found")
        progress = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=lesson.id)
        level = normalize_level((lesson.course.level or "beginner").replace(" ", "_").lower())
        previous_questions = (
            list(progress.current_questions_json)
            if isinstance(progress.current_questions_json, list)
            else []
        )
        questions = await self.assessment_service.generate_assessment(
            topic=lesson.topic,
            level=level,
            lesson_title=lesson.title,
            lesson_markdown=(lesson.markdown_content or ""),
            attempt_number=max(1, progress.attempts + 1),
            previous_questions=previous_questions,
        )
        for i, q in enumerate(questions):
            q["id"] = f"q{i}"
        progress.current_questions_json = questions
        await self.lesson_progress_repo.save(progress)
        return {
            "lesson_id": f"lesson_{lesson.id}",
            "attempts_used": progress.attempts,
            "attempts_remaining": max(0, 3 - progress.attempts),
            "questions": questions,
        }

    async def submit_lesson_assessment(
        self,
        user_id: int,
        lesson_id: int,
        answers: list[dict],
    ) -> dict:
        lesson = await self.course_repo.get_lesson_with_course(lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")
        if lesson.course is None or lesson.course.user_id != user_id:
            raise ValueError("Lesson not found")
        progress = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=lesson.id)
        questions = progress.current_questions_json or []
        if not isinstance(questions, list) or len(questions) != 5:
            level = normalize_level((lesson.course.level or "beginner").replace(" ", "_").lower())
            questions = await self.assessment_service.generate_assessment(
                topic=lesson.topic,
                level=level,
                lesson_title=lesson.title,
                lesson_markdown=(lesson.markdown_content or ""),
                attempt_number=max(1, progress.attempts + 1),
                previous_questions=[],
            )
            for i, q in enumerate(questions):
                q["id"] = f"q{i}"
            progress.current_questions_json = questions

        answer_map: dict[int, int] = {}
        for a in answers:
            if not isinstance(a, dict):
                continue
            try:
                qi = int(a.get("question_index"))
                ci = int(a.get("choice_index"))
            except (TypeError, ValueError):
                continue
            answer_map[qi] = ci

        score = 0
        for idx, q in enumerate(questions):
            if idx not in answer_map:
                continue
            choices = q.get("choices") or []
            ci = answer_map[idx]
            if not isinstance(choices, list) or ci < 0 or ci >= len(choices):
                continue
            selected = str(choices[ci]).strip()
            correct = str(q.get("correct_answer") or "").strip()
            if selected == correct:
                score += 1

        progress.last_score = score
        if score >= 4:
            progress.passed = True
            await self.lesson_progress_repo.save(progress)
            next_lesson_id = await self.course_repo.get_next_lesson_id(lesson)
            return {"passed": True, "score": score, "next_lesson": next_lesson_id}

        # Failed attempt
        if progress.attempts < 3:
            progress.attempts += 1
        attempt_number = progress.attempts
        progress.passed = False

        if attempt_number >= 3:
            await self.lesson_progress_repo.save(progress)
            return {
                "passed": False,
                "locked": True,
                "score": score,
                "attempts": progress.attempts,
                "message": "You have reached the maximum attempts. Please review the lesson before retrying.",
            }

        adaptation = (
            "Use simpler explanation, more examples, beginner-friendly style."
            if attempt_number == 1
            else "Use even simpler explanation, step-by-step breakdown, and focus on weak concepts."
        )
        level = normalize_level((lesson.course.level or "beginner").replace(" ", "_").lower())
        chapter_ref = None
        try:
            if isinstance(lesson.metadata_json, dict):
                cr = lesson.metadata_json.get("chapter_ref")
                if cr is not None:
                    chapter_ref = int(cr)
        except Exception:
            chapter_ref = None
        raw_lesson = self.lesson_generator.generate(
            topic=lesson.topic,
            lesson_title=lesson.title,
            level=level,
            chapter_ref=chapter_ref,
            adaptation_instructions=adaptation,
        )
        generated = self.lesson_validator.validate(raw_lesson)
        await self.course_repo.update_lesson_content(lesson.id, generated["markdown"])
        await self.lesson_progress_repo.save(progress)
        return {
            "passed": False,
            "locked": False,
            "score": score,
            "attempts": progress.attempts,
            "message": f"Assessment failed. Lesson regenerated for attempt {attempt_number + 1}.",
        }
