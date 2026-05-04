import json
from itertools import groupby

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.agent_repository import AgentRepository
from app.repositories.course_repository import CourseRepository
from app.repositories.lesson_progress_repository import LessonProgressRepository
from app.core.placement_rubric import (
    LEVEL_ORDER,
    LEVEL_TO_SCORE_PCT,
    PASS_THRESHOLD,
    QUESTIONS_PER_LEVEL,
    normalize_level,
    normalize_track,
)
from app.services.agents import (
    AgentValidationError,
    AnalyticsAgent,
    LessonGeneratorAgent,
    LessonValidatorAgent,
    PlacementGeneratorAgent,
    PlacementValidatorAgent,
    QAGeneratorAgent,
    QAValidatorAgent,
    SyllabusGeneratorAgent,
    SyllabusValidatorAgent,
)
from app.services.assessment_service import AssessmentService
from app.services.guardrails import run_exam_code_in_sandbox, sanitize_prompt
from app.services.llm_client import LLMClient
from app.services.orchestrator.common import (
    assign_question_ids as _assign_question_ids,
    duration_minutes_for_level as _duration_minutes_for_level,
    extract_chapter_ref as _extract_chapter_ref,
    is_dynamic_lesson_markdown as _is_dynamic_lesson_markdown,
    lesson_response_payload as _lesson_response_payload,
    normalized_course_level as _normalized_course_level,
)
from app.services.orchestrator.placement import (
    format_placement_question as _format_placement_question,
    placement_answer_matches as _placement_answer_matches,
    score_to_level as _score_to_level,
    set_placement_questions_json as _set_placement_questions_json,
)
from app.core.errors import LessonLockedError
from app.services.orchestrator.lesson_access import (
    build_progression_blocks,
    can_user_access_lesson,
    split_markdown_into_sub_focuses,
)
from app.services.orchestrator.syllabus import (
    build_local_syllabus_payload as _build_local_syllabus_payload,
    topic_slug as _topic_slug,
)
from app.services.rag_service import RAGService


