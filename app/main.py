from fastapi import FastAPI

from app.db import get_pg_pool, get_redis, lifespan

app = FastAPI(lifespan=lifespan)


@app.get("/health")
async def health():
    try:
        pool = get_pg_pool()
        async with pool.connection() as conn:
            await conn.execute("SELECT 1")
        pg_status = "ok"
    except Exception as e:
        print(f"Postgres health check failed: {e}")
        pg_status = "error"

    try:
        client = get_redis()
        pong = await client.ping()
        redis_status = "ok" if pong else "error"
    except Exception as e:
        print(f"Redis health check failed: {e}")
        redis_status = "error"

    return {"postgres": pg_status, "redis": redis_status}
