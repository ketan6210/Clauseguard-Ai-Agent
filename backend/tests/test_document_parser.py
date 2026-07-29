import pytest

from app.services import document_parser


class ScannedPage:
    def __init__(self, ocr_text="OCR contract text", fail=False):
        self.ocr_text = ocr_text
        self.fail = fail
        self.ocr_called = False

    def get_text(self, mode, textpage=None):
        return self.ocr_text if textpage else ""

    def get_textpage_ocr(self, **kwargs):
        self.ocr_called = True
        if self.fail:
            raise RuntimeError("missing tesseract")
        return object()


def test_blank_pdf_page_uses_ocr(monkeypatch):
    monkeypatch.setattr(document_parser.settings, "ocr_enabled", True)
    page = ScannedPage()

    assert document_parser._pdf_page_text(page) == "OCR contract text"
    assert page.ocr_called


def test_scanned_pdf_has_clear_error_when_ocr_engine_is_missing(monkeypatch):
    monkeypatch.setattr(document_parser.settings, "ocr_enabled", True)

    with pytest.raises(ValueError, match="Tesseract"):
        document_parser._pdf_page_text(ScannedPage(fail=True))
