# RCM Guardian

## Overview

RCM Guardian is a FastAPI service that runs a LangGraph workflow over billing documents: multimodal extraction (PDF/image), pgvector-backed retrieval of payer policy rules, forensic auditing with optional **LIMS** prior-authorization reconciliation, and human-in-the-loop checkpoints with resumable graph state.

The codebase is intended as a **production-oriented prototype**: Docker images align with an AWS Fargate–style deployment defined under `terraform/`. Configure secrets via environment variables locally and via AWS Secrets Manager in deployed environments.

## Run locally

Payer rules and the pgvector schema are loaded at API startup (`lifespan` → `seed_payer_rules_if_empty`).

1. **Stack** (Postgres + LIMS mock + API): set **`OPENAI_API_KEY`** in **`.env`** (see **`.env.example`**). **`scripts/start-local.ps1`** / **`start-local.sh`** exit if it is missing.

   ```bash
   docker compose up --build
   ```

   Windows:

   ```powershell
   .\scripts\start-local.ps1
   ```

2. **Health**: [http://localhost:8000/v1/ready](http://localhost:8000/v1/ready) should report `"seeded": true` and `payer_rules_count` ≥ 4. API reference: [http://localhost:8000/docs](http://localhost:8000/docs).

3. **Seed without API** (Postgres on port 5432):

   ```bash
   docker compose up -d postgres
   pip install -r requirements.txt
   python scripts/ensure_local_data.py
   ```

**Models:** OpenAI is required for embeddings (RAG) and primary vision extraction. If OpenAI vision fails and **`ANTHROPIC_API_KEY`** is set, extraction retries using Claude (`rcm_guardian/agents/vision_extract.py`).

**Tests:** `tests/test_complete_flow_mocked.py` patches vision and embeddings and uses an in-memory RAG fixture. `tests/test_eob_processing.py` stubs LLM calls unless **`RUN_OPENAI_INTEGRATION=1`**.

## Deployment topology

| Concern | Docker Compose | AWS (`terraform/`) |
|--------|----------------|---------------------|
| Runtime | FastAPI + Uvicorn in `api` service | ECS on Fargate behind ALB |
| Database | `pgvector/pgvector:pg16` | RDS PostgreSQL (pgvector-capable) |
| Secrets | `.env` (not committed); `.env.example` template | Secrets Manager (`DATABASE_URL`, OpenAI, optional Anthropic) |
| Documents | `./uploads` → `/uploads` | Private S3 (`terraform/s3.tf`); SSE-S3 baseline, SSE-KMS optional |
| LIMS | `lims-mock` on host `:8081` | Same HTTP contract via internal networking |
| Scaling | One task per service | ECS desired count; autoscaling configured separately |

When **`LIMS_BASE_URL`** is set, the forensic auditor calls the LIMS HTTP API (Compose uses `http://lims-mock:8080`) to reconcile extracted CPTs against prior-authorization data before scoring denial risk.

## Architecture

```mermaid
flowchart TB
    subgraph Clients
        UI[Web / EHR / Batch Jobs]
        Analyst[Human Analyst]
    end

    subgraph AWS["AWS (terraform/)"]
        ECS[ECS Fargate]
        ALB[Application Load Balancer]
        RDS[(RDS Postgres)]
        SM[Secrets Manager]
        S3[S3 documents<br/>SSE-S3 / SSE-KMS]
        CW[CloudWatch Logs]
        ALB --> ECS
        ECS --> RDS
        ECS --> SM
        ECS --> S3
        ECS --> CW
    end

    subgraph Docker_Local["Docker Compose"]
        API[FastAPI :8000]
        PG[(Postgres 16 + pgvector)]
        LIMS[LIMS mock :8081]
        VOL[(./uploads volume)]
    end

    subgraph Orchestration["LangGraph"]
        direction TB
        EX[Extraction<br/>Multimodal vision]
        RO[Rule Oracle<br/>RAG]
        FA{Forensic Auditor}
        HITL[Human review<br/>interrupt]
        OUT([Output])
        EX --> RO
        RO --> FA
        FA -->|Low confidence| HITL
        HITL -->|Command resume| FA
        FA -->|High confidence| OUT
    end

    UI --> API
    Analyst -->|resume| API
    API --> EX
    RO --> PG
    FA -->|HTTP when LIMS_BASE_URL set| LIMS
    API --> VOL
    API -.->|same container contract| ECS
```

```mermaid
sequenceDiagram
    participant C as Client
    participant F as FastAPI
    participant U as /uploads volume
    participant G as LangGraph
    participant V as Vision LLM
    participant DB as Postgres/pgvector
    participant L as LIMS HTTP service

    C->>F: POST /v1/process (base64 doc + thread_id?)
    F->>U: optional persist inbound artifact
    F->>G: ainvoke(state, checkpoint thread_id)
    G->>V: Extract billing fields
    V-->>G: extracted_billing_data JSON
    G->>DB: Embed query + similarity search
    DB-->>G: payer_rules[]
    G->>L: POST /v1/prior-authorizations
    L-->>G: CPT-level PA coverage

    alt Auditor confidence >= 0.85
        G-->>F: completed state
        F-->>C: 200 ProcessDocumentResponse
    else Auditor confidence < 0.85
        Note over G: Checkpoint (MemorySaver) before API returns 202
        G-->>F: __interrupt__ + checkpointed state
        F-->>C: 202 HumanReviewAcceptedResponse
        C->>F: POST /v1/resume (thread_id + feedback)
        F->>G: Command(resume=...)
        G-->>F: final state
        F-->>C: 200 ProcessDocumentResponse
    end
```

## Features

| Area | Description |
|------|-------------|
| **API** | Async FastAPI; Pydantic request/response models |
| **Orchestration** | LangGraph graph with conditional routing and `interrupt()` for HITL |
| **Extraction** | PyMuPDF PDF rasterization + vision model; prompts tuned for tabular billing lines |
| **RAG** | OpenAI embeddings + cosine similarity in PostgreSQL/pgvector |
| **Auditing** | Rule hits vs CPT/NPI; LIMS reconciliation; structured findings (`finding_kind`, `status`, `reason`) and `prior_authorization_reconciliation` |
| **LIMS** | In-process fallback or HTTP **`lims-mock`** via **`LIMS_BASE_URL`** |
| **Artifact storage** | Optional `UPLOADS_DIR` persistence (Compose: `./uploads`) |
| **Checkpoints** | `MemorySaver`; replace with `PostgresSaver` for multi-instance deployments |
| **Observability** | OTLP/Sentry hooks documented in `rcm_guardian/app.py`; Grafana template `dashboards/grafana-denial-forecasting.json` (placeholder PromQL for OTLP-derived metrics) |
| **IaC** | `terraform/`: VPC, ALB, ECS, ECR, RDS, Secrets Manager, S3, IAM |

## Tech stack

- Python 3.12, FastAPI, Uvicorn  
- LangGraph, LangChain  
- PostgreSQL 16 + pgvector  
- Docker Compose  
- Terraform (AWS)

## Repository layout

```text
the-rcm-guardian/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── scripts/
│   ├── start-local.ps1
│   ├── start-local.sh
│   └── ensure_local_data.py
├── docker/lims-mock/
├── uploads/
├── dashboards/
├── terraform/
├── pytest.ini
├── requirements.txt
├── README.md
├── rcm_guardian/
│   ├── app.py
│   ├── graph.py
│   ├── state.py
│   ├── config.py
│   ├── bootstrap.py
│   ├── agents/
│   │   ├── prompts.py
│   │   └── vision_extract.py
│   ├── models/schemas.py
│   └── services/
│       ├── rag_service.py
│       ├── lims_service.py
│       └── storage_service.py
└── tests/
    ├── conftest.py
    ├── fixtures/
    ├── test_complete_flow_mocked.py
    └── test_eob_processing.py
```

Python imports use the package name **`rcm_guardian`** (underscores).

## Quick reference

### Docker Compose

```bash
docker compose up --build
```

| Endpoint | URL |
|----------|-----|
| API | http://localhost:8000 (`/docs` OpenAPI) |
| LIMS mock | http://localhost:8081/docs |
| Postgres | `localhost:5432` — db `rcm_guardian`, user/password `rcm` |
| Upload volume | `./uploads` → `/uploads` in `api` |

Compose sets **`LIMS_BASE_URL=http://lims-mock:8080`** and **`PERSIST_UPLOADS=true`** where applicable. Do not commit **`.env`**.

### Local Python only

1. Postgres with pgvector running  
2. `pip install -r requirements.txt`  
3. Optional: **`LIMS_BASE_URL`** (e.g. `http://127.0.0.1:8081`)

```bash
export OPENAI_API_KEY=sk-...
export DATABASE_URL=postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian
uvicorn rcm_guardian.app:app --reload --host 0.0.0.0 --port 8000
```

Optional: **`ANTHROPIC_API_KEY`** for vision fallback.

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | local Docker DSN | Async SQLAlchemy + asyncpg |
| `OPENAI_API_KEY` | — | **Required** — embeddings + primary vision |
| `OPENAI_VISION_MODEL` | `gpt-4o` | OpenAI vision model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings for payer rules |
| `ANTHROPIC_API_KEY` | empty | Optional vision fallback |
| `ANTHROPIC_VISION_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic vision model |
| `LIMS_BASE_URL` | empty | HTTP base URL for LIMS prior-auth API |
| `UPLOADS_DIR` | `/uploads` | Inbound artifact directory |
| `PERSIST_UPLOADS` | `false` | Write decoded uploads under `UPLOADS_DIR` |
| `DOCUMENTS_S3_BUCKET` | empty | Set by Terraform for S3-backed deployments |
| `OTEL_SERVICE_NAME` | `rcm-guardian` | OpenTelemetry service name |

## LangGraph state (`RCMGraphState`)

Field definitions and HITL semantics are documented in **`rcm_guardian/state.py`**. **`audit_report`** includes structured findings and **`prior_authorization_reconciliation`**. Checkpoints use **`MemorySaver`** keyed by **`configurable.thread_id`**.

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `POST` | `/v1/process` | Submit document; `200` completed or `202` human review |
| `POST` | `/v1/resume` | Resume interrupted graph with `Command(resume=...)` |
| `GET` | `/v1/ready` | Database connectivity and payer-rules seed status |

## Testing

```bash
pytest tests/test_eob_processing.py -q
pytest tests/test_complete_flow_mocked.py -v
```

- **`test_complete_flow_mocked.py`**: Full graph path with patched vision/embeddings and fixture payer rules (no Postgres).
- **`test_eob_processing.py`**: LIMS contract without Postgres; Postgres-backed tests skip if DB unavailable; use **`RUN_OPENAI_INTEGRATION=1`** for live OpenAI.

## Terraform (AWS)

Resources under **`terraform/`** include VPC, ALB, ECS Fargate, ECR, RDS, Secrets Manager, S3, IAM, and CloudWatch logs. Apply only in accounts you control.

```bash
cd terraform
terraform init
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform apply
```

ECS tasks should use a task role scoped to the documents bucket and load database/API secrets from Secrets Manager rather than environment literals in task definitions for production.

## Security

- Treat billing and PHI-adjacent payloads as sensitive; operational compliance (e.g. HIPAA) is an organizational control beyond this repository.
- Do not commit `.env` or credentials.
- Restrict RDS and S3 network access (security groups, bucket policies, VPC endpoints) in production accounts.

## Observability

`rcm_guardian/app.py` documents where to attach OpenTelemetry traces/metrics, error reporting (e.g. Sentry), and structured logs. **`dashboards/grafana-denial-forecasting.json`** is an optional Grafana import; replace placeholder metric names with series exported from your OTLP pipeline.

## License

Specify your organization’s license here.
