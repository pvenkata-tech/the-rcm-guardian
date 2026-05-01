# RCM Guardian

## Executive summary

**Objective:** Reduce friction in the **Order-to-Cash** path by replacing manual EOB and remittance review with **autonomous, stateful agents** that honor payer-specific policy complexity while staying inside **HIPAA-aware** architecture boundaries (least-privilege IAM, encrypted artifacts, auditable checkpoints—not a compliance attestation in this repo, but the shape is intentional).

Production-oriented prototype for an **agentic Revenue Cycle Management (RCM)** workflow: multimodal extraction from billing documents (PDF/image), **pgvector** retrieval over payer policy snippets, forensic auditing against rules and **LabVantage-style LIMS** reconciliation signals, and **human-in-the-loop** pauses with **checkpoint-resumable** LangGraph state.

## Run on localhost (data ready)

Payer rules and pgvector schema load **automatically** when the API starts (`lifespan` → `seed_payer_rules_if_empty`).

1. **Start the full stack** (Postgres + LIMS mock + API). Put **`OPENAI_API_KEY`** in **`.env`** (copy from **`.env.example`**) — **`scripts/start-local.ps1`** / **`start-local.sh`** refuse to start without it.

   ```bash
   docker compose up --build
   ```

   Windows helper (creates `./uploads`, optional `.env` from `.env.example`):

   ```powershell
   .\scripts\start-local.ps1
   ```

