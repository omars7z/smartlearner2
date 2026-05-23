from app.core.config import get_settings
from app.core.deep_learning_curriculum import DL_SOURCE_RESOURCE, DL_SOURCE_SCOPE
from app.services.agents.base import AgentValidationError
from app.services.guardrails import has_python3_hallucinations


def _qa_source_grounding_suffix() -> str:
    s = get_settings()
    return (
        f"\n\n(Source grounding: {s.source_resource}; {s.source_scope}. "
        "Concepts: expressions, values, data types, string replication.)"
    )


class QAValidatorAgent:
    name = "qa-validator"

    @staticmethod
    def _ensure_quick_check_suffix(answer: str) -> str:
        if "💡 **Quick check:**" in answer and '_Reply with your answer or type "next" to continue._' in answer:
            return answer
        quick_prompt = (
            '\n\n> 💡 **Quick check:** What is one key idea from the explanation above?\n'
            '> _Reply with your answer or type "next" to continue._'
        )
        return answer.rstrip() + quick_prompt

    def validate(self, payload: dict, track: str = "python") -> dict:
        track_key = (track or "python").strip().lower().replace("-", "_")
        if track_key in {"deep_learning", "dl"}:
            required_substring = "deep learning"
            source_suffix = (
                f"\n\n(Source grounding: {DL_SOURCE_RESOURCE}; "
                f"scope: {DL_SOURCE_SCOPE}.)"
            )
        else:
            required_substring = "python for everybody"
            source_suffix = _qa_source_grounding_suffix()
        answer = str(payload.get("answer", ""))
        if has_python3_hallucinations(answer):
            raise AgentValidationError("Hallucinated Python 2-only functions detected.")
        if required_substring not in answer.lower():
            answer = answer.rstrip() + source_suffix
        payload["answer"] = self._ensure_quick_check_suffix(answer)
        return payload
