#!/usr/bin/env bash
# Deploy Serverless Document Processing Pipeline to Google Cloud
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Load environment configuration
if [[ -f "${SCRIPT_DIR}/env.sh" ]]; then
  echo "==> Sourcing ${SCRIPT_DIR}/env.sh..."
  # shellcheck source=/dev/null
  source "${SCRIPT_DIR}/env.sh"
else
  echo "==> No scripts/env.sh found, checking environment variables..."
fi

# Validation
: "${PROJECT_ID:?Error: PROJECT_ID is required. Set in scripts/env.sh or environment.}"
: "${REGION:=us-central1}"
: "${BUCKET_NAME:=${PROJECT_ID}-doc-ingest}"
: "${TOPIC_NAME:=doc-upload-events}"
: "${SUBSCRIPTION_NAME:=doc-upload-push-sub}"
: "${BIGQUERY_DATASET:=doc_pipeline_ds}"
: "${BIGQUERY_TABLE:=processed_documents}"
: "${SERVICE_NAME:=document-processor}"
: "${SERVICE_ACCOUNT:=doc-processor-sa}"

SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"

echo "=========================================================="
echo " Deploying Document Processing Pipeline to Google Cloud   "
echo " Project:          ${PROJECT_ID}"
echo " Region:           ${REGION}"
echo " Bucket:           gs://${BUCKET_NAME}"
echo " Topic:            ${TOPIC_NAME}"
echo " Cloud Run:        ${SERVICE_NAME}"
echo " BigQuery Table:   ${PROJECT_ID}:${BIGQUERY_DATASET}.${BIGQUERY_TABLE}"
echo " Service Account:  ${SA_EMAIL}"
echo "=========================================================="

echo "==> [1/9] Setting gcloud active project..."
gcloud config set project "${PROJECT_ID}"

echo "==> [2/9] Enabling required Google Cloud APIs..."
gcloud services enable \
  run.googleapis.com \
  pubsub.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com

echo "==> [3/9] Creating Service Account and granting IAM permissions..."
if ! gcloud iam service-accounts describe "${SA_EMAIL}" >/dev/null 2>&1; then
  gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
    --display-name="Document Processing Pipeline Service Account"
fi

# Grant Cloud Storage and BigQuery access
for ROLE in roles/storage.objectViewer roles/bigquery.dataEditor roles/bigquery.jobUser; do
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="${ROLE}" --condition=None >/dev/null
done

echo "==> [4/9] Provisioning Cloud Storage bucket gs://${BUCKET_NAME}..."
if ! gcloud storage buckets describe "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
  gcloud storage buckets create "gs://${BUCKET_NAME}" --location="${REGION}"
fi

echo "==> [5/9] Provisioning BigQuery Dataset and Table..."
if ! bq show "${PROJECT_ID}:${BIGQUERY_DATASET}" >/dev/null 2>&1; then
  bq mk --location="${REGION}" --dataset "${PROJECT_ID}:${BIGQUERY_DATASET}"
fi

if ! bq show "${PROJECT_ID}:${BIGQUERY_DATASET}.${BIGQUERY_TABLE}" >/dev/null 2>&1; then
  bq mk --table \
    "${PROJECT_ID}:${BIGQUERY_DATASET}.${BIGQUERY_TABLE}" \
    "${SCRIPT_DIR}/schema.json"
fi

echo "==> [6/9] Building and deploying Cloud Run service..."
cd "${ROOT_DIR}"
gcloud run deploy "${SERVICE_NAME}" \
  --source . \
  --region="${REGION}" \
  --service-account="${SA_EMAIL}" \
  --set-env-vars="GCP_PROJECT=${PROJECT_ID},BIGQUERY_DATASET=${BIGQUERY_DATASET},BIGQUERY_TABLE=${BIGQUERY_TABLE}" \
  --no-allow-unauthenticated

SERVICE_URL=$(gcloud run services describe "${SERVICE_NAME}" --region="${REGION}" --format="value(status.url)")
echo "Service deployed at: ${SERVICE_URL}"

# Grant push service account permission to invoke Cloud Run
gcloud run services add-iam-policy-binding "${SERVICE_NAME}" \
  --region="${REGION}" \
  --member="serviceAccount:${SA_EMAIL}" \
  --role="roles/run.invoker" >/dev/null

echo "==> [7/9] Provisioning Pub/Sub topic and granting GCS publishing rights..."
if ! gcloud pubsub topics describe "${TOPIC_NAME}" >/dev/null 2>&1; then
  gcloud pubsub topics create "${TOPIC_NAME}"
fi

PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format="value(projectNumber)")
GCS_SA="service-${PROJECT_NUMBER}@gs-project-accounts.iam.gserviceaccount.com"

gcloud pubsub topics add-iam-policy-binding "${TOPIC_NAME}" \
  --member="serviceAccount:${GCS_SA}" \
  --role="roles/pubsub.publisher" >/dev/null

echo "==> [8/9] Creating Cloud Storage notification on bucket..."
EXISTING_NOTIF=$(gcloud storage buckets notifications list "gs://${BUCKET_NAME}" --format="value(topic)" 2>/dev/null | grep "${TOPIC_NAME}" || true)
if [[ -z "${EXISTING_NOTIF}" ]]; then
  gcloud storage buckets notifications create "gs://${BUCKET_NAME}" \
    --topic="${TOPIC_NAME}" \
    --event-types="OBJECT_FINALIZE" \
    --payload-format="json"
else
  echo "Notification already configured for topic ${TOPIC_NAME}."
fi

echo "==> [9/9] Configuring Pub/Sub Push Subscription to Cloud Run..."
PUSH_ENDPOINT="${SERVICE_URL}/process"
if ! gcloud pubsub subscriptions describe "${SUBSCRIPTION_NAME}" >/dev/null 2>&1; then
  gcloud pubsub subscriptions create "${SUBSCRIPTION_NAME}" \
    --topic="${TOPIC_NAME}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --push-auth-service-account="${SA_EMAIL}" \
    --ack-deadline=60
else
  gcloud pubsub subscriptions update "${SUBSCRIPTION_NAME}" \
    --push-endpoint="${PUSH_ENDPOINT}" \
    --push-auth-service-account="${SA_EMAIL}" \
    --ack-deadline=60
fi

echo "=========================================================="
echo " Pipeline deployed successfully!"
echo " Upload files to trigger processing:"
echo "   gcloud storage cp sample.pdf gs://${BUCKET_NAME}/"
echo " View BigQuery results:"
echo "   bq query --use_legacy_sql=false 'SELECT * FROM \`${PROJECT_ID}.${BIGQUERY_DATASET}.${BIGQUERY_TABLE}\` LIMIT 10;'"
echo "=========================================================="
