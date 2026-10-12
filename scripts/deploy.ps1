# Deploy Serverless Document Processing Pipeline to Google Cloud (PowerShell)
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

# Load environment configuration if available
$EnvScript = Join-Path $ScriptDir "env.ps1"
if (Test-Path $EnvScript) {
    Write-Host "==> Sourcing $EnvScript..." -ForegroundColor Cyan
    . $EnvScript
} else {
    Write-Host "==> No scripts/env.ps1 found, using environment variables..." -ForegroundColor Yellow
}

# Validation and Defaults
$ProjectId = $env:PROJECT_ID
if (-not $ProjectId) {
    throw "Error: PROJECT_ID is required. Set in scripts/env.ps1 or as `$env:PROJECT_ID."
}

$Region = if ($env:REGION) { $env:REGION } else { "us-central1" }
$BucketName = if ($env:BUCKET_NAME) { $env:BUCKET_NAME } else { "$ProjectId-doc-ingest" }
$TopicName = if ($env:TOPIC_NAME) { $env:TOPIC_NAME } else { "doc-upload-events" }
$SubName = if ($env:SUBSCRIPTION_NAME) { $env:SUBSCRIPTION_NAME } else { "doc-upload-push-sub" }
$DatasetId = if ($env:BIGQUERY_DATASET) { $env:BIGQUERY_DATASET } else { "doc_pipeline_ds" }
$TableId = if ($env:BIGQUERY_TABLE) { $env:BIGQUERY_TABLE } else { "processed_documents" }
$ServiceName = if ($env:SERVICE_NAME) { $env:SERVICE_NAME } else { "document-processor" }
$ServiceAccount = if ($env:SERVICE_ACCOUNT) { $env:SERVICE_ACCOUNT } else { "doc-processor-sa" }

$SaEmail = "$ServiceAccount@$ProjectId.iam.gserviceaccount.com"

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Deploying Document Processing Pipeline to Google Cloud   " -ForegroundColor Green
Write-Host " Project:          $ProjectId"
Write-Host " Region:           $Region"
Write-Host " Bucket:           gs://$BucketName"
Write-Host " Topic:            $TopicName"
Write-Host " Cloud Run:        $ServiceName"
Write-Host " BigQuery Table:   $ProjectId`:$DatasetId.$TableId"
Write-Host " Service Account:  $SaEmail"
Write-Host "==========================================================" -ForegroundColor Green

Write-Host "==> [1/9] Setting gcloud active project..." -ForegroundColor Cyan
gcloud config set project $ProjectId

Write-Host "==> [2/9] Enabling required Google Cloud APIs..." -ForegroundColor Cyan
gcloud services enable `
  run.googleapis.com `
  pubsub.googleapis.com `
  storage.googleapis.com `
  bigquery.googleapis.com `
  cloudbuild.googleapis.com `
  artifactregistry.googleapis.com

Write-Host "==> [3/9] Creating Service Account and granting IAM permissions..." -ForegroundColor Cyan
$saExists = gcloud iam service-accounts describe $SaEmail 2>$null
if (-not $saExists) {
    gcloud iam service-accounts create $ServiceAccount --display-name="Document Processing Pipeline Service Account"
}

