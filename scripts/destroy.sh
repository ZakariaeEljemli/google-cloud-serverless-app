#!/usr/bin/env bash
# Tear down and clean up all resources created for the pipeline
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ -f "${SCRIPT_DIR}/env.sh" ]]; then
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/env.sh"
fi

: "${PROJECT_ID:?Error: PROJECT_ID is required. Set in scripts/env.sh or environment.}"
: "${REGION:=us-central1}"
: "${BUCKET_NAME:=${PROJECT_ID}-doc-ingest}"
: "${TOPIC_NAME:=doc-upload-events}"
: "${SUBSCRIPTION_NAME:=doc-upload-push-sub}"
: "${BIGQUERY_DATASET:=doc_pipeline_ds}"
: "${SERVICE_NAME:=document-processor}"
: "${SERVICE_ACCOUNT:=doc-processor-sa}"

SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================================="
echo " Destroying GCP Document Processing Pipeline Resources    "
echo " Project: $PROJECT_ID"
echo "=========================================================="

echo "==> [1/6] Deleting Pub/Sub Subscription..."
gcloud pubsub subscriptions delete "${SUBSCRIPTION_NAME}" --quiet || true

echo "==> [2/6] Deleting Pub/Sub Topic..."
gcloud pubsub topics delete "${TOPIC_NAME}" --quiet || true

echo "==> [3/6] Deleting Cloud Run service..."
gcloud run services delete "${SERVICE_NAME}" --region="${REGION}" --quiet || true

echo "==> [4/6] Deleting Cloud Storage bucket gs://${BUCKET_NAME}..."
gcloud storage rm --recursive "gs://${BUCKET_NAME}" --quiet || true

echo "==> [5/6] Deleting BigQuery Dataset and Tables..."
bq rm -r -f -d "${PROJECT_ID}:${BIGQUERY_DATASET}" || true

echo "==> [6/6] Deleting Service Account..."
gcloud iam service-accounts delete "${SA_EMAIL}" --quiet || true

echo "Cleanup complete!"
