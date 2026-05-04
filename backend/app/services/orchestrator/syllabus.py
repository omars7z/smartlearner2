import re

from app.core.placement_rubric import normalize_level, normalize_track
from app.services.agents.syllabus_common import (
    syllabus_allowed_topics_ordered,
    syllabus_rubric_concepts_for_level,
)


def topic_slug(topic: str) -> str:
    s = (topic or "").lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_") or "topic"


def _prioritized_concepts(
    concepts: list[str],
    weak_topics: list[str] | None = None,
    strong_topics: list[str] | None = None,
) -> list[str]:
    weak = [str(x).strip() for x in (weak_topics or []) if str(x).strip()]
    strong = [str(x).strip() for x in (strong_topics or []) if str(x).strip()]
    base = [c for c in concepts if c]
    if not base:
        return []
    out: list[str] = []
    used: set[str] = set()
    for c in weak + base:
        if c in base and c not in used:
            out.append(c)
            used.add(c)
    # Keep strong concepts later to focus more on weak areas first.
    for c in strong:
        if c in base and c in out:
            out.remove(c)
            out.append(c)
    return out or base


def build_local_syllabus_payload(
    level: str,
    track: str = "python",
    weak_topics: list[str] | None = None,
    strong_topics: list[str] | None = None,
) -> dict:
    lvl = normalize_level(level)
    norm_track = (track or "python").strip().lower().replace("-", "_")
    topics = syllabus_allowed_topics_ordered(lvl, track=norm_track)
    concepts = syllabus_rubric_concepts_for_level(lvl, track=norm_track)
    concept_by_topic = {topics[i]: concepts[i] for i in range(min(len(topics), len(concepts)))}
    concept_priority = _prioritized_concepts(concepts, weak_topics=weak_topics, strong_topics=strong_topics)

    if normalize_track(norm_track) in {"deep_learning", "dl"}:
        chapter_map = {
            "beginner": [1, 2, 3, 4],
            "intermediate": [5, 6, 7, 8],
            "advanced": [9, 10, 11, 12],
            "very_advanced": [13, 14, 15, 16],
        }
        chapter_titles = {
            1: "Math Foundations",
            2: "Python for Deep Learning",
            3: "Data Pipelines and Splits",
            4: "Linear and Logistic Models",
            5: "Neural Network Fundamentals",
            6: "Backpropagation",
            7: "Optimization",
            8: "Generalization and Regularization",
            9: "Convolutional Networks",
            10: "Sequence Models",
            11: "Transformers",
            12: "Training Systems",
            13: "Generative Modeling",
            14: "Reinforcement Learning",
            15: "Scaling Laws and LLM Training",
            16: "MLOps for Deep Learning",
        }
    else:
        chapter_map = {
            "beginner": [1, 2, 3, 6],
            "intermediate": [4, 5, 7, 8, 9, 10],
            "advanced": [11, 12, 13, 14],
            "very_advanced": [15, 16],
        }
        chapter_titles = {
            1: "Why we program",
            2: "Variables, Expressions and Statements",
            3: "Conditional execution",
            4: "Functions",
            5: "Iteration",
            6: "Strings",
            7: "Files",
            8: "Lists",
            9: "Dictionaries",
            10: "Tuples",
            11: "Regular Expressions",
            12: "Networked Programs",
            13: "Web Services",
            14: "Object-Oriented Programming",
            15: "Databases and SQL",
            16: "Visualizing Data",
        }
    allowed_chapters = chapter_map.get(lvl, chapter_map["beginner"])
    chunk = max(1, (len(topics) + len(allowed_chapters) - 1) // len(allowed_chapters))

    units: list[dict] = []
    idx = 0
    for ch in allowed_chapters:
        part = topics[idx : idx + chunk]
        idx += chunk
        if not part:
            break
        lessons: list[dict] = []
        for local_idx, t in enumerate(part):
            mapped = concept_by_topic.get(t)
            if mapped:
                rubric_concept = mapped
            elif concept_priority:
                rubric_concept = concept_priority[(idx + local_idx) % len(concept_priority)]
            else:
                rubric_concept = t
            lessons.append(
                {
                    "topic": t,
                    "lesson_title": f"{t}",
                    "description": (
                        (
                            f"Learn {t} through practical deep learning examples and experiments. "
                            "Practice model reasoning, diagnostics, and training trade-offs."
                            if normalize_track(norm_track) in {"deep_learning", "dl"}
                            else f"Learn {t} through practical Python exercises and small examples. "
                            "Practice predictable coding patterns and explain your reasoning clearly."
                        )
                    ),
                    "learning_objectives": [
                        f"Identify key ideas behind {t}.",
                        (
                            f"Implement a concise deep learning example for {t}."
                            if normalize_track(norm_track) in {"deep_learning", "dl"}
                            else f"Write a short Python example using {t}."
                        ),
                        (
                            f"Diagnose common modeling mistakes related to {t}."
                            if normalize_track(norm_track) in {"deep_learning", "dl"}
                            else f"Debug common mistakes related to {t}."
                        ),
                    ],
                    "rubric_concept": rubric_concept,
                    "chapter_ref": ch,
                }
            )
        units.append(
            {
                "chapter": ch,
                "title": chapter_titles.get(ch, f"Chapter {ch}"),
                "summary": f"Core learning outcomes for {chapter_titles.get(ch, f'Chapter {ch}')}.",
                "lessons": lessons,
            }
        )
    return {"units": units}
