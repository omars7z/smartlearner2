from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_current_user_id, get_password_hash, verify_password
from app.db.session import get_db
from app.repositories.course_repository import CourseRepository
from app.repositories.user_repository import UserRepository
from app.schemas.contracts import (
    ChatRequest,
    ExamExecutionRequest,
    LessonGenerationRequest,
    LoginRequest,
    PlacementAnswerRequest,
    PlacementGenerationRequest,
    PlacementStartRequest,
    PlacementSubmissionRequest,
    RegisterRequest,
    SyllabusRequest,
    TokenResponse,
)
from app.services.agents import AgentValidationError
from app.services.orchestrator_service import OrchestratorService

router = APIRouter(prefix="/api/v1")


async def _login_issue_token(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    users = UserRepository(db)
    user = await users.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.post("/auth/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    users = UserRepository(db)
    existing = await users.get_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    user = await users.create(payload.email, get_password_hash(payload.password))
    token = create_access_token(str(user.id))
    return TokenResponse(access_token=token)


@router.post("/auth/token", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    return await _login_issue_token(payload, db)


@router.post("/auth/login", response_model=TokenResponse)
async def login_alias(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """Same as /auth/token — kept for clients that expect /auth/login."""
    return await _login_issue_token(payload, db)


@router.post("/placement/start")
async def placement_start(
    payload: PlacementStartRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    try:
        return await service.start_placement_session(user_id, payload.track)
    except AgentValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/placement/answer")
async def placement_answer(
    payload: PlacementAnswerRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    try:
        return await service.answer_placement_step(
            user_id,
            payload.placement_id,
            payload.track,
            payload.question_id,
            payload.answer_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/placement/generate")
async def generate_placement(
    payload: PlacementGenerationRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    return await service.create_placement_test(user_id, payload.level, payload.question_count)


@router.post("/placement/submit")
async def submit_placement(
    payload: PlacementSubmissionRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = CourseRepository(db)
    placement = await repo.update_placement_score(payload.placement_id, payload.score)
    if placement is None or placement.user_id != user_id:
        raise HTTPException(status_code=404, detail="Placement test not found")
    return {"placement_id": placement.id, "score": placement.score}


@router.post("/syllabus/generate")
async def generate_syllabus(
    payload: SyllabusRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    try:
        return await service.build_syllabus(user_id, payload.placement_id, payload.course_title)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/lessons/generate")
async def generate_lesson(
    payload: LessonGenerationRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    try:
        return await service.generate_lesson_content(user_id, payload.lesson_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Fetch lesson content. lesson_id can be a direct integer or in format 'lesson_N'."""
    service = OrchestratorService(db)
    try:
        # Parse lesson_id: if it's "lesson_19", extract 19
        actual_id = lesson_id
        if lesson_id.startswith("lesson_"):
            actual_id = int(lesson_id.replace("lesson_", ""))
        else:
            actual_id = int(lesson_id)
        return await service.generate_lesson_content(user_id, actual_id)
    except ValueError as exc:
        if "Invalid literal" in str(exc) or "invalid literal" in str(exc):
            raise HTTPException(status_code=400, detail=f"Invalid lesson_id format: {lesson_id}")
        raise HTTPException(status_code=404, detail=str(exc))
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid lesson_id format: {lesson_id}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Error generating lesson content: {str(exc)}")


@router.post("/chat/ask")
@router.post("/qa/ask")  # alias for frontend (api.ts)
async def ask_chatbot(
    payload: ChatRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    try:
        return await service.answer_question(
            user_id,
            payload.question,
            lesson_id=payload.lesson_id,
            current_topic=payload.current_topic,
            student_context=payload.student_context,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/exam/run")
async def run_exam(
    payload: ExamExecutionRequest,
    user_id: Annotated[int, Depends(get_current_user_id)],
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = OrchestratorService(db)
    return await service.run_exam_code(payload.code)
