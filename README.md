# RCM Guardian

## Overview

RCM Guardian is a FastAPI service that runs a LangGraph workflow over billing documents: multimodal extraction (PDF/image), pgvector-backed retrieval of payer policy rules, forensic auditing with a **mock LIMS** (Docker `lims-mock` or in-process fallback) or a **real LIMS URL** when you set `LIMS_BASE_URL`, Postgres-backed checkpoints, and **LangSmith** tracing to the live LangSmith API.

The codebase is **production-oriented prototype**: Docker images align with an AWS Fargate–style deployment defined under `terraform/`. Configure secrets via environment variables locally and via AWS Secrets Manager in deployed environments.

## Run locally

Payer rules and the pgvector schema are loaded at API startup (`lifespan` → `seed_payer_rules_if_empty`).

1. **Stack** (Postgres + **LIMS mock** + API + Prometheus + Grafana): set **`OPENAI_API_KEY`** and **`LANGCHAIN_API_KEY`** in **`.env`** (LangSmith is **required**; get a key at [smith.langchain.com](https://smith.langchain.com)). **`LANGCHAIN_TRACING_V2`** defaults to **`true`** — do not turn it off. **`scripts/start-local.ps1`** / **`start-local.sh`** check both OpenAI and LangSmith keys.

   ```bash
   docker compose up --build
   ```

   Windows:

   ```powershell
   .\scripts\start-local.ps1
   ```

2. **Health / readiness**:
   - **`GET /health`** — liveness (no DB); use for simple probes.
   - **`GET /v1/ready`** — DB reachable, payer-rules count, and **non-secret** config snapshot (`ai_models`, LangSmith flags, `lims_base_url`, uploads). Expect `"seeded": true` and `payer_rules_count` ≥ 4 after startup. API reference: [http://localhost:8000/docs](http://localhost:8000/docs).

3. **Seed without API** (Postgres on port 5432):

   ```bash
   docker compose up -d postgres
   pip install -r requirements.txt
   python scripts/ensure_local_data.py
   ```

**Models:** OpenAI is required for embeddings (RAG) and primary vision extraction. If OpenAI vision fails and **`ANTHROPIC_API_KEY`** is set, extraction retries using Claude (`rcm_guardian/agents/vision_extract.py`).

**Tests:** `tests/test_complete_flow_fixtures.py` patches vision and embeddings and uses fixture payer rules (no Postgres). `tests/test_eob_processing.py` stubs LLM calls unless **`RUN_OPENAI_INTEGRATION=1`**.

## Deployment topology

| Concern | Docker Compose | AWS (`terraform/`) |
|--------|----------------|---------------------|
| Runtime | FastAPI + Uvicorn in `api` service | ECS on Fargate behind ALB |
| Database | `pgvector/pgvector:pg16` | RDS PostgreSQL (pgvector-capable) |
| Secrets | `.env` (not committed); `.env.example` template | Secrets Manager (`DATABASE_URL`, OpenAI, LangSmith, optional Anthropic) |
| Documents | `./uploads` → `/uploads` | Private S3 (`terraform/s3.tf`); SSE-S3 baseline, SSE-KMS optional |
| LIMS | **`lims-mock`** on host `:8081` (Compose default) or in-process when `LIMS_BASE_URL` is unset | `lims_base_url` Terraform → `LIMS_BASE_URL` for a real system |
| Metrics / dashboards | Prometheus `:9090`, Grafana `:3000` (local Compose) | Use managed Grafana/Prometheus or ADOT in AWS |
| Scaling | One task per service | ECS desired count; autoscaling configured separately |

**`LIMS_BASE_URL`** defaults to **`http://lims-mock:8080`** in Compose. Override in `.env` for a **real** LIMS (same `POST /v1/prior-authorizations` JSON contract). **LangSmith is mandatory:** **`LANGCHAIN_API_KEY`** must be set; **`LANGCHAIN_TRACING_V2`** must remain **`true`** (the app refuses to start otherwise).

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

    subgraph Ext["External"]
        LIMS_API[LIMS prior-auth HTTP when LIMS_BASE_URL external]
        LS[LangSmith LANGCHAIN_API_KEY required]
    end

    subgraph Docker_Local["Docker Compose"]
        API[FastAPI :8000]
        PG[(Postgres 16 + pgvector)]
        LIMSM[LIMS mock :8081]
        VOL[(./uploads volume)]
        PRO[Prometheus :9090]
        GRA[Grafana :3000]
    end

    PRO -.-> GRA

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
    FA -->|default: POST /v1/prior-authorizations| LIMSM
    FA -.->|external LIMS_BASE_URL| LIMS_API
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
        Note over G: Postgres checkpoint before API returns 202
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
| **LIMS** | **`lims-mock`** container or in-process mock; or real URL via **`LIMS_BASE_URL`** |
| **Artifact storage** | Optional `UPLOADS_DIR` persistence (Compose: `./uploads`) |
| **Checkpoints** | **`AsyncPostgresSaver`** in the same database as pgvector (multi-instance safe) |
| **Observability** | **`GET /metrics`** (Prometheus); **Grafana** dashboard; **LangSmith** (required, **`LANGCHAIN_*`**); OTLP/Sentry placeholders in `rcm_guardian/app.py` |
| **IaC** | `terraform/`: VPC, ALB, ECS, ECR, RDS, Secrets Manager, S3, IAM |

## Tech stack

- Python 3.12, FastAPI, Uvicorn  
- LangGraph, LangChain  
- PostgreSQL 16 + pgvector  
- Docker Compose (API, Postgres, **lims-mock**, Prometheus, Grafana)  
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
├── docker/
│   ├── grafana/
│   │   └── provisioning/
│   ├── prometheus/
│   └── lims-mock/
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
│   ├── db_uri.py
│   ├── metrics.py
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
    ├── test_complete_flow_fixtures.py
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
| API | http://localhost:8000 (`/docs` OpenAPI; `/metrics` for Prometheus) |
| LIMS mock | http://localhost:8081/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (default login `admin` / `admin` — change in production) |
| Postgres | `localhost:5432` — db `rcm_guardian`, user/password `rcm` |
| Upload volume | `./uploads` → `/uploads` in `api` |

Compose provisions the **Prometheus** datasource (UID `prometheus`), scrapes **`http://api:8000/metrics`**, and loads **`dashboards/grafana-denial-forecasting.json`**. **`LIMS_BASE_URL`** defaults to **`http://lims-mock:8080`** inside Compose unless you set it in **`.env`**. **`LANGCHAIN_API_KEY`** must be set for the API container (see **`.env.example`**).

Do not commit **`.env`**.

### Local Python only

1. Postgres with pgvector running  
2. `pip install -r requirements.txt`  
3. Optional: **`LIMS_BASE_URL`** (defaults to in-process mock if unset; use `http://127.0.0.1:8081` if `lims-mock` is running)

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_VISION_MODEL=gpt-4o
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
export OPENAI_EMBEDDING_DIMENSIONS=1536
export LANGCHAIN_API_KEY=lsv2_pt_...   # required — from LangSmith
export LANGCHAIN_TRACING_V2=true       # required (default); do not set false
export DATABASE_URL=postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian
uvicorn rcm_guardian.app:app --reload --host 0.0.0.0 --port 8000
```

Optional: **`ANTHROPIC_API_KEY`** for vision fallback.

## Configuration

Copy **`.env.example`** to **`.env`** and fill required values. The template is grouped in this order for easier maintenance: **OpenAI** (key + all `OPENAI_*`), **Anthropic** (`ANTHROPIC_*`), **LangSmith** (`LANGCHAIN_*`), **LIMS**, optional **database / uploads**, then **AWS** (`DOCUMENTS_S3_BUCKET`). Compose automatically loads **`.env`** next to **`docker-compose.yml`**.

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | local Docker DSN | Async SQLAlchemy + asyncpg |
| `OPENAI_API_KEY` | — | **Required** — embeddings + primary vision |
| `OPENAI_VISION_MODEL` | `gpt-4o` | OpenAI vision model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embeddings for payer rules |
| `OPENAI_EMBEDDING_DIMENSIONS` | `1536` | pgvector width — **must match** embedding model (e.g. `3072` for `text-embedding-3-large`). Changing this on a DB that already has rules may require migrating or recreating `payer_rules`. |
| `ANTHROPIC_API_KEY` | empty | Optional vision fallback |
| `ANTHROPIC_VISION_MODEL` | `claude-3-5-sonnet-20241022` | Anthropic vision model |
| `LIMS_BASE_URL` | empty / Compose default `http://lims-mock:8080` | Prior-auth HTTP base (`POST /v1/prior-authorizations`). Empty uses in-process mock (non-Docker). |
| `UPLOADS_DIR` | `/uploads` | Inbound artifact directory |
| `PERSIST_UPLOADS` | `false` | Write decoded uploads under `UPLOADS_DIR` |
| `DOCUMENTS_S3_BUCKET` | empty | Set by Terraform for S3-backed deployments |
| `OTEL_SERVICE_NAME` | `rcm-guardian` | OpenTelemetry service name |
| `LANGCHAIN_TRACING_V2` | `true` | **Must be `true`** — tracing to LangSmith is required |
| `LANGCHAIN_API_KEY` | — | **Required** — LangSmith API key ([Smith](https://smith.langchain.com)) |
| `LANGCHAIN_PROJECT` | `rcm-guardian` | LangSmith project name |
| `LANGCHAIN_ENDPOINT` | `https://api.smith.langchain.com` | LangSmith API base URL (e.g. EU region if required) |

## LangGraph state (`RCMGraphState`)

Field definitions and HITL semantics are documented in **`rcm_guardian/state.py`**. **`audit_report`** includes structured findings and **`prior_authorization_reconciliation`**. Checkpoints are stored in **PostgreSQL** via **`AsyncPostgresSaver`**, keyed by **`configurable.thread_id`**.

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `GET` | `/metrics` | Prometheus text exposition |
| `POST` | `/v1/process` | Submit document; `200` completed or `202` human review |
| `POST` | `/v1/resume` | Resume interrupted graph with `Command(resume=...)` |
| `GET` | `/v1/ready` | Readiness: DB + seed status; returns `ai_models`, LangSmith config flags (no secrets), LIMS URL, uploads paths |

## Testing

```bash
pytest -q
# or individually:
pytest tests/test_eob_processing.py -q
pytest tests/test_complete_flow_fixtures.py -v
```

- **`test_complete_flow_fixtures.py`**: Full graph path with patched vision/embeddings, fixture payer rules, and **in-process LIMS mock** (`MemorySaver`).
- **`test_eob_processing.py`**: Patches LIMS HTTP for Postgres e2e; skips if DB unavailable; use **`RUN_OPENAI_INTEGRATION=1`** for live OpenAI.

## Terraform (AWS)

Resources under **`terraform/`** include VPC, ALB, ECS Fargate, ECR, RDS, Secrets Manager, S3, IAM, and CloudWatch logs. Apply only in accounts you control.

```bash
cd terraform
terraform init
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform apply
```

ECS tasks should use a task role scoped to the documents bucket and load database/API secrets from Secrets Manager rather than environment literals in task definitions for production. Set **`langsmith_api_secret_arn`** in `terraform.tfvars` so **`LANGCHAIN_API_KEY`** is injected (**required**). Optional **`lims_base_url`** sets **`LIMS_BASE_URL`**.

## Security

- Treat billing and PHI-adjacent payloads as sensitive; operational compliance (e.g. HIPAA) is an organizational control beyond this repository.
- Do not commit **`.env`** or credentials; use **AWS Secrets Manager** (or equivalent) in deployed environments and inject at runtime (see **`langsmith_api_secret_arn`** and related task definitions under **`terraform/`**).
- Restrict RDS and S3 network access (security groups, bucket policies, VPC endpoints) in production accounts.
- **API surface:** this service does **not** ship API keys or OAuth for callers. Put it behind an authenticated gateway, private network, or mTLS as your threat model requires; terminate TLS at the load balancer in AWS.
- **Compose-only tools:** Prometheus and Grafana default credentials (`admin` / `admin`) and open ports are for **local development** only—do not expose them on the public internet without hardening (secrets, TLS, auth, allowlists).

## Production checklist

Use this as a pre-go-live pass; adapt to your org’s policies.

| Area | Guidance |
|------|----------|
| **Secrets** | OpenAI, LangSmith, DB, and optional Anthropic keys only from a secret store; `terraform.tfvars` never committed; **`LANGCHAIN_TRACING_V2=true`** and non-empty **`LANGCHAIN_API_KEY`** remain mandatory. |
| **Networking** | RDS and ECS tasks in private subnets where possible; ALB TLS; no public bind for Postgres; S3 bucket policy and encryption (SSE-S3 baseline in Terraform; SSE-KMS optional). |
| **LIMS** | Set **`LIMS_BASE_URL`** to production prior-auth HTTP; confirm **`POST /v1/prior-authorizations`** contract and timeouts. |
| **Embeddings / pgvector** | **`OPENAI_EMBEDDING_DIMENSIONS`** must match the chosen **`OPENAI_EMBEDDING_MODEL`**; changing dimensions after seeding payer rules requires a planned migration or re-seed. |
| **Observability** | LangSmith for traces; **`GET /metrics`** for Prometheus in your environment; ship container logs to a central store (e.g. CloudWatch, already configured in Terraform). |
| **Readiness** | Load balancers and orchestrators can use **`GET /v1/ready`** for dependency checks; **`GET /health`** for simple liveness only. |
| **Dependencies** | Lock container image tags and rebuild on CVE notices; keep Postgres major version aligned with RDS. |

## Observability

- **Grafana + Prometheus (local Compose):** after `docker compose up`, open Grafana at [http://localhost:3000](http://localhost:3000) (default `admin` / `admin`). Prometheus: [http://localhost:9090](http://localhost:9090). Targets include **`rcm-guardian-api`** scraping **`/metrics`** from the FastAPI container; panels use `rcm_auditor_confidence`, `rcm_finding_total`, `rcm_route_human_review_total`, and `rcm_graph_duration_seconds`.
- **LangSmith:** **`LANGCHAIN_API_KEY`** and **`LANGCHAIN_TRACING_V2=true`** are **required** in `.env` (validated at startup). Traces go to the live LangSmith API. `/v1/ready` reports LangSmith configuration flags.
- **`rcm_guardian/app.py`:** comments note OpenTelemetry/Sentry hooks for production.

## License

This repository does not include a `LICENSE` file. Add one (e.g. proprietary notice or OSS license) before publishing or open-sourcing the project.
