from pathlib import Path
from pypdf import PdfReader
from docx import Document


def read_document(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if ext == ".pdf":
        return "\n\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if ext == ".docx":
        return "\n".join(p.text for p in Document(str(path)).paragraphs)
    raise ValueError(f"Unsupported file type: {ext}")


def chunk_text(text: str, max_chars: int = 1000, overlap_chars: int = 120) -> list[dict]:
    paragraphs = [p.strip() for p in text.replace("\r\n", "\n").split("\n") if p.strip()]
    chunks: list[dict] = []
    buf = ""
    heading = None
    for p in paragraphs:
        if p.startswith("#"):
            heading = p.lstrip("#").strip()
        if len(buf) + len(p) + 1 <= max_chars:
            buf = (buf + "\n" + p).strip()
        else:
            if buf:
                chunks.append({"heading": heading, "content": buf})
            tail = buf[-overlap_chars:] if overlap_chars and buf else ""
            buf = (tail + "\n" + p).strip()
    if buf:
        chunks.append({"heading": heading, "content": buf})
    return chunks
