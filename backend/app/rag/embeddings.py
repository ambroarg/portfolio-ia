"""Embedding dim 1024"""

import ollama

from app.config import Settings


def embed_texts(client: ollama.Client, settings: Settings, texts: list[str]) -> list[list[float]]:
    vectors = client.embed(
        model=settings.embedding_model,
        input=texts,
        keep_alive=settings.ollama_keep_alive,
    ).embeddings
    if len(vectors) != len(texts):
        raise ValueError(f"{len(vectors)} vecteurs pour {len(texts)} textes")
    if len(vectors[0]) != settings.embedding_dim:
        raise ValueError(f"dimension {len(vectors[0])} au lieu de {settings.embedding_dim}")
    return [list(v) for v in vectors]
