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

    def validate(self, payload: dict, track: str = "python") -> dict:
        track_key = (track or "python").strip().lower().replace("-", "_")
        if track_key in {"deep_learning", "dl"}:
            required_substring = "deep learning"
            source_suffix = (
                "\n\n(Source grounding: Deep Learning (Goodfellow, Bengio, Courville; MIT Press); "
                "resource: https://www.deeplearningbook.org/; "
                "scope: deep learning lecture-note style foundations and practical modeling concepts.)"
            )
        else:
            required_substring = "python for everybody"
            source_suffix = _qa_source_grounding_suffix()
        answer = str(payload.get("answer", ""))
        if has_python3_hallucinations(answer):
            raise AgentValidationError("Hallucinated Python 2-only functions detected.")
        if required_substring not in answer.lower():
            payload["answer"] = answer.rstrip() + source_suffix
        return payload
