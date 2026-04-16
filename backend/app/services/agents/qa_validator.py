from app.core.config import get_settings
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

    def validate(self, payload: dict) -> dict:
        answer = str(payload.get("answer", ""))
        if has_python3_hallucinations(answer):
            raise AgentValidationError("Hallucinated Python 2-only functions detected.")
        if "python for everybody" not in answer.lower():
            payload["answer"] = answer.rstrip() + _qa_source_grounding_suffix()
        return payload