def _track_from_course_title(title: str | None) -> str:
    t = (title or "").strip().lower()
    if "deep learning" in t or "neural" in t or "machine learning" in t:
        return "deep_learning"
    return "python"


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
        self.analytics_agent = AnalyticsAgent()
        self.assessment_service = AssessmentService(self.llm)
        self.lesson_progress_repo = LessonProgressRepository(db)

    async def _course_progression_context(self, user_id: int, course_id: int):
        lessons = await self.course_repo.list_lessons_by_course(course_id)
        blocks = build_progression_blocks(lessons)
        pmap = await self.lesson_progress_repo.get_passed_map(user_id, [L.id for L in lessons])
        return lessons, blocks, pmap

    async def _ensure_lesson_accessible(self, user_id: int, course_id: int, lesson_id: int) -> None:
        _, blocks, pmap = await self._course_progression_context(user_id, course_id)
        if not can_user_access_lesson(lesson_id=lesson_id, blocks=blocks, passed_map=pmap):
            raise LessonLockedError()

    async def _sync_parent_passed_if_subs_done(self, user_id: int, parent_lesson_id: int | None) -> None:
        if not parent_lesson_id:
            return
        children = await self.course_repo.get_child_lessons(parent_lesson_id)
        if not children:
            return
        pmap = await self.lesson_progress_repo.get_passed_map(user_id, [c.id for c in children])
        if not all(pmap.get(c.id) for c in children):
            return
        pp = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=parent_lesson_id)
        pp.passed = True
        await self.lesson_progress_repo.save(pp)

    @staticmethod
    def _normalize_track_key(track: str | None) -> str:
        return normalize_track(track or "python")

    @staticmethod
    def _placement_track(payload: dict | None) -> str:
        data = payload if isinstance(payload, dict) else {}
        sess = data.get("placement_session") if isinstance(data.get("placement_session"), dict) else {}
        raw = (
            sess.get("track")
            or data.get("track")
            or (
                data.get("placement_result", {}).get("track")
                if isinstance(data.get("placement_result"), dict)
                else None
            )
        )
        return normalize_track(str(raw or "python"))

    async def build_analytics_summary(self, user_id: int, track: str | None = None) -> dict:
        from app.models.entities import Course, Lesson, LessonProgress, PlacementTest

        track_key = self._normalize_track_key(track)

        placement_rows = await self.db.execute(
            select(PlacementTest).where(PlacementTest.user_id == user_id).order_by(PlacementTest.created_at.desc())
        )
        placements = [p for p in placement_rows.scalars().all() if self._placement_track(p.questions_json) == track_key]
        latest_placement = placements[0] if placements else None

        placement_data = latest_placement.questions_json if latest_placement and isinstance(latest_placement.questions_json, dict) else {}
        placement_result = placement_data.get("placement_result") if isinstance(placement_data.get("placement_result"), dict) else {}
        placement_session = (
            placement_data.get("placement_session") if isinstance(placement_data.get("placement_session"), dict) else {}
        )
        placement_percentage = (
            float(placement_result.get("percentage"))
            if isinstance(placement_result.get("percentage"), (int, float))
            else (float(latest_placement.score) if latest_placement and latest_placement.score is not None else None)
        )
        placement_level = (
            str(placement_result.get("level") or placement_result.get("final_level") or "").strip() or None
        )
        strong_topics = [
            str(x).strip() for x in (placement_result.get("strong_topics") or placement_session.get("strong_concepts") or []) if str(x).strip()
        ]
        weak_topics = [
            str(x).strip() for x in (placement_result.get("weak_topics") or placement_session.get("wrong_concepts") or []) if str(x).strip()
        ]
        recommended_start_topic = str(placement_result.get("recommended_start_topic") or "").strip() or None
        total_answered = int(placement_session.get("answered_total") or 0)

        course_rows = await self.db.execute(select(Course).where(Course.user_id == user_id))
        user_courses = [c for c in course_rows.scalars().all() if _track_from_course_title(getattr(c, "title", None)) == track_key]
        course_ids = [c.id for c in user_courses]
        course_count = len(user_courses)

        if course_ids:
            lesson_rows = await self.db.execute(select(Lesson).where(Lesson.course_id.in_(course_ids)))
            lessons = lesson_rows.scalars().all()
        else:
            lessons = []
        lesson_count = len(lessons)
        generated_lesson_count = sum(1 for l in lessons if str(l.markdown_content or "").strip())
        lesson_ids = [l.id for l in lessons]

        if lesson_ids:
            progress_rows = await self.db.execute(
                select(LessonProgress).where(LessonProgress.user_id == user_id, LessonProgress.lesson_id.in_(lesson_ids))
            )
            progresses = progress_rows.scalars().all()
        else:
            progresses = []
        passed_count = sum(1 for p in progresses if bool(p.passed))
        lesson_completion_rate = (passed_count / lesson_count) if lesson_count > 0 else 0.0

        if track_key == "deep_learning":
            course_title = "Deep Learning Foundations"
            subject = "Deep Learning"
            source = "Deep Learning textbook excerpts and generated curriculum context"
        else:
            course_title = "Python Foundations"
            subject = "Python Programming"
            source = self.llm.settings.source_resource

        metrics = {
            "student_id": user_id,
            "track": track_key,
            "course_title": course_title,
            "has_placement": latest_placement is not None,
            "placement_id": latest_placement.id if latest_placement else None,
            "placement_level": placement_level,
            "placement_percentage": placement_percentage,
            "total_answered": total_answered,
            "strong_topics": list(dict.fromkeys(strong_topics))[:10],
            "weak_topics": list(dict.fromkeys(weak_topics))[:10],
            "recommended_start_topic": recommended_start_topic,
            "course_count": course_count,
            "lesson_count": lesson_count,
            "generated_lesson_count": generated_lesson_count,
            "lesson_completion_rate": round(float(lesson_completion_rate), 4),
        }

        insights = self.analytics_agent.generate(metrics)
        await self.agent_repo.log_run(
            agent_name=self.analytics_agent.name,
            stage="generate",
            input_json={"track": track_key, "metrics": metrics},
            output_json=insights,
            is_valid=True,
            user_id=user_id,
        )

        return {
            "status": "ok",
            "intent": "analytics_summary",
            "result": {
                "course_context": {
                    "track": track_key,
                    "course_title": course_title,
                    "subject": subject,
                    "source": source,
                },
                "metrics": metrics,
                "insights": insights,
            },
        }

    async def create_placement_test(
        self,
        user_id: int,
        level: str,
        question_count: int,
        track: str = "python",
    ) -> dict:
        if question_count != QUESTIONS_PER_LEVEL:
            raise ValueError(
                f"Placement must use exactly {QUESTIONS_PER_LEVEL} questions per rubric tier (got {question_count})."
            )
        norm_track = normalize_track(track)
        raw = self.placement_generator.generate(level=level, question_count=question_count, track=norm_track)
        await self.agent_repo.log_run(
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={"level": level, "question_count": question_count, "track": norm_track, "flow": "generate"},
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        try:
            generated = self.placement_validator.validate(raw, level, question_count, track=norm_track)
        except AgentValidationError as exc:
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": level, "question_count": question_count, "track": norm_track},
                output_json={"error": str(exc)},
                is_valid=False,
                user_id=user_id,
            )
            raise
        await self.agent_repo.log_run(
            agent_name=self.placement_validator.name,
            stage="validate",
            input_json={"level": level, "question_count": question_count, "track": norm_track},
            output_json=generated,
            is_valid=True,
            user_id=user_id,
        )
        placement = await self.course_repo.create_placement_test(user_id=user_id, questions_json=generated)
        return {"placement_id": placement.id, "questions": generated["questions"]}

    async def start_placement_session(self, user_id: int, track: str) -> dict:
        first_level = LEVEL_ORDER[0]
        ui_track = normalize_track(track) or "python"
        gen_track = "deep_learning" if ui_track in ("deep_learning", "dl") else "python"

        last_exc: AgentValidationError | None = None
        generated: dict | None = None
        raw: dict | None = None
        for attempt in range(3):
            try:
                raw = self.placement_generator.generate(
                    level=first_level,
                    question_count=QUESTIONS_PER_LEVEL,
                    track=gen_track,
                )
            except AgentValidationError as exc:
                last_exc = exc
                continue
            await self.agent_repo.log_run(
                agent_name=self.placement_generator.name,
                stage="generate",
                input_json={
                    "level": first_level,
                    "question_count": QUESTIONS_PER_LEVEL,
                    "track": track,
                    "flow": "session",
                    "attempt": attempt + 1,
                    "gen_track": gen_track,
                },
                output_json=raw,
                is_valid=True,
                user_id=user_id,
            )
            try:
                generated = self.placement_validator.validate(raw, first_level, QUESTIONS_PER_LEVEL, track=gen_track)
            except AgentValidationError as exc:
                last_exc = exc
                await self.agent_repo.log_run(
                    agent_name=self.placement_validator.name,
                    stage="validate",
                    input_json={
                        "level": first_level,
                        "question_count": QUESTIONS_PER_LEVEL,
                        "track": track,
                        "attempt": attempt + 1,
                    },
                    output_json={"error": str(exc)},
                    is_valid=False,
                    user_id=user_id,
                )
                generated = None
                continue
            await self.agent_repo.log_run(
                agent_name=self.placement_validator.name,
                stage="validate",
                input_json={"level": first_level, "question_count": QUESTIONS_PER_LEVEL, "track": track},
                output_json=generated,
                is_valid=True,
                user_id=user_id,
            )
            break

        if not generated:
            raise last_exc or AgentValidationError("Could not start placement session after retries.")

        full_payload = {
            **generated,
            "placement_session": {
                "track": ui_track,
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
        if normalize_track(str(sess.get("track") or "")) != normalize_track(str(track or "")):
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
        raw = self.placement_generator.generate(
            level=next_level,
            question_count=QUESTIONS_PER_LEVEL,
            track=normalize_track(track),
        )
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
            generated = self.placement_validator.validate(
                raw,
                next_level,
                QUESTIONS_PER_LEVEL,
                track=normalize_track(track),
            )
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
        track = normalize_track(sess.get("track") if isinstance(sess, dict) else None)
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

        try:
            raw_syllabus = self.syllabus_generator.generate(
                score=int(score) if score is not None else 0,
                level=level_str,
                track=track,
                weak_topics=weak_topics,
                strong_topics=strong_topics,
            )
        except AgentValidationError:
            raw_syllabus = _build_local_syllabus_payload(
                level_str,
                track=track,
                weak_topics=weak_topics,
                strong_topics=strong_topics,
            )
        if not isinstance(raw_syllabus, dict) or (
            not raw_syllabus.get("units") and not raw_syllabus.get("lessons")
        ):
            raw_syllabus = _build_local_syllabus_payload(
                level_str,
                track=track,
                weak_topics=weak_topics,
                strong_topics=strong_topics,
            )
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
            generated = self.syllabus_validator.validate(raw_syllabus, placement_level=level_str, track=track)
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
        lesson_duration_minutes = _duration_minutes_for_level(level_str)

        def _module_key(les) -> str:
            ut = (les.unit_title or "").strip()
            return ut or "__single__"

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
                mod_title = course.title
                if normalize_track(track) in {"deep_learning", "dl"}:
                    mod_desc = f"{level_str.replace('_', ' ').title()} track — Deep Learning scope."
                else:
                    mod_desc = f"{level_str.replace('_', ' ').title()} track — Python for Everybody scope."
            else:
                mod_title = unit_title or f"Module {mod_idx}"
                mod_desc = f"Unit in {course.title}."

            def _lesson_payload(les) -> dict:
                base = {
                    "lesson_id": f"lesson_{les.id}",
                    "id": f"lesson_{les.id}",
                    "title": les.title,
                    "topic": les.topic,
                    "topic_name": les.topic,
                    "duration_minutes": lesson_duration_minutes,
                    "order": les.order_index,
                    "course_id": course.id,
                    "parent_lesson_id": les.parent_lesson_id,
                    "is_sub_lesson": bool(les.is_sub_lesson),
                }
                kids = sorted(
                    [x for x in sorted_lessons if x.parent_lesson_id == les.id],
                    key=lambda x: x.order_index,
                )
                if kids:
                    base["sub_lessons"] = [_lesson_payload(k) for k in kids]
                return base

            modules.append({
                "id": f"module_{mod_idx}",
                "module_id": f"module_{mod_idx}",
                "title": mod_title,
                "description": mod_desc,
                "topics": list(dict.fromkeys([r.topic for r in chunk])),
                "duration": f"{len(chunk) * lesson_duration_minutes} min",
                "target_level": level_str,
                "lessons": [_lesson_payload(les) for les in rows],
            })
        
        return {
            "status": "success",
            "intent": "syllabus_generation",
            "result": {
                "status": "generated",
                "track": track,
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

        course = await self.db.get(Course, lesson.course_id) if lesson.course_id else None
        if course is None or course.user_id != user_id:
            raise ValueError("Lesson not found")

        await self._ensure_lesson_accessible(user_id, lesson.course_id, lesson.id)

        level: str = "beginner"
        course_track = "python"
        chapter_ref: int | None = None
        duration_minutes = _duration_minutes_for_level(level)
        try:
            if course.level:
                level = _normalized_course_level(course.level)
                duration_minutes = _duration_minutes_for_level(level)
            course_track = _track_from_course_title(getattr(course, "title", None))
        except Exception:
            pass

        children = await self.course_repo.get_child_lessons(lesson.id)
        if children:
            overview = (lesson.markdown_content or "").strip()
            if not overview or not _is_dynamic_lesson_markdown(overview):
                overview = (
                    "## Focused review\n\n"
                    "This topic is split into smaller steps. Open each part below in order and pass its quiz "
                    "before moving on.\n\n"
                    + "\n".join(f"{i + 1}. **{c.title}**" for i, c in enumerate(children))
                )
            sub_payload = [
                {
                    "lesson_id": f"lesson_{c.id}",
                    "id": f"lesson_{c.id}",
                    "title": c.title,
                    "topic": c.topic,
                    "topic_name": c.topic,
                    "duration_minutes": duration_minutes,
                    "order": c.order_index,
                    "course_id": lesson.course_id,
                    "parent_lesson_id": c.parent_lesson_id,
                    "is_sub_lesson": True,
                }
                for c in children
            ]
            return _lesson_response_payload(
                lesson_id=lesson.id,
                title=lesson.title,
                duration_minutes=duration_minutes,
                markdown=overview,
                llm_used=False,
                sub_lessons=sub_payload,
                is_parent_with_sub_lessons=True,
                course_id=lesson.course_id,
            )

        existing_markdown = (lesson.markdown_content or "").strip()
        if existing_markdown and _is_dynamic_lesson_markdown(existing_markdown):
            return _lesson_response_payload(
                lesson_id=lesson.id,
                title=lesson.title,
                duration_minutes=duration_minutes,
                markdown=existing_markdown,
                llm_used=False,
                course_id=lesson.course_id,
            )

        chapter_ref = _extract_chapter_ref(getattr(lesson, "metadata_json", None))

        raw_lesson = self.lesson_generator.generate(
            topic=lesson.topic,
            lesson_title=lesson.title,
            track=course_track,
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
            generated = self.lesson_validator.validate(raw_lesson, track=course_track)
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
        return _lesson_response_payload(
            lesson_id=updated.id,
            title=updated.title,
            duration_minutes=duration_minutes,
            markdown=md,
            llm_used=True,
            course_id=lesson.course_id,
        )

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
        track_from_ctx = student_context.get("track") if isinstance(student_context, dict) else None
        track_key = normalize_track(track_from_ctx)
        if not self.rag.is_likely_book_related_question(safe_q):
            return self._qa_track_scope_envelope(track_key)

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
            lesson_markdown = (
                "General Deep Learning Foundations."
                if track_key in {"deep_learning", "dl"}
                else "General Python Foundations (Python Basics)."
            )

        raw_qa = self.qa_generator.generate(
            question=question,
            lesson_markdown=lesson_markdown,
            track=track_key,
            student_context=student_context,
        )
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
            generated = self.qa_validator.validate(raw_qa, track=track_key)
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

    def _qa_track_scope_envelope(self, track: str) -> dict:
        """No LLM call: question looks unrelated to selected-track chunks (saves tokens)."""
        if normalize_track(track) in {"deep_learning", "dl"}:
            msg = (
                "I'm only the **Deep Learning** chatbot for this course - I help with deep learning "
                "book and lecture-note material plus your lessons. Ask something about deep learning topics."
            )
        else:
            msg = (
                "I'm only the **Python for Everybody (PY4E)** chatbot for this course - I help with the "
                "book material and your lessons. Ask something about PY4E or your course topics."
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

    async def _remediation_split_root_lesson(self, user_id: int, lesson) -> list[dict]:
        """Persist 2–4 sub-lessons after a failed root-level assessment."""
        course = lesson.course
        if course is None:
            raise ValueError("Lesson not found")
        level = _normalized_course_level(course.level)
        existing_children = await self.course_repo.get_child_lessons(lesson.id)
        if existing_children:
            refreshed = await self.course_repo.list_lessons_by_course(lesson.course_id)
            return self.course_repo.build_syllabus_modules_from_lessons(
                course.title,
                refreshed,
                lesson_duration_minutes=_duration_minutes_for_level(level),
                target_level=level,
            )
        old_md = (lesson.markdown_content or "").strip()
        parts, titles = split_markdown_into_sub_focuses(old_md)
        track = _track_from_course_title(getattr(course, "title", None))
        chapter_ref = _extract_chapter_ref(lesson.metadata_json)
        child_rows: list[dict] = []
        for i, (snippet, stitle) in enumerate(zip(parts, titles)):
            raw_sl = self.lesson_generator.generate_sub_lesson(
                parent_topic=lesson.topic,
                sub_title=f"{lesson.title} — {stitle}",
                source_excerpt=snippet,
                track=track,
                level=level,
                chapter_ref=chapter_ref,
            )
            await self.agent_repo.log_run(
                agent_name=self.lesson_generator.name,
                stage="generate_sub_lesson",
                input_json={"parent_lesson_id": lesson.id, "part_index": i + 1},
                output_json=raw_sl,
                is_valid=True,
                user_id=user_id,
            )
            gen_sl = self.lesson_validator.validate(raw_sl, track=track)
            slug_base = (lesson.topic or "topic").replace(" ", "_")[:40]
            topic_slug = f"{slug_base}_p{i + 1}_{lesson.id}"[:100]
            meta = dict(lesson.metadata_json or {})
            meta["sub_lesson_index"] = i + 1
            meta["parent_topic"] = lesson.topic
            if chapter_ref is not None:
                meta["chapter_ref"] = chapter_ref
            child_rows.append(
                {
                    "title": f"{lesson.title} (part {i + 1}/{len(parts)})"[:255],
                    "topic": topic_slug,
                    "markdown_content": str(gen_sl.get("markdown") or ""),
                    "metadata_json": meta,
                }
            )

        n = len(titles)
        overview = (
            "## Focused review\n\n"
            "This topic was split into smaller steps after your last assessment. "
            "Open each part below **in order** and pass its quiz before moving on.\n\n"
            + "\n".join(f"{i + 1}. **{t}**" for i, t in enumerate(titles))
            + f"\n\n_Total parts: {n}._"
        )
        await self.course_repo.persist_sub_lesson_split(
            lesson,
            overview_markdown=overview,
            children=child_rows,
        )
        refreshed = await self.course_repo.list_lessons_by_course(lesson.course_id)
        return self.course_repo.build_syllabus_modules_from_lessons(
            course.title,
            refreshed,
            lesson_duration_minutes=_duration_minutes_for_level(level),
            target_level=level,
        )

    async def generate_lesson_assessment(self, user_id: int, lesson_id: int) -> dict:
        lesson = await self.course_repo.get_lesson_with_course(lesson_id)
        if lesson is None:
            raise ValueError("Lesson not found")
        if lesson.course is None or lesson.course.user_id != user_id:
            raise ValueError("Lesson not found")
        await self._ensure_lesson_accessible(user_id, lesson.course_id, lesson.id)
        subs = await self.course_repo.get_child_lessons(lesson.id)
        if subs and not lesson.is_sub_lesson:
            raise ValueError("Assessments run on each part below. Open the first sub-lesson.")
        progress = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=lesson.id)
        level = _normalized_course_level(lesson.course.level)
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
        progress.current_questions_json = _assign_question_ids(questions)
        await self.lesson_progress_repo.save(progress)
        return {
            "lesson_id": f"lesson_{lesson.id}",
            "attempts_used": progress.attempts,
            "attempts_remaining": max(0, 3 - progress.attempts),
            "questions": progress.current_questions_json,
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
        await self._ensure_lesson_accessible(user_id, lesson.course_id, lesson.id)
        subs_blocking = await self.course_repo.get_child_lessons(lesson.id)
        if subs_blocking and not lesson.is_sub_lesson:
            pmap0 = await self.lesson_progress_repo.get_passed_map(user_id, [c.id for c in subs_blocking])
            if not all(pmap0.get(c.id) for c in subs_blocking):
                raise ValueError("Complete each sub-lesson for this topic before submitting here.")
        progress = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=lesson.id)
        questions = progress.current_questions_json or []
        if not isinstance(questions, list) or len(questions) != 5:
            level = _normalized_course_level(lesson.course.level)
            questions = await self.assessment_service.generate_assessment(
                topic=lesson.topic,
                level=level,
                lesson_title=lesson.title,
                lesson_markdown=(lesson.markdown_content or ""),
                attempt_number=max(1, progress.attempts + 1),
                previous_questions=[],
            )
            progress.current_questions_json = _assign_question_ids(questions)
            questions = progress.current_questions_json

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
            await self._sync_parent_passed_if_subs_done(user_id, lesson.parent_lesson_id)
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

        level = _normalized_course_level(lesson.course.level)
        chapter_ref = _extract_chapter_ref(lesson.metadata_json)
        track = _track_from_course_title(getattr(lesson.course, "title", None))

        if lesson.is_sub_lesson:
            raw_sl = self.lesson_generator.generate_sub_lesson(
                parent_topic=lesson.topic,
                sub_title=lesson.title,
                source_excerpt=(lesson.markdown_content or "")[:12000],
                track=track,
                level=level,
                chapter_ref=chapter_ref,
            )
            gen_sl = self.lesson_validator.validate(raw_sl, track=track)
            regenerated_markdown = str(gen_sl.get("markdown") or "")
            await self.course_repo.update_lesson_content(lesson.id, regenerated_markdown)
            new_questions = await self.assessment_service.generate_assessment(
                topic=lesson.topic,
                level=level,
                lesson_title=lesson.title,
                lesson_markdown=regenerated_markdown,
                attempt_number=max(1, progress.attempts + 1),
                previous_questions=questions if isinstance(questions, list) else [],
            )
            progress.current_questions_json = _assign_question_ids(new_questions)
            await self.lesson_progress_repo.save(progress)
            return {
                "passed": False,
                "locked": False,
                "score": score,
                "attempts": progress.attempts,
                "message": f"Assessment failed. This part was expanded for attempt {attempt_number + 1}.",
                "next_action": "retry_after_regeneration",
                "sub_lessons_created": False,
            }

        kids_exist = await self.course_repo.get_child_lessons(lesson.id)
        if kids_exist:
            await self.lesson_progress_repo.save(progress)
            return {
                "passed": False,
                "locked": False,
                "score": score,
                "attempts": progress.attempts,
                "message": "Use the numbered sub-lessons for this topic.",
                "next_action": "go_to_sub_lessons",
                "sub_lessons_created": False,
            }

        updated_modules = await self._remediation_split_root_lesson(user_id, lesson)
        progress.current_questions_json = []
        progress.attempts = 0
        await self.lesson_progress_repo.save(progress)
        return {
            "passed": False,
            "locked": False,
            "score": score,
            "attempts": progress.attempts,
            "message": "Assessment failed. This topic was split into smaller lessons—start with part 1.",
            "next_action": "go_to_sub_lessons",
            "sub_lessons_created": True,
            "updated_syllabus_modules": updated_modules,
        }
