from __future__ import annotations

from functools import lru_cache
from typing import Any

_TRACKS: tuple[dict[str, Any], ...] = (
    {
        "id": "beginner",
        "label_en": "Beginner",
        "chapter_keys": ("dl_01_math", "dl_02_python", "dl_03_data", "dl_04_linear_models"),
    },
    {
        "id": "intermediate",
        "label_en": "Intermediate",
        "chapter_keys": ("dl_05_nn_basics", "dl_06_backprop", "dl_07_optimization", "dl_08_regularization"),
    },
    {
        "id": "advanced",
        "label_en": "Advanced",
        "chapter_keys": ("dl_09_cnn", "dl_10_sequence", "dl_11_transformers", "dl_12_training_systems"),
    },
    {
        "id": "very_advanced",
        "label_en": "Very Advanced",
        "chapter_keys": ("dl_13_generative", "dl_14_rl", "dl_15_scaling", "dl_16_mlops"),
    },
)

_CHAPTERS: dict[str, dict[str, Any]] = {
    "dl_01_math": {"number": 1, "title": "Math Foundations", "difficulty": "beginner", "topics": ["vectors", "matrices", "calculus"]},
    "dl_02_python": {"number": 2, "title": "Python for Deep Learning", "difficulty": "beginner", "topics": ["numpy", "pytorch_basics"]},
    "dl_03_data": {"number": 3, "title": "Data Pipelines and Splits", "difficulty": "beginner", "topics": ["datasets", "dataloaders"]},
    "dl_04_linear_models": {"number": 4, "title": "Linear and Logistic Models", "difficulty": "beginner", "topics": ["regression", "classification"]},
    "dl_05_nn_basics": {"number": 5, "title": "Neural Network Fundamentals", "difficulty": "intermediate", "topics": ["mlp", "activations"]},
    "dl_06_backprop": {"number": 6, "title": "Backpropagation", "difficulty": "intermediate", "topics": ["gradients", "chain_rule"]},
    "dl_07_optimization": {"number": 7, "title": "Optimization", "difficulty": "intermediate", "topics": ["sgd", "adam", "lr_schedules"]},
    "dl_08_regularization": {"number": 8, "title": "Generalization and Regularization", "difficulty": "intermediate", "topics": ["dropout", "batchnorm"]},
    "dl_09_cnn": {"number": 9, "title": "Convolutional Networks", "difficulty": "advanced", "topics": ["conv", "vision"]},
    "dl_10_sequence": {"number": 10, "title": "Sequence Models", "difficulty": "advanced", "topics": ["rnn", "lstm", "gru"]},
    "dl_11_transformers": {"number": 11, "title": "Transformers", "difficulty": "advanced", "topics": ["attention", "encoder_decoder"]},
    "dl_12_training_systems": {"number": 12, "title": "Training Systems", "difficulty": "advanced", "topics": ["mixed_precision", "distributed"]},
    "dl_13_generative": {"number": 13, "title": "Generative Modeling", "difficulty": "very_advanced", "topics": ["vae", "diffusion"]},
    "dl_14_rl": {"number": 14, "title": "Reinforcement Learning", "difficulty": "very_advanced", "topics": ["mdp", "policy_gradient"]},
    "dl_15_scaling": {"number": 15, "title": "Scaling Laws and LLM Training", "difficulty": "very_advanced", "topics": ["tokenization", "pretraining"]},
    "dl_16_mlops": {"number": 16, "title": "MLOps for Deep Learning", "difficulty": "very_advanced", "topics": ["serving", "monitoring"]},
}

_SUB_LESSONS: dict[str, list[dict[str, str]]] = {
    k: [{"id": f"{i+1}.1", "title": t} for i, t in enumerate([
        "Core concepts", "Worked examples", "Common failure modes", "Hands-on practice"
    ])]
    for k in _CHAPTERS
}


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
        "source": "Deep Learning track from lecture-note aligned curriculum schema.",
        "tracks": [dict(t) for t in _TRACKS],
        "chapters": chapters,
    }
