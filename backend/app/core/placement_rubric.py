"""
Placement levels and rubric aligned with Python for Everybody (PY4E) scope.
Used to constrain MCQ concepts and validate syllabus topics.
"""

from __future__ import annotations

# Progressive order: each stage is 5 questions; pass >= 4/5 to continue.
LEVEL_ORDER: tuple[str, ...] = ("beginner", "intermediate", "advanced", "very_advanced")

LEVEL_LABELS: dict[str, str] = {
    "beginner": "Beginner",
    "intermediate": "Intermediate",
    "advanced": "Advanced",
    "very_advanced": "Very advanced",
}

QUESTIONS_PER_LEVEL = 5
PASS_THRESHOLD = 4  # need at least this many correct to advance

# Score stored on PlacementTest.score for syllabus compatibility (discrete bands).
LEVEL_TO_SCORE_PCT: dict[str, int] = {
    "beginner": 25,
    "intermediate": 50,
    "advanced": 75,
    "very_advanced": 100,
}

# Exactly one concept per question slot (index 0..4) maps to PY4E-style objectives.
PLACEMENT_CONCEPTS_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "beginner": (
        "Variables, values, and types",
        "Expressions and operators",
        "Conditionals",
        "Strings and basic I/O",
        "Programs, semantics, and errors",
    ),
    "intermediate": (
        "Functions and reuse",
        "Iteration and loops",
        "String operations and methods",
        "Files and persistence",
        "Lists and mutability",
    ),
    "advanced": (
        "Dictionaries and data shapes",
        "Tuples and immutability",
        "Regular expressions",
        "Networked programs and protocols",
        "Clients, services, and data exchange",
    ),
    "very_advanced": (
        "Web services, APIs, and service data",
        "Objects, classes, and OOP",
        "Databases and SQL with Python",
        "Data visualization",
        "Design, testing, and integration",
    ),
}

# Syllabus topics must draw from these labels for the given placement level (validator).
SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL: dict[str, frozenset[str]] = {
    "beginner": frozenset(
        {
            "Expressions",
            "Variable Assignment",
            "Conditionals",
            "Strings",
            "Debugging and Reading Code",
        }
    ),
    "intermediate": frozenset(
        {
            "Functions",
            "Loops",
            "String Methods",
            "Files",
            "Lists",
        }
    ),
    "advanced": frozenset(
        {
            "Dictionaries",
            "Tuples",
            "Regular Expressions",
            "Networking",
            "Data Parsing",
        }
    ),
    "very_advanced": frozenset(
        {
            "Web APIs",
            "Object-Oriented Python",
            "Databases",
            "Visualization",
            "Architecture and Best Practices",
        }
    ),
}


def concepts_for_level(level: str) -> tuple[str, ...]:
    return PLACEMENT_CONCEPTS_BY_LEVEL.get(level.lower(), PLACEMENT_CONCEPTS_BY_LEVEL["beginner"])


def normalize_level(level: str) -> str:
    k = (level or "beginner").lower().replace(" ", "_").replace("-", "_")
    if k == "veryadvanced":
        return "very_advanced"
    if k in LEVEL_ORDER:
        return k
    return "beginner"


def validate_question_concepts_for_level(questions: list[dict], level: str) -> None:
    """Ensure each question concept is in the rubric list for this level."""
    allowed = set(concepts_for_level(level))
    for i, q in enumerate(questions):
        c = str(q.get("concept") or "").strip()
        if c not in allowed:
            raise ValueError(
                f"Question {i + 1}: concept must be one of the rubric entries for {level!r}; got {c!r}."
            )


def validate_syllabus_topics_for_level(lessons: list[dict], level: str) -> None:
    """Ensure each lesson topic appears in the allowlist for the placement level."""
    norm = normalize_level(level)
    allowed = SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(norm)
    if not allowed:
        return
    for i, lesson in enumerate(lessons):
        topic = str(lesson.get("topic") or "").strip()
        if topic and topic not in allowed:
            raise ValueError(
                f"Lesson {i + 1}: topic {topic!r} is not in the syllabus rubric for level {norm!r}."
            )
