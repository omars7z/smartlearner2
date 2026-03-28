from pydantic import BaseModel, ConfigDict, Field


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


class PlacementGenerationRequest(BaseModel):
    level: str = "Beginner"
    question_count: int = Field(default=5, ge=5, le=10)


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
