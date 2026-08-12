"""Extract the CV, split it into self-contained chunks and embed them with Ollama.

Temporary stage: the vectors stay in memory and are only consumed by the
validation search at the bottom. Persistence to Qdrant comes next, and the
search will then move to its own script.
"""

import re
import unicodedata
from pathlib import Path

import ollama
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "raw" / "Ambroise_Arrigoni_CV.pdf"
OUTPUT_PATH = ROOT / "data" / "processed" / "cv.txt"

OLLAMA_HOST = "http://localhost:11434"
EMBEDDING_MODEL = "bge-m3"
EMBEDDING_DIM = 1024

SECTIONS = [
    "PROFIL",
    "EXPÉRIENCE PROFESSIONNELLE",
    "PROJETS ACADÉMIQUES",
    "FORMATION",
    "LANGUES & COMPÉTENCES TECHNIQUES",
    "CENTRES D'INTÉRÊTS",
]

MIN_SECTION_LEN = 40

client = ollama.Client(host=OLLAMA_HOST)


def extract_text(pdf_path: Path) -> str:
    raw = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()


def split_sections(text: str) -> dict[str, str]:
    pattern = "|".join(re.escape(s) for s in SECTIONS)
    parts = re.split(rf"\b({pattern})\b", text, flags=re.IGNORECASE)

    sections = {"EN-TÊTE": parts[0].strip()}
    for header, body in zip(parts[1::2], parts[2::2]):
        key = header.upper()
        if key in sections:
            raise ValueError(f"section '{key}' rencontrée deux fois : découpage ambigu")
        sections[key] = body.strip(" :•–—")
    return sections


def build_chunks(sections: dict[str, str]) -> list[str]:
    return [f"{header} — {body}" for header, body in sections.items() if body]


def check_chunks(text: str, sections: dict[str, str], chunks: list[str]) -> None:
    if len(text) < 1000:
        raise ValueError(f"texte extrait trop court ({len(text)} car.) : couche texte absente ?")

    missing = [s for s in SECTIONS if s.upper() not in sections]
    if missing:
        raise ValueError(f"sections introuvables dans le PDF : {missing}")

    short = [h for h, b in sections.items() if 0 < len(b) < MIN_SECTION_LEN]
    if short:
        raise ValueError(f"sections suspectement courtes : {short}")

    covered = sum(len(c) for c in chunks)
    if covered < 0.8 * len(text):
        raise ValueError(f"chunks ne couvrent que {covered}/{len(text)} caractères")


def embed_texts(texts: list[str]) -> list[list[float]]:
    vectors = client.embed(model=EMBEDDING_MODEL, input=texts).embeddings
    if len(vectors) != len(texts):
        raise ValueError(f"{len(vectors)} vecteurs pour {len(texts)} textes")
    if len(vectors[0]) != EMBEDDING_DIM:
        raise ValueError(f"dimension {len(vectors[0])} au lieu de {EMBEDDING_DIM}")
    return vectors # type: ignore


# validation temporaire

QUESTIONS = [
    "Comment le contacter ?",
    "Où a-t-il étudié ?",
    "Parle-t-il espagnol ?",
    "Quelles sont ses compétences en machine learning ?",
    "A-t-il une expérience à l'étranger ?",
]


def search(question: str, vectors: list[list[float]], chunks: list[str], k: int = 3,) -> list[tuple[float, str]]:
    query_vector = embed_texts([question])[0]
    scored = [
        (sum(a * b for a, b in zip(query_vector, vector)), chunk)
        for vector, chunk in zip(vectors, chunks)
    ]
    return sorted(scored, key=lambda pair: pair[0], reverse=True)[:k]


def run_validation(vectors: list[list[float]], chunks: list[str]) -> None:
    for question in QUESTIONS:
        print(f"\n{question}")
        for score, chunk in search(question, vectors, chunks):
            print(f"  {score:.3f}  {chunk[:100]}")


# ----------------------------------------------------------------------------


def main() -> None:
    text = extract_text(PDF_PATH)
    sections = split_sections(text)
    chunks = build_chunks(sections)
    check_chunks(text, sections, chunks)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n\n".join(chunks), encoding="utf-8")
    print(f"{len(chunks)} chunks écrits dans {OUTPUT_PATH}")

    vectors = embed_texts(chunks)
    print(f"{len(vectors)} vecteurs de dimension {len(vectors[0])}")

    run_validation(vectors, chunks)


if __name__ == "__main__":
    main()
