from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai_client import close_ai_client, init_ai_client
from app.db import close_postgres, close_redis, init_postgres, init_redis
from app.watcher import start_file_watcher, stop_file_watcher

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    await init_redis()
    await init_ai_client()
    file_watcher = start_file_watcher()
    app.state.file_watcher = file_watcher
    try:
        yield
    finally:
        await stop_file_watcher(file_watcher)
        await close_postgres()
        await close_redis()
        await close_ai_client()
