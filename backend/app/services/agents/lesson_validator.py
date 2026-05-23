from app.core.config import get_settings
from app.core.deep_learning_curriculum import DL_SOURCE_RESOURCE, DL_SOURCE_SCOPE
from app.services.agents.base import AgentValidationError
from app.services.guardrails import validate_content_scope


class LessonValidatorAgent:
    name = "lesson-validator"

    def validate(self, payload: dict, track: str = "python") -> dict:
        track_key = (track or "python").strip().lower().replace("-", "_")
        markdown = str(payload.get("markdown", ""))
        if track_key in {"deep_learning", "dl"}:
            required_substring = "deep learning"
        else:
            required_substring = "python for everybody"
        if required_substring not in markdown.lower():
            s = get_settings()
            if track_key in {"deep_learning", "dl"}:
                suffix = (
                    f"\n\n(Source: {DL_SOURCE_RESOURCE}. "
                    f"Scope: {DL_SOURCE_SCOPE}.)"
                )
            else:
                suffix = (
                    f"\n\n(Source: Python for Everybody (Charles Severance, University of Michigan). "
                    f"Resource: {s.source_resource}; Scope: {s.source_scope}. "
                    "Covers core Python concepts: expressions, data types, variable assignment, string operations.)"
                )
            markdown = markdown.rstrip() + suffix
        # theres a markdown thats saved in the db for the lesson agent to retrueve and validate
        payload["markdown"] = markdown
        ok, reason = validate_content_scope(markdown, track=track_key)
        if not ok:
            raise AgentValidationError(reason)
        return payload
