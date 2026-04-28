import json

from app.core.placement_rubric import (
    DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL,
    DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    PLACEMENT_CONCEPTS_BY_LEVEL,
    SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    chapter_scope_for_level,
    normalize_level,
    normalize_track,
    validate_syllabus_topics_for_level,
)
from app.services.agents.base import AgentPair, AgentValidationError
from app.services.agents.syllabus_common import (
    syllabus_allowed_topics_ordered,
    syllabus_rubric_concepts_for_level,
)
from app.services.llm_client import LLMClient

_SYLLABUS_VALIDATOR_SYSTEM = """You are SyllabusValidatorAgent for Python for Everybody.
You receive JSON with:
- placement_level (string)
- chapter_scope (string)
- allowed_chapters (object: chapter number → chapter title)
- allowed_topics (array of exact allowed topic strings for this level)
- rubric_concepts (array of exact rubric concept strings for this level)
- candidate_units (the generated units array)

Validate every unit and sub-lesson:
1. topic must be copied EXACTLY from allowed_topics — no paraphrasing
2. lesson_title must NOT equal topic — must be more descriptive
3. description must be at least 2 sentences specific to the topic
4. learning_objectives must be a list of at least 3 actionable strings (verb-first)
5. rubric_concept must exactly match one entry from rubric_concepts
6. Every topic in allowed_topics appears exactly once — no omissions, no duplicates
7. No topics from other levels appear
8. chapter_ref must belong to allowed_chapters keys
9. Units must be in ascending chapter number order
10. Within Ch 2: sub-lesson with topic related to 'Expressions' appears before 'Variable Assignment'
11. Each chapter unit must have at least 4 sub-lessons

Return JSON only:
{"valid": true, "units": [ ...normalized units array unchanged... ]}
or {"valid": false, "error": "which lesson/unit failed and which rule number"}.
If valid, echo the full units array unchanged."""


def flatten_syllabus_payload(payload: dict) -> list[dict]:
    """
    Normalize syllabus JSON: either legacy flat `lessons[]` or hierarchical `units[]`
    with nested `lessons` (sub-lessons). Each row: topic, title, description, unit_title.
    """
    units = payload.get("units")
    if isinstance(units, list) and units:
        out: list[dict] = []
        for u in units:
            if not isinstance(u, dict):
                continue
            ut = str(u.get("title") or u.get("unit_title") or "").strip() or "Unit"
            summary = str(u.get("summary") or u.get("description") or "").strip()
            for sl in u.get("lessons") or []:
                if not isinstance(sl, dict):
                    continue
                topic = str(sl.get("topic") or "").strip()
                if not topic:
                    continue
                title = str(sl.get("lesson_title") or sl.get("title") or topic).strip()
                desc = str(sl.get("description") or "").strip()
                lo = sl.get("learning_objectives")
                row = {
                    "topic": topic,
                    "title": title,
                    "description": desc,
                    "unit_title": ut,
                    "learning_objectives": lo if isinstance(lo, list) else [],
                    "rubric_concept": str(sl.get("rubric_concept") or "").strip(),
                }
                lit = str(sl.get("lesson_title") or sl.get("title") or "").strip()
                if lit:
                    row["lesson_title"] = lit
                cref = sl.get("chapter_ref")
                if cref is not None:
                    try:
                        row["chapter_ref"] = int(cref)
                    except (TypeError, ValueError):
                        row["chapter_ref"] = cref
                if summary and not desc:
                    row["description"] = summary
                out.append(row)
        return out

    legacy = payload.get("lessons") or []
    rows: list[dict] = []
    for lesson in legacy:
        if not isinstance(lesson, dict):
            continue
        topic = str(lesson.get("topic") or "").strip()
        if not topic:
            continue
        lo = lesson.get("learning_objectives")
        lr = {
            "topic": topic,
            "title": str(lesson.get("lesson_title") or lesson.get("title") or topic).strip(),
            "description": str(lesson.get("description") or "").strip(),
            "unit_title": str(lesson.get("unit_title") or "").strip() or None,
            "learning_objectives": lo if isinstance(lo, list) else [],
            "rubric_concept": str(lesson.get("rubric_concept") or "").strip(),
        }
        cref = lesson.get("chapter_ref")
        if cref is not None:
            try:
                lr["chapter_ref"] = int(cref)
            except (TypeError, ValueError):
                lr["chapter_ref"] = cref
        rows.append(lr)
    return rows


