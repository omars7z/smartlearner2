import json
import logging
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
    ExamGeneratorAgent,
    ExamValidatorAgent,
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
from app.services.llm_client import LLMClient, LLMClientError

logger = logging.getLogger(__name__)


def _json_for_agent_log(obj: object) -> dict:
    """Ensure JSON-serializable dict for agent_runs.output_json (avoids DB/encode 500s)."""
    if not isinstance(obj, dict):
        return {"_note": "non-dict payload", "repr": repr(obj)[:2000]}
    try:
        return json.loads(json.dumps(obj, default=str))
    except (TypeError, ValueError) as exc:
        logger.warning("Syllabus log payload not JSON-safe: %s", exc)
        return {"_error": "payload omitted", "detail": str(exc)[:500]}


def _questions_json_as_dict(raw: object) -> dict:
    """Some DB drivers return JSON as str; normalize for placement_session / track."""
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}

from app.core.exam_constants import COMPREHENSIVE_EXAM_LESSON_ID, parse_exam_lesson_ref
from app.services.orchestrator.common import (
    assign_question_ids as _assign_question_ids,
    duration_minutes_for_level as _duration_minutes_for_level,
    extract_chapter_ref as _extract_chapter_ref,
    is_dynamic_lesson_markdown as _is_dynamic_lesson_markdown,
    lesson_response_payload as _lesson_response_payload,
    normalized_course_level as _normalized_course_level,
    pack_exam_questions as _pack_exam_questions,
    unpack_exam_questions as _unpack_exam_questions,
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
from app.services.orchestrator.agent_runs import log_agent_run, validate_and_log
from app.services.orchestrator.qa_helpers import build_failure_context, qa_envelope, qa_track_scope_envelope
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


def _exam_questions_for_frontend(questions: list[dict]) -> list[dict]:
    letters = ["A", "B", "C", "D"]
    out: list[dict] = []
    for i, q in enumerate(questions):
        choices = list(q.get("choices") or [])
        correct = str(q.get("correct_answer") or "").strip()
        correct_idx = 0
        for j, c in enumerate(choices):
            if str(c).strip() == correct:
                correct_idx = j
                break
        qid = str(q.get("id") or f"eq{i}")
        diff = str(q.get("difficulty") or "medium").lower()
        if diff not in {"easy", "medium", "hard"}:
            diff = "medium"
        out.append(
            {
                "id": qid,
                "question_id": qid,
                "text": str(q.get("question") or ""),
                "question_text": str(q.get("question") or ""),
                "difficulty": diff,
                "options": choices,
                "correct_answer": letters[correct_idx] if correct_idx < len(letters) else "A",
                "correct_index": correct_idx,
                "explanation": str(q.get("explanation") or ""),
            }
        )
    return out


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
        self.exam_generator = ExamGeneratorAgent(self.llm, self.rag)
        self.exam_validator = ExamValidatorAgent()
        self.analytics_agent = AnalyticsAgent(self.llm)
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

    async def get_lessons_progress(self, user_id: int, course_id: int) -> dict:
        from app.services.orchestrator.lesson_access import (
            assessable_sequence_ids,
            block_for_lesson,
            can_user_access_lesson,
            is_block_fully_passed,
        )

        course = await self.course_repo.get_course_with_lessons(course_id)
        if course is None or course.user_id != user_id:
            raise ValueError("Course not found")

        lessons, blocks, pmap = await self._course_progression_context(user_id, course_id)
        details = await self.lesson_progress_repo.get_details_map(user_id, [L.id for L in lessons])
        assessable_ids = assessable_sequence_ids(blocks)
        completed = sum(1 for aid in assessable_ids if pmap.get(aid, False))

        lesson_entries: dict[str, dict] = {}
        for les in lessons:
            block = block_for_lesson(blocks, les.id)
            block_passed = is_block_fully_passed(block, pmap) if block else bool(pmap.get(les.id, False))
            detail = details.get(les.id, {})
            lesson_entries[f"lesson_{les.id}"] = {
                "passed": bool(pmap.get(les.id, False)),
                "accessible": can_user_access_lesson(
                    lesson_id=les.id,
                    blocks=blocks,
                    passed_map=pmap,
                ),
                "block_passed": block_passed,
                "attempts": int(detail.get("attempts") or 0),
                "last_score": detail.get("last_score"),
            }

        total = len(assessable_ids)
        return {
            "course_id": course_id,
            "completed_assessable": completed,
            "total_assessable": total,
            "overall_percent": round(100.0 * completed / total, 1) if total else 0.0,
            "lessons": lesson_entries,
        }

    async def _course_for_exam(self, user_id: int, course_id: int | None):
        if course_id is not None:
            course = await self.course_repo.get_course_with_lessons(course_id)
            if course is None or course.user_id != user_id:
                raise ValueError("Course not found")
            return course
        raise ValueError("course_id is required for this exam")

    async def _ensure_lesson_completed_for_exam(self, user_id: int, course_id: int, lesson_id: int):
        from app.services.orchestrator.lesson_access import (
            assessable_sequence_ids,
            block_for_lesson,
            is_block_fully_passed,
        )

        lessons, blocks, pmap = await self._course_progression_context(user_id, course_id)
        lesson = next((les for les in lessons if les.id == lesson_id), None)
        if lesson is None:
            raise ValueError("Lesson not found")
        block = block_for_lesson(blocks, lesson_id)
        if block and is_block_fully_passed(block, pmap):
            return lesson
        assessable = assessable_sequence_ids(blocks)
        if lesson_id in assessable and pmap.get(lesson_id, False):
            return lesson
        raise ValueError("Complete this lesson before requesting an exam.")

    async def _ensure_comprehensive_exam_eligible(self, user_id: int, course_id: int) -> tuple:
        from app.services.orchestrator.lesson_access import assessable_sequence_ids

        course = await self._course_for_exam(user_id, course_id)
        lessons, blocks, pmap = await self._course_progression_context(user_id, course.id)
        assessable = assessable_sequence_ids(blocks)
        if not assessable:
            raise ValueError("No assessable lessons in this course yet.")
        if not all(pmap.get(aid, False) for aid in assessable):
            raise ValueError(
                "Complete all lessons in the track before taking the comprehensive exam."
            )
        return course, lessons, assessable

    def _aggregate_track_markdown(self, lessons: list, *, max_chars: int = 14_000) -> str:
        parts: list[str] = []
        for les in sorted(lessons, key=lambda x: x.order_index):
            md = (getattr(les, "markdown_content", None) or "").strip()
            if not md:
                continue
            title = (getattr(les, "title", None) or les.topic or "Lesson").strip()
            parts.append(f"## {title}\n\n{md}")
        combined = "\n\n".join(parts).strip()
        if len(combined) <= max_chars:
            return combined
        return combined[:max_chars] + "\n\n…"

    async def _sync_parent_passed_if_subs_done(self, user_id: int, parent_lesson_id: int | None) -> None:
        if not parent_lesson_id:
            return
        children = await self.course_repo.get_child_lessons(parent_lesson_id)
        if not children:
            return
        ordered = sorted(children, key=lambda c: c.order_index)
        last_id = ordered[-1].id
        pmap = await self.lesson_progress_repo.get_passed_map(user_id, [last_id])
        if not pmap.get(last_id):
            return
        pp = await self.lesson_progress_repo.get_or_create(user_id=user_id, lesson_id=parent_lesson_id)
        pp.passed = True
        await self.lesson_progress_repo.save(pp)

    @staticmethod
    def _normalize_track_key(track: str | None) -> str:
        return normalize_track(track or "python")

    @staticmethod
    def _build_fallback_placement_questions(level: str, track: str) -> list[dict]:
        """
        Deterministic fallback so placement/start never hard-fails on transient LLM issues.
        """
        from app.core.placement_rubric import concepts_for_level

        concepts = list(concepts_for_level(level, track=track))
        questions: list[dict] = []
        for concept in concepts[:QUESTIONS_PER_LEVEL]:
            stem = (
                f"Which statement best matches this concept: {concept}?"
                if track in {"deep_learning", "dl"}
                else f"In Python, which option best describes: {concept}?"
            )
            choices = [
                f"A clear definition and practical use of {concept}",
                "An unrelated advanced topic from another stage",
                "A statement that contradicts the concept",
                "A vague statement with no concrete meaning",
            ]
            questions.append(
                {
                    "question": stem,
                    "choices": choices,
                    "correct_answer": choices[0],
                    "concept": concept,
                }
            )
        return questions

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

    @staticmethod
    def _track_from_lesson_context(lesson, course) -> str:
        # Prefer explicit, persisted track metadata over title heuristics.
        meta = getattr(lesson, "metadata_json", None)
        if isinstance(meta, dict):
            raw = meta.get("track")
            if isinstance(raw, str) and raw.strip():
                return normalize_track(raw)

        # Backward-compatible fallback for existing rows without track metadata.
        lesson_text = " ".join(
            [
                str(getattr(lesson, "title", "") or ""),
                str(getattr(lesson, "topic", "") or ""),
            ]
        ).lower()
        if any(k in lesson_text for k in ("deep learning", "neural", "gradient", "tensor", "backprop")):
            return "deep_learning"

        return _track_from_course_title(getattr(course, "title", None))

    @staticmethod
    def _fallback_lesson_markdown(*, title: str, topic: str, track: str, level: str) -> str:
        topic_text = (topic or title or "this topic").replace("_", " ").strip()
        level_text = (level or "beginner").replace("_", " ").title()
        if normalize_track(track) in {"deep_learning", "dl"}:
            from app.core.deep_learning_curriculum import DL_SOURCE_RESOURCE

            source_line = f"{DL_SOURCE_RESOURCE} and lesson context."
            example = (
                "```python\n"
                "import numpy as np\n\n"
                "x = np.array([0.5, -1.2, 3.0])\n"
                "relu = np.maximum(0, x)\n"
                "print(relu)\n"
                "```\n"
            )
        else:
            source_line = "Python for Everybody and lesson context."
            example = (
                "```python\n"
                "x = [2, -1, 5]\n"
                "positive = [v for v in x if v > 0]\n"
                "print(positive)\n"
                "```\n"
            )
        return (
            f"## Learning objectives\n"
            f"- Explain the key idea behind **{topic_text}**.\n"
            f"- Apply the concept in a small, runnable example.\n"
            f"- Identify one common mistake and how to avoid it.\n\n"
            f"## Core ideas\n"
            f"This fallback lesson is generated because live LLM providers are temporarily unavailable. "
            f"It focuses on **{topic_text}** at **{level_text}** level using {source_line}\n\n"
            f"## Worked example\n"
            f"{example}\n"
            f"## Common pitfalls\n"
            f"- Using the concept without checking assumptions.\n"
            f"- Copying formulas/code without validating outputs.\n\n"
            f"## Practice\n"
            f"1. Summarize **{topic_text}** in 2-3 lines.\n"
            f"2. Modify the example and explain the output.\n\n"
            f"## Summary\n"
            f"- This is a temporary fallback lesson.\n"
            f"- Retry generation later for a richer, personalized version.\n"
        )

    @staticmethod
    def _build_personal_syllabus(lessons: list) -> list[dict]:
        root = [l for l in lessons if not getattr(l, "is_sub_lesson", False)]
        ordered = sorted(root or lessons, key=lambda l: l.order_index)
        topics: dict[str, dict] = {}
        for lesson in ordered:
            topic = str(getattr(lesson, "topic", "") or "").replace("_", " ").strip()
            if not topic:
                topic = str(getattr(lesson, "title", "") or "").strip()
            if not topic:
                continue
            if topic not in topics:
                topics[topic] = {"topic": topic, "subtopics": [], "order": len(topics)}
            title = str(getattr(lesson, "title", "") or "").strip()
            if title and title not in topics[topic]["subtopics"]:
                topics[topic]["subtopics"].append(title)
        return list(topics.values())

    @staticmethod
    def _build_interaction_logs(lessons: list, progresses: list) -> list[dict]:
        lesson_by_id = {int(l.id): l for l in lessons}
        logs: list[dict] = []
        for progress in progresses:
            lesson = lesson_by_id.get(int(progress.lesson_id))
            if lesson is None:
                continue
            topic = str(getattr(lesson, "topic", "") or "").replace("_", " ")
            updated = getattr(progress, "updated_at", None) or getattr(progress, "created_at", None)
            ts = updated.isoformat() if updated is not None else ""
            attempts = int(getattr(progress, "attempts", 0) or 0)
            last_score = getattr(progress, "last_score", None)
            passed = bool(getattr(progress, "passed", False))
            if attempts > 0 and last_score is not None:
                logs.append(
                    {
                        "type": "quiz",
                        "topic": topic,
                        "score": float(last_score) / 5.0,
                        "timestamp": ts,
                    }
                )
            elif passed:
                logs.append({"type": "lesson_done", "topic": topic, "score": 1.0, "timestamp": ts})
            elif str(getattr(lesson, "markdown_content", "") or "").strip():
                logs.append({"type": "lesson_done", "topic": topic, "score": None, "timestamp": ts})
        logs.sort(key=lambda row: str(row.get("timestamp") or ""))
        return logs

    @staticmethod
    def _seed_mastery_state(
        syllabus: list[dict],
        strong_topics: list[str],
        weak_topics: list[str],
    ) -> dict[str, float]:
        mastery: dict[str, float] = {}
        for row in syllabus:
            topic = str(row.get("topic") or "").strip()
            if topic:
                mastery[topic] = 0.5

        def _match_topic(label: str) -> str | None:
            needle = label.replace("_", " ").strip().lower()
            if not needle:
                return None
            for row in syllabus:
                topic = str(row.get("topic") or "").strip()
                if topic.lower() == needle or needle in topic.lower() or topic.lower() in needle:
                    return topic
            return None

        for raw in strong_topics:
            matched = _match_topic(str(raw))
            if matched:
                mastery[matched] = 0.65
        for raw in weak_topics:
            matched = _match_topic(str(raw))
            if matched:
                mastery[matched] = 0.3
        return mastery

    async def _gather_track_analytics_context(self, user_id: int, track: str | None) -> dict:
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
            str(x).strip()
            for x in (placement_result.get("strong_topics") or placement_session.get("strong_concepts") or [])
            if str(x).strip()
        ]
        weak_topics = [
            str(x).strip()
            for x in (placement_result.get("weak_topics") or placement_session.get("wrong_concepts") or [])
            if str(x).strip()
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
        passed_lesson_ids = {int(p.lesson_id) for p in progresses if bool(p.passed)}
        completed_lessons = [str(l.title).strip() for l in lessons if l.id in passed_lesson_ids and str(l.title).strip()]
        pending_lessons = [str(l.title).strip() for l in lessons if l.id not in passed_lesson_ids and str(l.title).strip()]
        completed_topics = [str(l.topic).replace("_", " ").strip() for l in lessons if l.id in passed_lesson_ids and str(l.topic).strip()]
        pending_topics = [str(l.topic).replace("_", " ").strip() for l in lessons if l.id not in passed_lesson_ids and str(l.topic).strip()]

        personal_syllabus = self._build_personal_syllabus(lessons)
        interaction_logs = self._build_interaction_logs(lessons, progresses)
        mastery_state = self._seed_mastery_state(personal_syllabus, strong_topics, weak_topics)

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
            "completed_lessons": list(dict.fromkeys(completed_lessons))[:20],
            "pending_lessons": list(dict.fromkeys(pending_lessons))[:20],
            "completed_topics": list(dict.fromkeys(completed_topics))[:20],
            "pending_topics": list(dict.fromkeys(pending_topics))[:20],
            "personal_syllabus": personal_syllabus,
            "mastery_state": mastery_state,
            "interaction_logs": interaction_logs,
        }

        return {
            "track_key": track_key,
            "course_title": course_title,
            "subject": subject,
            "source": source,
            "metrics": metrics,
        }

    async def _run_analytics_for_event(
        self,
        user_id: int,
        track: str | None,
        current_event: dict,
    ) -> dict:
        ctx = await self._gather_track_analytics_context(user_id, track)
        state = {
            "student_id": str(user_id),
            "personal_syllabus": ctx["metrics"]["personal_syllabus"],
            "mastery_state": ctx["metrics"]["mastery_state"],
            "interaction_logs": ctx["metrics"]["interaction_logs"],
            "current_event": current_event,
        }
        output = self.analytics_agent.process(state)
        await log_agent_run(
            self.agent_repo,
            agent_name=self.analytics_agent.name,
            stage="process_event",
            input_json={"track": ctx["track_key"], "event": current_event},
            output_json=output,
            is_valid=True,
            user_id=user_id,
        )
        return self.analytics_agent.to_analytics_payload(output)

    async def build_analytics_summary(self, user_id: int, track: str | None = None) -> dict:
        ctx = await self._gather_track_analytics_context(user_id, track)
        track_key = ctx["track_key"]
        metrics = ctx["metrics"]

        insights = self.analytics_agent.generate(metrics)
        agent_output = insights.pop("agent_output", None)
        await log_agent_run(
            self.agent_repo,
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
                    "course_title": ctx["course_title"],
                    "subject": ctx["subject"],
                    "source": ctx["source"],
                },
                "metrics": metrics,
                "insights": insights,
                "agent_output": agent_output,
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
        await log_agent_run(
            self.agent_repo,
            agent_name=self.placement_generator.name,
            stage="generate",
            input_json={"level": level, "question_count": question_count, "track": norm_track, "flow": "generate"},
            output_json=raw,
            is_valid=True,
            user_id=user_id,
        )
        generated = await validate_and_log(
            self.agent_repo,
            validator_name=self.placement_validator.name,
            input_json={"level": level, "question_count": question_count, "track": norm_track},
            payload=raw,
            user_id=user_id,
            validate_fn=lambda p: self.placement_validator.validate(p, level, question_count, track=norm_track),
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
            generated = {"questions": self._build_fallback_placement_questions(first_level, gen_track)}
            await self.agent_repo.log_run(
                agent_name=self.placement_generator.name,
                stage="fallback_generate",
                input_json={
                    "level": first_level,
                    "question_count": QUESTIONS_PER_LEVEL,
                    "track": track,
                    "gen_track": gen_track,
                    "reason": str(last_exc) if last_exc else "unknown",
                },
                output_json=generated,
                is_valid=True,
                user_id=user_id,
            )

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
        pj = _questions_json_as_dict(placement.questions_json)
        ps_raw = pj.get("placement_session")
        sess = ps_raw if isinstance(ps_raw, dict) else {}
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
        except (AgentValidationError, LLMClientError):
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
        try:
            await log_agent_run(
                self.agent_repo,
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
                output_json=_json_for_agent_log(raw_syllabus),
                is_valid=True,
                user_id=user_id,
            )
        except Exception as exc:
            logger.warning("agent_repo.log_run syllabus generate skipped: %s", exc)
        generated = await validate_and_log(
            self.agent_repo,
            validator_name=self.syllabus_validator.name,
            input_json={"placement_id": placement_id, "score": score, "level": level_str},
            payload=raw_syllabus,
            user_id=user_id,
            validate_fn=lambda p: self.syllabus_validator.validate(p, placement_level=level_str, track=track),
        )

        # Transform lessons from syllabus format to CourseRepository format
        transformed_lessons = []
        for lesson in generated.get("lessons", []):
            rubric_topic = str(lesson.get("topic") or "").strip()
            display_title = str(lesson.get("title") or rubric_topic).strip()
            ch_ref = lesson.get("chapter_ref")
            meta: dict = {}
            if ch_ref is not None:
                try:
                    meta = {"chapter_ref": int(ch_ref)}
                except (TypeError, ValueError):
                    meta = {}
            topic_slug = _topic_slug(rubric_topic)[:100]
            raw_pre = lesson.get("prerequisites", [])
            if isinstance(raw_pre, list):
                prereqs = [str(x).strip() for x in raw_pre if str(x).strip()]
            else:
                prereqs = []
            transformed_lessons.append({
                "title": display_title[:255],
                "topic": topic_slug,
                "prerequisites": prereqs,
                "markdown_content": str(lesson.get("description") or ""),
                "unit_title": (str(lesson.get("unit_title")).strip()[:255] if lesson.get("unit_title") else None),
                "metadata_json": (
                    {"chapter_ref": int(ch_ref), "track": track}
                    if ch_ref is not None
                    else {"track": track}
                ),
            })

        safe_title = (course_title or "My course").strip()[:255]
        course = await self.course_repo.create_course_with_lessons(
            user_id=user_id,
            title=safe_title,
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
                    base["sub_lessons"] = [
                        {**_lesson_payload(k), "is_final_sub_lesson": k.id == kids[-1].id} for k in kids
                    ]
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

        async def _decorate_sub_lesson_flags(entity, payload: dict) -> dict:
            if not getattr(entity, "is_sub_lesson", False) or not entity.parent_lesson_id:
                return payload
            sibs = await self.course_repo.get_child_lessons(entity.parent_lesson_id)
            ordered = sorted(sibs, key=lambda x: x.order_index)
            is_final = bool(ordered) and entity.id == ordered[-1].id
            lesson_obj = payload.setdefault("lesson", {})
            lesson_obj["is_sub_lesson"] = True
            lesson_obj["is_final_sub_lesson"] = is_final
            return payload

        level: str = "beginner"
        course_track = "python"
        chapter_ref: int | None = None
        duration_minutes = _duration_minutes_for_level(level)
        try:
            if course.level:
                level = _normalized_course_level(course.level)
                duration_minutes = _duration_minutes_for_level(level)
            course_track = self._track_from_lesson_context(lesson, course)
        except Exception:
            pass

        children = await self.course_repo.get_child_lessons(lesson.id)
        if children:
            child_list = sorted(children, key=lambda x: x.order_index)
            overview = (lesson.markdown_content or "").strip()
            if not overview or not _is_dynamic_lesson_markdown(overview):
                overview = (
                    "## Focused review\n\n"
                    "This topic is split into smaller steps. Read the parts in any order; only the **final** part "
                    "includes the topic quiz. Passing that quiz unlocks the next lesson.\n\n"
                    + "\n".join(f"{i + 1}. **{c.title}**" for i, c in enumerate(child_list))
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
                    "is_final_sub_lesson": j == len(child_list) - 1,
                }
                for j, c in enumerate(child_list)
            ]
            return await _decorate_sub_lesson_flags(
                lesson,
                _lesson_response_payload(
                    lesson_id=lesson.id,
                    title=lesson.title,
                    duration_minutes=duration_minutes,
                    markdown=overview,
                    llm_used=False,
                    sub_lessons=sub_payload,
                    is_parent_with_sub_lessons=True,
                    course_id=lesson.course_id,
                ),
            )

        existing_markdown = (lesson.markdown_content or "").strip()
        if existing_markdown and _is_dynamic_lesson_markdown(existing_markdown):
            return await _decorate_sub_lesson_flags(
                lesson,
                _lesson_response_payload(
                    lesson_id=lesson.id,
                    title=lesson.title,
                    duration_minutes=duration_minutes,
                    markdown=existing_markdown,
                    llm_used=False,
                    course_id=lesson.course_id,
                ),
            )

        chapter_ref = _extract_chapter_ref(getattr(lesson, "metadata_json", None))

        try:
            raw_lesson = self.lesson_generator.generate(
                topic=lesson.topic,
                lesson_title=lesson.title,
                track=course_track,
                level=level,
                chapter_ref=chapter_ref,
            )
        except LLMClientError:
            # Graceful degradation when providers are rate-limited/unavailable:
            # serve persisted lesson text instead of failing the whole endpoint.
            fallback_markdown = (lesson.markdown_content or "").strip()
            if not _is_dynamic_lesson_markdown(fallback_markdown):
                fallback_markdown = self._fallback_lesson_markdown(
                    title=lesson.title,
                    topic=lesson.topic,
                    track=course_track,
                    level=level,
                )
            return await _decorate_sub_lesson_flags(
                lesson,
                _lesson_response_payload(
                    lesson_id=lesson.id,
                    title=lesson.title,
                    duration_minutes=duration_minutes,
                    markdown=fallback_markdown,
                    llm_used=False,
                    course_id=lesson.course_id,
                ),
            )
        await log_agent_run(
            self.agent_repo,
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
        generated = await validate_and_log(
            self.agent_repo,
            validator_name=self.lesson_validator.name,
            input_json={"lesson_id": lesson_id, "topic": lesson.topic},
            payload=raw_lesson,
            user_id=user_id,
            validate_fn=lambda p: self.lesson_validator.validate(p, track=course_track),
        )
        updated = await self.course_repo.update_lesson_content(lesson.id, generated["markdown"])

        md = (updated.markdown_content or "").strip()
        if not md:
            md = f"## {updated.title}\n\n_Content could not be loaded. Try refreshing or regenerating this lesson._"
        return await _decorate_sub_lesson_flags(
            updated,
            _lesson_response_payload(
                lesson_id=updated.id,
                title=updated.title,
                duration_minutes=duration_minutes,
                markdown=md,
                llm_used=True,
                course_id=lesson.course_id,
            ),
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
            return qa_track_scope_envelope(track_key)

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
            student_context=student_context if isinstance(student_context, dict) else None,
        )
        qa_input = {
            "lesson_id": lesson_id,
            "current_topic": current_topic,
            "question": question,
        }
        await log_agent_run(
            self.agent_repo,
            agent_name=self.qa_generator.name,
            stage="generate",
            input_json=qa_input,
            output_json=raw_qa,
            is_valid=True,
            user_id=user_id,
        )
        generated = await validate_and_log(
            self.agent_repo,
            validator_name=self.qa_validator.name,
            input_json=qa_input,
            payload=raw_qa,
            user_id=user_id,
            validate_fn=lambda p: self.qa_validator.validate(p, track=track_key),
        )
        return qa_envelope(generated)

    async def _latest_placement_topics(self, user_id: int, track: str) -> tuple[list[str], list[str]]:
        from app.models.entities import PlacementTest

        track_key = self._normalize_track_key(track)
        placement_rows = await self.db.execute(
            select(PlacementTest).where(PlacementTest.user_id == user_id).order_by(PlacementTest.created_at.desc())
        )
        for placement in placement_rows.scalars().all():
            if self._placement_track(placement.questions_json) != track_key:
                continue
            data = placement.questions_json if isinstance(placement.questions_json, dict) else {}
            result = data.get("placement_result") if isinstance(data.get("placement_result"), dict) else {}
            sess = data.get("placement_session") if isinstance(data.get("placement_session"), dict) else {}
            weak = [
                str(x).strip()
                for x in (result.get("weak_topics") or sess.get("wrong_concepts") or [])
                if str(x).strip()
            ]
            strong = [
                str(x).strip()
                for x in (result.get("strong_topics") or sess.get("strong_concepts") or [])
                if str(x).strip()
            ]
            return list(dict.fromkeys(weak))[:10], list(dict.fromkeys(strong))[:10]
        return [], []

    async def generate_exam(
        self,
        user_id: int,
        lesson_id: str,
        level: str = "beginner",
        question_count: int = 5,
        course_id: int | None = None,
    ) -> dict:
        if question_count not in {3, 5, 10}:
            raise ValueError("question_count must be 3, 5, or 10")

        exam_kind, numeric_lesson_id = parse_exam_lesson_ref(lesson_id)
        is_comprehensive = exam_kind == "comprehensive"
        response_lesson_id = lesson_id.strip()

        if is_comprehensive:
            course, lessons, assessable = await self._ensure_comprehensive_exam_eligible(
                user_id, course_id
            )
            storage_lesson_id = assessable[-1]
            lesson = await self.course_repo.get_lesson_with_course(storage_lesson_id)
            if lesson is None:
                raise ValueError("Lesson not found")
            lesson_title = "Comprehensive Track Exam"
            topic = "track_comprehensive"
            track = self._track_from_lesson_context(lesson, course)
            course_level = _normalized_course_level(course.level)
            markdown = self._aggregate_track_markdown(lessons)
            if not markdown.strip():
                markdown = self._fallback_lesson_markdown(
                    title=lesson_title,
                    topic=topic,
                    track=track,
                    level=course_level,
                )
        else:
            assert numeric_lesson_id is not None
            lesson = await self.course_repo.get_lesson_with_course(numeric_lesson_id)
            if lesson is None:
                raise ValueError("Lesson not found")
            if lesson.course is None or lesson.course.user_id != user_id:
                raise ValueError("Lesson not found")
            await self._ensure_lesson_completed_for_exam(
                user_id, lesson.course_id, lesson.id
            )
            course = lesson.course
            storage_lesson_id = lesson.id
            lesson_title = lesson.title
            topic = lesson.topic
            track = self._track_from_lesson_context(lesson, course)
            course_level = _normalized_course_level(course.level)
            response_lesson_id = f"lesson_{lesson.id}"
            markdown = (lesson.markdown_content or "").strip()
            if not markdown:
                markdown = self._fallback_lesson_markdown(
                    title=lesson.title,
                    topic=lesson.topic,
                    track=track,
                    level=course_level,
                )

        weak_topics, strong_topics = await self._latest_placement_topics(user_id, track)

        progress = await self.lesson_progress_repo.get_or_create(
            user_id=user_id, lesson_id=storage_lesson_id
        )
        prior = _unpack_exam_questions(progress.current_questions_json)
        previous_stems = [
            str(q.get("question") or "").strip()
            for q in prior
            if isinstance(q, dict) and str(q.get("question") or "").strip()
        ]
        attempt_number = max(1, int(progress.attempts or 0) + 1)

        exam_input = {
            "lesson_id": response_lesson_id,
            "level": level,
            "question_count": question_count,
            "topic": topic,
            "track": track,
            "exam_scope": "comprehensive" if is_comprehensive else "lesson",
        }
        generated: dict | None = None
        used_llm = True
        last_exc: AgentValidationError | None = None
        for attempt in range(3):
            try:
                raw = self.exam_generator.generate(
                    lesson_title=lesson_title,
                    topic=topic,
                    track=track,
                    level=level,
                    question_count=question_count,
                    lesson_markdown=markdown,
                    weak_topics=weak_topics,
                    strong_topics=strong_topics,
                    previous_stems=previous_stems,
                    attempt_number=attempt_number + attempt,
                )
            except AgentValidationError as exc:
                last_exc = exc
                used_llm = False
                raw = self.exam_generator._fallback_questions(
                    topic=topic,
                    level=level,
                    lesson_title=lesson_title,
                    question_count=question_count,
                    attempt_number=attempt_number + attempt,
                    previous_stems=previous_stems,
                )
            await log_agent_run(
                self.agent_repo,
                agent_name=self.exam_generator.name,
                stage="generate",
                input_json={**exam_input, "attempt": attempt + 1},
                output_json=_json_for_agent_log(raw if isinstance(raw, dict) else {"raw": str(raw)[:500]}),
                is_valid=True,
                user_id=user_id,
            )
            try:
                generated = self.exam_validator.validate(raw, question_count=question_count)
            except AgentValidationError as exc:
                last_exc = exc
                await log_agent_run(
                    self.agent_repo,
                    agent_name=self.exam_validator.name,
                    stage="validate",
                    input_json={**exam_input, "attempt": attempt + 1},
                    output_json={"error": str(exc)},
                    is_valid=False,
                    user_id=user_id,
                )
                generated = None
                continue
            await log_agent_run(
                self.agent_repo,
                agent_name=self.exam_validator.name,
                stage="validate",
                input_json={**exam_input, "attempt": attempt + 1},
                output_json=generated,
                is_valid=True,
                user_id=user_id,
            )
            break

        if not generated:
            used_llm = False
            raw = self.exam_generator._fallback_questions(
                topic=topic,
                level=level,
                lesson_title=lesson_title,
                question_count=question_count,
                attempt_number=attempt_number + 3,
                previous_stems=previous_stems,
            )
            generated = self.exam_validator.validate(raw, question_count=question_count)
            await log_agent_run(
                self.agent_repo,
                agent_name=self.exam_generator.name,
                stage="generate_fallback",
                input_json={**exam_input, "reason": str(last_exc or "validation retries exhausted")},
                output_json=generated,
                is_valid=True,
                user_id=user_id,
            )

        stored = _assign_question_ids(list(generated.get("questions") or []))
        progress.current_questions_json = _pack_exam_questions(
            stored, comprehensive=is_comprehensive
        )
        progress.attempts = attempt_number
        await self.lesson_progress_repo.save(progress)

        frontend_questions = _exam_questions_for_frontend(stored)
        return {
            "status": "ok",
            "intent": "exam_generation",
            "result": {
                "status": "generated",
                "lesson_id": response_lesson_id,
                "exam_scope": "comprehensive" if is_comprehensive else "lesson",
                "questions": frontend_questions,
                "llm_used": used_llm,
                "attempt_number": attempt_number,
            },
        }

    async def grade_exam(
        self,
        user_id: int,
        lesson_id: str,
        answers: list[dict],
        course_id: int | None = None,
    ) -> dict:
        exam_kind, numeric_lesson_id = parse_exam_lesson_ref(lesson_id)
        is_comprehensive = exam_kind == "comprehensive"
        response_lesson_id = lesson_id.strip()

        if is_comprehensive:
            course, _lessons, assessable = await self._ensure_comprehensive_exam_eligible(
                user_id, course_id
            )
            storage_lesson_id = assessable[-1]
            lesson = await self.course_repo.get_lesson_with_course(storage_lesson_id)
            if lesson is None:
                raise ValueError("Lesson not found")
            analytics_topic = "track_comprehensive"
        else:
            assert numeric_lesson_id is not None
            lesson = await self.course_repo.get_lesson_with_course(numeric_lesson_id)
            if lesson is None:
                raise ValueError("Lesson not found")
            if lesson.course is None or lesson.course.user_id != user_id:
                raise ValueError("Lesson not found")
            storage_lesson_id = lesson.id
            response_lesson_id = f"lesson_{lesson.id}"
            analytics_topic = lesson.topic

        progress = await self.lesson_progress_repo.get_or_create(
            user_id=user_id, lesson_id=storage_lesson_id
        )
        questions = _unpack_exam_questions(progress.current_questions_json)
        if not questions:
            raise ValueError("No active exam session for this lesson. Generate an exam first.")

        answer_map: dict[str, int] = {}
        for a in answers:
            if not isinstance(a, dict):
                continue
            qid = str(a.get("question_id") or "").strip()
            try:
                answer_map[qid] = int(a.get("answer_index"))
            except (TypeError, ValueError):
                continue

        letters = ["A", "B", "C", "D"]
        score = 0
        per_question: list[dict] = []
        exam_analytics_questions: list[dict] = []
        difficulty_breakdown: dict[str, int] = {"easy": 0, "medium": 0, "hard": 0}

        for idx, q in enumerate(questions):
            if not isinstance(q, dict):
                continue
            qid = str(q.get("id") or f"q{idx}")
            choices = q.get("choices") or []
            if not isinstance(choices, list):
                choices = []
            correct_answer = str(q.get("correct_answer") or "").strip()
            correct_idx = 0
            for j, c in enumerate(choices):
                if str(c).strip() == correct_answer:
                    correct_idx = j
                    break
            selected_idx = answer_map.get(qid)
            is_correct = selected_idx is not None and selected_idx == correct_idx
            if is_correct:
                score += 1
            diff = str(q.get("difficulty") or "medium").lower()
            if diff not in {"easy", "medium", "hard"}:
                diff = "medium"
            if diff in difficulty_breakdown:
                difficulty_breakdown[diff] += 1 if is_correct else 0
            exam_analytics_questions.append({"correct": is_correct, "difficulty": diff})
            per_question.append(
                {
                    "question_id": qid,
                    "question_text": str(q.get("question") or ""),
                    "correct": is_correct,
                    "student_answer": letters[selected_idx] if selected_idx is not None and 0 <= selected_idx < 4 else "—",
                    "correct_answer": letters[correct_idx] if correct_idx < 4 else "A",
                    "explanation": str(q.get("explanation") or ""),
                }
            )

        total = len(questions)
        overall_score = int(round(100 * score / total)) if total else 0
        progress.last_score = score
        await self.lesson_progress_repo.save(progress)

        await log_agent_run(
            self.agent_repo,
            agent_name="exam-grader",
            stage="grade",
            input_json={"lesson_id": response_lesson_id, "answer_count": len(answers)},
            output_json={
                "score": score,
                "total": total,
                "overall_score": overall_score,
                "results": per_question,
            },
            is_valid=True,
            user_id=user_id,
        )

        analytics = None
        try:
            track = self._track_from_lesson_context(lesson, lesson.course)
            analytics = await self._run_analytics_for_event(
                user_id=user_id,
                track=track,
                current_event={
                    "type": "exam",
                    "payload": {
                        "topic": analytics_topic,
                        "questions": exam_analytics_questions,
                    },
                },
            )
        except Exception as exc:
            logger.warning("analytics after exam grade skipped: %s", exc)

        result_payload: dict = {
            "status": "graded",
            "lesson_id": response_lesson_id,
            "exam_scope": "comprehensive" if is_comprehensive else "lesson",
            "score": score,
            "total": total,
            "overall_score": overall_score,
            "passed": overall_score >= 60,
            "difficulty_breakdown": difficulty_breakdown,
            "results": per_question,
        }
        if analytics is not None:
            result_payload["analytics"] = analytics

        return {
            "status": "ok",
            "intent": "exam_grading",
            "result": result_payload,
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
        track = self._track_from_lesson_context(lesson, course)
        chapter_ref = _extract_chapter_ref(lesson.metadata_json)
        child_rows: list[dict] = []
        for i, (snippet, stitle) in enumerate(zip(parts, titles)):
            continuation_context = (
                f"This is part {i + 1} of {len(parts)} in a continuous lesson sequence.\n"
                "Teach only this slice, connect naturally with adjacent parts, and avoid duplicating full explanations "
                "from earlier/later parts.\n"
                f"Part title: {stitle}"
            )
            raw_sl = self.lesson_generator.generate_sub_lesson(
                parent_topic=lesson.topic,
                sub_title=f"{lesson.title} — {stitle}",
                source_excerpt=snippet,
                continuity_instructions=continuation_context,
                sequence_part=(i + 1, len(parts)),
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
            "Read the parts in any order; only the **final** part has the topic quiz—pass it to unlock the next lesson.\n\n"
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
            ordered = sorted(subs, key=lambda x: x.order_index)
            last = ordered[-1]
            raise ValueError(
                f"The topic quiz runs on the final part only: «{last.title}». Open it from the sidebar under this topic."
            )
        if lesson.is_sub_lesson and lesson.parent_lesson_id:
            sibs = await self.course_repo.get_child_lessons(lesson.parent_lesson_id)
            ordered = sorted(sibs, key=lambda x: x.order_index)
            if ordered and lesson.id != ordered[-1].id:
                raise ValueError(
                    "This part has no quiz. Open the **final** part of this topic to take the assessment that unlocks the next lesson."
                )
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
        if lesson.is_sub_lesson and lesson.parent_lesson_id:
            sibs = await self.course_repo.get_child_lessons(lesson.parent_lesson_id)
            ordered = sorted(sibs, key=lambda x: x.order_index)
            if ordered and lesson.id != ordered[-1].id:
                raise ValueError("Submit the assessment only on the final part of this topic.")
        subs_blocking = await self.course_repo.get_child_lessons(lesson.id)
        if subs_blocking and not lesson.is_sub_lesson:
            ordered = sorted(subs_blocking, key=lambda x: x.order_index)
            last = ordered[-1]
            pmap0 = await self.lesson_progress_repo.get_passed_map(user_id, [last.id])
            if not pmap0.get(last.id):
                raise ValueError("Pass the quiz on the final part of this topic before submitting here.")
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
            payload: dict = {"passed": True, "score": score, "next_lesson": next_lesson_id}
            try:
                track = self._track_from_lesson_context(lesson, lesson.course)
                payload["analytics"] = await self._run_analytics_for_event(
                    user_id=user_id,
                    track=track,
                    current_event={
                        "type": "lesson_done",
                        "payload": {
                            "topic": lesson.topic,
                            "passed": True,
                            "quiz_taken": True,
                            "score_ratio": float(score) / 5.0,
                        },
                    },
                )
            except Exception as exc:
                logger.warning("analytics after lesson assessment skipped: %s", exc)
            return payload

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
        track = self._track_from_lesson_context(lesson, lesson.course)

        if lesson.is_sub_lesson:
            failure_context = build_failure_context(
                questions if isinstance(questions, list) else [],
                answer_map,
            )
            raw_sl = self.lesson_generator.generate_sub_lesson(
                parent_topic=lesson.topic,
                sub_title=lesson.title,
                source_excerpt=(lesson.markdown_content or "")[:12000],
                failure_context=failure_context or None,
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
