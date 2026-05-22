from contextlib import asynccontextmanager

import redis.asyncio as aioredis
from fastapi import FastAPI
from psycopg_pool import AsyncConnectionPool

from app.config import settings

_pg_pool: AsyncConnectionPool | None = None
_redis_client: aioredis.Redis | None = None


async def init_postgres():
    connection_string = settings.postgres_url
    global _pg_pool
    _pg_pool = AsyncConnectionPool(
        connection_string, min_size=1, max_size=10, open=False
    )
    await _pg_pool.open()
    await _pg_pool.wait()
    print("Postgres connection pool initialized")


async def init_redis():
    connection_string = settings.redis_url
    global _redis_client
    _redis_client = aioredis.from_url(
        connection_string, encoding="utf-8", decode_responses=True
    )
    pong = await _redis_client.ping()
    print(f"Redis client initialized: {pong}")


async def close_postgres():
    global _pg_pool
    if _pg_pool:
        await _pg_pool.close()
        _pg_pool = None
        print("Postgres connection pool closed")


async def close_redis():
    global _redis_client
    if _redis_client:
        await _redis_client.aclose()
        _redis_client = None
        print("Redis client closed")


def get_pg_pool() -> AsyncConnectionPool:
    if _pg_pool is None:
        raise RuntimeError("Postgres pool not initialised")
    return _pg_pool


def get_redis() -> aioredis.Redis:
    if _redis_client is None:
        raise RuntimeError("Redis not initialised")
    return _redis_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    await init_redis()
    yield
    await close_postgres()
    await close_redis()
