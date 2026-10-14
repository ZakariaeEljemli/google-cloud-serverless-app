#!/usr/bin/env bash
# Environment configuration for Google Cloud deployment (Bash)
# Copy this file to scripts/env.sh and customize for your project:
#   cp scripts/env.example.sh scripts/env.sh

# GCP Project & Region
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"

# Ingestion Cloud Storage Bucket
export BUCKET_NAME="${PROJECT_ID}-doc-ingest"

# Pub/Sub Topic and Push Subscription
export TOPIC_NAME="doc-upload-events"
export SUBSCRIPTION_NAME="doc-upload-push-sub"

# BigQuery Dataset and Table
export BIGQUERY_DATASET="doc_pipeline_ds"
export BIGQUERY_TABLE="processed_documents"

# Cloud Run Service & Service Account
export SERVICE_NAME="document-processor"
export SERVICE_ACCOUNT="doc-processor-sa"
