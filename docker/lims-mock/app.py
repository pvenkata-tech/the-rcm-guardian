"""
Minimal LabVantage-style LIMS HTTP facade for local Docker demos.

The main RCM Guardian API calls this service when LIMS_BASE_URL is set,
mirroring how production would integrate via REST/SOAP behind a VPC.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="LIMS Mock (LabVantage-style)", version="0.1.0")


class PriorAuthRequest(BaseModel):
    patient_id: str | None = None
    cpt_codes: list[str] = Field(default_factory=list)
    payer_hint: str | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "lims-mock"}


@app.post("/v1/prior-authorizations")
def prior_authorizations(body: PriorAuthRequest) -> dict[str, Any]:
    normalized = [c.strip().upper() for c in body.cpt_codes if c and str(c).strip()]
    # Same semantics as rcm_guardian.services.lims_service in-process mock
    demo_auth_cpts = {"99213", "99214", "93000"}
    found = [c for c in normalized if c in demo_auth_cpts]
    missing_auth = [c for c in normalized if c not in demo_auth_cpts]

    return {
        "lims_system": "LabVantage (HTTP mock container)",
        "patient_id": body.patient_id,
        "payer_hint": body.payer_hint,
        "prior_auth_document_ids": [f"PA-MOCK-{c}-2026" for c in found],
        "cpt_with_documented_auth": found,
        "cpt_without_documented_auth": missing_auth,
        "raw_rows_returned": 1 if found else 0,
    }
