"""
LLM-based rubric scoring for a batch of placement MCQs (experiment / offline use).

Reads criteria from evaluation_rubric.json; returns structured scores for logging next to prompt runs.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.core.config import get_settings
from app.services.guardrails import safe_json_loads
from app.services.llm_client import LLMClient

_SYSTEM = """You evaluate a batch of placement multiple-choice questions for the selected track.
You receive JSON with: placement_level, track, source_note, scale (integer max score per criterion), criteria (array of {id, name, description}), questions (array of objects with question, choices, correct_answer, concept).

Return JSON only, with this exact shape:
{
  "scores": { "<criterion_id>": <integer 1..scale inclusive>, ... },
  "criterion_notes": { "<criterion_id>": "<one short sentence>", ... },
  "overall_average": <number>,
  "set_summary": "<2-4 sentences in English>"
}

Rules:
- Include every criterion id from the input exactly once in scores and criterion_notes.
- overall_average is the mean of all criterion scores, rounded to one decimal.
- Be strict but fair; placement is diagnostic, not trick questions.
"""


def load_evaluation_rubric(path: str | Path) -> dict:
    p = Path(path)
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("criteria"), list):
        raise ValueError("Rubric must be a JSON object with a \"criteria\" array")
    for c in data["criteria"]:
        if not isinstance(c, dict) or not str(c.get("id") or "").strip():
            raise ValueError("Each criterion needs a non-empty string \"id\"")
    return data


def evaluate_placement_questions(
    llm: LLMClient,
    *,
    level: str,
    track: str = "python",
    questions: list[dict],
    rubric: dict,
) -> dict:
    settings = get_settings()
    scale = int(rubric.get("scale_max") or 5)
    if scale < 2:
        scale = 5

    track_key = (track or "python").strip().lower().replace("-", "_")
    source_note = (
        "AI342 Deep Learning lecture materials (Dr. Rasha Obeidat, JUST)"
        if track_key in {"deep_learning", "dl"}
        else "Python for Everybody (University of Michigan / Coursera)"
    )
    payload = {
        "placement_level": level,
        "track": track_key,
        "source_note": source_note,
        "scale": scale,
        "criteria": rubric.get("criteria", []),
        "questions": questions,
    }
    user_prompt = json.dumps(payload, ensure_ascii=False)

    last_err = ""
    for attempt in range(2):
        hint = ""
        if attempt == 1:
            hint = (
                "Your previous reply was not valid JSON or missed required keys. "
                "Reply with a single JSON object only, matching the schema, all criterion ids in scores.\n\n"
            )
        raw = llm.generate_json(
            model=settings.fast_model,
            system_prompt=_SYSTEM,
            user_prompt=hint + user_prompt,
        )
        try:
            out = safe_json_loads(raw)
        except json.JSONDecodeError as exc:
            last_err = str(exc)
            continue
        if not isinstance(out, dict):
            last_err = "parsed root is not an object"
            continue
        scores = out.get("scores")
        if not isinstance(scores, dict):
            last_err = "missing or invalid scores object"
            continue
        crit_ids = [str(c["id"]).strip() for c in rubric["criteria"] if str(c.get("id") or "").strip()]
        missing = [cid for cid in crit_ids if cid not in scores]
        if missing:
            last_err = f"scores missing keys: {missing}"
            continue
        return {
            "rubric_title": rubric.get("title"),
            "scale_max": scale,
            "scores": scores,
            "criterion_notes": out.get("criterion_notes") if isinstance(out.get("criterion_notes"), dict) else {},
            "overall_average": out.get("overall_average"),
            "set_summary": out.get("set_summary"),
            "evaluator_model": settings.fast_model,
        }

    return {
        "error": f"Rubric evaluation failed after retries: {last_err}",
        "evaluator_model": settings.fast_model,
    }
