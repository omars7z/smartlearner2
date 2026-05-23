from app.core.exam_constants import COMPREHENSIVE_EXAM_LESSON_ID
from app.core.placement_rubric import normalize_level


def duration_minutes_for_level(level: str) -> int:
    lvl = normalize_level(level)
    if lvl == "beginner":
        return 10
    if lvl == "intermediate":
        return 15
    if lvl == "advanced":
        return 20
    if lvl == "very_advanced":
        return 25
    return 10


def normalized_course_level(raw_level: str | None) -> str:
    return normalize_level((raw_level or "beginner").replace(" ", "_").lower())


def extract_chapter_ref(metadata_json: object) -> int | None:
    if not isinstance(metadata_json, dict):
        return None
    try:
        chapter_ref = metadata_json.get("chapter_ref")
        return int(chapter_ref) if chapter_ref is not None else None
    except (TypeError, ValueError):
        return None


def assign_question_ids(questions: list[dict]) -> list[dict]:
    for i, q in enumerate(questions):
        q["id"] = f"q{i}"
    return questions


def pack_exam_questions(questions: list[dict], *, comprehensive: bool = False) -> list:
    if comprehensive:
        return [{"_exam_scope": COMPREHENSIVE_EXAM_LESSON_ID, "_questions": questions}]
    return questions


def unpack_exam_questions(payload: object) -> list[dict]:
    if not isinstance(payload, list):
        return []
    for item in payload:
        if isinstance(item, dict) and item.get("_exam_scope") == COMPREHENSIVE_EXAM_LESSON_ID:
            nested = item.get("_questions")
            if isinstance(nested, list):
                return [q for q in nested if isinstance(q, dict)]
            return []
    return [q for q in payload if isinstance(q, dict) and not q.get("_exam_scope")]


def lesson_response_payload(
    *,
    lesson_id: int,
    title: str,
    duration_minutes: int,
    markdown: str,
    llm_used: bool,
    sub_lessons: list[dict] | None = None,
    is_parent_with_sub_lessons: bool = False,
    course_id: int | None = None,
) -> dict:
    lesson_obj: dict = {
        "lesson_id": f"lesson_{lesson_id}",
        "title": title,
        "duration_minutes": duration_minutes,
        "sections": [{"type": "markdown", "content": markdown}],
    }
    if course_id is not None:
        lesson_obj["course_id"] = course_id
    if is_parent_with_sub_lessons:
        lesson_obj["is_parent_with_sub_lessons"] = True
    if sub_lessons:
        lesson_obj["sub_lessons"] = sub_lessons
    return {
        "status": "success",
        "lesson": lesson_obj,
        "generated_in_ms": 0,
        "llm_used": llm_used,
    }


def is_dynamic_lesson_markdown(markdown: str) -> bool:
    md = (markdown or "").strip()
    if not md:
        return False
    has_structure = "## " in md or "### " in md or "```" in md
    return has_structure and len(md) >= 220
