import sys

sys.dont_write_bytecode = True

from contextlib import asynccontextmanager
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import text

from app.api.routes import router
from app.core.config import get_settings
from app.core.groq_rate_limits import response_header_pairs
from app.db.base import Base
from app.db.session import engine
from app.services.llm_client import LLMClient, LLMClientError


async def _ensure_users_table_columns(conn) -> None:
    """
    Lightweight SQLite migration for existing dev DBs.
    `create_all` won't add columns to an existing table.
    """
    try:
        rows = (await conn.execute(text("PRAGMA table_info(users)"))).fetchall()
    except Exception:
        return
    if not rows:
        return
    existing_cols = {r[1] for r in rows}  # row[1] = column name

    if "full_name" not in existing_cols:
        await conn.execute(text("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)"))

    if "role" not in existing_cols:
        await conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) DEFAULT 'student' NOT NULL"))
    if "is_active" not in existing_cols:
        await conn.execute(text("ALTER TABLE users ADD COLUMN is_active BOOLEAN DEFAULT 1 NOT NULL"))


async def _ensure_lessons_table_columns(conn) -> None:
    try:
        rows = (await conn.execute(text("PRAGMA table_info(lessons)"))).fetchall()
    except Exception:
        return
    if not rows:
        return
    existing_cols = {r[1] for r in rows}
    if "unit_title" not in existing_cols:
        await conn.execute(text("ALTER TABLE lessons ADD COLUMN unit_title VARCHAR(255)"))
    if "metadata_json" not in existing_cols:
        await conn.execute(text("ALTER TABLE lessons ADD COLUMN metadata_json TEXT DEFAULT '{}'"))
    if "prerequisites_json" not in existing_cols:
        await conn.execute(text("ALTER TABLE lessons ADD COLUMN prerequisites_json TEXT DEFAULT '[]'"))
    if "parent_lesson_id" not in existing_cols:
        await conn.execute(text("ALTER TABLE lessons ADD COLUMN parent_lesson_id INTEGER REFERENCES lessons(id)"))
    if "is_sub_lesson" not in existing_cols:
        await conn.execute(text("ALTER TABLE lessons ADD COLUMN is_sub_lesson BOOLEAN DEFAULT 0 NOT NULL"))


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        settings = get_settings()
        if settings.database_url.startswith("sqlite"):
            await _ensure_users_table_columns(conn)
            await _ensure_lessons_table_columns(conn)
        await conn.run_sync(Base.metadata.create_all)
    yield


_EXPOSE_RATE_HEADERS = [
    "X-App-RateLimit-Limit-Requests",
    "X-App-RateLimit-Remaining-Requests",
    "X-App-RateLimit-Reset-Requests",
    "X-App-RateLimit-Remaining-Tokens",
]

def _cors_origin_list() -> list[str]:
    base = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ]
    settings = get_settings()
    extra = [o.strip() for o in settings.cors_extra_origins.split(",") if o.strip()]
    return base + extra


app = FastAPI(title="SmartLearner 2.0 Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origin_list(),
    # Any Vite/other dev port on loopback (Origin includes host + port).
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=_EXPOSE_RATE_HEADERS,
)


@app.middleware("http")
async def attach_groq_rate_limit_headers(request, call_next):
    response = await call_next(request)
    for name, value in response_header_pairs():
        response.headers[name] = value
    return response


app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


class EvaluateCheckRequest(BaseModel):
    question: str = Field(min_length=3)
    student_answer: str = Field(min_length=1)
    topic: str = Field(default="General")
    course: str = Field(default="General")
    context: str = Field(default="")


@app.post("/api/evaluate-check")
async def evaluate_check(payload: EvaluateCheckRequest) -> dict:
    """LLM-based quick-check evaluator with safe fallback."""
    q = payload.question.strip()
    a = payload.student_answer.strip()
    course = payload.course.strip()
    topic = payload.topic.strip()
    context = payload.context.strip()

    prompt = f"""
You are evaluating a student's answer to a comprehension check.

Course: {course}
Topic: {topic}
Context covered in the lesson: {context}

Question: {q}

Student Answer: {a}

Evaluation Rules:
- Be GENEROUS — if the student shows understanding of ANY concept 
  mentioned in the Context, mark as correct
- Do NOT expect a perfect textbook answer
- partial = student shows some understanding but misses key detail
- wrong = answer is clearly incorrect or completely irrelevant to context
- Never mark wrong if the answer reflects any valid idea from the context

Respond ONLY in this exact JSON format with no extra text:
{{
  "result": "correct" | "partial" | "wrong",
  "feedback": "one short encouraging sentence max 15 words",
  "next_check": "one applied follow-up question requiring code or example"
}}
"""
    concept_keywords = {
        "mutable",
        "change",
        "index",
        "slice",
        "append",
        "extend",
        "loop",
        "list",
        "element",
        "ordered",
        "collection",
        "traversal",
        "modify",
        "creation",
        "immutable",
        "iterate",
        "method",
        "assign",
    }
    normalized = a.lower().translate(str.maketrans("", "", ".,!?;:\"'()[]{}"))
    llm = LLMClient()
    system = "You are a strict JSON evaluator. Return only valid JSON."
    hits: set[str] | str = set()
    try:
        raw = llm.generate_json_for_qa(model=llm.settings.qa_model, system_prompt=system, user_prompt=prompt)
        data = json.loads(raw)
        result = str(data.get("result", "")).lower().strip()
        if result not in {"correct", "partial", "wrong"}:
            raise ValueError("Invalid result label from model.")
        feedback = str(data.get("feedback", "")).strip() or "Good effort—keep going."
        next_check = str(data.get("next_check", "")).strip() or "Write one short code example applying this concept."
        a_tokens = {t for t in normalized.split() if len(t) > 2}
        hits = concept_keywords.intersection(a_tokens)
        if "immutable" in a_tokens and "mutable" not in a_tokens:
            result = "wrong"
            feedback = "Try again — that reverses the concept of list mutability."
            next_check = "Write one line of code that modifies an existing list element."
        elif result == "correct" and len(hits) == 1:
            result = "partial"
            feedback = "Almost — add one more detail to complete the idea."
            next_check = "Write one line of code that demonstrates the concept you described."
    except (LLMClientError, json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"[evaluate-check] LLM failed: {type(e).__name__}: {e}")
        # Safe lexical fallback for local/dev reliability
        a_tokens = {t for t in normalized.split() if len(t) > 2}
        hits = concept_keywords.intersection(a_tokens)

        if "immutable" in a_tokens and "mutable" not in a_tokens:
            result = "wrong"
            feedback = "Try again — that reverses the concept of list mutability."
            next_check = "Write one line of code that modifies an existing list element."
        elif len(hits) >= 2:
            result = "correct"
            feedback = "Good — you identified a key concept correctly."
            next_check = "Write one line of code that demonstrates the concept you described."
        elif len(hits) == 1:
            result = "partial"
            feedback = "Almost — add one more detail to complete the idea."
            next_check = "Write one line of code that demonstrates the concept you described."
        else:
            result = "wrong"
            feedback = "Try again — mention a specific concept from the explanation."
            next_check = "Write one line of code that demonstrates the concept you described."

    print(f"Result: {result} | Hits: {hits} | Answer: {a}")

    verdict_map = {"correct": "✅ Exactly right", "partial": "🟡 Almost", "wrong": "❌ Not quite"}
    return {
        "status": "ok",
        "result": result,
        "verdict": verdict_map[result],
        "feedback": feedback,
        "topic": topic,
        "course": course,
        "next_quick_check": next_check,
    }
