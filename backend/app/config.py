"""Application settings, loaded from environment variables (see .env.example)."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/app/config.py -> repository root
ROOT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT_DIR / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"


class Settings(BaseSettings):
    """Runtime configuration, read from the environment or the root .env file.

    `qdrant_url` and `qdrant_api_key` have no default on purpose: the app fails
    fast at startup rather than silently pointing at the wrong vector store.
    """

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Qdrant Cloud
    qdrant_url: str
    qdrant_api_key: str
    qdrant_collection: str = "portfolio_data"

    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "gemma4:e4b"
    embedding_model: str = "bge-m3"

    # Retrieval
    embedding_dim: int = 1024  # checked against bge-m3 via /api/embed
    top_k: int = 4


@lru_cache
def get_settings() -> Settings:
    """Return the cached settings instance, so the .env file is read only once."""
    return Settings()
