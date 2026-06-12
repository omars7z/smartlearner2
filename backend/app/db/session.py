import ssl
import logging
from collections.abc import AsyncGenerator

from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

import app.models  # noqa: F401

settings = get_settings()
_url = settings.database_url
_parsed = make_url(_url)
_is_postgres = _parsed.drivername.startswith("postgresql")

# Diagnostic logger: helps debug SSL decisions during container startup
logger = logging.getLogger(__name__)
try:
    host = (_parsed.host or "").lower() if _parsed.host else ""
    is_local = host in ("localhost", "127.0.0.1", "::1", "")
    explicit = settings.database_ssl
    use_ssl_guess = explicit is True or (explicit is None and not is_local)
    logger.info(
        "DB connection: driver=%s host=%s port=%s is_postgres=%s use_ssl_guess=%s DATABASE_SSL=%s DATABASE_SSL_VERIFY=%s",
        _parsed.drivername,
        host,
        _parsed.port,
        _is_postgres,
        use_ssl_guess,
        settings.database_ssl,
        settings.database_ssl_verify,
    )
except Exception:
    # Avoid raising during import; logging is best-effort
    logger.exception("Failed to compute DB SSL diagnostic info")


def _connect_args() -> dict | None:
    if not _is_postgres:
        return None
    explicit = settings.database_ssl
    host = (_parsed.host or "").lower() if _parsed.host else ""
    is_local = host in ("localhost", "127.0.0.1", "::1", "")
    use_ssl = explicit is True or (explicit is None and not is_local)
    args: dict = {}
    if use_ssl:
        if settings.database_ssl_verify:
            args["ssl"] = ssl.create_default_context()
        else:
            uctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            uctx.check_hostname = False
            uctx.verify_mode = ssl.CERT_NONE
            args["ssl"] = uctx
    # PgBouncer pooler (e.g. Supabase port 6543): asyncpg must disable statement cache
    if _parsed.port in (6543, 6432) or "pooler" in host:
        args["statement_cache_size"] = 0
    return args


def _engine_kwargs() -> dict:
    # Change "echo": False to "echo": True temporarily
    base: dict = {"future": True, "echo": True} 
    if _is_postgres:
        base["pool_pre_ping"] = True
    ca = _connect_args()
    if ca is not None:
        base["connect_args"] = ca
    return base


engine = create_async_engine(_url, **_engine_kwargs())
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session
