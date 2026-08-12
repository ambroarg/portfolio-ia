"""Recherche Vectorielle dans Qdrant"""

from dataclasses import dataclass

import ollama
from qdrant_client import QdrantClient

from app.config import Settings
from app.rag.embeddings import embed_texts


@dataclass(frozen=True)
class Passage:
    score: float
    text: str
    section: str


def search(
    qdrant: QdrantClient,
    client: ollama.Client,
    settings: Settings,
    question: str,
    k: int | None = None,
) -> list[Passage]:
    vector = embed_texts(client, settings, [question])[0]
    response = qdrant.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=k or settings.top_k,
        with_payload=True,
    )
    return [
        Passage(
            score=point.score,
            text=(point.payload or {}).get("text", ""),
            section=(point.payload or {}).get("section", ""),
        )
        for point in response.points
    ]
