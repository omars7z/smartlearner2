import json

from app.core.config import get_settings
from app.services.guardrails import safe_json_loads
from app.services.llm_client import LLMClient


class AgentValidationError(Exception):
    pass


class AgentPair:
    """Base for LLM-backed agents: shared settings and JSON generation with retries."""

    def __init__(self, name: str, llm: LLMClient):
        self.name = name
        self.llm = llm
        self.settings = get_settings()

    def _generate_with_retries(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        *,
        use_ollama_qa: bool = False,
    ) -> dict:
        last_error = "Unknown error"
        for _ in range(3):
            if use_ollama_qa:
                raw = self.llm.generate_json_for_qa(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                )
            else:
                raw = self.llm.generate_json(model=model, system_prompt=system_prompt, user_prompt=user_prompt)
            try:
                return safe_json_loads(raw)
            except json.JSONDecodeError as exc:
                last_error = str(exc)
        raise AgentValidationError(f"JSON parsing failed after 3 retries: {last_error}")
