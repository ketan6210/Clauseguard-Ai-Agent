from pathlib import Path

import pytest

from app.services.upload_security import validate_uploaded_document


def test_rejects_spoofed_pdf(tmp_path: Path):
    path = tmp_path / "malware.pdf"
    path.write_bytes(b"MZ executable content")

    with pytest.raises(ValueError, match="not a valid PDF"):
        validate_uploaded_document(path, ".pdf")


def test_accepts_utf8_text_and_rejects_binary_text(tmp_path: Path):
    text = tmp_path / "contract.txt"
    text.write_text("1. Payment. Invoices are Net 30.", encoding="utf-8")
    validate_uploaded_document(text, ".txt")

    text.write_bytes(b"contract\x00binary")
    with pytest.raises(ValueError, match="binary content"):
        validate_uploaded_document(text, ".txt")
