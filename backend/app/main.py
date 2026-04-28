import sys

sys.dont_write_bytecode = True

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.core.groq_rate_limits import response_header_pairs
from app.db.base import Base
from app.db.session import engine


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
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

app = FastAPI(title="SmartLearner 2.0 Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
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
