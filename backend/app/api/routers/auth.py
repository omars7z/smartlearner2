from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.contracts import LoginRequest, RegisterRequest, TokenResponse

router = APIRouter(tags=["auth"])


async def _login_issue_token(payload: LoginRequest, db: AsyncSession) -> TokenResponse:
    users = UserRepository(db)
    user = await users.get_by_email(payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_access_token(str(user.id))
    role = getattr(user, "role", "student") or "student"
    if role not in ("student", "admin"):
        role = "student"
    return TokenResponse(
        access_token=token,
        full_name=user.full_name or "",
        email=user.email,
        role=role,  # type: ignore[arg-type]
    )


@router.post("/auth/register", response_model=TokenResponse)
async def register(payload: RegisterRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> TokenResponse:
    users = UserRepository(db)
    existing = await users.get_by_email(payload.email)
    if existing:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already exists")
    user = await users.create(
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name.strip(),
        role="student",
    )
    token = create_access_token(str(user.id))
    return TokenResponse(
        access_token=token,
        full_name=user.full_name or payload.full_name,
        email=user.email,
        role=user.role,  # type: ignore[arg-type]
    )


@router.post("/auth/token", response_model=TokenResponse)
@router.post("/tokens", response_model=TokenResponse)
async def login(payload: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]) -> TokenResponse:
    return await _login_issue_token(payload, db)
