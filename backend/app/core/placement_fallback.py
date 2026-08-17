"""Varied placement MCQ fallbacks when the LLM path is unavailable."""

from __future__ import annotations

import random

from app.core.placement_rubric import concepts_for_level, normalize_level, normalize_track

_STEM_TEMPLATES_DL = (
    "In deep learning, which statement best describes {concept}?",
    "Which option correctly explains {concept}?",
    "A student is studying AI342 material on {concept}. Which answer is most accurate?",
    "For {concept}, which choice reflects correct understanding?",
)

_STEM_TEMPLATES_PY = (
    "In Python, which statement best describes {concept}?",
    "Which option correctly explains {concept}?",
    "A beginner is learning {concept}. Which answer is most accurate?",
    "When working with {concept}, which choice is correct?",
)

_DL_CORRECT = (
    "It is a core idea in the AI342 Deep Learning lectures, applied correctly in practice.",
    "It matches the definition and typical use case taught in the course materials.",
    "It accurately reflects how this concept works in neural network workflows.",
)

_DL_WRONG = (
    "It only applies to classical machine learning with no neural networks.",
    "It is unrelated to training data, loss, or model parameters.",
    "It means gradient descent never updates weights during training.",
    "It describes a purely rule-based system with no learned representations.",
    "It is only used in NLP and never in computer vision.",
    "It guarantees 100% accuracy on any dataset without tuning.",
    "It replaces the need for train/validation/test splits entirely.",
)

_PY_WRONG = (
    "It means Python programs never produce runtime errors.",
    "It is only relevant for web frameworks like Django.",
    "It can only be used after learning advanced networking topics.",
    "It is unrelated to expressions, conditions, or loops.",
    "It replaces the need to test or debug your code.",
    # NOTE: keep this pool free of forbidden-term substrings
    # (placement_rubric.FORBIDDEN_TERMS_BY_LEVEL) so fallback content passes
    # the same scope rules the placement validator enforces on generations.
    "It is a rule that only matters when printing long reports.",
    "It is not used in beginner-level Python at all.",
)

_PY_CORRECT = (
    "It focuses on the concept and applying it correctly in small Python tasks.",
    "It is a core PY4E idea used to write predictable Python programs.",
    "It helps reason about the concept while avoiding common beginner mistakes.",
)


def build_placement_fallback_questions(level: str, track: str) -> list[dict]:
    """Randomized fallback MCQs — different stems and shuffled choices each session."""
    lvl = normalize_level(level)
    track_key = normalize_track(track)
    is_dl = track_key in {"deep_learning", "dl"}
    concepts = list(concepts_for_level(lvl, track=track_key))
    stems = _STEM_TEMPLATES_DL if is_dl else _STEM_TEMPLATES_PY
    correct_pool = _DL_CORRECT if is_dl else _PY_CORRECT
    wrong_pool = _DL_WRONG if is_dl else _PY_WRONG

    questions: list[dict] = []
    for concept in concepts[:5]:
        stem = random.choice(stems).format(concept=concept)
        correct = random.choice(correct_pool)
        wrongs = random.sample(wrong_pool, k=3)
        choices = wrongs + [correct]
        random.shuffle(choices)
        questions.append(
            {
                "question": stem,
                "choices": choices,
                "correct_answer": correct,
                "concept": concept,
            }
        )
    return questions
