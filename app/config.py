from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Postgres
    postgres_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Ollama
    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "llama3.2"
    llm_api_key: str = "ollama"
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768

    # Ingestion
    docs_dir: str
    chunk_size: int = 500
    chunk_overlap: int = 50

    # Semantic cache
    cache_similarity_threshold: float = 0.15
    cache_ttl_seconds: int = 86400

    # Sessions
    session_ttl_seconds: int = 86400

    # Logging
    log_level: str = "INFO"
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()
