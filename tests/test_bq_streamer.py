"""Unit tests for the BigQuery streamer module."""

from unittest.mock import MagicMock
from app.bq_streamer import BigQueryStreamer


def test_table_ref_generation():
    """Verify table_ref generates expected GCP format."""
    streamer = BigQueryStreamer(
        project_id="test-proj", dataset_id="test_ds", table_id="test_tbl"
    )
    assert streamer.table_ref == "test-proj.test_ds.test_tbl"

    streamer_no_proj = BigQueryStreamer(
        project_id="", dataset_id="test_ds", table_id="test_tbl"
    )
    assert streamer_no_proj.table_ref == "test_ds.test_tbl"


def test_record_success_payload():
    """Verify record_success builds correct row structure and passes insert_id."""
    streamer = BigQueryStreamer(project_id="test-proj", dataset_id="ds", table_id="tbl")
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []
    streamer._client = mock_client

    errors = streamer.record_success(
        file_name="invoice.pdf",
        bucket_name="invoices-bucket",
        file_size_bytes=1024,
        mime_type="application/pdf",
        upload_date="2026-10-12T12:00:00Z",
        word_count=150,
        tags=["invoice", "finance"],
        ocr_preview_snippet="Invoice #1234",
        insert_id="msg-123",
    )

    assert errors == []
    assert mock_client.insert_rows_json.called
    args, kwargs = mock_client.insert_rows_json.call_args
    assert args[0] == "test-proj.ds.tbl"
    rows = args[1]
    assert len(rows) == 1
    row = rows[0]
    assert row["file_name"] == "invoice.pdf"
    assert row["bucket_name"] == "invoices-bucket"
    assert row["status"] == "SUCCESS"
    assert row["word_count"] == 150
    assert row["tags"] == ["invoice", "finance"]
    assert row["error_message"] is None
    assert kwargs["row_ids"] == ["msg-123"]


def test_record_error_payload():
    """Verify record_error creates valid error audit entry with status ERROR."""
    streamer = BigQueryStreamer(project_id="test-proj", dataset_id="ds", table_id="tbl")
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = []
    streamer._client = mock_client

    errors = streamer.record_error(
        file_name="corrupt.bin",
        bucket_name="invoices-bucket",
        error_message="Corrupted file header",
        insert_id="msg-err-456",
    )

    assert errors == []
    assert mock_client.insert_rows_json.called
    args, kwargs = mock_client.insert_rows_json.call_args
    row = args[1][0]
    assert row["file_name"] == "corrupt.bin"
    assert row["status"] == "ERROR"
    assert row["error_message"] == "Corrupted file header"
    assert row["word_count"] is None
    assert row["tags"] == []
    assert kwargs["row_ids"] == ["msg-err-456"]


def test_streaming_returns_errors():
    """Verify that BigQuery client errors are returned to caller."""
    streamer = BigQueryStreamer(project_id="test-proj", dataset_id="ds", table_id="tbl")
    mock_client = MagicMock()
    mock_client.insert_rows_json.return_value = [{"index": 0, "errors": ["Permission denied"]}]
    streamer._client = mock_client

    errors = streamer.record_success(
        file_name="test.txt",
        bucket_name="b",
        file_size_bytes=10,
        mime_type="text/plain",
        upload_date=None,
        word_count=5,
        tags=["txt"],
        ocr_preview_snippet="test",
    )

    assert len(errors) == 1
    assert "Permission denied" in errors[0]["errors"][0]