def _validate_syllabus_deterministic(payload: dict, placement_level: str | None, track: str = "python") -> dict:
    """Deterministic fallback — mirrors placement validator pattern."""
    flat = flatten_syllabus_payload(payload)
    if not flat:
        raise AgentValidationError(
            "Syllabus must contain units with lessons, or a non-empty lessons array."
        )

    seen_topics: set[str] = set()
    unique_lessons: list[dict] = []
    for lesson in flat:
        topic = lesson.get("topic", "")
        if topic and topic not in seen_topics:
            seen_topics.add(topic)
            unique_lessons.append(lesson)

    if placement_level:
        try:
            validate_syllabus_topics_for_level(unique_lessons, placement_level, track=track)
        except ValueError as exc:
            raise AgentValidationError(str(exc)) from exc

    if placement_level:
        lvl = normalize_level(placement_level)
        if normalize_track(track) in {"deep_learning", "dl"}:
            allowed_concepts = set(
                DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(
                    lvl,
                    DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ()),
                )
            )
        else:
            allowed_concepts = set(
                SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(lvl, PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ()))
            )
        for i, lesson in enumerate(unique_lessons):
            rc = str(lesson.get("rubric_concept") or "").strip()
            if rc and rc not in allowed_concepts:
                raise AgentValidationError(
                    f"Lesson {i + 1} ({lesson.get('topic')}): "
                    f"rubric_concept {rc!r} is not valid for level {lvl!r}."
                )

        ALLOWED_CHAPTER_NUMBERS = {
            "beginner": {1, 2, 3, 6},
            "intermediate": {4, 5, 7, 8, 9, 10},
            "advanced": {11, 12, 13, 14},
            "very_advanced": {15, 16},
        }
        if normalize_track(track) in {"deep_learning", "dl"}:
            ALLOWED_CHAPTER_NUMBERS = {
                "beginner": {1, 2, 3, 4},
                "intermediate": {5, 6, 7, 8},
                "advanced": {9, 10, 11, 12},
                "very_advanced": {13, 14, 15, 16},
            }
        lvl_ch = normalize_level(placement_level)
        allowed_ch = ALLOWED_CHAPTER_NUMBERS.get(lvl_ch, set())
        for i, lesson in enumerate(unique_lessons):
            ch_ref = lesson.get("chapter_ref")
            if ch_ref is not None:
                try:
                    if int(ch_ref) not in allowed_ch:
                        raise AgentValidationError(
                            f"Lesson {i + 1} ({lesson.get('topic')}): "
                            f"chapter_ref {ch_ref} is outside allowed chapters "
                            f"for level {lvl_ch!r}: {sorted(allowed_ch)}"
                        )
                except (TypeError, ValueError):
                    pass

    for i, lesson in enumerate(unique_lessons):
        desc = str(lesson.get("description") or "").strip()
        if len(desc) < 30:
            raise AgentValidationError(
                f"Lesson {i + 1} ({lesson.get('topic')}): description too short or missing."
            )
        objectives = lesson.get("learning_objectives")
        if not isinstance(objectives, list) or len(objectives) < 3:
            raise AgentValidationError(
                f"Lesson {i + 1} ({lesson.get('topic')}): "
                "learning_objectives must be a list of at least 3 items."
            )
        title = str(lesson.get("lesson_title") or lesson.get("title") or "").strip()
        topic = str(lesson.get("topic") or "").strip()
        if title.lower() == topic.lower():
            raise AgentValidationError(
                f"Lesson {i + 1}: lesson_title must differ from topic name."
            )

    topics = [lesson.get("topic", "") for lesson in unique_lessons]
    if "Variable Assignment" in topics and "Expressions" in topics:
        i_exp = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Expressions")
        i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
        if i_exp > i_var:
            exp_lesson = unique_lessons.pop(i_exp)
            i_var = next(i for i, l in enumerate(unique_lessons) if l.get("topic") == "Variable Assignment")
            unique_lessons.insert(i_var, exp_lesson)

    topics = [lesson.get("topic", "") for lesson in unique_lessons]
    if len(set(topics)) != len(topics):
        raise AgentValidationError("Syllabus contains duplicate topics.")

    return {"lessons": unique_lessons, "units": payload.get("units")}


