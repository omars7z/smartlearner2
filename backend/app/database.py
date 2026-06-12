import ssl
import os
from sqlalchemy.ext.asyncio import create_async_engine

# Grab your URL
database_url = os.getenv("DATABASE_URL")

# Create the permissive SSL context
ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

print("🚀 TRACER BULLET: Custom SSL Context is loading!") # <--- Add this!

# Inject it into your code router's database engine
engine = create_async_engine(
    database_url,
    connect_args={"ssl": ssl_ctx} 
)