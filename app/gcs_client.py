"""Google Cloud Storage client wrapper for document retrieval."""

import logging
from typing import Any, Dict, Optional, Tuple
from google.cloud import storage

logger = logging.getLogger(__name__)


class GCSClient:
    """Wrapper for downloading objects and inspecting metadata from Google Cloud Storage."""

    def __init__(self, project_id: Optional[str] = None):
        """Initialize GCS client."""
        self.project_id = project_id
        self._client: Optional[storage.Client] = None

    @property
    def client(self) -> storage.Client:
        """Lazy initialization of storage.Client."""
        if self._client is None:
            if self.project_id:
                self._client = storage.Client(project=self.project_id)
            else:
                self._client = storage.Client()
        return self._client

    def download_blob(
        self, bucket_name: str, blob_name: str
    ) -> Tuple[bytes, Dict[str, Any]]:
        """Download blob content bytes and metadata.

        Args:
            bucket_name: Name of the GCS bucket.
            blob_name: Name/path of the object in GCS.

        Returns:
            Tuple of (content_bytes, metadata_dict).

        Raises:
            Exception if blob cannot be found or downloaded.
        """
        logger.info(f"Downloading gs://{bucket_name}/{blob_name}")
        bucket = self.client.bucket(bucket_name)
        blob = bucket.get_blob(blob_name)

        if blob is None:
            raise FileNotFoundError(f"Object gs://{bucket_name}/{blob_name} not found in GCS.")

        content_bytes = blob.download_as_bytes()

        upload_time_iso = None
        if blob.time_created:
            upload_time_iso = blob.time_created.isoformat()

        metadata = {
            "size": blob.size or len(content_bytes),
            "content_type": blob.content_type or "",
            "time_created": upload_time_iso,
            "md5_hash": blob.md5_hash or "",
        }

        return content_bytes, metadata
