# End-to-end testing script for the serverless document pipeline (PowerShell)
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

$BucketName = if ($env:BUCKET_NAME) { $env:BUCKET_NAME } else { "$ProjectId-doc-ingest" }
$DatasetId = if ($env:BIGQUERY_DATASET) { $env:BIGQUERY_DATASET } else { "doc_pipeline_ds" }
$TableId = if ($env:BIGQUERY_TABLE) { $env:BIGQUERY_TABLE } else { "processed_documents" }

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Testing Document Processing Pipeline End-to-End          " -ForegroundColor Cyan
Write-Host " Target Bucket: gs://$BucketName"
Write-Host " BigQuery:      $ProjectId`:$DatasetId.$TableId"
Write-Host "==========================================================" -ForegroundColor Cyan

$TempDir = Join-Path $env:TEMP ([System.Guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $TempDir -Force | Out-Null

try {
    Write-Host "==> [1/3] Generating test documents..." -ForegroundColor Green
    
    # 1. Plain text invoice
    $invoiceText = @"
INVOICE #98124
Vendor: Acme Cloud Solutions LLC
Client: Horizon Analytics
Date: 2026-10-12
Item 1: Serverless Event Architecture Setup - `$3,500.00
Item 2: BigQuery Schema Optimization - `$1,200.00
Total: `$4,700.00
Payment due within 30 days. Thank you for your business.
"@
    $invoicePath = Join-Path $TempDir "sample_invoice.txt"
    Set-Content -Path $invoicePath -Value $invoiceText -Encoding utf8

    # 2. Simulated PNG image bytes
    $pngBytes = [byte[]](0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52, 0x00, 0x00, 0x00, 0x10, 0x00, 0x00, 0x00, 0x10, 0x08, 0x06, 0x00, 0x00, 0x00)
    $pngPath = Join-Path $TempDir "sample_receipt.png"
    [System.IO.File]::WriteAllBytes($pngPath, $pngBytes)

    # 3. Architecture markdown
    $specText = @"
# System Architecture Specification
This document outlines the event-driven ingestion pipeline on Google Cloud.
Files uploaded to Cloud Storage emit Pub/Sub messages to trigger Cloud Run.
Extracted metadata is streamed directly into BigQuery.
"@
    $specPath = Join-Path $TempDir "sample_spec.md"
    Set-Content -Path $specPath -Value $specText -Encoding utf8

    Write-Host "==> [2/3] Uploading sample files to gs://$BucketName/..." -ForegroundColor Green
    gcloud storage cp $invoicePath "gs://$BucketName/test-uploads/sample_invoice.txt"
    gcloud storage cp $pngPath "gs://$BucketName/test-uploads/sample_receipt.png"
    gcloud storage cp $specPath "gs://$BucketName/test-uploads/sample_spec.md"

    Write-Host "==> [3/3] Upload complete. Waiting 15 seconds for event-driven pipeline execution..." -ForegroundColor Yellow
    Start-Sleep -Seconds 15

    Write-Host "==> Querying BigQuery metadata table..." -ForegroundColor Green
    bq query --use_legacy_sql=false `
      "SELECT file_name, status, word_count, ARRAY_TO_STRING(tags, ', ') AS tags, SUBSTR(ocr_preview_snippet, 1, 60) AS preview, processed_at FROM \`$ProjectId.$DatasetId.$TableId\` ORDER BY processed_at DESC LIMIT 5;"

    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " Test pipeline execution completed!" -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan

} finally {
    if (Test-Path $TempDir) {
        Remove-Item -Path $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}