class SyllabusValidatorAgent(AgentPair):
    """LLM-assisted syllabus validation with deterministic fallback."""

    name = "syllabus-validator"

    def __init__(self, llm: LLMClient):
        super().__init__("syllabus-validator", llm)

    def validate(self, payload: dict, placement_level: str | None = None, track: str = "python") -> dict:
        lvl = normalize_level(placement_level) if placement_level else "beginner"
        track_key = (track or "python").strip().lower().replace("-", "_")
        allowed_topics = syllabus_allowed_topics_ordered(lvl, track=track_key)
        rubric_concepts = syllabus_rubric_concepts_for_level(lvl, track=track_key)

        ALLOWED_CHAPTERS = {
            "beginner": {
                1: "Why we program",
                2: "Variables, Expressions and Statements",
                3: "Conditional execution",
                6: "Strings",
            },
            "intermediate": {
                4: "Functions",
                5: "Iteration",
                7: "Files",
                8: "Lists",
                9: "Dictionaries",
                10: "Tuples",
            },
            "advanced": {
                11: "Regular Expressions",
                12: "Networked Programs",
                13: "Web Services",
                14: "Object-Oriented Programming",
            },
            "very_advanced": {
                15: "Databases and SQL",
                16: "Visualizing Data",
            },
        }
        if normalize_track(track_key) in {"deep_learning", "dl"}:
            ALLOWED_CHAPTERS = {
                "beginner": {1: "Math Foundations", 2: "Python for DL", 3: "Data Pipelines", 4: "Linear Models"},
                "intermediate": {5: "NN Basics", 6: "Backpropagation", 7: "Optimization", 8: "Regularization"},
                "advanced": {9: "CNN", 10: "Sequence Models", 11: "Transformers", 12: "Training Systems"},
                "very_advanced": {13: "Generative", 14: "RL", 15: "Scaling", 16: "MLOps"},
            }

        validation_input = {
            "placement_level": lvl,
            "track": track_key,
            "chapter_scope": chapter_scope_for_level(lvl, track=track_key),
            "allowed_chapters": ALLOWED_CHAPTERS.get(lvl, {}),
            "allowed_topics": allowed_topics,
            "rubric_concepts": rubric_concepts,
            "candidate_units": payload.get("units") or [],
        }

        try:
            out = self._generate_with_retries(
                model=self.settings.fast_model,
                system_prompt=_SYLLABUS_VALIDATOR_SYSTEM,
                user_prompt=json.dumps(validation_input, ensure_ascii=False),
            )
            if not isinstance(out, dict) or not out.get("valid"):
                raise AgentValidationError(
                    str(out.get("error") or "SyllabusValidatorAgent rejected the syllabus")
                )
            merged = {"units": out.get("units") or [], "lessons": payload.get("lessons")}
            return _validate_syllabus_deterministic(merged, placement_level, track=track_key)
        except AgentValidationError:
            return _validate_syllabus_deterministic(payload, placement_level, track=track_key)
