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

TRACK_IDS: tuple[str, ...] = ("python", "deep_learning")

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

DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "beginner": (
        "Introduction to machine and deep learning",
        "Supervised learning and data splits",
        "Logistic regression intuition",
        "Gradient descent and learning rate",
        "Loss functions for classification",
    ),
    "intermediate": (
        "Feed-forward network layers",
        "Activation functions",
        "Forward propagation and shapes",
        "Backpropagation intuition",
        "Training an MLP",
    ),
    "advanced": (
        "Convolutional neural networks",
        "Convolution pooling and feature maps",
        "RNN and sequence modeling",
        "LSTM and GRU gates",
        "Sequence task applications",
    ),
    "very_advanced": (
        "Classification evaluation metrics",
        "Precision recall and F1",
        "Confusion matrix interpretation",
        "Regression metrics (MSE MAE)",
        "Choosing metrics for a task",
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

DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL: dict[str, frozenset[str]] = {
    "beginner": frozenset(
        {
            "What is Machine Learning",
            "Deep Learning vs Traditional ML",
            "Training Validation and Test Sets",
            "Logistic Regression Model",
            "Sigmoid and Probabilities",
            "Binary Cross-Entropy Loss",
            "Gradient Descent Steps",
            "Learning Rate Effects",
        }
    ),
    "intermediate": frozenset(
        {
            "Perceptron and MLP Layers",
            "Activation Functions",
            "Forward Pass and Tensor Shapes",
            "Weight Initialization",
            "Backpropagation Overview",
            "Training Loop Structure",
        }
    ),
    "advanced": frozenset(
        {
            "Convolution Operation",
            "Pooling and Feature Maps",
            "CNN Architectures",
            "RNN Unrolling",
            "LSTM Cell",
            "GRU vs LSTM",
            "Sequence Modeling Tasks",
        }
    ),
    "very_advanced": frozenset(
        {
            "Accuracy and Error Rate",
            "Precision Recall and F1",
            "Confusion Matrix",
            "ROC and AUC",
            "MSE and MAE",
            "Choosing the Right Metric",
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

DEEP_LEARNING_SYLLABUS_TOPIC_ORDER_BY_LEVEL: dict[str, tuple[str, ...]] = {
    "beginner": (
        "What is Machine Learning",
        "Deep Learning vs Traditional ML",
        "Training Validation and Test Sets",
        "Logistic Regression Model",
        "Sigmoid and Probabilities",
        "Binary Cross-Entropy Loss",
        "Gradient Descent Steps",
        "Learning Rate Effects",
    ),
    "intermediate": (
        "Perceptron and MLP Layers",
        "Activation Functions",
        "Forward Pass and Tensor Shapes",
        "Weight Initialization",
        "Backpropagation Overview",
        "Training Loop Structure",
    ),
    "advanced": (
        "Convolution Operation",
        "Pooling and Feature Maps",
        "CNN Architectures",
        "RNN Unrolling",
        "LSTM Cell",
        "GRU vs LSTM",
        "Sequence Modeling Tasks",
    ),
    "very_advanced": (
        "Accuracy and Error Rate",
        "Precision Recall and F1",
        "Confusion Matrix",
        "ROC and AUC",
        "MSE and MAE",
        "Choosing the Right Metric",
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

# Placement MCQ concepts → AI342 syllabus topic strings (see DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL).
_DEEP_LEARNING_PLACEMENT_TO_SYLLABUS_TOPIC_BY_LEVEL: dict[str, dict[str, str]] = {
    "beginner": {
        "Introduction to machine and deep learning": "What is Machine Learning",
        "Supervised learning and data splits": "Training Validation and Test Sets",
        "Logistic regression intuition": "Logistic Regression Model",
        "Gradient descent and learning rate": "Gradient Descent Steps",
        "Loss functions for classification": "Binary Cross-Entropy Loss",
    },
    "intermediate": {
        "Feed-forward network layers": "Perceptron and MLP Layers",
        "Activation functions": "Activation Functions",
        "Forward propagation and shapes": "Forward Pass and Tensor Shapes",
        "Backpropagation intuition": "Backpropagation Overview",
        "Training an MLP": "Training Loop Structure",
    },
    "advanced": {
        "Convolutional neural networks": "Convolution Operation",
        "Convolution pooling and feature maps": "Pooling and Feature Maps",
        "RNN and sequence modeling": "RNN Unrolling",
        "LSTM and GRU gates": "LSTM Cell",
        "Sequence task applications": "Sequence Modeling Tasks",
    },
    "very_advanced": {
        "Classification evaluation metrics": "Accuracy and Error Rate",
        "Precision recall and F1": "Precision Recall and F1",
        "Confusion matrix interpretation": "Confusion Matrix",
        "Regression metrics (MSE MAE)": "MSE and MAE",
        "Choosing metrics for a task": "Choosing the Right Metric",
    },
}

_DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPT_COUNTS_BY_LEVEL: dict[str, dict[str, int]] = {
    "beginner": {
        "Introduction to machine and deep learning": 2,
        "Supervised learning and data splits": 2,
        "Logistic regression intuition": 2,
        "Gradient descent and learning rate": 2,
        "Loss functions for classification": 1,
    },
    "intermediate": {
        "Feed-forward network layers": 2,
        "Activation functions": 1,
        "Forward propagation and shapes": 1,
        "Backpropagation intuition": 1,
        "Training an MLP": 1,
    },
    "advanced": {
        "Convolutional neural networks": 2,
        "Convolution pooling and feature maps": 2,
        "RNN and sequence modeling": 2,
        "LSTM and GRU gates": 1,
    },
    "very_advanced": {
        "Classification evaluation metrics": 2,
        "Precision recall and F1": 2,
        "Confusion matrix interpretation": 1,
        "Choosing metrics for a task": 1,
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


def _build_deep_learning_syllabus_rubric_concepts() -> dict[str, tuple[str, ...]]:
    result = {}
    for level in LEVEL_ORDER:
        norm = normalize_level(level)
        concept_counts = _DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPT_COUNTS_BY_LEVEL.get(norm, {})
        expanded = []
        for concept, count in concept_counts.items():
            expanded.extend([concept] * count)
        result[level] = tuple(expanded)
    return result


DEEP_LEARNING_SYLLABUS_RUBRIC_CONCEPTS_BY_LEVEL: dict[str, tuple[str, ...]] = (
    _build_deep_learning_syllabus_rubric_concepts()
)

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


def normalize_track(track: str | None) -> str:
    """Normalize any selected track id from UI/payload, preserving dynamic track values."""
    t = (track or "").strip().lower().replace("-", "_").replace(" ", "_")
    return t or "python"


def concepts_for_level(level: str, track: str = "python") -> tuple[str, ...]:
    lvl = normalize_level(level)
    if normalize_track(track) in {"deep_learning", "dl"}:
        return DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL.get(
            lvl, DEEP_LEARNING_PLACEMENT_CONCEPTS_BY_LEVEL["beginner"]
        )
    return PLACEMENT_CONCEPTS_BY_LEVEL.get(lvl, PLACEMENT_CONCEPTS_BY_LEVEL["beginner"])


def forbidden_terms_for_level(level: str, track: str = "python") -> tuple[str, ...]:
    """Return terms that must not appear in question stems for this level."""
    if normalize_track(track) in {"deep_learning", "dl"}:
        return ()
    return FORBIDDEN_TERMS_BY_LEVEL.get(normalize_level(level), ())


def chapter_scope_for_level(level: str, track: str = "python") -> str:
    """Return a human-readable chapter scope string for prompt injection."""
    if normalize_track(track) in {"deep_learning", "dl"}:
        scopes = {
            "beginner": "AI342 Ch 1–2: Introduction; logistic regression and gradient descent",
            "intermediate": "AI342 Ch 3: Feed-forward neural networks",
            "advanced": "AI342 Ch 4–5: CNNs; sequence models (RNN/LSTM/GRU)",
            "very_advanced": "AI342 Ch 6: Evaluation metrics",
        }
        return scopes.get(normalize_level(level), scopes["beginner"])
    scopes = {
        "beginner": "Ch 1-3 and Ch 6 (variables, expressions, conditionals, strings, basic I/O, errors)",
        "intermediate": "Ch 4-5 and Ch 7-10 (functions, loops, files, lists, dictionaries, tuples)",
        "advanced": "Ch 11-13 (regex, networking, web services, data parsing)",
        "very_advanced": "Ch 14-16 (OOP, databases, visualization)",
    }
    return scopes.get(normalize_level(level), scopes["beginner"])


def validate_question_concepts_for_level(questions: list[dict], level: str, track: str = "python") -> None:
    """Ensure each question concept is in the rubric list for this level."""
    allowed = set(concepts_for_level(level, track=track))
    for i, q in enumerate(questions):
        c = str(q.get("concept") or "").strip()
        if c not in allowed:
            raise ValueError(
                f"Question {i + 1}: concept must be one of the rubric entries for {level!r}; got {c!r}."
            )


def normalize_syllabus_topic(topic: str, level: str, track: str = "python") -> str:
    """
    Map placement/rubric concept strings to canonical syllabus topic labels.
    LLMs sometimes copy placement concepts into the topic field; this aligns them with AI342/PY4E allowlists.
    """
    raw = (topic or "").strip()
    if not raw:
        return raw
    norm = normalize_level(level)
    tr = normalize_track(track)
    if tr in {"deep_learning", "dl"}:
        allowed = DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(norm, frozenset())
        mapping = _DEEP_LEARNING_PLACEMENT_TO_SYLLABUS_TOPIC_BY_LEVEL.get(norm, {})
    else:
        allowed = SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(norm, frozenset())
        mapping = {}
    if raw in allowed:
        return raw
    mapped = mapping.get(raw)
    if mapped:
        return mapped
    low = raw.lower()
    for candidate in allowed:
        if candidate.lower() == low:
            return candidate
    for placement_label, syllabus_label in mapping.items():
        if placement_label.lower() == low:
            return syllabus_label
    return raw


def map_placement_concepts_for_syllabus(
    concepts: list[str] | None,
    level: str,
    track: str = "python",
) -> list[str]:
    """Turn placement weak/strong concept labels into syllabus topic strings for prompts."""
    out: list[str] = []
    seen: set[str] = set()
    for item in concepts or []:
        mapped = normalize_syllabus_topic(str(item).strip(), level, track=track)
        if mapped and mapped not in seen:
            out.append(mapped)
            seen.add(mapped)
    return out


def validate_syllabus_topics_for_level(lessons: list[dict], level: str, track: str = "python") -> None:
    """Ensure each lesson topic appears in the allowlist for the placement level."""
    norm = normalize_level(level)
    if normalize_track(track) in {"deep_learning", "dl"}:
        allowed = DEEP_LEARNING_SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(norm)
    else:
        allowed = SYLLABUS_TOPIC_ALLOWLIST_BY_LEVEL.get(norm)
    if not allowed:
        return
    for i, lesson in enumerate(lessons):
        topic = normalize_syllabus_topic(str(lesson.get("topic") or "").strip(), norm, track=track)
        if topic:
            lesson["topic"] = topic
        if topic and topic not in allowed:
            raise ValueError(
                f"Lesson {i + 1}: topic {topic!r} is not in the syllabus rubric for level {norm!r}."
            )
