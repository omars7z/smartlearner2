from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router
from app.db.base import Base
from app.db.session import engine
from app.models import entities  # noqa: F401


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


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as conn:
        await _ensure_users_table_columns(conn)
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="SmartLearner 2.0 Backend", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
