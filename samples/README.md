<div align="center">

# Samples

**Local helpers & synthetic documents** for RCM Guardian (no real PHI).

[![Synthetic non-PHI](https://img.shields.io/badge/Documents-synthetic%20non--PHI-0891b2?style=flat-square)](./README.md)
[![Docker volume](https://img.shields.io/badge/Docker-generated%E2%86%92_uploads-2496ED?style=flat-square&logo=docker&logoColor=white)](../docker-compose.yml)
[![Python 3.12+](https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)

<br/>

<img src="assets/samples-hub.svg" width="820" alt="Diagram: samples helpers flow to generated folder and Docker API uploads mount" />

<br/>

<img src="assets/ordinal-scenarios.svg" width="780" alt="Table graphic: ordinal 01-05 PDF vs PNG scenario names" />

</div>

---

## Contents

| | |
| :--- | :--- |
| 📂 | [What lives here](#what-lives-here) |
| 🔢 | [Ordinal reference](#ordinal-reference-generated-synthetic-files) |
| ⚡ | [Commands](#commands) |
| 🔁 | [Data flow (Mermaid)](#data-flow) |

---

## What lives here

| Path | Purpose |
|------|---------|
| **`start-local.ps1`** / **`start-local.sh`** | From **repo root**: checks `.env` for OpenAI + LangSmith keys, ensures **`samples/generated/`** exists, then **`docker compose up --build`**. |
| **`ensure_local_data.py`** | Seed payer rules in Postgres without starting the API: `python samples/ensure_local_data.py` (run from **repo root**). |
| **`generate_synthetic_samples.py`** | Writes five ordinal pairs **`synthetic_eob_01` … `_05`**: **`.pdf` and `.png` are different synthetic documents** (not a PNG export of the PDF), each with its own **`asset_key`**. |
| **`generated/`** | **Gitignored** PDF/PNG outputs. Compose bind-mounts this directory to **`/uploads`** in the `api` service. |
| **`assets/`** | **Committed** SVG diagrams used by this README (not patient data). |

Each synthetic file embeds a **stable `asset_key`** line. The generator **requires all 10 outputs to have distinct SHA-256** hashes.

---

## Ordinal reference (`generated/` synthetic files)

Each `synthetic_eob_NN.pdf` and `synthetic_eob_NN.png` is a **different** scenario (definitions in **`generate_synthetic_samples.py`**).

| Ordinal | PDF | PNG |
|--------|-----|-----|
| 01 | EOB / office + lab | Pharmacy remittance |
| 02 | Urgent care claim summary | PT plan of care |
| 03 | ASC / surgery | Molecular lab requisition |
| 04 | DME / CPAP | Home health authorization |
| 05 | Radiology (landscape) | Mammography screening (portrait) |

---

## Commands

Regenerate synthetic PDFs and PNGs (**repo root**):

```bash
python samples/generate_synthetic_samples.py
```

---

## Data flow

```mermaid
flowchart LR
  subgraph samples_dir["samples/"]
    H[Helpers: start-local, ensure_local_data, generate_*]
    G[generated/]
  end
  H -->|generate_synthetic_samples.py| G
  G -->|docker compose bind-mount| U[/uploads in api container/]
```

---

**Do not** place real PHI in **`generated/`**.
