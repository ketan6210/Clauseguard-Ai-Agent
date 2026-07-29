import zipfile
from pathlib import Path


def validate_uploaded_document(path: Path, suffix: str) -> None:
    if path.stat().st_size == 0:
        raise ValueError("The uploaded document is empty")
    opening = path.read_bytes()[:4096]
    if suffix == ".pdf" and not opening.startswith(b"%PDF-"):
        raise ValueError("The file extension is PDF but the content is not a valid PDF")
    if suffix == ".docx":
        if not opening.startswith(b"PK"):
            raise ValueError("The file extension is DOCX but the content is not a valid DOCX")
        try:
            with zipfile.ZipFile(path) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" not in names or "word/document.xml" not in names:
                    raise ValueError("The DOCX package is missing required document content")
        except zipfile.BadZipFile as exc:
            raise ValueError("The uploaded DOCX package is corrupted") from exc
    if suffix in {".txt", ".md"}:
        if b"\x00" in opening:
            raise ValueError("The text document contains binary content")
        try:
            opening.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Text and Markdown uploads must use UTF-8 encoding") from exc
