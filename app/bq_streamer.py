"""BigQuery streaming ingestion client for document metadata."""

from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from google.cloud import bigquery

from app.config import Config

logger = logging.getLogger(__name__)


class BigQueryStreamer:
    """Streams document metadata rows into BigQuery with deduplication support."""

    SCHEMA = [
        bigquery.SchemaField("file_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("bucket_name", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("file_size_bytes", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("mime_type", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("upload_date", "TIMESTAMP", mode="NULLABLE"),
        bigquery.SchemaField("processed_at", "TIMESTAMP", mode="REQUIRED"),
        bigquery.SchemaField("status", "STRING", mode="REQUIRED"),
        bigquery.SchemaField("word_count", "INTEGER", mode="NULLABLE"),
        bigquery.SchemaField("tags", "STRING", mode="REPEATED"),
        bigquery.SchemaField("ocr_preview_snippet", "STRING", mode="NULLABLE"),
        bigquery.SchemaField("error_message", "STRING", mode="NULLABLE"),
    ]

    def __init__(
        self,
        project_id: Optional[str] = None,
        dataset_id: Optional[str] = None,
        table_id: Optional[str] = None,
    ):
        """Initialize BigQuery streamer."""
        self.project_id = project_id or Config.PROJECT_ID
        self.dataset_id = dataset_id or Config.BIGQUERY_DATASET
        self.table_id = table_id or Config.BIGQUERY_TABLE
        self._client: Optional[bigquery.Client] = None

    @property
    def client(self) -> bigquery.Client:
        """Lazy initialization of bigquery.Client."""
        if self._client is None:
            if self.project_id:
                self._client = bigquery.Client(project=self.project_id)
            else:
                self._client = bigquery.Client()
        return self._client

    @property
    def table_ref(self) -> str:
        """Fully qualified table ID in format: project.dataset.table or dataset.table."""
        if self.project_id:
            return f"{self.project_id}.{self.dataset_id}.{self.table_id}"
        return f"{self.dataset_id}.{self.table_id}"

    def stream_row(
        self,
        row_data: Dict[str, Any],
        insert_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Insert a single row into BigQuery using streaming insert.

        Args:
            row_data: Dictionary containing fields matching the BigQuery table schema.
            insert_id: Unique identifier used by BigQuery to deduplicate retries.

        Returns:
            List of insertion errors, or an empty list if successful.
        """
        row_ids = [insert_id] if insert_id else None
        logger.info(
            f"Streaming record for {row_data.get('file_name')} to {self.table_ref} (insert_id={insert_id})"
        )

        errors = self.client.insert_rows_json(
            self.table_ref,
            [row_data],
            row_ids=row_ids,
        )

        if errors:
            logger.error(f"BigQuery streaming errors encountered: {errors}")
        else:
            logger.info("BigQuery streaming insert completed successfully.")

        return errors

    def record_success(
        self,
        file_name: str,
        bucket_name: str,
        file_size_bytes: int,
        mime_type: str,
        upload_date: Optional[str],
        word_count: int,
        tags: List[str],
        ocr_preview_snippet: str,
        insert_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Record successful document processing metadata."""
        now_iso = datetime.now(timezone.utc).isoformat()
        row = {
            "file_name": file_name,
            "bucket_name": bucket_name,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "upload_date": upload_date,
            "processed_at": now_iso,
            "status": "SUCCESS",
            "word_count": word_count,
            "tags": tags,
            "ocr_preview_snippet": ocr_preview_snippet,
            "error_message": None,
        }
        return self.stream_row(row, insert_id=insert_id)

    def record_error(
        self,
        file_name: str,
        bucket_name: str,
        error_message: str,
        file_size_bytes: Optional[int] = None,
        mime_type: Optional[str] = None,
        upload_date: Optional[str] = None,
        insert_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Record failed document processing metadata."""
        now_iso = datetime.now(timezone.utc).isoformat()
        row = {
            "file_name": file_name,
            "bucket_name": bucket_name,
            "file_size_bytes": file_size_bytes,
            "mime_type": mime_type,
            "upload_date": upload_date,
            "processed_at": now_iso,
            "status": "ERROR",
            "word_count": None,
            "tags": [],
            "ocr_preview_snippet": None,
            "error_message": error_message,
        }
        return self.stream_row(row, insert_id=insert_id)
