"""Pytest fixtures and sample test data generators."""

import base64
import io
import json
import pytest
from pypdf import PdfWriter


@pytest.fixture
def sample_text_content() -> bytes:
    """Sample plain text document bytes."""
    return (
        b"Google Cloud serverless document processing architecture.\n"
        b"Files uploaded to Cloud Storage trigger Pub/Sub push messages to Cloud Run.\n"
        b"Extracted metadata streams directly into BigQuery datasets for analytics.\n"
    )


@pytest.fixture
def sample_pdf_content() -> bytes:
    """Generate a minimal valid PDF document with text layer."""
    writer = PdfWriter()
    # Add a blank page
    page = writer.add_blank_page(width=200, height=200)
    # Write to memory buffer
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


@pytest.fixture
def sample_image_bytes() -> bytes:
    """Simulated image binary bytes."""
    return b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06"


@pytest.fixture
def valid_pubsub_envelope() -> dict:
    """Construct a valid Pub/Sub push notification envelope for GCS upload."""
    gcs_payload = {
        "kind": "storage#object",
        "id": "test-bucket/docs/invoice-101.pdf/123456",
        "bucket": "test-bucket",
        "name": "docs/invoice-101.pdf",
        "contentType": "application/pdf",
        "timeCreated": "2026-10-12T20:00:00.000Z",
        "size": "2048",
    }
    encoded_data = base64.b64encode(json.dumps(gcs_payload).encode("utf-8")).decode("utf-8")

    return {
        "message": {
            "attributes": {
                "bucketId": "test-bucket",
                "objectId": "docs/invoice-101.pdf",
                "eventType": "OBJECT_FINALIZE",
                "eventTime": "2026-10-12T20:00:00.000Z",
            },
            "data": encoded_data,
            "messageId": "msg-abc-987654",
            "publishTime": "2026-10-12T20:00:01.000Z",
        },
        "subscription": "projects/test-project/subscriptions/doc-sub",
    }
