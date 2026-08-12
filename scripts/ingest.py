import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader

# Chemins
ROOT = Path(__file__).resolve().parents[1]
PDF_PATH = ROOT / "data" / "raw" / "Ambroise_Arrigoni_CV.pdf"
OUTPUT_PATH = ROOT / "data" / "processed" / "cv.txt"

SECTIONS = [
    "PROFIL",
    "EXPÉRIENCE PROFESSIONNELLE",
    "PROJETS ACADÉMIQUES",
    "FORMATION",
    "LANGUES",
    "Compétences Techniques",
    "CENTRES D'INTÉRÊTS",
]


def extract_text(pdf_path: Path) -> str:
    raw = "\n".join((p.extract_text() or "") for p in PdfReader(str(pdf_path)).pages)
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", raw)).strip()


def split_sections(text: str) -> dict[str, str]:
    escaped_sections = [re.escape(s) for s in SECTIONS]
    pattern = "|".join(escaped_sections)
    parts = re.split(f"({pattern})", text, flags=re.IGNORECASE)
    sections = {"EN-TÊTE": parts[0].strip()} 
    for header, body in zip(parts[1::2], parts[2::2]):
        sections[header.upper()] = body.strip()
    return sections


raw_text = extract_text(PDF_PATH)
sections = split_sections(raw_text)

chunks = [f"{h} — {b}" for h, b in sections.items() if b]

OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
OUTPUT_PATH.write_text("\n\n".join(chunks), encoding="utf-8")
print(f"Fichier écrit dans : {OUTPUT_PATH}")
