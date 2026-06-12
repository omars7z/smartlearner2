import ssl
from sqlalchemy.ext.asyncio import create_async_engine
import os

# 1. Create the permissive SSL context
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

# 2. Grab your URL
database_url = os.getenv("DATABASE_URL")

# 3. Inject the context into the engine
engine = create_async_engine(
    database_url,
    connect_args={"ssl": ssl_ctx}  # This is the magic line that bypasses the crash
)