"""Unit and integration tests for Flask HTTP Pub/Sub endpoints."""

from unittest.mock import MagicMock, patch
import pytest
from app.main import app


@pytest.fixture
def client():
    """Create Flask test client."""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


def test_health_check(client):
    """Verify /health returns 200 OK and health status."""
    res = client.get("/health")
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "healthy"
    assert "service" in data


def test_process_invalid_payload(client):
    """Verify non-JSON payload returns HTTP 400 Bad Request."""
    res = client.post("/process", data="not json", content_type="text/plain")
    assert res.status_code == 400


def test_process_skip_non_finalize_event(client, valid_pubsub_envelope):
    """Verify non-OBJECT_FINALIZE events (e.g. OBJECT_DELETE) are skipped with HTTP 200."""
    valid_pubsub_envelope["message"]["attributes"]["eventType"] = "OBJECT_DELETE"
    res = client.post("/process", json=valid_pubsub_envelope)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "skipped"
    assert "OBJECT_DELETE" in data["reason"]


def test_process_skip_directory_placeholder(client, valid_pubsub_envelope):
    """Verify directory placeholder objects (trailing slash) are skipped."""
    valid_pubsub_envelope["message"]["attributes"]["objectId"] = "uploads/subfolder/"
    # Clear data so it falls back to attributes
    valid_pubsub_envelope["message"]["data"] = ""
    res = client.post("/process", json=valid_pubsub_envelope)
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "skipped"


def test_process_successful_pipeline(client, valid_pubsub_envelope, sample_text_content):
    """Verify successful end-to-end processing: download, process, and stream."""
    mock_gcs = MagicMock()
    mock_gcs.download_blob.return_value = (
        sample_text_content,
        {"size": len(sample_text_content), "content_type": "text/plain", "time_created": "2026-10-12T20:00:00Z"},
    )

    mock_bq = MagicMock()
    mock_bq.record_success.return_value = []

    with patch("app.main.gcs_client", mock_gcs), patch("app.main.bq_streamer", mock_bq):
        res = client.post("/process", json=valid_pubsub_envelope)

        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "success"
        assert data["file_name"] == "docs/invoice-101.pdf"
        assert mock_gcs.download_blob.called
        assert mock_bq.record_success.called


def test_process_failure_recorded_in_bq(client, valid_pubsub_envelope):
    """Verify that file download/parse failures record to BigQuery and return HTTP 200."""
    mock_gcs = MagicMock()
    mock_gcs.download_blob.side_effect = Exception("Blob download failed: 404 Not Found")

    mock_bq = MagicMock()
    mock_bq.record_error.return_value = []

    with patch("app.main.gcs_client", mock_gcs), patch("app.main.bq_streamer", mock_bq):
        res = client.post("/process", json=valid_pubsub_envelope)

        assert res.status_code == 200
        data = res.get_json()
        assert data["status"] == "error_recorded"
        assert "404 Not Found" in data["error"]
        assert mock_bq.record_error.called
        # Check that insert_id was passed
        kwargs = mock_bq.record_error.call_args[1]
        assert kwargs["insert_id"] == "msg-abc-987654"
