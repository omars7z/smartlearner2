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
            # Ch 1
            "What is Programming",
            "Hardware Architecture",
            "Python as a Language",
            "Writing Your First Program",
            # Ch 2
            "Values and Types",
            "Variable Assignment",
            "Expressions",
            "Statements and Execution Order",
            "User Input",
            # Ch 3
            "Boolean Expressions",
            "Logical Operators",
            "if elif else",
            "Nested Conditionals",
            "try except Basics",
            # Ch 6
            "String Operations",
            "String Slicing",
            "String Methods",
            "Searching in Strings",
            "String Formatting",
        }
    ),
    "intermediate": frozenset(
        {
            # Ch 4
            "Defining Functions",
            "Parameters and Arguments",
            "Return Values",
            "Local and Global Scope",
            "Fruitful Functions",
            # Ch 5
            "while Loop",
            "for Loop",
            "Loop Patterns",
            "break and continue",
            "Infinite Loops and Guards",
            # Ch 7
            "Opening and Reading Files",
            "Writing to Files",
            "File Paths",
            "Looping Over File Lines",
            "try except with Files",
            # Ch 8
            "List Operations",
            "List Methods",
            "List Slicing",
            "Lists and Loops",
            "List Algorithms",
            # Ch 9
            "Dictionary Basics",
            "Looping Over Dictionaries",
            "Dictionary Patterns",
            "get() and Default Values",
            # Ch 10
            "Tuple Basics",
            "Tuples vs Lists",
            "Sorting with Tuples",
            "DSU Pattern",
            "Tuples in Loops",
        }
    ),
    "advanced": frozenset(
        {
            # Ch 11
            "re Module Basics",
            "search() and findall()",
            "Character Classes and Quantifiers",
            "Greedy vs Non-Greedy",
            "Practical Regex Patterns",
            # Ch 12
            "HTTP Basics",
            "urllib and urlopen",
            "Parsing HTML",
            "Web Scraping Patterns",
            "Error Handling in Networking",
            # Ch 13
            "JSON Basics",
            "Parsing JSON",
            "REST APIs and Requests",
            "XML Basics",
            "Service-Oriented Architecture",
            # Ch 14
            "Classes and Objects",
            "init and self",
            "Methods",
            "Inheritance",
            "OOP Design Patterns",
        }
    ),
    "very_advanced": frozenset(
        {
            # Ch 15
            "SQLite Basics",
            "CREATE INSERT SELECT",
            "Filtering and Sorting",
            "Joins and Relationships",
            "Python SQLite Integration",
            # Ch 16
            "Data Visualization Concepts",
            "OpenStreetMap Data",
            "Network Graphs",
            "Mail Data Analysis",
            "End-to-End Data Pipeline",
        }
    ),
}

# Canonical lesson order in the syllabus UI (must match SYLLABUS_TOPIC_ALLOWLIST for that level).
SYLLABUS_TOPIC_ORDER_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "beginner": (
        "What is Programming",
        "Hardware Architecture",
        "Python as a Language",
        "Writing Your First Program",
        "Values and Types",
        "Expressions",
        "Variable Assignment",
        "Statements and Execution Order",
        "User Input",
        "Boolean Expressions",
        "Logical Operators",
        "if elif else",
        "Nested Conditionals",
        "try except Basics",
        "String Operations",
        "String Slicing",
        "String Methods",
        "Searching in Strings",
        "String Formatting",
    ),
    "intermediate": (
        "Defining Functions",
        "Parameters and Arguments",
        "Return Values",
        "Local and Global Scope",
        "Fruitful Functions",
        "while Loop",
        "for Loop",
        "Loop Patterns",
        "break and continue",
        "Infinite Loops and Guards",
        "Opening and Reading Files",
        "Writing to Files",
        "File Paths",
        "Looping Over File Lines",
        "try except with Files",
        "List Operations",
        "List Methods",
        "List Slicing",
        "Lists and Loops",
        "List Algorithms",
        "Dictionary Basics",
        "Looping Over Dictionaries",
        "Dictionary Patterns",
        "get() and Default Values",
        "Tuple Basics",
        "Tuples vs Lists",
        "Sorting with Tuples",
        "DSU Pattern",
        "Tuples in Loops",
    ),
    "advanced": (
        "re Module Basics",
        "search() and findall()",
        "Character Classes and Quantifiers",
        "Greedy vs Non-Greedy",
        "Practical Regex Patterns",
        "HTTP Basics",
        "urllib and urlopen",
        "Parsing HTML",
        "Web Scraping Patterns",
        "Error Handling in Networking",
        "JSON Basics",
        "Parsing JSON",
        "REST APIs and Requests",
        "XML Basics",
        "Service-Oriented Architecture",
        "Classes and Objects",
        "init and self",
        "Methods",
        "Inheritance",
        "OOP Design Patterns",
    ),
    "very_advanced": (
        "SQLite Basics",
        "CREATE INSERT SELECT",
        "Filtering and Sorting",
        "Joins and Relationships",
        "Python SQLite Integration",
        "Data Visualization Concepts",
        "OpenStreetMap Data",
        "Network Graphs",
        "Mail Data Analysis",
        "End-to-End Data Pipeline",
    ),
}