$roles = @("roles/storage.objectViewer", "roles/bigquery.dataEditor", "roles/bigquery.jobUser")
foreach ($role in $roles) {
    gcloud projects add-iam-policy-binding $ProjectId `
      --member="serviceAccount:$SaEmail" `
      --role="$role" `
      --condition=None 2>$null | Out-Null
}

Write-Host "==> [4/9] Provisioning Cloud Storage bucket gs://$BucketName..." -ForegroundColor Cyan
$bucketExists = gcloud storage buckets describe "gs://$BucketName" 2>$null
if (-not $bucketExists) {
    gcloud storage buckets create "gs://$BucketName" --location="$Region"
}

Write-Host "==> [5/9] Provisioning BigQuery Dataset and Table..." -ForegroundColor Cyan
$datasetExists = bq show "$ProjectId`:$DatasetId" 2>$null
if (-not $datasetExists) {
    bq mk --location="$Region" --dataset "$ProjectId`:$DatasetId"
}

$tableExists = bq show "$ProjectId`:$DatasetId.$TableId" 2>$null
if (-not $tableExists) {
    $schemaPath = Join-Path $ScriptDir "schema.json"
    bq mk --table "$ProjectId`:$DatasetId.$TableId" $schemaPath
}

Write-Host "==> [6/9] Building and deploying Cloud Run service..." -ForegroundColor Cyan
Set-Location $RootDir
gcloud run deploy $ServiceName `
  --source . `
  --region="$Region" `
  --service-account="$SaEmail" `
  --set-env-vars="GCP_PROJECT=$ProjectId,BIGQUERY_DATASET=$DatasetId,BIGQUERY_TABLE=$TableId" `
  --no-allow-unauthenticated

$ServiceUrl = gcloud run services describe $ServiceName --region="$Region" --format="value(status.url)"
Write-Host "Service deployed at: $ServiceUrl" -ForegroundColor Green

# Grant invoker role to the service account
gcloud run services add-iam-policy-binding $ServiceName `
  --region="$Region" `
  --member="serviceAccount:$SaEmail" `
  --role="roles/run.invoker" 2>$null | Out-Null

Write-Host "==> [7/9] Provisioning Pub/Sub topic and granting GCS publishing rights..." -ForegroundColor Cyan
$topicExists = gcloud pubsub topics describe $TopicName 2>$null
if (-not $topicExists) {
    gcloud pubsub topics create $TopicName
}

$ProjectNumber = gcloud projects describe $ProjectId --format="value(projectNumber)"
$GcsSa = "service-$ProjectNumber@gs-project-accounts.iam.gserviceaccount.com"
gcloud pubsub topics add-iam-policy-binding $TopicName `
  --member="serviceAccount:$GcsSa" `
  --role="roles/pubsub.publisher" 2>$null | Out-Null

Write-Host "==> [8/9] Creating Cloud Storage notification on bucket..." -ForegroundColor Cyan
$notifList = gcloud storage buckets notifications list "gs://$BucketName" --format="value(topic)" 2>$null
if (-not ($notifList -match $TopicName)) {
    gcloud storage buckets notifications create "gs://$BucketName" `
      --topic="$TopicName" `
      --event-types="OBJECT_FINALIZE" `
      --payload-format="JSON_API_V1"
} else {
    Write-Host "Notification already configured for topic $TopicName." -ForegroundColor Yellow
}

Write-Host "==> [9/9] Configuring Pub/Sub Push Subscription to Cloud Run..." -ForegroundColor Cyan
$PushEndpoint = "$ServiceUrl/process"
$subExists = gcloud pubsub subscriptions describe $SubName 2>$null
if (-not $subExists) {
    gcloud pubsub subscriptions create $SubName `
      --topic="$TopicName" `
      --push-endpoint="$PushEndpoint" `
      --push-auth-service-account="$SaEmail" `
      --ack-deadline=60
} else {
    gcloud pubsub subscriptions update $SubName `
      --push-endpoint="$PushEndpoint" `
      --push-auth-service-account="$SaEmail" `
      --ack-deadline=60
}

Write-Host "==========================================================" -ForegroundColor Green
Write-Host " Pipeline deployed successfully!" -ForegroundColor Green
Write-Host " Upload files to trigger processing:"
Write-Host "   gcloud storage cp sample.pdf gs://$BucketName/"
Write-Host " View BigQuery results:"
Write-Host "   bq query --use_legacy_sql=false 'SELECT * FROM \`$ProjectId.$DatasetId.$TableId\` LIMIT 10;'"
Write-Host "==========================================================" -ForegroundColor Green
