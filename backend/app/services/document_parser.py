from pathlib import Path

from app.core.config import settings
from app.schemas.review import DocumentPage


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}


def _pdf_page_text(page) -> str:
    text = page.get_text("text")
    if text.strip() or not settings.ocr_enabled:
        return text
    try:
        text_page = page.get_textpage_ocr(
            language=settings.ocr_language,
            dpi=settings.ocr_dpi,
            full=True,
        )
        return page.get_text("text", textpage=text_page)
    except (RuntimeError, AttributeError) as exc:
        raise ValueError(
            "This PDF appears to be scanned. OCR was attempted but Tesseract "
            "is unavailable or could not read the page."
        ) from exc


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
            pages = [
                DocumentPage(page_number=index + 1, text=_pdf_page_text(page))
                for index, page in enumerate(document)
            ]
    else:
        from docx import Document

        document = Document(path)
        pages = [DocumentPage(page_number=1, text="\n".join(p.text for p in document.paragraphs))]

    if not any(page.text.strip() for page in pages):
        raise ValueError("The document contains no extractable text.")
    return pages
