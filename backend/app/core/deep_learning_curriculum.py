from __future__ import annotations

from functools import lru_cache
from typing import Any

# Primary RAG corpus: AI342 lecture slides (Dr. Rasha Obeidat, JUST).
DL_SOURCE_RESOURCE = "AI342 Deep Learning lecture materials (Dr. Rasha Obeidat, JUST)"
DL_SOURCE_SCOPE = (
    "Course slides: Introduction, Logistic Regression & Gradient Descent, "
    "Feed-Forward Networks, CNNs, Sequence Models (RNN/LSTM/GRU), Evaluation Metrics"
)

_TRACKS: tuple[dict[str, Any], ...] = (
    {
        "id": "beginner",
        "label_en": "Beginner",
        "chapter_keys": ("dl_01_intro", "dl_02_logistic_gd"),
    },
    {
        "id": "intermediate",
        "label_en": "Intermediate",
        "chapter_keys": ("dl_03_ffnn",),
    },
    {
        "id": "advanced",
        "label_en": "Advanced",
        "chapter_keys": ("dl_04_cnn", "dl_05_sequence"),
    },
    {
        "id": "very_advanced",
        "label_en": "Very Advanced",
        "chapter_keys": ("dl_06_metrics",),
    },
)

_CHAPTERS: dict[str, dict[str, Any]] = {
    "dl_01_intro": {
        "number": 1,
        "title": "Introduction to Deep Learning",
        "difficulty": "beginner",
        "topics": ["ml_dl_overview", "supervised_learning"],
    },
    "dl_02_logistic_gd": {
        "number": 2,
        "title": "Logistic Regression and Gradient Descent",
        "difficulty": "beginner",
        "topics": ["logistic_regression", "gradient_descent"],
    },
    "dl_03_ffnn": {
        "number": 3,
        "title": "Feed-Forward Neural Networks",
        "difficulty": "intermediate",
        "topics": ["mlp", "activations", "forward_pass"],
    },
    "dl_04_cnn": {
        "number": 4,
        "title": "Convolutional Neural Networks",
        "difficulty": "advanced",
        "topics": ["conv", "cnn", "vision"],
    },
    "dl_05_sequence": {
        "number": 5,
        "title": "Sequence Modeling (RNN, LSTM, GRU)",
        "difficulty": "advanced",
        "topics": ["rnn", "lstm", "gru"],
    },
    "dl_06_metrics": {
        "number": 6,
        "title": "Evaluation Metrics",
        "difficulty": "very_advanced",
        "topics": ["classification_metrics", "regression_metrics"],
    },
}

_SUB_LESSONS: dict[str, list[dict[str, str]]] = {
    k: [{"id": f"{i + 1}.1", "title": t} for i, t in enumerate(
        ["Core concepts", "Worked examples", "Common failure modes", "Hands-on practice"]
    )]
    for k in _CHAPTERS
}

# Chapter number → title (syllabus / local fallback builder).
DL_CHAPTER_TITLES: dict[int, str] = {
    meta["number"]: meta["title"] for meta in _CHAPTERS.values()
}

DL_CHAPTERS_BY_LEVEL: dict[str, tuple[int, ...]] = {
    "beginner": (1, 2),
    "intermediate": (3,),
    "advanced": (4, 5),
    "very_advanced": (6,),
}


def allowed_chapter_numbers_by_level() -> dict[str, frozenset[int]]:
    return {lvl: frozenset(nums) for lvl, nums in DL_CHAPTERS_BY_LEVEL.items()}


def allowed_chapters_for_level(level: str) -> dict[int, str]:
    """Chapter number → title for syllabus validator / generator hints."""
    lvl = (level or "beginner").strip().lower().replace(" ", "_").replace("-", "_")
    if lvl == "veryadvanced":
        lvl = "very_advanced"
    nums = DL_CHAPTERS_BY_LEVEL.get(lvl, DL_CHAPTERS_BY_LEVEL["beginner"])
    return {n: DL_CHAPTER_TITLES[n] for n in nums}


def book_chunker_chapter_config() -> dict[str, dict[str, Any]]:
    """Metadata for pdf_chunker BOOK_CONFIG deep_learning_lectures."""
    return {
        key: {
            "title": meta["title"],
            "difficulty": meta["difficulty"],
            "topics": list(meta["topics"]),
        }
        for key, meta in _CHAPTERS.items()
    }


def sub_lessons_for_chapter(chapter_key: str) -> list[dict[str, str]]:
    return list(_SUB_LESSONS.get(chapter_key, []))


@lru_cache
def curriculum_payload() -> dict[str, Any]:
    chapters = {
        key: {
            "key": key,
            "track_id": next((t["id"] for t in _TRACKS if key in t["chapter_keys"]), "beginner"),
            **meta,
            "sub_lessons": _SUB_LESSONS.get(key, []),
        }
        for key, meta in _CHAPTERS.items()
    }
    return {
        "source": DL_SOURCE_RESOURCE,
        "tracks": [dict(t) for t in _TRACKS],
        "chapters": chapters,
    }
