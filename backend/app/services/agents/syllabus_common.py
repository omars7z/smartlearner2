"""Shared syllabus topic ordering and chapter hints for generator and validator."""

from app.core.deep_learning_curriculum import DL_CHAPTERS_BY_LEVEL, DL_CHAPTER_TITLES
from app.core.placement_rubric import (
    DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL,
    DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL,
    DEEP_LEARNING_SYLLABUS_TOPIC_ORDER_BY_LEVEL,
    PLACEMENT_CONCEPTS_BY_LEVEL,
    SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL,
    SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL,
    SYLLABUS_TOPIC_ORDER_BY_LEVEL,
    normalize_level,
    normalize_track,
)


def syllabus_allowed_topics_ordered(level: str, track: str = "python") -> list[str]:
    """Topics in syllabus order, not alphabetical."""
    lvl = normalize_level(level)
    if normalize_track(track) in {"deep_learning", "dl"}:
        allow = DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(lvl, frozenset())
        order = DEEP_LEARNING_SYLLABUS_TOPIC_ORDER_BY_LEVEL.get(lvl)
    else:
        allow = SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(lvl, frozenset())
        order = SYLLABUS_TOPIC_ORDER_BY_LEVEL.get(lvl)
    if order:
        out: list[str] = [t for t in order if t in allow]
        for t in allow:
            if t not in out:
                out.append(t)
        return out
    return sorted(allow)


def lesson_title_from_topic(topic: str, *, track: str = "python") -> str:
    """Human-readable title that must differ from the exact topic string (validator rule)."""
    t = (topic or "").strip()
    if not t:
        return "Lesson overview"
    if normalize_track(track) in {"deep_learning", "dl"}:
        return f"Applied practice: {t}"
    return f"Hands-on: {t}"


def syllabus_rubric_concepts_for_level(level: str, track: str = "python") -> list[str]:
    lvl = normalize_level(level)
    if normalize_track(track) in {"deep_learning", "dl"}:
        return list(
            DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(
                lvl, DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ())
            )
        )
    return list(SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL.get(lvl, PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, ())))


def chapter_structure_hint(level: str, track: str = "python") -> str:
    """Track chapter breakdown injected into syllabus prompt."""
    norm_track = (track or "python").strip().lower().replace("-", "_")
    if norm_track in {"deep_learning", "dl"}:
        lvl = normalize_level(level)
        lines = [
            f"Ch {n} – {DL_CHAPTER_TITLES[n]}"
            for n in DL_CHAPTERS_BY_LEVEL.get(lvl, DL_CHAPTERS_BY_LEVEL["beginner"])
        ]
        return "\n".join(lines)

    hints = {
        "beginner": (
            "Ch 1 – Why we program: What is programming, Hardware architecture, "
            "Python as a language, Writing your first program\n"
            "Ch 2 – Variables, expressions, statements: Values and types, "
            "Variables and assignment, Expressions and operators, "
            "Statements and order of execution, User input\n"
            "Ch 3 – Conditional execution: Boolean expressions, Logical operators, "
            "if/elif/else, Nested conditionals, try/except basics\n"
            "Ch 6 – Strings: String operations, String slicing, "
            "String methods, Searching in strings, String formatting"
        ),
        "intermediate": (
            "Ch 4 – Functions: Defining functions, Parameters and arguments, "
            "Return values, Local vs global scope, Fruitful functions\n"
            "Ch 5 – Iteration: while loop, for loop, "
            "Loop patterns (counting/summing/min/max), break and continue, "
            "Infinite loops and guards\n"
            "Ch 7 – Files: Opening and reading files, Writing to files, "
            "File paths, Looping over file lines, try/except with files\n"
            "Ch 8 – Lists: List operations, List methods, List slicing, "
            "Lists and loops, List algorithms\n"
            "Ch 9 – Dictionaries: Dictionary basics, Looping over dictionaries, "
            "Dictionary patterns (counting/grouping), get() and default values\n"
            "Ch 10 – Tuples: Tuple basics, Tuples vs lists, "
            "Sorting with tuples, DSU pattern, Tuples in loops"
        ),
        "advanced": (
            "Ch 11 – Regular Expressions: re module basics, search() and findall(), "
            "Character classes and quantifiers, Greedy vs non-greedy, "
            "Practical regex patterns\n"
            "Ch 12 – Networked Programs: HTTP basics, urllib and urlopen, "
            "Parsing HTML, Web scraping patterns, Error handling in networking\n"
            "Ch 13 – Web Services: JSON basics, Parsing JSON, "
            "REST APIs and requests, XML basics, Service-Oriented Architecture\n"
            "Ch 14 – OOP: Classes and objects, __init__ and self, "
            "Methods, Inheritance, OOP design patterns"
        ),
        "very_advanced": (
            "Ch 15 – Databases & SQL: SQLite basics, CREATE/INSERT/SELECT, "
            "Filtering and sorting, Joins and relationships, "
            "Python + SQLite integration\n"
            "Ch 16 – Visualizing Data: Data visualization concepts, "
            "OpenStreetMap data, Network graphs, "
            "Mail data analysis, End-to-end data pipeline"
        ),
    }
    return hints.get(normalize_level(level), hints["beginner"])
