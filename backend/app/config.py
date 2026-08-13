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
    # Score cosinus minimal pour qu'un passage soit retenu. Mesure sur 24
    # questions : les questions legitimes vont de 0,40 a 0,60, les questions
    # hors sujet de 0,29 a 0,41. Les bandes se chevauchent, donc aucun seuil
    # ne les separe proprement : 0,35 est volontairement bas, il ecarte le
    # hors-sujet le plus net sans jamais bloquer une vraie question. Monter a
    # 0,40 filtre davantage mais commence a risquer des refus injustifies.
    min_score: float = 0.35

    # Origines autorisees par CORS, separees par des virgules. Volontairement
    # restreint au poste de dev : en Docker le frontend passe par nginx sur la
    # meme origine et n'emet aucune requete cross-origin. A remplacer par le
    # domaine du portfolio lors du deploiement.
    allowed_origins: str = "http://localhost:5500,http://127.0.0.1:5500"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