# Syllabus sub-lesson rubric_concept strings (may differ from placement MCQ rubric; can include Ch tags).
# Maps each concept to how many times it appears across lessons for that level (eliminates repetition).
_SYLLABUS_RUBRIC_CONCEPT_COUNTS_BY_LEVEL: dict[str, dict[str, int]] = {
    "beginner": {
        "Programs, semantics, and errors": 5,
        "Variables, values, and types": 2,
        "Expressions and operators": 2,
        "Strings and basic I/O": 6,
        "Conditionals": 4,
    },
    "intermediate": {
        "Functions (Ch 4): definitions, calls, parameters, return values": 5,
        "Iteration and loops (Ch 5): for, while, definite and indefinite iteration": 5,
        "Files and persistence (Ch 7): reading, writing, file objects": 5,
        "Lists and mutability (Ch 8): indexing, methods, aliasing": 5,
        "Dictionaries and mappings (Ch 9): keys, values, dict operations": 4,
        "Tuples and immutability (Ch 10): tuples, packing, unpacking": 5,
    },
    "advanced": {
        "Regular expressions": 5,
        "Networked programs and protocols": 5,
        "Clients, services, and data exchange": 5,
        "Objects, classes, and OOP": 5,
    },
    "very_advanced": {
        "Databases and SQL with Python": 5,
        "Data visualization": 5,
    },
}


def normalize_level(level: str) -> str:
    k = (level or "beginner").lower().replace(" ", "_").replace("-", "_")
    if k == "veryadvanced":
        return "very_advanced"
    if k in LEVEL_ORDER:
        return k
    return "beginner"


# Cached expanded tuples for backward compatibility with existing code.
def _build_syllabus_rubric_concepts() -> dict[str, tuple[str, ...]]:
    """Expand concept counts into flat tuples (one concept per lesson)."""
    result = {}
    for level in LEVEL_ORDER:
        norm = normalize_level(level)
        concept_counts = _SYLLABUS_RUBRIC_CONCEPT_COUNTS_BY_LEVEL.get(norm, {})
        expanded = []
        for concept, count in concept_counts.items():
            expanded.extend([concept] * count)
        result[level] = tuple(expanded)
    return result

SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL: dict[str, tuple[str, ...]] = _build_syllabus_rubric_concepts()

FORBIDDEN_TERMS_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "beginner": (
        "self.",
        "class ",
        "__init__",
        "asyncio",
        "import os",
        "sql",
        "database",
        "api",
        "json.loads",
        "regex",
        "re.compile",
        "urllib",
        "socket",
        ".cursor()",
        "matplotlib",
    ),
    "intermediate": (
        "self.",
        "__init__",
        "asyncio",
        "sql",
        "database",
        ".cursor()",
        "matplotlib",
        "urllib",
        "socket",
    ),
    "advanced": (
        "self.",
        "__init__",
        "asyncio",
        "sql",
        "database",
        ".cursor()",
        "matplotlib",
    ),
    "very_advanced": (),
}


def concepts_for_level(level: str) -> tuple[str, ...]:
    return PLACEMENT_CONCEPTS_BY_LEVEL.get(level.lower(), PLACEMENT_CONCEPTS_BY_LEVEL["beginner"])


def forbidden_terms_for_level(level: str) -> tuple[str, ...]:
    """Return terms that must not appear in question stems for this level."""
    return FORBIDDEN_TERMS_BY_LEVEL.get(normalize_level(level), ())


def chapter_scope_for_level(level: str) -> str:
    """Return a human-readable chapter scope string for prompt injection."""
    scopes = {
        "beginner": "Ch 1-3 and Ch 6 (variables, expressions, conditionals, strings, basic I/O, errors)",
        "intermediate": "Ch 4-5 and Ch 7-10 (functions, loops, files, lists, dictionaries, tuples)",
        "advanced": "Ch 11-13 (regex, networking, web services, data parsing)",
        "very_advanced": "Ch 14-16 (OOP, databases, visualization)",
    }
    return scopes.get(normalize_level(level), scopes["beginner"])


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
