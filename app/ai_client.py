from openai import AsyncOpenAI

_ai_client: AsyncOpenAI | None = None

from app.config import settings


async def init_ai_client():
    connection_string = settings.llm_api_key
    global _ai_client
    _ai_client = AsyncOpenAI(base_url=settings.llm_base_url, api_key=connection_string)
    print("AI client initialized")


async def close_ai_client():
    global _ai_client
    if _ai_client:
        await _ai_client.close()
        _ai_client = None
        print("AI client closed")
