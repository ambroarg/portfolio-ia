"""FastAPI du RAG chat endpoint."""

import json
from collections.abc import Iterator
from functools import lru_cache

import ollama
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from qdrant_client import QdrantClient

from app.config import get_settings
from app.rag.prompt import NO_CONTEXT_ANSWER, SYSTEM_PROMPT, build_user_prompt
from app.rag.retrieval import Passage, search

app = FastAPI(
    title="Portfolio IA Ambroise Arrigoni",
    description="Chat RAG repondant aux questions de recruteurs sur Ambroise Arrigoni.",
)

# A restreindre au domaine du portfolio avant la mise en production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


@lru_cache
def get_ollama_client() -> ollama.Client:
    return ollama.Client(host=get_settings().ollama_base_url)


@lru_cache
def get_qdrant_client() -> QdrantClient:
    settings = get_settings()
    return QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)


class ChatRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Source(BaseModel):
    section: str
    score: float


class ChatResponse(BaseModel):
    answer: str
    sources: list[Source]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    settings = get_settings()
    client = get_ollama_client()

    passages = search(get_qdrant_client(), client, settings, request.question)
    if not passages:
        return ChatResponse(answer=NO_CONTEXT_ANSWER, sources=[])

    response = client.chat(
        model=settings.ollama_model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(request.question, passages)},
        ],
        # Temperature basse : on veut de la restitution factuelle, pas de la creativite.
        # Je veux pas que l'IA m'invente une vie mais quelle se base sur son RAG
        options={"temperature": 0.2},
        keep_alive=settings.ollama_keep_alive,
    )

    return ChatResponse(
        answer=(response.message.content or "").strip(),
        sources=[Source(section=p.section, score=round(p.score, 3)) for p in passages],
    )


def _sse(event: str, payload: dict) -> str:
    """Format one Server-Sent Event. The blank line is what flushes it."""
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_messages(question: str, passages: list[Passage]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(question, passages)},
    ]


def _stream_answer(question: str) -> Iterator[str]:
    settings = get_settings()
    client = get_ollama_client()

    passages = search(get_qdrant_client(), client, settings, question)

    # Les sources partent en premier : l'interface peut les afficher pendant
    # que le modele genere encore.
    yield _sse(
        "sources",
        {"sources": [{"section": p.section, "score": round(p.score, 3)} for p in passages]},
    )

    if not passages:
        yield _sse("token", {"text": NO_CONTEXT_ANSWER})
        yield _sse("done", {})
        return

    for part in client.chat(
        model=settings.ollama_model,
        messages=_build_messages(question, passages),
        options={"temperature": 0.2},
        keep_alive=settings.ollama_keep_alive,
        stream=True,
    ):
        text = part.message.content or ""
        if text:
            yield _sse("token", {"text": text})

    yield _sse("done", {})


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        _stream_answer(request.question),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            # Empeche nginx de bufferiser la reponse et d'annuler le streaming.
            "X-Accel-Buffering": "no",
        },
    )
