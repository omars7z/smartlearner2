"""LLM-backed agents: one module per agent; shared base in `base`."""

from app.services.agents.base import AgentPair, AgentValidationError
from app.services.agents.lesson_generator import LessonGeneratorAgent
from app.services.agents.lesson_validator import LessonValidatorAgent
from app.services.agents.placement_generator import (
    DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE,
    PLACEMENT_MCQ_SYSTEM_PROMPT,
    PlacementGeneratorAgent,
)
from app.services.agents.placement_validator import PlacementValidatorAgent
from app.services.agents.qa_generator import QAGeneratorAgent
from app.services.agents.qa_validator import QAValidatorAgent
from app.services.agents.syllabus_generator import SyllabusGeneratorAgent
from app.services.agents.syllabus_validator import SyllabusValidatorAgent

__all__ = [
    "DEFAULT_PLACEMENT_USER_PROMPT_TEMPLATE",
    "PLACEMENT_MCQ_SYSTEM_PROMPT",
    "AgentPair",
    "AgentValidationError",
    "LessonGeneratorAgent",
    "LessonValidatorAgent",
    "PlacementGeneratorAgent",
    "PlacementValidatorAgent",
    "QAGeneratorAgent",
    "QAValidatorAgent",
    "SyllabusGeneratorAgent",
    "SyllabusValidatorAgent",
]
