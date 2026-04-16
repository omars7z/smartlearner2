import json

from app.core.placement_rubric import (
    chapter_scope_for_level,
    concepts_for_level,
    forbidden_terms_for_level,
    normalize_level,
    validate_question_concepts_for_level,
)
from app.services.agents.base import AgentPair, AgentValidationError
from app.services.llm_client import LLMClient

_PLACEMENT_VALIDATOR_SYSTEM = """You are PlacementValidatorAgent. Validate placement MCQs for Python for Everybody.
You receive JSON with:
- placement_level (string)
- expected_question_count (int)
- rubric_concepts_in_order (array of exact concept strings, one per slot)
- candidate_questions (array)

Check: each question has non-empty stem, exactly 4 distinct choices (strings), correct_answer must equal one choice after trim,
no duplicate stems (case-insensitive), for beginner level stems must not mention asyncio,
and for each index i concept must EXACTLY equal rubric_concepts_in_order[i].
Return JSON only:
{"valid": true, "questions": [ ... normalized objects with question, choices, correct_answer, concept ... ]}
or {"valid": false, "error": "brief reason"}.
If valid, echo normalized questions with correct_answer and choices as trimmed strings."""


def _validate_placement_deterministic(data: dict, level: str, question_count: int) -> dict:
    """Rule-based validation and normalization (authoritative rubric enforcement)."""
    lvl = normalize_level(level)
    questions = data.get("questions") or []
    if len(questions) != question_count:
        raise AgentValidationError(
            f"Placement validator expected {question_count} questions, got {len(questions)}."
        )

    seen_texts: set[str] = set()
    normalized: list[dict] = []

    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            raise AgentValidationError(f"Question {i + 1} is not an object.")
        text = str(q.get("question", "")).strip()
        if not text:
            raise AgentValidationError(f"Question {i + 1} has empty text.")
        text_lower = text.lower()
        if text_lower in seen_texts:
            raise AgentValidationError(f"Duplicate question text at index {i + 1}.")
        seen_texts.add(text_lower)

        choices = q.get("choices", [])
        if not isinstance(choices, list) or len(choices) != 4:
            raise AgentValidationError(f"Question {i + 1} must have exactly 4 choices.")
        correct = q.get("correct_answer")
        norm_choices = [str(c).strip() for c in choices]
        correct_str = str(correct).strip()
        if correct_str not in norm_choices:
            raise AgentValidationError(f"Question {i + 1}: correct_answer must be one of choices.")

        forbidden = forbidden_terms_for_level(lvl)
        for term in forbidden:
            if term in text_lower:
                raise AgentValidationError(
                    f"Question {i + 1}: level {lvl!r} must not reference '{term}'. "
                    f"Allowed scope: {chapter_scope_for_level(lvl)}."
                )

        normalized.append(
            {
                "question": text,
                "choices": norm_choices,
                "correct_answer": correct_str,
                "concept": str(q.get("concept") or "").strip(),
            }
        )

    expected = list(concepts_for_level(lvl))
    for i, row in enumerate(normalized):
        if row["concept"] != expected[i]:
            raise AgentValidationError(
                f"Question {i + 1}: concept must match rubric slot {expected[i]!r}; got {row['concept']!r}."
            )

    try:
        validate_question_concepts_for_level(normalized, lvl)
    except ValueError as exc:
        raise AgentValidationError(str(exc)) from exc

    return {"questions": normalized}


class PlacementValidatorAgent(AgentPair):
    """LLM-assisted validation (validator API key) with deterministic rubric enforcement as fallback."""

    name = "placement-validator"

    def __init__(self, llm: LLMClient):
        super().__init__("placement-validator", llm)

    def validate(self, data: dict, level: str, question_count: int) -> dict:
        lvl = normalize_level(level)
        expected = list(concepts_for_level(lvl))
        payload = {
            "placement_level": lvl,
            "expected_question_count": question_count,
            "rubric_concepts_in_order": expected,
            "candidate_questions": data.get("questions") or [],
        }
        user_prompt = json.dumps(payload, ensure_ascii=False)
        try:
            out = self._generate_with_retries(
                model=self.settings.fast_model,
                system_prompt=_PLACEMENT_VALIDATOR_SYSTEM,
                user_prompt=user_prompt,
            )
            if not isinstance(out, dict) or not out.get("valid"):
                raise AgentValidationError(str(out.get("error") or "PlacementValidatorAgent rejected input"))
            merged = {"questions": out.get("questions") or []}
            return _validate_placement_deterministic(merged, level, question_count)
        except AgentValidationError:
            return _validate_placement_deterministic(data, level, question_count)
