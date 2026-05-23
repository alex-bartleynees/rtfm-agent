import logging
import logging.config

from app.config import settings


def configure_logging() -> None:
    formatter = "json" if settings.environment == "production" else "default"

    logging.config.dictConfig({
        "version": 1,
        "disable_existing_loggers": False,
        "filters": {
            "request_id": {
                "()": "app.middleware.RequestIDFilter",
            },
        },
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s",
                "defaults": {"request_id": "-"},
            },
            "json": {
                "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s",
                "defaults": {"request_id": "-"},
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": formatter,
                "filters": ["request_id"],
            },
        },
        "root": {
            "handlers": ["console"],
            "level": settings.log_level,
        },
        "loggers": {
            "uvicorn.access": {"propagate": True},
            "uvicorn.error": {"propagate": True},
            "httpx": {"level": "WARNING", "propagate": True},
            "asyncpg": {"level": "WARNING", "propagate": True},
            "app.ingestion": {"level": "DEBUG", "propagate": True},
        },
    })
