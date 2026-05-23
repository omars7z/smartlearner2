"""Shared exam API identifiers."""

from __future__ import annotations

from typing import Literal

COMPREHENSIVE_EXAM_LESSON_ID = "track_comprehensive"


def parse_lesson_id(lesson_id: str) -> int:
    return int(lesson_id.replace("lesson_", "")) if lesson_id.startswith("lesson_") else int(lesson_id)


def parse_exam_lesson_ref(lesson_id: str) -> tuple[Literal["lesson", "comprehensive"], int | None]:
    raw = (lesson_id or "").strip().lower()
    if raw in {COMPREHENSIVE_EXAM_LESSON_ID, "comprehensive", "track-final", "track_final"}:
        return "comprehensive", None
    return "lesson", parse_lesson_id(lesson_id)