2. **Confirm DB + seed data**:

   Open [http://localhost:8000/v1/ready](http://localhost:8000/v1/ready) — you should see `"seeded": true` and `payer_rules_count` ≥ 3.

   API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

3. **Optional — seed without starting the API** (Postgres must already be listening on port 5432):

   ```bash
   docker compose up -d postgres
   pip install -r requirements.txt
   python scripts/ensure_local_data.py
   ```

**OpenAI is required:** put **`OPENAI_API_KEY`** in a `.env` file next to `docker-compose.yml` (never commit it). The API validates configuration at startup and uses OpenAI for **embeddings** (RAG) and **primary vision extraction**. If OpenAI vision fails and **`ANTHROPIC_API_KEY`** is set, extraction retries on **Claude** (`rcm_guardian/agents/vision_extract.py`).

**Tests:** `tests/test_complete_flow_mocked.py` patches vision + uses fixture RAG; `tests/test_eob_processing.py` stubs embeddings and vision unless **`RUN_OPENAI_INTEGRATION=1`**. **`tests/fixtures`** still validates **state transitions and business logic** independent of **LLM non-determinism**.

## Local Dev, Cloud Logic (interview strategy)

**Demo everything in Docker** — fast, free, and identical container images to what you would promote to **AWS Fargate**.

**Talking point:** “I containerized the full stack with Docker Compose so my dev environment matches production topology: FastAPI + Postgres/pgvector, a dedicated **LIMS HTTP mock** (same integration shape as LabVantage behind a VPC), and a **bind-mounted uploads volume** as the local analogue of encrypted **S3** (**SSE-S3** baseline; **SSE-KMS** with CMKs where auditors require explicit encryption-at-rest ownership). Terraform under `terraform/` shows how this becomes ECS Fargate, RDS, Secrets Manager, private **S3**, and least-privilege **IAM** — without needing a hundred-dollar always-on AWS sandbox for a first-round screen-share.”

| Concern | Local (Docker Compose) | AWS (discussion / `terraform/`) |
|--------|---------------------------|-----------------------------------|
| **Runtime** | FastAPI + Uvicorn in `api` container | **ECS on Fargate** behind **ALB** |
| **Database** | `pgvector/pgvector:pg16` | **RDS PostgreSQL** (pgvector-capable) |
| **Secrets** | `.env` (git-ignored), `.env.example` template | **Secrets Manager** (`DATABASE_URL`, OpenAI secret, optional Anthropic secret) |
| **Document storage** | `./uploads` → `/uploads` (object-store analogue) | **Private S3** with **SSE-S3** baseline + path to **SSE-KMS** (customer-managed keys) for encryption-at-rest in regulated workloads (`terraform/s3.tf`) |
| **LIMS** | `lims-mock` service on `:8081` | Internal HTTP bridge / partner VPC (same contract) |
| **Scaling** | Single task per service locally | **ECS Service** desired count + auto-scaling policies (add in AWS Console / TF) |

**LIMS interview win:** “The forensic auditor performs an **HTTP round-trip** to the LIMS facade (`LIMS_BASE_URL`) to **reconcile clinical intent with financial claims**—a closed-loop **Order-to-Result** validation step before denial-risk scoring. In Compose that’s the `lims-mock` service; in AWS it’s the same contract over a private integration.”

## Architecture

```mermaid
flowchart TB
    subgraph Clients
        UI[Web / EHR / Batch Jobs]
        Analyst[Human Analyst]
    end

    subgraph AWS_Discussion["AWS (terraform/)"]
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

    subgraph Docker_Local["Docker Compose (demo)"]
        API[FastAPI :8000]
        PG[(Postgres 16 + pgvector)]
        LIMS[LIMS mock :8081]
        VOL[(./uploads volume)]
    end

    subgraph Orchestration["LangGraph + Persistence"]
        direction TB
        EX[Extraction Node<br/>Multimodal Vision]
        RO[Policy Oracle<br/>Agentic RAG]
        FA{Forensic Auditor<br/>Denial Prediction}
        HITL[Human Review Gate<br/>State Suspended]
        OUT([Output: Validated Claim])
        EX --> RO
        RO --> FA
        FA -->|Low confidence / policy pause| HITL
        HITL -->|"Feedback / Resume (Command)"| FA
        FA -->|High confidence| OUT
    end

    UI --> API
    Analyst -->|resume| API
    API --> EX
    RO --> PG
    FA -->|HTTP when LIMS_BASE_URL set| LIMS
    API --> VOL
    API -.->|same images / IAM-ready env vars| ECS
```

```mermaid
sequenceDiagram
    participant C as Client
    participant F as FastAPI
    participant U as /uploads volume
    participant G as LangGraph
    participant V as Vision LLM
    participant DB as Postgres/pgvector
    participant L as LIMS HTTP mock

    C->>F: POST /v1/process (base64 doc + thread_id?)
    F->>U: optional persist inbound artifact
    F->>G: ainvoke(state, checkpoint thread_id)
    G->>V: Extract tables / billing fields
    V-->>G: extracted_billing_data JSON
    G->>DB: Embed query + similarity search
    DB-->>G: payer_rules[]
    G->>L: POST /v1/prior-authorizations
    L-->>G: CPT-level PA coverage

    alt Auditor confidence >= 0.85
        G-->>F: completed state
        F-->>C: 200 ProcessDocumentResponse
    else Auditor confidence < 0.85
        Note over G: Checkpoint persisted via MemorySaver (same thread_id) before API returns 202 — supports resume after rate limits or human review
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
| **API** | Async FastAPI with Pydantic request/response models |
| **Orchestration** | LangGraph stateful graph with conditional edges + `interrupt()` HITL |
| **Multimodal extraction** | PDF **targeted rasterization** (PyMuPDF) + Vision model with **table-first** prompts; **strategic chunking** (e.g., render priority surfaces only) to **reduce token pressure and latency** while preserving fidelity on tabular billing lines |
| **Agentic RAG** | Embeddings + cosine similarity in PostgreSQL/pgvector |
| **Auditing** | Rules vs CPT/NPI; **reconciliation** vs LIMS prior-auth signals → denial-risk scoring |
| **LIMS** | In-process mock **or** HTTP **lims-mock** (`LIMS_BASE_URL`) for **Order-to-Result** alignment |
| **Document persistence** | Optional writes under `UPLOADS_DIR` (Compose: `./uploads`) |
| **Persistence** | `MemorySaver` checkpoints (swap for PostgresSaver at scale) |
| **Observability** | **Designed for** OpenTelemetry **and** Sentry-style capture points in `rcm_guardian/app.py`; Grafana / Prometheus-compatible metrics would hang off the same signals—oriented toward KPIs such as **denial-rate forecasting inputs** and **agent turnaround time** per thread |
| **IaC** | `terraform/` — VPC, ALB, ECS Fargate, ECR, RDS, Secrets Manager, **S3 + IAM** |

## Tech stack

- Python 3.12, FastAPI, Uvicorn  
- LangGraph, LangChain (OpenAI-compatible)  
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
│   ├── start-local.ps1      # Windows: uploads + optional .env + compose up
│   ├── start-local.sh       # macOS/Linux: same
│   └── ensure_local_data.py # Seed DB only (needs Postgres on localhost)
├── docker/
│   └── lims-mock/          # FastAPI microservice — LabVantage-style PA API
├── uploads/                # bind-mount target (gitignored except .gitkeep)
├── terraform/              # VPC, ALB, ECS, RDS, ECR, Secrets, S3, IAM
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
│   │   └── vision_extract.py   # OpenAI vision + Anthropic fallback
│   ├── models/schemas.py
│   └── services/
│       ├── rag_service.py
│       ├── lims_service.py   # HTTP or in-process mock
│       └── storage_service.py # local volume ↔ S3 narrative
└── tests/
    ├── conftest.py              # pytest sets placeholder OPENAI_API_KEY unless already exported
    ├── fixtures/
    │   ├── mock_eob.json
    │   └── mock_payer_rules.json
    ├── test_complete_flow_mocked.py
    └── test_eob_processing.py
```

The repo folder may use hyphens; the Python package **`rcm_guardian`** uses underscores for valid imports.

## Quick start

### Docker Compose (recommended demo)

```bash
docker compose up --build
```

| Endpoint | URL |
|----------|-----|
| RCM API + Swagger | http://localhost:8000 and `/docs` |
| LIMS mock + docs | http://localhost:8081/docs |
| Postgres | `localhost:5432` (`rcm` / `rcm` / `rcm_guardian`) |
| Local “object storage” | `./uploads` on your host → `/uploads` in `api` |

Compose passes **`OPENAI_API_KEY`**, optional **`ANTHROPIC_API_KEY`**, and model overrides from your **`.env`** (see **`.env.example`**). **`LIMS_BASE_URL=http://lims-mock:8080`** and **`PERSIST_UPLOADS=true`** are set in Compose so inbound artifacts land under **`./uploads`**.

**Never commit `.env`** (it contains secrets).

### Local Python (without full Compose)

1. Run Postgres with pgvector (or `docker compose up -d postgres`).  
2. `pip install -r requirements.txt`  
3. Optionally export `LIMS_BASE_URL` pointing at a running mock (`http://127.0.0.1:8081` if you start `lims-mock` separately).  

```bash
export OPENAI_API_KEY=sk-...
export DATABASE_URL=postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian
uvicorn rcm_guardian.app:app --reload --host 0.0.0.0 --port 8000
```

Optional vision fallback: `export ANTHROPIC_API_KEY=...` (same variables as **`.env.example`**).

## Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `DATABASE_URL` | local Docker DSN | Async SQLAlchemy + asyncpg |
| `OPENAI_API_KEY` | empty | **Required** — embeddings (RAG) + primary vision extraction |
| `OPENAI_VISION_MODEL` | `gpt-4o` | OpenAI multimodal model |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model for payer rules |
| `ANTHROPIC_API_KEY` | empty | Optional — vision extraction retry after OpenAI failure |
| `ANTHROPIC_VISION_MODEL` | `claude-3-5-sonnet-20241022` | Claude model for fallback path |
| `LIMS_BASE_URL` | empty | Set to `http://lims-mock:8080` (Compose) for HTTP LIMS |
| `UPLOADS_DIR` | `/uploads` | Local volume mount path |
| `PERSIST_UPLOADS` | `false` | Persist decoded uploads under `UPLOADS_DIR` |
| `DOCUMENTS_S3_BUCKET` | empty | Injected by Terraform for Fargate (`PutObject` IAM ready) |
| `OTEL_SERVICE_NAME` | `rcm-guardian` | Telemetry resource name |

## LangGraph state (`RCMGraphState`)

Key fields: `raw_text`, `extracted_billing_data`, `payer_rules`, `audit_report`, `is_human_required`, plus input/checkpoint keys (`document_base64`, `thread_id`, …). Checkpointer: **`MemorySaver`** keyed by `configurable.thread_id`.

## HTTP API

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Liveness |
| `POST` | `/v1/process` | Submit document; **200** complete or **202** human review |
| `POST` | `/v1/resume` | Resume with `Command(resume=...)` |
| `GET` | `/v1/ready` | DB connectivity + payer-rules seed count (`seeded: true` when OK) |

## Testing

```bash
pytest tests/test_eob_processing.py -q
pytest tests/test_complete_flow_mocked.py -v
```

- **`tests/test_complete_flow_mocked.py`** — full LangGraph path (**extract → Rule Oracle → forensic auditor → HITL**) using **`tests/fixtures/mock_eob.json`** (mock tabular EOB extraction) and **`tests/fixtures/mock_payer_rules.json`** (mock vector-hit payloads). No Postgres; vision and **`embed_query`** are patched so CI stays deterministic.
- **`tests/test_eob_processing.py`** — LIMS contract test without Postgres; graph/API cases **skip** until Postgres is reachable (`docker compose up -d postgres`). Embeddings and vision are **stubbed** unless **`RUN_OPENAI_INTEGRATION=1`** (live OpenAI).

For HTTP LIMS verification, run Compose (includes `lims-mock`) and exercise `/v1/process` manually.

## Terraform (AWS — optional spend)

All definitions live in **`terraform/`** (not applied by default):

- VPC (public + private subnets, NAT)
- ALB + HTTP/HTTPS listeners
- ECS Fargate cluster, service, task definition (image from **ECR**)
- **RDS PostgreSQL** + Secrets Manager `DATABASE_URL`
- **S3** private bucket (**SSE-S3** in-tree; production hardening adds **SSE-KMS** with CMKs for HIPAA-grade encryption-at-rest storylines) + **ECS task IAM** for `GetObject`/`PutObject`
- CloudWatch log group

```bash
cd terraform
terraform init
cp terraform.tfvars.example terraform.tfvars   # edit values / image tag
terraform apply
```

Narrative for directors: Fargate tasks assume a **task role** scoped to the documents bucket and rely on **Secrets Manager** instead of baking credentials. Pair **SSE-KMS** (customer-managed keys) with bucket policies and KMS grants where auditors expect clear **encryption-at-rest** ownership—then layer VPC endpoints, PrivateLink, and BAAs as organizational controls beyond this prototype.

## Security notes

- Billing payloads are sensitive; this repo is a prototype, not a HIPAA attestation.  
- Never commit `.env`. Restrict RDS/S3 network paths in real accounts.

## Observability (OpenTelemetry / Sentry / Grafana)

Integration points are **called out in code** (`rcm_guardian/app.py`) so production wiring is deliberate—not an afterthought: OTLP exporters for traces/metrics, **Sentry** for error budgets on agent failures, and **Grafana**-friendly dashboards that roll up **denial-risk pipeline latency** and **human-review queue depth** per `thread_id`. The prototype ships comments rather than vendor deps so local demos stay lightweight.

## License

Specify your organization’s license here.
