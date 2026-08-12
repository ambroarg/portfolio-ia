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
    ollama_model: str = "llama3.2:3b"
    embedding_model: str = "bge-m3"
    # Ollama decharge un modele apres 5 min par defaut ; le recharger coute ~2 s
    # par question. On les garde residents (cout : ~3,8 Go de RAM pour les deux).
    ollama_keep_alive: str = "30m"

    # Retrieval
    embedding_dim: int = 1024  # checked against bge-m3 via /api/embed
    top_k: int = 4


@lru_cache
def get_settings() -> Settings:
    return Settings()
