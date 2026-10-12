"""Unit tests for the document processing and hybrid OCR engine."""

from unittest.mock import MagicMock, patch
from app.processor import (
    extract_keywords,
    process_document,
    process_pdf_document,
    process_text_document,
    simulate_ocr,
)


def test_extract_keywords():
    """Verify stop words are excluded and top terms are extracted."""
    sample = "Cloud computing and serverless cloud architecture with Google Cloud"
    tags = extract_keywords(sample, max_tags=3)
    assert "cloud" in tags
    assert "computing" in tags or "serverless" in tags or "architecture" in tags
    assert "and" not in tags
    assert "with" not in tags
    assert len(tags) <= 3


def test_extract_keywords_empty():
    """Verify fallback when no words match criteria."""
    tags = extract_keywords("the the the and")
    assert tags == ["document"]


def test_process_text_document(sample_text_content):
    """Test text processing extracts word count and preview correctly."""
    result = process_text_document(sample_text_content, "text/plain")

    assert result["word_count"] > 10
    assert result["mime_type"] == "text/plain"
    assert "serverless" in result["tags"] or "cloud" in result["tags"]
    assert len(result["ocr_preview_snippet"]) > 0
    assert len(result["ocr_preview_snippet"]) <= 200


def test_simulate_ocr_determinism(sample_image_bytes):
    """Verify simulated OCR gives identical results for identical byte inputs."""
    res1 = simulate_ocr("invoice_scan.png", sample_image_bytes, "image/png")
    res2 = simulate_ocr("invoice_scan.png", sample_image_bytes, "image/png")

    assert res1["word_count"] == res2["word_count"]
    assert res1["tags"] == res2["tags"]
    assert res1["ocr_preview_snippet"] == res2["ocr_preview_snippet"]
    assert res1["word_count"] > 0
    assert "format-png" in res1["tags"]


def test_process_pdf_document_with_fallback(sample_pdf_content):
    """Verify that a PDF without text layer falls back to simulated OCR gracefully."""
    result = process_pdf_document("scanned_receipt.pdf", sample_pdf_content, "application/pdf")

    assert result["word_count"] > 0
    assert "scanned-pdf" in result["tags"]
    assert result["mime_type"] == "application/pdf"
    assert len(result["ocr_preview_snippet"]) > 0


def test_process_pdf_document_with_extracted_text():
    """Verify that a PDF with extractable text returns real extracted text metrics."""
    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Quarterly financial report revenue growth statement."

    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]

    with patch("app.processor.PdfReader", return_value=mock_reader):
        result = process_pdf_document("report.pdf", b"mock-pdf-bytes", "application/pdf")
        assert result["word_count"] == 6
        assert "financial" in result["tags"] or "quarterly" in result["tags"]
        assert "pdf" in result["tags"]


def test_process_document_routing(sample_text_content, sample_image_bytes):
    """Test process_document routes to correct sub-engine based on filename/mime."""
    # Text routing
    txt_res = process_document("readme.txt", sample_text_content, "text/plain")
    assert txt_res["mime_type"] == "text/plain"

    # Image routing
    img_res = process_document("photo.jpg", sample_image_bytes, "image/jpeg")
    assert img_res["mime_type"] == "image/jpeg"
    assert "format-jpg" in img_res["tags"]
