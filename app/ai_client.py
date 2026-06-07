from openai import AsyncOpenAI

from app.config import settings

_ai_client: AsyncOpenAI | None = None


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


def get_ai_client() -> AsyncOpenAI:
    if _ai_client is None:
        raise RuntimeError("AI client not initialised")
    return _ai_client
