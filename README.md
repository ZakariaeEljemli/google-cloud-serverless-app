# Serverless Event-Driven Document Processing Pipeline on Google Cloud

A production-ready, serverless event-driven document processing and metadata extraction pipeline built on Google Cloud Platform.

---

## Architecture Overview

```
                      +-----------------------------+
                      |   User / Client Uploader    |
                      +--------------+--------------+
                                     |
                                     v Uploads file (PDF, TXT, PNG, etc.)
                      +-----------------------------+
                      | Cloud Storage (GCS) Bucket  |
                      |   gs://${BUCKET_NAME}       |
                      +--------------+--------------+
                                     |
                                     v GCS Object Finalize Notification
                      +-----------------------------+
                      |      Pub/Sub Topic          |
                      |   ${TOPIC_NAME}             |
                      +--------------+--------------+
                                     |
                                     v Authenticated Push Subscription (OIDC)
                      +-----------------------------+
                      |   Cloud Run Microservice    |
                      |      Flask + Gunicorn       |
                      |                             |
                      |  - Base64 parse event       |
                      |  - Download from GCS        |
                      |  - Hybrid Simulated OCR     |
                      |  - Extract tags/word count  |
                      |  - Catch & log errors       |
                      +--------------+--------------+
                                     |
                                     v Streaming insert with insert_id deduplication
                      +-----------------------------+
                      |     BigQuery Dataset        |
                      |  ${DATASET}.${TABLE}        |
                      +-----------------------------+
```

### Key Architectural Highlights
- **Real-Time Event Ingestion**: Cloud Storage bucket notifications emit messages immediately upon file uploads (`OBJECT_FINALIZE`).
- **Secure Pub/Sub Push**: Cloud Run service endpoints are protected with IAM authentication. The Pub/Sub push subscription uses a dedicated Google Cloud Service Account with OIDC tokens (`roles/run.invoker`).
- **Hybrid Document Processing Engine**:
  - Plain text, markdown, CSV, and JSON files are parsed directly.
  - Native PDFs with text layers are read using `pypdf`.
  - Scanned PDFs, images (`.png`, `.jpg`, `.tiff`), and binary files pass through a deterministic synthetic OCR engine that produces realistic text, keyword tags, and word counts based on cryptographic content digests.
- **Deduplication & Idempotency in BigQuery**: Pub/Sub provides at-least-once delivery. Each streaming insert passes the Pub/Sub `message_id` as BigQuery's `insert_id`, ensuring duplicate events are automatically deduplicated.
- **Fail-Silent Resilience**: Processing failures are caught, logged, and streamed to BigQuery with `status="ERROR"` and `error_message`, returning HTTP `200` to acknowledge Pub/Sub and prevent retry storms.

---

## Directory Structure

```text
google-cloud-serverless-app/
├── app/
│   ├── __init__.py          # Package initialization
│   ├── config.py            # Environment configuration settings
│   ├── gcs_client.py        # Cloud Storage download client wrapper
│   ├── processor.py         # Hybrid OCR and metadata extraction engine
│   ├── bq_streamer.py       # BigQuery streaming client with deduplication
│   └── main.py              # Flask HTTP Push handler and orchestrator
├── tests/
│   ├── __init__.py          # Test package
│   ├── conftest.py          # Pytest fixtures and mock envelopes
│   ├── test_processor.py    # Unit tests for OCR and keyword extraction
│   ├── test_bq_streamer.py  # Unit tests for BigQuery streamer & deduplication
│   └── test_app.py          # Unit tests for Flask endpoints & error handling
├── scripts/
│   ├── schema.json          # BigQuery table schema definition
│   ├── env.example.sh       # Bash environment variable template
│   ├── env.example.ps1      # PowerShell environment variable template
│   ├── deploy.sh            # Complete automated provisioning in Bash
│   ├── deploy.ps1           # Complete automated provisioning in PowerShell
│   ├── destroy.sh           # Resource teardown script in Bash
│   ├── destroy.ps1          # Resource teardown script in PowerShell
│   ├── test_pipeline.sh     # Upload test documents and query BigQuery (Bash)
│   └── test_pipeline.ps1    # Upload test documents and query BigQuery (PowerShell)
├── Dockerfile               # Container build definition for Cloud Run
├── requirements.txt         # Production runtime dependencies
├── requirements-dev.txt     # Local development and test dependencies
└── README.md
```

