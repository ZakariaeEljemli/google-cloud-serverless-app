"""Document processor with Google Cloud Vision OCR and text extraction.

Extracts text, word count, topic tags, and preview snippets from:
1. Plain text and markdown documents (native UTF-8 parsing)
2. PDF files (native text extraction via pypdf + Vision OCR for scanned pages)
3. Images and scans via Google Cloud Vision API (document_text_detection & label_detection)
"""

import io
import logging
import mimetypes
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from pypdf import PdfReader

try:
    from google.cloud import vision
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

logger = logging.getLogger(__name__)

# Standard English stop words and generic document filler words
STOP_WORDS: Set[str] = {
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "aren't", "as", "at", "be", "because", "been", "before", "being",
    "below", "between", "both", "but", "by", "can", "cannot", "could", "did", "do",
    "does", "doing", "down", "during", "each", "few", "for", "from", "further",
    "had", "has", "have", "having", "he", "her", "here", "hers", "herself", "him",
    "himself", "his", "how", "i", "if", "in", "into", "is", "it", "its", "itself",
    "let", "me", "more", "most", "my", "myself", "no", "nor", "not", "of", "off",
    "on", "once", "only", "or", "other", "ought", "our", "ours", "ourselves", "out",
    "over", "own", "same", "she", "should", "so", "some", "such", "than", "that",
    "the", "their", "theirs", "them", "themselves", "then", "there", "these", "they",
    "this", "those", "through", "to", "too", "under", "until", "up", "very", "was",
    "we", "were", "what", "when", "where", "which", "while", "who", "whom", "why",
    "with", "won't", "would", "you", "your", "yours", "yourself", "yourselves",
    # Common document filler words
    "item", "items", "date", "dates", "page", "pages", "total", "subtotal", "amount",
    "number", "numbers", "thank", "thanks", "due", "within", "days", "http", "https",
    "www", "com", "net", "org", "email", "tel", "fax", "phone"
}


def extract_keywords(text: str, max_tags: int = 5) -> List[str]:
    """Extract top frequent and relevant keyword tags from text.

    Args:
        text: The source document text.
        max_tags: Maximum number of keyword tags to return.

    Returns:
        List of lowercase keyword strings.
    """
    words = re.findall(r"\b[a-zA-Z]{3,}\b", text.lower())
    filtered = [w for w in words if w not in STOP_WORDS]
    if not filtered:
        return ["document"]

    freq: Dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.keys(), key=lambda w: freq[w], reverse=True)
    return sorted_words[:max_tags]


def perform_vision_ocr(content_bytes: bytes) -> Tuple[str, List[str]]:
    """Perform Optical Character Recognition using Google Cloud Vision API.

    Calls document_text_detection for dense text recognition and
    label_detection for semantic topic tags.

    Args:
        content_bytes: Image binary data.

    Returns:
        Tuple of (extracted_text, list_of_labels).
    """
    if not VISION_AVAILABLE or not content_bytes:
        return "", []

    try:
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=content_bytes)

        # 1. Dense document text detection
        response = client.document_text_detection(image=image)
        extracted_text = ""
        if response.full_text_annotation and response.full_text_annotation.text:
            extracted_text = response.full_text_annotation.text.strip()

        # 2. Semantic label detection for classification tags
        label_res = client.label_detection(image=image, max_results=5)
        labels = [
            lbl.description.lower().replace(" ", "-")
            for lbl in label_res.label_annotations
            if lbl.description
        ]

        return extracted_text, labels

    except Exception as exc:
        logger.warning(f"Google Cloud Vision OCR call failed or skipped: {exc}")
        return "", []


