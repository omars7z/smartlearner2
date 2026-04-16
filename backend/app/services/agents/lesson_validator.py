from app.core.config import get_settings
from app.services.agents.base import AgentValidationError
from app.services.guardrails import validate_content_scope


class LessonValidatorAgent:
    name = "lesson-validator"

    def validate(self, payload: dict) -> dict:
        markdown = str(payload.get("markdown", ""))
        if "python for everybody" not in markdown.lower():
            s = get_settings()
            suffix = (
                f"\n\n(Source: Python for Everybody (Charles Severance, University of Michigan). "
                f"Resource: {s.source_resource}; Scope: {s.source_scope}. "
                "Covers core Python concepts: expressions, data types, variable assignment, string operations.)"
            )
            markdown = markdown.rstrip() + suffix
            payload["markdown"] = markdown
        ok, reason = validate_content_scope(markdown)
        if not ok:
            raise AgentValidationError(reason)
        return payload
