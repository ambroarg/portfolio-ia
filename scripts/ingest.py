"""Extract the CV, split it into self-contained chunks, embed them and index them in Qdrant.

The validation search at the bottom now goes through Qdrant, so it exercises
the whole chain. It will move to its own script once the API needs it.
"""

import re
import sys
import unicodedata
import uuid
from pathlib import Path

import ollama
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings, get_settings

PDF_PATH = ROOT / "data" / "raw" / "Ambroise_Arrigoni_CV.pdf"
OUTPUT_PATH = ROOT / "data" / "processed" / "cv.txt"
SOURCE = "cv"

SECTIONS = [
    "PROFIL",
    "EXPÉRIENCE PROFESSIONNELLE",
    "PROJETS ACADÉMIQUES",
    "FORMATION",
    "LANGUES & COMPÉTENCES TECHNIQUES",
    "CENTRES D'INTÉRÊTS",
]

MIN_SECTION_LEN = 40

QUESTIONS = [
    "Comment le contacter ?",
    "Où a-t-il étudié ?",
    "Parle-t-il espagnol ?",
    "Quelles sont ses compétences en machine learning ?",
    "A-t-il une expérience à l'étranger ?",
]


def extract_text(pdf_path: Path) -> str:
    raw = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()


def split_sections(text: str) -> dict[str, str]:
    pattern = "|".join(re.escape(s) for s in SECTIONS)
    # Les \b evitent que "FORMATION" matche dans "information".
    parts = re.split(rf"\b({pattern})\b", text, flags=re.IGNORECASE)

    sections = {"EN-TÊTE": parts[0].strip()}
    for header, body in zip(parts[1::2], parts[2::2]):
        key = header.upper()
        if key in sections:
            raise ValueError(f"section '{key}' rencontrée deux fois : découpage ambigu")
        sections[key] = body.strip(" :•–—")
    return sections


def build_chunks(sections: dict[str, str]) -> list[tuple[str, str]]:
    return [(header, f"{header} — {body}") for header, body in sections.items() if body]


def check_chunks(text: str, sections: dict[str, str], chunks: list[tuple[str, str]]) -> None:
    if len(text) < 1000:
        raise ValueError(f"texte extrait trop court ({len(text)} car.) : couche texte absente ?")

    missing = [s for s in SECTIONS if s.upper() not in sections]
    if missing:
        raise ValueError(f"sections introuvables dans le PDF : {missing}")

    short = [h for h, b in sections.items() if 0 < len(b) < MIN_SECTION_LEN]
    if short:
        raise ValueError(f"sections suspectement courtes : {short}")

    covered = sum(len(t) for _, t in chunks)
    if covered < 0.8 * len(text):
        raise ValueError(f"chunks ne couvrent que {covered}/{len(text)} caractères")


def embed_texts(client: ollama.Client, settings: Settings, texts: list[str]) -> list[list[float]]:
    vectors = client.embed(model=settings.embedding_model, input=texts).embeddings
    if len(vectors) != len(texts):
        raise ValueError(f"{len(vectors)} vecteurs pour {len(texts)} textes")
    if len(vectors[0]) != settings.embedding_dim:
        raise ValueError(f"dimension {len(vectors[0])} au lieu de {settings.embedding_dim}")
    return [list(v) for v in vectors]


def ensure_collection(qdrant: QdrantClient, name: str, dim: int) -> None:
    if qdrant.collection_exists(name):
        return
    qdrant.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    print(f"collection '{name}' créée ({dim} dimensions, cosine)")


def upsert_chunks(
    qdrant: QdrantClient,
    name: str,
    chunks: list[tuple[str, str]],
    vectors: list[list[float]],
    source: str,
) -> int:
    points = [
        PointStruct(
            # ID deterministe : relancer le script met a jour au lieu de dupliquer.
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"{source}#{index}")),
            vector=vector,
            # Qdrant ne rend que ce qu'on stocke : sans "text", la recherche est inexploitable.
            payload={"text": text, "section": section, "source": source},
        )
        for index, ((section, text), vector) in enumerate(zip(chunks, vectors))
    ]
    qdrant.upsert(collection_name=name, points=points, wait=True)
    return len(points)


def search(
    qdrant: QdrantClient,
    client: ollama.Client,
    settings: Settings,
    question: str,
    k: int = 3,
) -> list[tuple[float, str]]:
    vector = embed_texts(client, settings, [question])[0]
    response = qdrant.query_points(
        collection_name=settings.qdrant_collection,
        query=vector,
        limit=k,
        with_payload=True,
    )
    return [(point.score, (point.payload or {}).get("text", "")) for point in response.points]


def run_validation(qdrant: QdrantClient, client: ollama.Client, settings: Settings) -> None:
    for question in QUESTIONS:
        print(f"\n{question}")
        for score, text in search(qdrant, client, settings, question):
            print(f"  {score:.3f}  {text[:70]}")


def main() -> None:
    settings = get_settings()
    client = ollama.Client(host=settings.ollama_base_url)
    qdrant = QdrantClient(url=settings.qdrant_url, api_key=settings.qdrant_api_key)

    text = extract_text(PDF_PATH)
    sections = split_sections(text)
    chunks = build_chunks(sections)
    check_chunks(text, sections, chunks)

    texts = [t for _, t in chunks]
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n\n".join(texts), encoding="utf-8")
    print(f"{len(chunks)} chunks écrits dans {OUTPUT_PATH}")

    vectors = embed_texts(client, settings, texts)
    print(f"{len(vectors)} vecteurs de dimension {len(vectors[0])}")

    ensure_collection(qdrant, settings.qdrant_collection, settings.embedding_dim)
    upserted = upsert_chunks(qdrant, settings.qdrant_collection, chunks, vectors, SOURCE)
    total = qdrant.count(settings.qdrant_collection).count
    print(f"{upserted} points upsertés, {total} points dans la collection")

    run_validation(qdrant, client, settings)


if __name__ == "__main__":
    main()
