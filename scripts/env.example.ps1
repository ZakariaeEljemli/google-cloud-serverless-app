# Environment configuration for Google Cloud deployment (PowerShell)
# Copy this file to scripts/env.ps1 and customize for your project:
#   Copy-Item scripts/env.example.ps1 scripts/env.ps1

$env:PROJECT_ID = "your-gcp-project-id"
$env:REGION = "us-central1"

# Ingestion Cloud Storage Bucket
$env:BUCKET_NAME = "$($env:PROJECT_ID)-doc-ingest"

# Pub/Sub Topic and Push Subscription
$env:TOPIC_NAME = "doc-upload-events"
$env:SUBSCRIPTION_NAME = "doc-upload-push-sub"

# BigQuery Dataset and Table
$env:BIGQUERY_DATASET = "doc_pipeline_ds"
$env:BIGQUERY_TABLE = "processed_documents"

# Cloud Run Service & Service Account
$env:SERVICE_NAME = "document-processor"
$env:SERVICE_ACCOUNT = "doc-processor-sa"
