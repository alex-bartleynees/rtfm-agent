from app.logging_config import configure_logging

configure_logging()

import logging

from fastapi import FastAPI

from app.db import get_pg_pool, get_redis
from app.lifespan import lifespan
from app.middleware import RequestIDMiddleware

logger = logging.getLogger(__name__)

app = FastAPI(lifespan=lifespan)
app.add_middleware(RequestIDMiddleware)


@app.get("/health")
async def health():
    try:
        pool = get_pg_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        pg_status = "ok"
    except Exception:
        logger.exception("Postgres health check failed")
        pg_status = "error"

    try:
        client = get_redis()
        pong = await client.ping()
        redis_status = "ok" if pong else "error"
    except Exception:
        logger.exception("Redis health check failed")
        redis_status = "error"

    return {"postgres": pg_status, "redis": redis_status}
