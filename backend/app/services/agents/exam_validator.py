from __future__ import annotations

from app.services.agents.base import AgentValidationError


_VALID_DIFFICULTIES = frozenset({"easy", "medium", "hard"})


class ExamValidatorAgent:
    name = "exam-validator"

    def validate(self, payload: dict, *, question_count: int) -> dict:
        if not isinstance(payload, dict):
            raise AgentValidationError("Exam payload must be a JSON object.")
        questions = payload.get("questions")
        if not isinstance(questions, list):
            raise AgentValidationError("Exam payload must include a questions array.")
        if len(questions) != question_count:
            raise AgentValidationError(
                f"Exam validator expected {question_count} questions, got {len(questions)}."
            )

        seen_stems: set[str] = set()
        normalized: list[dict] = []
        for i, q in enumerate(questions):
            if not isinstance(q, dict):
                raise AgentValidationError(f"Question {i + 1} is not an object.")
            stem = str(q.get("question") or "").strip()
            if not stem:
                raise AgentValidationError(f"Question {i + 1} has empty stem.")
            stem_key = stem.lower()
            if stem_key in seen_stems:
                raise AgentValidationError(f"Duplicate question stem at index {i + 1}.")
            seen_stems.add(stem_key)

            choices = q.get("choices")
            if not isinstance(choices, list) or len(choices) != 4:
                raise AgentValidationError(f"Question {i + 1} must have exactly 4 choices.")
            norm_choices = [str(c).strip() for c in choices]
            if any(not c for c in norm_choices):
                raise AgentValidationError(f"Question {i + 1} has empty choice text.")
            if len({c.casefold() for c in norm_choices}) != 4:
                raise AgentValidationError(f"Question {i + 1} choices must be distinct.")

            correct = str(q.get("correct_answer") or "").strip()
            if correct not in norm_choices:
                raise AgentValidationError(f"Question {i + 1}: correct_answer must match one choice exactly.")

            difficulty = str(q.get("difficulty") or "medium").strip().lower()
            if difficulty not in _VALID_DIFFICULTIES:
                difficulty = "medium"

            concept = str(q.get("concept") or "").strip() or "lesson concept"
            explanation = str(q.get("explanation") or "").strip() or (
                f"The correct answer applies {concept} as taught in the lesson."
            )
            normalized.append(
                {
                    "question": stem,
                    "choices": norm_choices,
                    "correct_answer": correct,
                    "concept": concept,
                    "difficulty": difficulty,
                    "explanation": explanation,
                }
            )
        return {"questions": normalized}