---

## BigQuery Metadata Schema

The BigQuery table (`processed_documents`) stores the following fields:

| Field Name | Type | Mode | Description |
| :--- | :--- | :--- | :--- |
| `file_name` | STRING | REQUIRED | Object path in Cloud Storage |
| `bucket_name` | STRING | REQUIRED | Source Cloud Storage bucket |
| `file_size_bytes` | INT64 | NULLABLE | File size in bytes |
| `mime_type` | STRING | NULLABLE | Detected or reported MIME content type |
| `upload_date` | TIMESTAMP | NULLABLE | Upload timestamp in Cloud Storage |
| `processed_at` | TIMESTAMP | REQUIRED | Timestamp when pipeline processed the file |
| `status` | STRING | REQUIRED | `SUCCESS` or `ERROR` |
| `word_count` | INT64 | NULLABLE | Document word count |
| `tags` | STRING | REPEATED | Extracted keyword and classification tags |
| `ocr_preview_snippet` | STRING | NULLABLE | First 200 characters of OCR text |
| `error_message` | STRING | NULLABLE | Stack trace or failure description if failed |

---

## Local Development & Testing

### 1. Set Up Virtual Environment
```bash
# Using Python 3.11+
python -m venv .venv

# Activate on Linux / macOS:
source .venv/bin/activate

# Activate on Windows (PowerShell):
.venv\Scripts\Activate.ps1
```

### 2. Install Dependencies
```bash
pip install -r requirements-dev.txt
```

### 3. Run Unit and Integration Tests
```bash
pytest -v
```

All 17 tests verify document parsing, tag generation, PDF handling, BigQuery streaming formatting, deduplication keys, and HTTP endpoint resilience.

---

## Deployment to Google Cloud

### Prerequisites
1. [Google Cloud SDK (`gcloud`)](https://cloud.google.com/sdk/docs/install) installed and authenticated:
   ```bash
   gcloud auth login
   gcloud auth application-default login
   ```
2. A GCP project with billing enabled.

---

### Option A: Deploying via Bash (Linux, macOS, Cloud Shell, WSL)

1. Copy and configure your environment variables:
   ```bash
   cp scripts/env.example.sh scripts/env.sh
   nano scripts/env.sh  # Set your PROJECT_ID and REGION
   ```

2. Run the deployment script:
   ```bash
   chmod +x scripts/*.sh
   ./scripts/deploy.sh
   ```

3. Test the deployed pipeline with sample uploads:
   ```bash
   ./scripts/test_pipeline.sh
   ```

4. Clean up all resources when finished:
   ```bash
   ./scripts/destroy.sh
   ```

---

### Option B: Deploying via PowerShell (Windows Native)

1. Copy and configure your environment variables:
   ```powershell
   Copy-Item scripts/env.example.ps1 scripts/env.ps1
   notepad scripts/env.ps1  # Set your PROJECT_ID and REGION
   ```

2. Run the deployment script:
   ```powershell
   .\scripts\deploy.ps1
   ```

3. Test the deployed pipeline with sample uploads:
   ```powershell
   .\scripts\test_pipeline.ps1
   ```

4. Clean up all resources when finished:
   ```powershell
   .\scripts\destroy.ps1
   ```

---

## Querying Processed Documents in BigQuery

Once files are uploaded, query the BigQuery table using the `bq` CLI or the Google Cloud Console:

```sql
SELECT 
  file_name,
  status,
  word_count,
  ARRAY_TO_STRING(tags, ', ') AS tags,
  SUBSTR(ocr_preview_snippet, 1, 80) AS preview,
  processed_at
FROM 
  `YOUR_PROJECT_ID.doc_pipeline_ds.processed_documents`
ORDER BY 
  processed_at DESC
LIMIT 20;
```
