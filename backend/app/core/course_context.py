from __future__ import annotations

from dataclasses import dataclass, field

from app.core.config import get_settings
from app.core.placement_rubric import (
    PLACEMENT_CONCEPTS_BY_LEVEL,
    SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    SYLLABUS_TOPIC_ORDER_BY_LEVEL,
    chapter_scope_for_level,
    concepts_for_level,
    normalize_level,
)


@dataclass(frozen=True)
class CourseContext:
    """Subject/course metadata that lets agents adapt beyond the default Python track."""

    track: str = "python"
    course_title: str = "Python Foundations"
    subject: str = "Python programming"
    source_resource: str = ""
    source_scope: str = ""
    level_labels: dict[str, str] = field(default_factory=dict)
    placement_concepts_by_level: dict[str, tuple[str, ...]] = field(default_factory=dict)
    syllabus_topics_by_level: dict[str, tuple[str, ...]] = field(default_factory=dict)
    syllabus_rubric_by_level: dict[str, tuple[str, ...]] = field(default_factory=dict)
    forbidden_topics: tuple[str, ...] = ()
    is_python_default: bool = False

    def concepts_for_level(self, level: str) -> list[str]:
        lvl = normalize_level(level)
        concepts = self.placement_concepts_by_level.get(lvl)
        if concepts:
            return list(concepts)
        return _generic_concepts_for_level(self.course_title, lvl)

    def syllabus_topics_for_level(self, level: str) -> list[str]:
        lvl = normalize_level(level)
        topics = self.syllabus_topics_by_level.get(lvl)
        if topics:
            return list(topics)
        return self.concepts_for_level(lvl)

    def syllabus_rubric_for_level(self, level: str) -> list[str]:
        lvl = normalize_level(level)
        rubric = self.syllabus_rubric_by_level.get(lvl)
        if rubric:
            return list(rubric)
        return self.concepts_for_level(lvl)

    def scope_for_level(self, level: str) -> str:
        if self.is_python_default:
            return chapter_scope_for_level(level)
        lvl = normalize_level(level).replace("_", " ")
        return (
            f"{self.course_title} ({self.subject}) at {lvl} level. "
            "Use only the selected course materials, uploaded resources, and objectives supplied in the prompt."
        )

    def source_label(self) -> str:
        if self.source_resource and self.source_scope:
            return f"{self.source_resource}; {self.source_scope}"
        return self.source_resource or self.source_scope or self.course_title

    def prompt_block(self, level: str | None = None) -> str:
        parts = [
            f"Course title: {self.course_title}",
            f"Subject / track: {self.subject} ({self.track})",
            f"Source grounding: {self.source_label()}",
        ]
        if level:
            parts.append(f"Target level: {normalize_level(level).replace('_', ' ')}")
            parts.append(f"Allowed scope: {self.scope_for_level(level)}")
            concepts = self.concepts_for_level(level)
            if concepts:
                parts.append("Placement / diagnostic concepts:\n" + "\n".join(f"- {c}" for c in concepts))
            topics = self.syllabus_topics_for_level(level)
            if topics:
                parts.append("Syllabus topics:\n" + "\n".join(f"- {t}" for t in topics))
        if self.forbidden_topics:
            parts.append("Forbidden / out-of-scope topics:\n" + "\n".join(f"- {t}" for t in self.forbidden_topics))
        return "\n".join(parts)


def _generic_concepts_for_level(course_title: str, level: str) -> list[str]:
    base = course_title.strip() or "the selected course"
    lvl = normalize_level(level)
    if lvl == "beginner":
        return (
            f"{base}: core vocabulary and definitions",
            f"{base}: foundational concepts",
            f"{base}: basic procedures or problem types",
            f"{base}: interpreting examples and representations",
            f"{base}: common errors and misconceptions",
        )
    if lvl == "intermediate":
        return (
            f"{base}: applying core ideas",
            f"{base}: multi-step reasoning",
            f"{base}: comparing methods or representations",
            f"{base}: analyzing examples",
            f"{base}: troubleshooting common mistakes",
        )
    if lvl == "advanced":
        return (
            f"{base}: advanced concepts",
            f"{base}: integration across topics",
            f"{base}: edge cases and exceptions",
            f"{base}: evaluating approaches",
            f"{base}: real-world application",
        )
    return (
        f"{base}: expert synthesis",
        f"{base}: design and strategy",
        f"{base}: complex problem solving",
        f"{base}: critique and optimization",
        f"{base}: independent transfer",
    )


def course_context_for_track(track: str | None = None, course_title: str | None = None) -> CourseContext:
    settings = get_settings()
    raw_track = (track or "python").strip() or "python"
    normalized = raw_track.lower().replace(" ", "_")
    title = (course_title or "").strip()

    if normalized in {"python", "py", "python_foundations", "py4e"}:
        return CourseContext(
            track="python",
            course_title=title or "Python Foundations",
            subject="Python programming",
            source_resource=settings.source_resource,
            source_scope=settings.source_scope,
            placement_concepts_by_level={k: tuple(v) for k, v in PLACEMENT_CONCEPTS_BY_LEVEL.items()},
            syllabus_topics_by_level={k: tuple(v) for k, v in SYLLABUS_TOPIC_ORDER_BY_LEVEL.items()},
            syllabus_rubric_by_level={k: tuple(v) for k, v in SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.items()},
            forbidden_topics=("content outside the PY4E level scope",),
            is_python_default=True,
        )

    display = title or raw_track.replace("_", " ").title()
    return CourseContext(
        track=normalized,
        course_title=display,
        subject=display,
        source_resource=f"Selected course materials for {display}",
        source_scope="Uploaded resources, generated syllabus, and student-selected course context.",
        placement_concepts_by_level={lvl: tuple(_generic_concepts_for_level(display, lvl)) for lvl in (
            "beginner",
            "intermediate",
            "advanced",
            "very_advanced",
        )},
        syllabus_topics_by_level={lvl: tuple(_generic_concepts_for_level(display, lvl)) for lvl in (
            "beginner",
            "intermediate",
            "advanced",
            "very_advanced",
        )},
        syllabus_rubric_by_level={lvl: tuple(_generic_concepts_for_level(display, lvl)) for lvl in (
            "beginner",
            "intermediate",
            "advanced",
            "very_advanced",
        )},
    )


def default_python_context() -> CourseContext:
    return course_context_for_track("python")


def legacy_concepts_for_level(level: str) -> list[str]:
    """Kept for callers that still need the old Python-only concept list."""
    return list(concepts_for_level(normalize_level(level)))
