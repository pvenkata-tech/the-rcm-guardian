# Samples (local tooling & test artifacts)

All **optional helpers** and **synthetic non-PHI** files for development live here.

| Path | Purpose |
|------|---------|
| **`start-local.ps1`** / **`start-local.sh`** | From repo root: checks `.env` for OpenAI + LangSmith keys, then `docker compose up --build` |
| **`ensure_local_data.py`** | Seed payer rules against Postgres without starting the API (`python samples/ensure_local_data.py` from repo root) |
| **`generate_synthetic_samples.py`** | Writes five **ordinal** pairs `synthetic_eob_01` … `_05`: each **`.pdf` and `.png` are different synthetic documents** (not image export of the same PDF), with distinct copy and `asset_key`. |
| **`generated/`** | **Gitignored** outputs — run the generator to fill it. Docker Compose bind-mounts this directory to **`/uploads`** in the API container. |

### Ordinal reference (`generated/` synthetic files)

Each `synthetic_eob_NN.pdf` and `synthetic_eob_NN.png` is a **different** scenario (see **`generate_synthetic_samples.py`**).

| Ordinal | PDF | PNG |
|--------|-----|-----|
| 01 | EOB / office + lab | Pharmacy remittance |
| 02 | Urgent care claim summary | PT plan of care |
| 03 | ASC / surgery | Molecular lab requisition |
| 04 | DME / CPAP | Home health authorization |
| 05 | Radiology (landscape) | Mammography screening (portrait) |

Each synthetic PDF/PNG embeds a **stable unique `asset_key`** line and the generator **asserts all 10 output files have distinct SHA-256** (so no accidental duplicates).

```bash
python samples/generate_synthetic_samples.py
```

Do not place real PHI in **`generated/`**.
