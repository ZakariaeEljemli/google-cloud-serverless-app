"""Flask entrypoint and HTTP push handler for Cloud Storage Pub/Sub events."""

import base64
import json
import logging
import sys
from typing import Any, Dict, Tuple

from flask import Flask, jsonify, request

from app.bq_streamer import BigQueryStreamer
from app.config import Config
from app.gcs_client import GCSClient
from app.processor import process_document

# Configure structured logging
logging.basicConfig(
    stream=sys.stdout,
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
)
logger = logging.getLogger("document-pipeline")

app = Flask(__name__)

# Initialize clients
gcs_client = GCSClient(project_id=Config.PROJECT_ID)
bq_streamer = BigQueryStreamer(
    project_id=Config.PROJECT_ID,
    dataset_id=Config.BIGQUERY_DATASET,
    table_id=Config.BIGQUERY_TABLE,
)


@app.route("/", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    """Health check endpoint for Cloud Run readiness and liveness probes."""
    return jsonify(
        {
            "status": "healthy",
            "service": "document-processor",
            "bigquery_table": bq_streamer.table_ref,
        }
    ), 200


def parse_pubsub_message(envelope: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Parse the Pub/Sub envelope and extract GCS notification payload and metadata.

    Args:
        envelope: JSON payload from Pub/Sub push HTTP POST.

    Returns:
        Tuple of (gcs_data_dict, attributes_dict, message_id).
    """
    message = envelope.get("message", {})
    message_id = message.get("messageId", "")
    attributes = message.get("attributes", {})

    gcs_data: Dict[str, Any] = {}
    data_b64 = message.get("data")
    if data_b64:
        try:
            decoded = base64.b64decode(data_b64).decode("utf-8")
            gcs_data = json.loads(decoded)
        except Exception as e:
            logger.warning(f"Could not parse base64 message.data as JSON: {e}")

    return gcs_data, attributes, message_id


@app.route("/process", methods=["POST"])
def process_event():
    """Receive and process GCS object notification pushed via Pub/Sub.

    Returns HTTP 200 on all completions (including caught processing failures)
    to acknowledge the message and avoid infinite Pub/Sub retry storms.
    """
    envelope = request.get_json(silent=True)
    if not envelope or not isinstance(envelope, dict):
        logger.warning(f"Invalid request body received: {request.data}")
        return jsonify({"error": "Bad Request: Expected JSON Pub/Sub envelope"}), 400

    gcs_data, attributes, message_id = parse_pubsub_message(envelope)

    # Check event type if provided in attributes
    event_type = attributes.get("eventType") or gcs_data.get("eventType")
    if event_type and event_type != "OBJECT_FINALIZE":
        logger.info(f"Skipping non-finalize event: {event_type}")
        return jsonify({"status": "skipped", "reason": f"Event type {event_type} ignored"}), 200

    # Extract bucket and object name from either payload data or attributes
    bucket_name = (
        gcs_data.get("bucket")
        or gcs_data.get("bucketId")
        or attributes.get("bucketId")
    )
    file_name = (
        gcs_data.get("name")
        or gcs_data.get("objectId")
        or attributes.get("objectId")
    )
    content_type = gcs_data.get("contentType") or attributes.get("contentType", "")
    upload_date = (
        gcs_data.get("timeCreated")
        or attributes.get("eventTime")
    )

    if not bucket_name or not file_name:
        logger.warning(
            f"Missing bucket or file name in message. Bucket: {bucket_name}, File: {file_name}"
        )
        return jsonify({"status": "skipped", "reason": "Missing bucket or file name"}), 200

    # Skip directory / folder placeholder objects
    if file_name.endswith("/"):
        logger.info(f"Skipping directory placeholder object: {file_name}")
        return jsonify({"status": "skipped", "reason": "Directory object ignored"}), 200

    logger.info(
        f"Processing document: gs://{bucket_name}/{file_name} (message_id={message_id})"
    )

    try:
        # 1. Download file content and metadata from GCS
        content_bytes, gcs_meta = gcs_client.download_blob(bucket_name, file_name)
        effective_mime = content_type or gcs_meta.get("content_type", "")
        effective_size = gcs_meta.get("size", len(content_bytes))
        effective_upload_date = upload_date or gcs_meta.get("time_created")

        # 2. Extract OCR text, word count, and keyword tags
        processed = process_document(file_name, content_bytes, effective_mime)

        # 3. Stream metadata record to BigQuery with idempotency insert_id
        bq_streamer.record_success(
            file_name=file_name,
            bucket_name=bucket_name,
            file_size_bytes=effective_size,
            mime_type=processed["mime_type"],
            upload_date=effective_upload_date,
            word_count=processed["word_count"],
            tags=processed["tags"],
            ocr_preview_snippet=processed["ocr_preview_snippet"],
            insert_id=message_id or None,
        )

        response_data = {
            "status": "success",
            "file_name": file_name,
            "bucket_name": bucket_name,
            "word_count": processed["word_count"],
            "tags": processed["tags"],
        }
        logger.info(f"Successfully processed and recorded gs://{bucket_name}/{file_name}")
        return jsonify(response_data), 200

    except Exception as exc:
        logger.exception(f"Error processing gs://{bucket_name}/{file_name}: {exc}")
        # Stream error record into BigQuery for audit/investigation
        try:
            bq_streamer.record_error(
                file_name=file_name,
                bucket_name=bucket_name,
                error_message=str(exc),
                upload_date=upload_date,
                insert_id=message_id or None,
            )
        except Exception as bq_err:
            logger.error(f"Failed to record error to BigQuery: {bq_err}")

        # Return HTTP 200 to acknowledge Pub/Sub message and prevent infinite retries
        return jsonify(
            {
                "status": "error_recorded",
                "file_name": file_name,
                "error": str(exc),
            }
        ), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=Config.PORT, debug=False)
