from pathlib import Path

from app.schemas.review import DocumentPage


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def parse_document(file_path: str | Path) -> list[DocumentPage]:
    path = Path(file_path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {suffix}")

    if suffix in {".txt", ".md"}:
        pages = [DocumentPage(page_number=1, text=path.read_text(encoding="utf-8", errors="replace"))]
    elif suffix == ".pdf":
        import fitz

        with fitz.open(path) as document:
            pages = [DocumentPage(page_number=index + 1, text=page.get_text("text")) for index, page in enumerate(document)]
    else:
        from docx import Document

        document = Document(path)
        pages = [DocumentPage(page_number=1, text="\n".join(p.text for p in document.paragraphs))]

    if not any(page.text.strip() for page in pages):
        raise ValueError("The document contains no extractable text. OCR is not included in the MVP.")
    return pages