def fallback_metadata(
    file_name: str,
    content_bytes: bytes,
    mime_type: str,
    labels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Construct honest metadata when no readable text layer is detected."""
    ext = os.path.splitext(file_name)[1].lower().strip(".")
    tags = []
    if ext:
        tags.append(f"format-{ext}")
    if labels:
        tags.extend(labels[:3])
    if not tags:
        tags = ["binary", "unindexed"]

    preview = f"[File: {file_name} ({len(content_bytes)} bytes) - No extractable text]"

    return {
        "word_count": 0,
        "tags": tags[:5],
        "ocr_preview_snippet": preview,
        "raw_text_length": 0,
        "mime_type": mime_type,
    }


def process_text_document(content_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Process plain text, markdown, CSV, or JSON document."""
    try:
        text = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        text = content_bytes.decode("latin-1", errors="replace")

    words = text.split()
    word_count = len(words)
    tags = extract_keywords(text)
    preview = text[:200].replace("\n", " ").strip()

    return {
        "word_count": word_count,
        "tags": tags,
        "ocr_preview_snippet": preview,
        "raw_text_length": len(text),
        "mime_type": mime_type,
    }


def process_pdf_document(
    file_name: str, content_bytes: bytes, mime_type: str
) -> Dict[str, Any]:
    """Extract text from PDF using pypdf, falling back to Vision OCR on scanned pages."""
    try:
        reader = PdfReader(io.BytesIO(content_bytes))
        pages_text = []
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                pages_text.append(extracted)

        full_text = "\n".join(pages_text).strip()
        if full_text:
            words = full_text.split()
            tags = extract_keywords(full_text, max_tags=4)
            if "pdf" not in tags:
                tags.append("pdf")
            preview = full_text[:200].replace("\n", " ").strip()
            return {
                "word_count": len(words),
                "tags": tags[:5],
                "ocr_preview_snippet": preview,
                "raw_text_length": len(full_text),
                "mime_type": mime_type,
            }

        # If PDF has no text layer, attempt Vision OCR on embedded page images
        scanned_texts = []
        scanned_labels: List[str] = []
        for page in reader.pages[:3]:
            for img_file in getattr(page, "images", []):
                ocr_text, labels = perform_vision_ocr(img_file.data)
                if ocr_text:
                    scanned_texts.append(ocr_text)
                scanned_labels.extend(labels)

        scanned_full = "\n".join(scanned_texts).strip()
        if scanned_full:
            words = scanned_full.split()
            tags = ["scanned-pdf"]
            for lbl in scanned_labels:
                if lbl not in tags and len(tags) < 5:
                    tags.append(lbl)
            for kw in extract_keywords(scanned_full, max_tags=3):
                if kw not in tags and len(tags) < 5:
                    tags.append(kw)

            preview = scanned_full[:200].replace("\n", " ").strip()
            return {
                "word_count": len(words),
                "tags": tags[:5],
                "ocr_preview_snippet": preview,
                "raw_text_length": len(scanned_full),
                "mime_type": mime_type,
            }

    except Exception as exc:
        logger.warning(f"Error parsing PDF: {exc}")

    return fallback_metadata(file_name, content_bytes, mime_type)


def process_image_document(
    file_name: str, content_bytes: bytes, mime_type: str
) -> Dict[str, Any]:
    """Perform real Vision OCR on images (PNG, JPEG, TIFF, WEBP)."""
    ocr_text, labels = perform_vision_ocr(content_bytes)

    if ocr_text:
        words = ocr_text.split()
        ext = os.path.splitext(file_name)[1].lower().strip(".")
        tags = []
        if ext:
            tags.append(f"format-{ext}")
        for lbl in labels:
            if lbl not in tags and len(tags) < 5:
                tags.append(lbl)
        for kw in extract_keywords(ocr_text, max_tags=3):
            if kw not in tags and len(tags) < 5:
                tags.append(kw)

        if not tags:
            tags = ["image", "ocr"]

        preview = ocr_text[:200].replace("\n", " ").strip()
        return {
            "word_count": len(words),
            "tags": tags[:5],
            "ocr_preview_snippet": preview,
            "raw_text_length": len(ocr_text),
            "mime_type": mime_type,
        }

    return fallback_metadata(file_name, content_bytes, mime_type, labels=labels)


def process_document(
    file_name: str,
    content_bytes: bytes,
    content_type: str = "",
) -> Dict[str, Any]:
    """Route document to appropriate processing strategy based on format."""
    inferred_type, _ = mimetypes.guess_type(file_name)
    mime_type = content_type or inferred_type or "application/octet-stream"
    mime_lower = mime_type.lower()
    ext = os.path.splitext(file_name)[1].lower()

    if mime_lower.startswith("text/") or ext in {".txt", ".md", ".csv", ".json", ".xml", ".log"}:
        return process_text_document(content_bytes, mime_type)

    if mime_lower == "application/pdf" or ext == ".pdf":
        return process_pdf_document(file_name, content_bytes, mime_type)

    # Images and graphics (PNG, JPEG, TIFF, etc.)
    return process_image_document(file_name, content_bytes, mime_type)
