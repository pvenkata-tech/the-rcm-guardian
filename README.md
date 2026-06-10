<div align="center">

# RCM Guardian

**Multimodal billing intelligence — LangGraph extraction, payer-rule RAG, LIMS reconciliation, Postgres checkpoints, and LangSmith tracing (validated at API startup for the default stack).**

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-111?style=flat-square&logo=langchain&logoColor=white)](https://langchain-ai.github.io/langgraph/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL_16_%2B_pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)](https://github.com/pgvector/pgvector)
[![Docker](https://img.shields.io/badge/Docker_Compose-2496ED?style=flat-square&logo=docker&logoColor=white)](https://docs.docker.com/compose/)
[![Terraform](https://img.shields.io/badge/Terraform-AWS-7B42BC?style=flat-square&logo=terraform&logoColor=white)](https://www.terraform.io/)
[![Prometheus](https://img.shields.io/badge/Prometheus-E6522C?style=flat-square&logo=prometheus&logoColor=white)](https://prometheus.io/)
[![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat-square&logo=grafana&logoColor=white)](https://grafana.com/)

</div>

---

## The Business Problem
Unstructured clinical notes often lack the exact data points required for rigid billing codes. This discrepancy causes prior-authorization failures, requires manual auditing, and results in downstream claim denials.

## The Architecture
The RCM Guardian is an AI-orchestrated pipeline that extracts and validates clinical data before claim submission. It processes billing documents in any format, matches extracted data against payer policy rules stored in a searchable knowledge base, and forensically audits the results against the Laboratory Information Management System. If the AI auditor's confidence falls below a set threshold, the workflow pauses and routes the claim to a human reviewer — preserving full context so the reviewer can pick up exactly where the AI left off.

## The Objective
Built to identify billing discrepancies at the source. Catching missing data before submission reduces manual data entry, lowers the claim denial rate, and speeds up the revenue cycle.

---

## 📑 Contents

| | |
| :--- | :--- |
| 📋 | [Overview](#overview) |
| 🚀 | [Run locally](#run-locally) |
| ⚡ | [Quick reference](#quick-reference) |
| 🐛 | [Troubleshooting](#troubleshooting) |
| 🌐 | [Deployment topology](#deployment-topology) |
| 🏗️ | [Architecture](#architecture) |
| ✨ | [Features](#features) |
| 🛠️ | [Tech stack](#tech-stack) |
| 📁 | [Repository layout](#repository-layout) |
| 🔧 | [Configuration](#configuration) |
| 🔀 | [LangGraph state](#langgraph-state-rcmgraphstate) |
| 🌍 | [HTTP API](#http-api) |
| 🧪 | [Testing](#testing) |
| ☁️ | [Terraform (AWS)](#terraform-aws) |
| 🔒 | [Security](#security) |
| ✅ | [Production checklist](#production-checklist) |
| 📊 | [Observability](#observability) |
| 📄 | [License](#license) |

---

## 📋 Overview

RCM Guardian is a FastAPI service that runs a LangGraph workflow over billing documents: multimodal extraction (PDF/image), retrieval of payer policy rules in **PostgreSQL** using the **pgvector** extension, forensic auditing with a **mock LIMS** (HTTP `lims-mock` in Compose or a **deterministic in-process mock** when `LIMS_BASE_URL` is unset — fixed CPT allow-lists, not random data) or a **real LIMS URL** when you set `LIMS_BASE_URL`, Postgres-backed checkpoints, and **LangSmith** tracing to the live LangSmith API.

The codebase is **built for production-style deployment**: Docker images align with an AWS Fargate–style layout defined under `terraform/`. Configure secrets via environment variables locally and via AWS Secrets Manager in deployed environments.

## 🚀 Run locally

Payer rules are seeded at API startup (`lifespan` → `seed_payer_rules_if_empty`). The `payer_rules` table and pgvector column are created idempotently via raw DDL in **`PayerRulesRAG.ensure_schema`** (`rcm_guardian/services/rag_service.py`) — there is **no Alembic** migration chain in this repo (fine for demos and small teams; production orgs usually add versioned migrations).

1. **Stack** (Postgres + **LIMS mock** + API + Prometheus + Grafana — run from repo root, where **`docker-compose.yml`** and **`requirements.txt`** live): copy **`.env.example`** → **`.env`**, set **`OPENAI_API_KEY`** and **`LANGCHAIN_API_KEY`** in **`.env`**. This repository’s **default Compose stack expects LangSmith** (`LANGCHAIN_TRACING_V2=true`); missing keys fail fast at API startup with an explicit **`RuntimeError`** / **`ValidationError`** message (see **`rcm_guardian/config.py`** and **`rcm_guardian/app.py`**). Get a key at [smith.langchain.com](https://smith.langchain.com). **`samples/start-local.ps1`** / **`samples/start-local.sh`** check **`docker`**, **`docker compose`**, both API keys, and ensure **`samples/generated/`** exists. **Service URLs and ports** are in [Quick reference](#quick-reference) below.

   ```bash
   docker compose up --build
   ```

   Windows:

   ```powershell
   .\samples\start-local.ps1
   ```

   macOS / Linux:

   ```bash
   chmod +x samples/start-local.sh
   ./samples/start-local.sh
   ```

2. **Health / readiness**:
   - **`GET /health`** — liveness (no DB); use for simple probes.
   - **`GET /v1/ready`** — DB reachable, payer-rules count, and **non-secret** config snapshot (`ai_models`, LangSmith flags, `lims_base_url`, uploads). Expect `"seeded": true` and `payer_rules_count` ≥ 4 after startup. API reference: [http://localhost:8000/docs](http://localhost:8000/docs).

3. **Seed without API** (Postgres on port 5432):

   ```bash
   docker compose up -d postgres
   pip install -r requirements.txt
   python samples/ensure_local_data.py
   ```

**Models:** OpenAI is required for embeddings (RAG) and primary vision extraction. If OpenAI vision fails and **`ANTHROPIC_API_KEY`** is set, extraction retries using Claude (`rcm_guardian/agents/vision_extract.py`).

**Tests:** `tests/test_complete_flow_fixtures.py` patches vision and embeddings and uses fixture payer rules (no Postgres). `tests/test_eob_processing.py` stubs LLM calls unless **`RUN_OPENAI_INTEGRATION=1`**.

**Synthetic documents (non-PHI):** Run **`python samples/generate_synthetic_samples.py`** from the repo root. For each **`synthetic_eob_01` … `_05`**, the **`.pdf` and `.png` are different synthetic documents** (distinct text, layout, and `asset_key` — the PNG is **not** a snapshot of the PDF). Outputs go to **`samples/generated/`** (gitignored). Docker Compose mounts that folder at **`/uploads`**. See **`samples/README.md`**. Do not use random internet “EOB samples,” which may contain real PHI or unclear licensing.

## ⚡ Quick reference

### 🐳 Docker Compose

```bash
docker compose up --build
```

| | Endpoint | URL |
| :---: | --- | --- |
| 🚀 | **API** | http://localhost:8000 (`/docs` OpenAPI; `/metrics` for Prometheus) |
| 🏥 | **LIMS mock (host)** | http://localhost:8081/docs — see **LIMS ports** below |
| 📈 | **Prometheus** | http://localhost:9090 |
| 📊 | **Grafana** | http://localhost:3000 (default login `admin` / `admin` — change in production) |
| 🗄️ | **Postgres** | `localhost:5432` — db `rcm_guardian`, user/password `rcm` |
| 📂 | **Artifact volume** | `./samples/generated` → `/uploads` in `api` |

#### LIMS mock: host port vs container port

Compose maps **`8081:8080`**: the FastAPI process **inside** the `lims-mock` container listens on **8080**. Other services on the Docker network (for example `api`) should use **`http://lims-mock:8080`** — this is the Compose default for **`LIMS_BASE_URL`**. **From your laptop browser or curl on the host**, use **`http://localhost:8081`** (published port). Using `localhost:8081` **from inside** a container (or using `lims-mock:8081`) is a common source of **connection refused** errors.

Compose provisions the **Prometheus** datasource (UID `prometheus`), scrapes **`http://api:8000/metrics`**, and loads the dashboard JSON at **`dashboards/grafana-denial-forecasting.json`** (repo path; mounted read-only into Grafana). **`LANGCHAIN_API_KEY`** must be set for the `api` container (see **`.env.example`**).

Do not commit **`.env`**.

### 🐍 Local Python only

1. PostgreSQL 16 with the **pgvector** extension available to your database user  
2. `pip install -r requirements.txt`  
3. Optional: **`LIMS_BASE_URL`** — unset uses the **deterministic in-process** mock; if the **`lims-mock`** container is running on the host, use **`http://127.0.0.1:8081`** (host-published port), not `8080`, from processes on the host

```bash
export OPENAI_API_KEY=sk-...
export OPENAI_VISION_MODEL=gpt-4o
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
export OPENAI_EMBEDDING_DIMENSIONS=1536
export LANGCHAIN_API_KEY=lsv2_pt_...   # required for default settings — from LangSmith
export LANGCHAIN_TRACING_V2=true       # required (default); must not be false
export DATABASE_URL=postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian
uvicorn rcm_guardian.app:app --reload --host 0.0.0.0 --port 8000
```

Optional: **`ANTHROPIC_API_KEY`** for vision fallback.

## 🐛 Troubleshooting

| Symptom | What to check |
|--------|----------------|
| **LIMS / prior-auth connection refused** | **Host vs container URLs:** API in Compose uses **`http://lims-mock:8080`**. From the host OS, use **`http://127.0.0.1:8081`**. Do not mix `lims-mock:8081` or in-container `localhost:8081` unless you know the listener is there. |
| **Files under `./samples/generated` missing inside the container (Windows)** | Enable **file sharing** for the drive in Docker Desktop; prefer **WSL2** backend; avoid paths Docker cannot bind-mount. Line-ending or path issues are common on Windows — keep the repo on a shared drive Docker is allowed to mount. |
| **API exits on startup with LangSmith / OpenAI errors** | Read the **`RuntimeError`** preamble from **`lifespan`** plus the nested **`ValidationError`**; confirm **`.env`** is beside **`docker-compose.yml`** and that **`LANGCHAIN_TRACING_V2`** is not set to **`false`**. |

## 🌐 Deployment topology

| Concern | Docker Compose | AWS (`terraform/`) |
|--------|----------------|---------------------|
| Runtime | FastAPI + Uvicorn in `api` service | ECS on Fargate behind ALB |
| Database | `pgvector/pgvector:pg16` | RDS PostgreSQL (pgvector-capable) |
| Secrets | `.env` (not committed); `.env.example` template | Secrets Manager (`DATABASE_URL`, OpenAI, LangSmith, optional Anthropic) |
| Documents | `./samples/generated` → `/uploads` in `api` | Private S3 (`terraform/s3.tf`); SSE-S3 baseline, SSE-KMS optional |
| LIMS | **Compose `api`:** **`LIMS_BASE_URL`** defaults to **`http://lims-mock:8080`** (Docker DNS, container listens on **8080**; host maps **8081:8080**). **Host tools / browser:** `http://localhost:8081`. **Local `uvicorn` (no Compose):** omit **`LIMS_BASE_URL`** for the in-process deterministic mock, or set **`http://127.0.0.1:8081`** if **`lims-mock`** is running. | `lims_base_url` Terraform → **`LIMS_BASE_URL`** for a real system |
| Metrics / dashboards | Prometheus `:9090`, Grafana `:3000` (local Compose) | Use managed Grafana/Prometheus or ADOT in AWS |
| Scaling | One task per service | ECS desired count; autoscaling configured separately |

**`LIMS_BASE_URL`** defaults to **`http://lims-mock:8080`** for the **`api`** service in Compose (Docker DNS + internal port **8080**). Override in **`.env`** for a **real** LIMS (same `POST /v1/prior-authorizations` JSON contract). **LangSmith:** for this repo’s **default settings**, **`LANGCHAIN_API_KEY`** must be set and **`LANGCHAIN_TRACING_V2`** must be **`true`** — **`get_settings()`** validates on startup and **`lifespan`** wraps failures in a **`RuntimeError`** with a short checklist (forks that need offline mode must relax **`rcm_guardian/config.py`**).

## 🏗️ Architecture

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
        LS[LangSmith default stack LANGCHAIN_API_KEY]
    end

    subgraph Docker_Local["Docker Compose"]
        API[FastAPI :8000]
        PG[(Postgres 16 + pgvector)]
        LIMSM[LIMS mock host :8081 in-container :8080]
        VOL[(./samples/generated volume)]
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
    participant DB as Postgres with pgvector
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

## ✨ Features

| | Area | Description |
| :---: | --- | --- |
| 🔌 | **API** | Async FastAPI; Pydantic request/response models |
| 🔁 | **Orchestration** | LangGraph graph with conditional routing and `interrupt()` for HITL |
| 👁️ | **Extraction** | PyMuPDF PDF rasterization + vision model; prompts tuned for tabular billing lines |
| 🧠 | **RAG** | OpenAI embeddings + cosine similarity in PostgreSQL using the pgvector extension |
| ⚖️ | **Auditing** | Rule hits vs CPT/NPI; LIMS reconciliation; structured findings (`finding_kind`, `status`, `reason`) and `prior_authorization_reconciliation` |
| 🏥 | **LIMS** | **`lims-mock`** HTTP service (deterministic **`docker/lims-mock`**) or **in-process** deterministic rules (`lims_service.py`); or real URL via **`LIMS_BASE_URL`** |
| 💾 | **Artifact storage** | Optional `UPLOADS_DIR` persistence (Compose: `./samples/generated` → `/uploads`) |
| ♻️ | **Checkpoints** | **`AsyncPostgresSaver`** in the same database as pgvector (multi-instance safe) |
| 📈 | **Observability** | **`GET /metrics`** (Prometheus); **Grafana** loads **`dashboards/grafana-denial-forecasting.json`**; **LangSmith** (**`LANGCHAIN_*`**, validated at startup); OTLP/Sentry placeholders in `rcm_guardian/app.py` |
| 🏗️ | **IaC** | `terraform/`: VPC, ALB, ECS, ECR, RDS, Secrets Manager, S3, IAM |

**Human-in-the-loop (HITL):**

1. The graph runs extraction and auditing; structured billing data and findings accumulate in graph state.
2. If auditor confidence is below threshold, the graph calls **`interrupt()`** — state is checkpointed to Postgres and **`POST /v1/process`** returns **202** with an interrupt payload.
3. The analyst sends **`POST /v1/resume`** with the same **`thread_id`** and **`human_feedback`**; the graph resumes with **`Command(resume=...)`** and returns a completed **200** payload when finished.

## 🛠️ Tech stack

| Stack | Details |
| :--- | :--- |
| 🐍 **Runtime** | **Dockerfile:** `python:3.12-slim` · **Application code:** Python **3.10+** (PEP 604 unions, `from __future__ import annotations`; no 3.12-only syntax required) · FastAPI · Uvicorn |
| 🔗 **AI / orchestration** | LangGraph · LangChain · OpenAI (required) · optional Anthropic vision fallback |
| 🗄️ **Data** | PostgreSQL 16 · pgvector · async SQLAlchemy |
| 📦 **Local ops** | Docker Compose — API, Postgres, **lims-mock**, Prometheus, Grafana |
| ☁️ **Cloud** | Terraform on AWS (Fargate, RDS, ALB, S3, Secrets Manager) |

## 📁 Repository layout

```text
the-rcm-guardian/
├── docker-compose.yml
├── Dockerfile
├── .env.example
├── samples/
│   ├── README.md
│   ├── assets/
│   │   ├── samples-hub.png
│   │   └── samples-hub.svg
│   ├── start-local.ps1
│   ├── start-local.sh
│   ├── ensure_local_data.py
│   ├── generate_synthetic_samples.py
│   ├── render_readme_assets.py
│   └── generated/
├── docker/
│   ├── grafana/
│   │   └── provisioning/
│   ├── prometheus/
│   └── lims-mock/
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

## 🔧 Configuration

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
| `LANGCHAIN_TRACING_V2` | `true` | **Must be `true`** for default settings — enforced in **`Settings`**; startup surfaces a **`RuntimeError`** if validation fails |
| `LANGCHAIN_API_KEY` | — | **Required** for default settings — LangSmith API key ([Smith](https://smith.langchain.com)); unset key fails **`get_settings()`** before the app serves traffic |
| `LANGCHAIN_PROJECT` | `rcm-guardian` | LangSmith project name |
| `LANGCHAIN_ENDPOINT` | `https://api.smith.langchain.com` | LangSmith API base URL (e.g. EU region if required) |

## 🔀 LangGraph state (`RCMGraphState`)

Field definitions and HITL semantics are documented in **`rcm_guardian/state.py`**. **`audit_report`** includes structured findings and **`prior_authorization_reconciliation`**. Checkpoints are stored in **PostgreSQL** via **`AsyncPostgresSaver`**, keyed by **`configurable.thread_id`**.

## 🌍 HTTP API

| | Method | Path | Description |
| :---: | --- | --- | --- |
| 💓 | `GET` | `/health` | Liveness |
| 📈 | `GET` | `/metrics` | Prometheus text exposition |
| 📄 | `POST` | `/v1/process` | Submit document; `200` completed or `202` human review |
| ▶️ | `POST` | `/v1/resume` | Resume interrupted graph with `Command(resume=...)` |
| ✅ | `GET` | `/v1/ready` | Readiness: DB + seed status; returns `ai_models`, LangSmith config flags (no secrets), LIMS URL, uploads paths |

## 🧪 Testing

```bash
pytest -q
# or individually:
pytest tests/test_eob_processing.py -q
pytest tests/test_complete_flow_fixtures.py -v
```

- **`test_complete_flow_fixtures.py`**: Full graph path with patched vision/embeddings, fixture payer rules, and **in-process LIMS mock** (`MemorySaver`).
- **`test_eob_processing.py`**: Patches LIMS HTTP for Postgres e2e; skips if DB unavailable; use **`RUN_OPENAI_INTEGRATION=1`** for live OpenAI.

## ☁️ Terraform (AWS)

Resources under **`terraform/`** include VPC, ALB, ECS Fargate, ECR, RDS, Secrets Manager, S3, IAM, and CloudWatch logs. Apply only in accounts you control.

```bash
cd terraform
terraform init
cp terraform.tfvars.example terraform.tfvars   # edit values
terraform apply
```

ECS tasks should use a task role scoped to the documents bucket and load database/API secrets from Secrets Manager rather than environment literals in task definitions for production. Set **`langsmith_api_secret_arn`** in `terraform.tfvars` so **`LANGCHAIN_API_KEY`** is injected (**required**). Optional **`lims_base_url`** sets **`LIMS_BASE_URL`**.

## 🔒 Security

- Treat billing and PHI-adjacent payloads as sensitive; operational compliance (e.g. HIPAA) is an organizational control beyond this repository.
- Do not commit **`.env`** or credentials; use **AWS Secrets Manager** (or equivalent) in deployed environments and inject at runtime (see **`langsmith_api_secret_arn`** and related task definitions under **`terraform/`**).
- Restrict RDS and S3 network access (security groups, bucket policies, VPC endpoints) in production accounts.
- **API surface:** this service does **not** ship API keys or OAuth for callers. Put it behind an authenticated gateway, private network, or mTLS as your threat model requires; terminate TLS at the load balancer in AWS.
- **Compose-only tools:** Prometheus and Grafana default credentials (`admin` / `admin`) and open ports are for **local development** only—do not expose them on the public internet without hardening (secrets, TLS, auth, allowlists).

## ✅ Production checklist

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

## 📊 Observability

- **Grafana + Prometheus (local Compose):** after `docker compose up`, open Grafana at [http://localhost:3000](http://localhost:3000) (default `admin` / `admin`). Prometheus: [http://localhost:9090](http://localhost:9090). Targets include **`rcm-guardian-api`** scraping **`/metrics`** from the FastAPI container; panels use `rcm_auditor_confidence`, `rcm_finding_total`, `rcm_route_human_review_total`, and `rcm_graph_duration_seconds`.
- **LangSmith:** **`LANGCHAIN_API_KEY`** and **`LANGCHAIN_TRACING_V2=true`** are **required by default** in **`.env`** — **`rcm_guardian/config.py`** validates on settings load and **`rcm_guardian/app.py`** **`lifespan`** re-raises **`ValidationError`** as a **`RuntimeError`** with a short remediation line. Traces go to the live LangSmith API. **`GET /v1/ready`** reports LangSmith configuration flags (never the secret value).
- **`rcm_guardian/app.py`:** commented **OpenTelemetry** tracer setup (OTLP → collector/Grafana backends) and **Sentry** initialization pattern — enable by adding `opentelemetry-*` / `sentry-sdk` and uncommenting; complements **`GET /metrics`** for denial-rate and audit panels in Grafana.

## 📄 License

This repository does not include a `LICENSE` file. Add one (e.g. proprietary notice or OSS license) before publishing or open-sourcing the project.
