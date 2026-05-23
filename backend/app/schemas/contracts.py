from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    full_name: str
    email: str
    role: Literal["student", "admin"]


class RegisterRequest(BaseModel):
    full_name: str = Field(min_length=1, max_length=255)
    email: str
    password: str
    role: Literal["student", "admin"] = "student"


class LoginRequest(BaseModel):
    email: str
    password: str


class PlacementGenerationRequest(BaseModel):
    level: str = "beginner"
    question_count: int = Field(default=5, ge=5, le=5)
    track: str = "python"


class PlacementSubmissionRequest(BaseModel):
    placement_id: int
    score: int = Field(ge=0, le=100)


class PlacementStartRequest(BaseModel):
    """Dashboard placement flow: one question at a time."""
    track: str = "python"


class PlacementAnswerRequest(BaseModel):
    placement_id: int
    track: str = "python"
    question_id: str
    answer_index: int = Field(ge=0)


class SyllabusRequest(BaseModel):
    placement_id: int
    course_title: str = "Python Foundations"


class LessonGenerationRequest(BaseModel):
    lesson_id: int


class ChatRequest(BaseModel):
    """Matches frontend qaApi.ask: question + optional current_topic / student_context."""

    model_config = ConfigDict(extra="ignore")

    question: str
    lesson_id: int | None = None
    current_topic: str | None = None
    student_context: dict | None = None


class ExamExecutionRequest(BaseModel):
    code: str


class ExamGenerateRequest(BaseModel):
    lesson_id: str
    course_id: int | None = None
    level: Literal["beginner", "intermediate", "advanced", "very_advanced"] = "beginner"
    question_count: int = Field(default=5, ge=3, le=10)


class ExamGradeAnswerDto(BaseModel):
    question_id: str
    answer_index: int = Field(ge=0, le=3)


class ExamGradeRequest(BaseModel):
    lesson_id: str
    course_id: int | None = None
    answers: list[ExamGradeAnswerDto] = Field(default_factory=list, min_length=1, max_length=10)


class ResourceCreateRequest(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    url: str = Field(min_length=5, max_length=2048)
    description: str | None = Field(default=None, max_length=5000)


class ResourceDto(BaseModel):
    id: int
    title: str
    url: str
    description: str | None = None
    created_by_user_id: int | None = None


class AssessmentAnswerDto(BaseModel):
    question_index: int = Field(ge=0, le=4)
    choice_index: int = Field(ge=0, le=3)


class SubmitAssessmentRequest(BaseModel):
    answers: list[AssessmentAnswerDto] = Field(default_factory=list, min_length=1, max_length=5)


class QuickAssessmentGenerateRequest(BaseModel):
    lesson_id: str
    topic: str
    level: str


class QuickAssessmentGradeAnswerDto(BaseModel):
    question_id: str
    answer_index: int = Field(ge=0, le=3)


class QuickAssessmentGradeRequest(BaseModel):
    lesson_id: str
    topic: str
    answers: list[QuickAssessmentGradeAnswerDto] = Field(default_factory=list, min_length=1, max_length=5)

