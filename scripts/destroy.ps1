# Tear down and clean up all resources created for the pipeline (PowerShell)
[CmdletBinding()]
param()

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

$EnvScript = Join-Path $ScriptDir "env.ps1"
if (Test-Path $EnvScript) {
    . $EnvScript
}

$ProjectId = $env:PROJECT_ID
if (-not $ProjectId) {
    throw "Error: PROJECT_ID is required. Set in scripts/env.ps1 or as `$env:PROJECT_ID."
}

$Region = if ($env:REGION) { $env:REGION } else { "us-central1" }
$BucketName = if ($env:BUCKET_NAME) { $env:BUCKET_NAME } else { "$ProjectId-doc-ingest" }
$TopicName = if ($env:TOPIC_NAME) { $env:TOPIC_NAME } else { "doc-upload-events" }
$SubName = if ($env:SUBSCRIPTION_NAME) { $env:SUBSCRIPTION_NAME } else { "doc-upload-push-sub" }
$DatasetId = if ($env:BIGQUERY_DATASET) { $env:BIGQUERY_DATASET } else { "doc_pipeline_ds" }
$ServiceName = if ($env:SERVICE_NAME) { $env:SERVICE_NAME } else { "document-processor" }
$ServiceAccount = if ($env:SERVICE_ACCOUNT) { $env:SERVICE_ACCOUNT } else { "doc-processor-sa" }

$SaEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"

Write-Host "==========================================================" -ForegroundColor Red
Write-Host " Destroying GCP Document Processing Pipeline Resources    " -ForegroundColor Red
Write-Host " Project: $ProjectId"
Write-Host "==========================================================" -ForegroundColor Red

Write-Host "==> [1/6] Deleting Pub/Sub Subscription..." -ForegroundColor Yellow
gcloud pubsub subscriptions delete $SubName --quiet 2>$null

Write-Host "==> [2/6] Deleting Pub/Sub Topic..." -ForegroundColor Yellow
gcloud pubsub topics delete $TopicName --quiet 2>$null

Write-Host "==> [3/6] Deleting Cloud Run service..." -ForegroundColor Yellow
gcloud run services delete $ServiceName --region="$Region" --quiet 2>$null

Write-Host "==> [4/6] Deleting Cloud Storage bucket gs://$BucketName..." -ForegroundColor Yellow
gcloud storage rm --recursive "gs://$BucketName" --quiet 2>$null

Write-Host "==> [5/6] Deleting BigQuery Dataset and Tables..." -ForegroundColor Yellow
bq rm -r -f -d "$ProjectId`:$DatasetId" 2>$null

Write-Host "==> [6/6] Deleting Service Account..." -ForegroundColor Yellow
gcloud iam service-accounts delete $SaEmail --quiet 2>$null

Write-Host "Cleanup complete!" -ForegroundColor Green
