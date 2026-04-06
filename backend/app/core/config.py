from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = Field(default="sqlite+aiosqlite:///./smartlearner.db", alias="DATABASE_URL")

    secret_key: str = Field(default="dev-insecure-change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=60, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    algorithm: str = "HS256"

    fast_model: str = Field(default="llama-3.1-8b-instant", alias="FAST_MODEL")
    smart_model: str = Field(default="llama-3.3-70b-versatile", alias="SMART_MODEL")
    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_api_key_validators: str | None = Field(default=None, alias="GROQ_API_KEY_VALIDATORS")

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
