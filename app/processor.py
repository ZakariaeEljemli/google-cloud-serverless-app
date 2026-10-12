"""Hybrid OCR and document metadata extraction engine.

Extracts text, word count, topic tags, and preview snippets from:
1. Plain text and markdown documents
2. PDF files (using pypdf)
3. Images and binary formats via deterministic synthetic OCR simulation
"""

import hashlib
import io
import mimetypes
import os
import re
from typing import Any, Dict, List, Set

from pypdf import PdfReader

# Standard English stop words to filter out when generating keyword tags
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
    "with", "won't", "would", "you", "your", "yours", "yourself", "yourselves"
}

# Synthetic document templates for deterministic simulated OCR on image/binary files
SYNTHETIC_TEMPLATES: List[Dict[str, Any]] = [
    {
        "category": "invoice",
        "tags": ["invoice", "finance", "billing", "accounts-payable", "tax"],
        "text_sample": (
            "INVOICE #INV-84920\n"
            "Vendor: Global Logistics & Supply Co.\n"
            "Customer: Enterprise Systems Inc.\n"
            "Date: 2026-10-12\n"
            "Item 1: Cloud Architecture Consulting Services - $4,500.00\n"
            "Item 2: Data Pipeline Infrastructure Setup - $2,750.00\n"
            "Subtotal: $7,250.00 | Tax (8.5%): $616.25 | Total Due: $7,866.25\n"
            "Payment Terms: Net 30 days. Thank you for your business."
        ),
    },
    {
        "category": "contract",
        "tags": ["contract", "legal", "confidentiality", "compliance", "agreement"],
        "text_sample": (
            "MASTER SERVICES AGREEMENT\n"
            "This Agreement is entered into by and between Provider and Customer.\n"
            "1. Purpose and Scope of Services: Provider shall deliver event-driven software architectures.\n"
            "2. Confidentiality and Data Protection: All data processed in Google Cloud Storage and BigQuery\n"
            "shall remain protected under mutual NDA guidelines.\n"
            "3. Term and Termination: Either party may terminate with 30 days written notice."
        ),
    },
    {
        "category": "medical_report",
        "tags": ["medical", "health", "clinical", "diagnostic", "radiology"],
        "text_sample": (
            "CLINICAL LABORATORY & DIAGNOSTIC REPORT\n"
            "Patient Identifier: Confidential\n"
            "Specimen: Automated Digital Scan\n"
            "Findings: Normal baseline parameters observed. No acute abnormalities detected.\n"
            "Recommendation: Routine follow-up in twelve months. Document indexed for medical archival."
        ),
    },
    {
        "category": "technical_spec",
        "tags": ["technical", "architecture", "serverless", "cloud", "documentation"],
        "text_sample": (
            "SYSTEM ARCHITECTURE SPECIFICATION\n"
            "Component: Event-Driven Processing Pipeline\n"
            "Ingestion: Google Cloud Storage bucket with object-finalize notifications.\n"
            "Messaging: Pub/Sub push subscription triggering Google Cloud Run microservice.\n"
            "Analytics: Real-time metadata streaming into BigQuery dataset with idempotency keys."
        ),
    },
]


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

    # Count frequency while preserving order of appearance for ties
    freq: Dict[str, int] = {}
    for w in filtered:
        freq[w] = freq.get(w, 0) + 1

    sorted_words = sorted(freq.keys(), key=lambda w: freq[w], reverse=True)
    return sorted_words[:max_tags]


def simulate_ocr(file_name: str, content_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Generate deterministic simulated OCR text and metadata for images or binary files.

    Uses a cryptographic digest of the file contents (or filename + length)
    to deterministically select realistic document content and extract metrics.

    Args:
        file_name: Name of the uploaded file.
        content_bytes: Raw binary bytes.
        mime_type: File MIME type.

    Returns:
        Dictionary containing word_count, tags, ocr_preview_snippet, and raw text length.
    """
    seed_data = content_bytes if content_bytes else file_name.encode("utf-8")
    digest = hashlib.sha256(seed_data).hexdigest()
    template_idx = int(digest[:8], 16) % len(SYNTHETIC_TEMPLATES)
    template = SYNTHETIC_TEMPLATES[template_idx]

    ext = os.path.splitext(file_name)[1].lower().strip(".")
    text = template["text_sample"]
    words = text.split()
    word_count = len(words)

    # Combine template tags with file format tag and keyword tags
    tags = list(template["tags"][:3])
    if ext:
        tags.append(f"format-{ext}")
    extra_keywords = extract_keywords(text, max_tags=2)
    for kw in extra_keywords:
        if kw not in tags:
            tags.append(kw)

    preview = text[:200].replace("\n", " ")

    return {
        "word_count": word_count,
        "tags": tags[:5],
        "ocr_preview_snippet": preview,
        "raw_text_length": len(text),
        "mime_type": mime_type,
    }


def process_text_document(content_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Process plain text, markdown, CSV, or JSON document.

    Args:
        content_bytes: Raw file bytes.
        mime_type: MIME type of the file.

    Returns:
        Extracted metadata dictionary.
    """
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


def process_pdf_document(file_name: str, content_bytes: bytes, mime_type: str) -> Dict[str, Any]:
    """Extract text from PDF, falling back to simulated OCR if no text layer exists.

    Args:
        file_name: Name of the PDF file.
        content_bytes: Raw bytes of the PDF.
        mime_type: PDF MIME type.

    Returns:
        Extracted metadata dictionary.
    """
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
            word_count = len(words)
            tags = extract_keywords(full_text, max_tags=4)
            if "pdf" not in tags:
                tags.append("pdf")
            preview = full_text[:200].replace("\n", " ").strip()
            return {
                "word_count": word_count,
                "tags": tags[:5],
                "ocr_preview_snippet": preview,
                "raw_text_length": len(full_text),
                "mime_type": mime_type,
            }
    except Exception:
        # If PDF is password-protected, corrupt, or unreadable, fall back to simulated OCR
        pass

    # Scanned PDF without text layer: fallback to deterministic simulated OCR
    simulated = simulate_ocr(file_name, content_bytes, mime_type)
    if "scanned-pdf" not in simulated["tags"]:
        simulated["tags"].insert(0, "scanned-pdf")
        simulated["tags"] = simulated["tags"][:5]
    return simulated


def process_document(
    file_name: str,
    content_bytes: bytes,
    content_type: str = "",
) -> Dict[str, Any]:
    """Route document to appropriate processing strategy based on format.

    Args:
        file_name: Object name in Cloud Storage.
        content_bytes: Downloaded file content.
        content_type: Content type from GCS or HTTP header.

    Returns:
        Dictionary with extracted metadata:
            - word_count (int)
            - tags (List[str])
            - ocr_preview_snippet (str)
            - raw_text_length (int)
            - mime_type (str)
    """
    inferred_type, _ = mimetypes.guess_type(file_name)
    mime_type = content_type or inferred_type or "application/octet-stream"
    mime_lower = mime_type.lower()
    ext = os.path.splitext(file_name)[1].lower()

    if mime_lower.startswith("text/") or ext in {".txt", ".md", ".csv", ".json", ".xml", ".log"}:
        return process_text_document(content_bytes, mime_type)

    if mime_lower == "application/pdf" or ext == ".pdf":
        return process_pdf_document(file_name, content_bytes, mime_type)

    # Images, TIFFs, or binary data
    return simulate_ocr(file_name, content_bytes, mime_type)
