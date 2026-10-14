#!/usr/bin/env bash
# End-to-end testing script for the serverless document pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf "$TEMP_DIR"' EXIT

if [[ -f "${SCRIPT_DIR}/env.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/env.sh"
fi

: "${PROJECT_ID:?Error: PROJECT_ID is required. Set in scripts/env.sh or environment.}"
: "${BUCKET_NAME:=${PROJECT_ID}-doc-ingest}"
: "${BIGQUERY_DATASET:=doc_pipeline_ds}"
: "${BIGQUERY_TABLE:=processed_documents}"

echo "=========================================================="
echo " Testing Document Processing Pipeline End-to-End          "
echo " Target Bucket: gs://${BUCKET_NAME}"
echo " BigQuery:      ${PROJECT_ID}:${BIGQUERY_DATASET}.${BIGQUERY_TABLE}"
echo "=========================================================="

echo "==> [1/3] Generating test documents..."
# 1. Plain text file
cat << 'EOF' > "${TEMP_DIR}/sample_invoice.txt"
INVOICE #98124
Vendor: Acme Cloud Solutions LLC
Client: Horizon Analytics
Date: 2026-10-12
Item 1: Serverless Event Architecture Setup - $3,500.00
Item 2: BigQuery Schema Optimization - $1,200.00
Total: $4,700.00
Payment due within 30 days. Thank you for your business.
EOF

# 2. Simulated PNG image
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10\x00\x00\x00\x10\x08\x06\x00\x00\x00' > "${TEMP_DIR}/sample_receipt.png"

# 3. Simple text document
cat << 'EOF' > "${TEMP_DIR}/sample_spec.md"
# System Architecture Specification
This document outlines the event-driven ingestion pipeline on Google Cloud.
Files uploaded to Cloud Storage emit Pub/Sub messages to trigger Cloud Run.
Extracted metadata is streamed directly into BigQuery.
EOF

echo "==> [2/3] Uploading sample files to gs://${BUCKET_NAME}/..."
gcloud storage cp "${TEMP_DIR}/sample_invoice.txt" "gs://${BUCKET_NAME}/test-uploads/sample_invoice.txt"
gcloud storage cp "${TEMP_DIR}/sample_receipt.png" "gs://${BUCKET_NAME}/test-uploads/sample_receipt.png"
gcloud storage cp "${TEMP_DIR}/sample_spec.md" "gs://${BUCKET_NAME}/test-uploads/sample_spec.md"

echo "==> [3/3] Upload complete. Waiting 15 seconds for event-driven pipeline execution..."
sleep 15

echo "==> Querying BigQuery metadata table..."
bq query --use_legacy_sql=false \
  "SELECT file_name, status, word_count, ARRAY_TO_STRING(tags, ', ') AS tags, SUBSTR(ocr_preview_snippet, 1, 60) AS preview, processed_at
   FROM \`${PROJECT_ID}.${BIGQUERY_DATASET}.${BIGQUERY_TABLE}\`
   ORDER BY processed_at DESC
   LIMIT 5;"

echo "=========================================================="
echo " Test pipeline execution completed!"
echo "=========================================================="
