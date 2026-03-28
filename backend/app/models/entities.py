from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    placements: Mapped[list["PlacementTest"]] = relationship(back_populates="user")
    courses: Mapped[list["Course"]] = relationship(back_populates="user")


class PlacementTest(Base):
    __tablename__ = "placement_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    questions_json: Mapped[dict] = mapped_column(JSON)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="placements")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    level: Mapped[str] = mapped_column(String(50), default="Beginner")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="courses")
    lessons: Mapped[list["Lesson"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"
    __table_args__ = (UniqueConstraint("course_id", "order_index", name="uq_course_lesson_order"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.id"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    topic: Mapped[str] = mapped_column(String(100))
    order_index: Mapped[int] = mapped_column(Integer)
    markdown_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    prerequisites_json: Mapped[list[str]] = mapped_column(JSON, default=list)

    course: Mapped["Course"] = relationship(back_populates="lessons")


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    agent_name: Mapped[str] = mapped_column(String(80), index=True)
    stage: Mapped[str] = mapped_column(String(40))
    input_json: Mapped[dict] = mapped_column(JSON)
    output_json: Mapped[dict] = mapped_column(JSON)
    is_valid: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
