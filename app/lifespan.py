from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai_client import close_ai_client, init_ai_client
from app.db import close_postgres, close_redis, init_postgres, init_redis


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    await init_redis()
    await init_ai_client()
    yield
    await close_postgres()
    await close_redis()
    await close_ai_client()
