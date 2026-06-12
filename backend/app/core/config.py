from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # SQLite (dev): sqlite+aiosqlite:///./smartlearner.db
    # One shared DB for all devices: use a hosted PostgreSQL, e.g. Neon or Supabase, then deploy backend
    # with this URL so /auth and /users use one place.
    database_url: str = Field(default="sqlite+aiosqlite:///./smartlearner.db", alias="DATABASE_URL")
    
    # For PostgreSQL: true/false, or leave unset to use TLS for non-localhost hosts.
    database_ssl: bool | None = Field(default=None, alias="DATABASE_SSL")
    
    # If you see SSLCertVerificationError with Supabase pooler on Windows, set to false (dev only).
    database_ssl_verify: bool = Field(default=True, alias="DATABASE_SSL_VERIFY")
    
    # Comma-separated front-end origins (e.g. https://app.vercel.app) when the UI is not on localhost.
    cors_extra_origins: str = Field(default="", alias="CORS_EXTRA_ORIGINS")

    secret_key: str = Field(default="dev-insecure-change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    algorithm: str = "HS256"

    fast_model: str = Field(default="llama-3.1-8b-instant", alias="FAST_MODEL")
    smart_model: str = Field(default="llama-3.3-70b-versatile", alias="SMART_MODEL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_api_key_validators: str | None = Field(default=None, alias="GROQ_API_KEY_VALIDATORS")
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")

    # Dedicated Q&A model (separate from SMART_MODEL used by other agents).
    qa_model: str = Field(default="llama-3.1-8b-instant", alias="QA_MODEL")

    embedding_model: str = Field(default="all-MiniLM-L6-v2", alias="EMBEDDING_MODEL")
    vector_db_path: str = Field(default="./vector_db", alias="VECTOR_DB_PATH")

    source_resource: str = Field(
        default=(
            "Python for Everybody (University of Michigan; Coursera) — "
            "https://www.coursera.org/specializations/python"
        ),
        alias="SOURCE_RESOURCE",
    )
    source_scope: str = Field(
        default="Open textbook & materials: https://www.py4e.com/ | Track: Python Foundations",
        alias="SOURCE_SCOPE",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
