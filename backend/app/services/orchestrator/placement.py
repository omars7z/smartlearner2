import json

from sqlalchemy.orm.attributes import flag_modified

from app.core.placement_rubric import LEVEL_LABELS, LEVEL_ORDER, QUESTIONS_PER_LEVEL


def placement_answer_matches(selected, correct) -> bool:
    if selected is None or correct is None:
        return False
    a, b = str(selected).strip(), str(correct).strip()
    if a == b:
        return True
    try:
        return float(a) == float(b)
    except ValueError:
        return False


def set_placement_questions_json(placement, data: dict) -> None:
    placement.questions_json = json.loads(json.dumps(data))
    flag_modified(placement, "questions_json")


def score_to_level(pct: int) -> str:
    if pct < 40:
        return "beginner"
    if pct < 75:
        return "intermediate"
    return "advanced"


def format_placement_question(
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
