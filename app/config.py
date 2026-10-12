"""Application configuration loaded from environment variables."""

import os

class Config:
    """Environment configuration settings for the pipeline processor."""

    PROJECT_ID = (
        os.getenv("GCP_PROJECT")
        or os.getenv("GOOGLE_CLOUD_PROJECT")
        or os.getenv("GCLOUD_PROJECT")
        or ""
    )
    BIGQUERY_DATASET = os.getenv("BIGQUERY_DATASET", "doc_pipeline_ds")
    BIGQUERY_TABLE = os.getenv("BIGQUERY_TABLE", "processed_documents")
    MAX_PREVIEW_LENGTH = int(os.getenv("MAX_PREVIEW_LENGTH", "200"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    PORT = int(os.getenv("PORT", "8080"))

    @classmethod
    def get_table_ref(cls) -> str:
        """Returns the fully qualified BigQuery table reference."""
        if cls.PROJECT_ID:
            return f"{cls.PROJECT_ID}.{cls.BIGQUERY_DATASET}.{cls.BIGQUERY_TABLE}"
        return f"{cls.BIGQUERY_DATASET}.{cls.BIGQUERY_TABLE}"
