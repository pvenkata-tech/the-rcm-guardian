"""LabVantage-style LIMS integration — in-process mock or HTTP mock container."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx

from rcm_guardian.config import Settings, get_settings


async def _fetch_prior_authorizations_inline(
    patient_id: str | None,
    cpt_codes: list[str],
    *,
    payer_hint: str | None,
) -> dict[str, Any]:
    await asyncio.sleep(0)

    normalized = [c.strip().upper() for c in cpt_codes if c and str(c).strip()]
    demo_auth_cpts = {"99213", "99214", "93000"}

    found = [c for c in normalized if c in demo_auth_cpts]
    missing_auth = [c for c in normalized if c not in demo_auth_cpts]

    return {
        "lims_system": "LabVantage (in-process mock)",
        "patient_id": patient_id,
        "payer_hint": payer_hint,
        "prior_auth_document_ids": [f"PA-MOCK-{c}-2026" for c in found],
        "cpt_with_documented_auth": found,
        "cpt_without_documented_auth": missing_auth,
        "raw_rows_returned": 1 if found else 0,
    }


async def _fetch_prior_authorizations_http(
    base_url: str,
    patient_id: str | None,
    cpt_codes: list[str],
    *,
    payer_hint: str | None,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/v1/prior-authorizations"
    payload = {
        "patient_id": patient_id,
        "cpt_codes": cpt_codes,
        "payer_hint": payer_hint,
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise TypeError("LIMS response must be a JSON object")
        return data


async def fetch_prior_authorizations(
    patient_id: str | None,
    cpt_codes: list[str],
    *,
    payer_hint: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Prior authorization / clinical sample reconciliation facade.

    - Docker (recommended demo): set `LIMS_BASE_URL` so the forensic auditor hits the `lims-mock` container.
    - Offline tests / CI: leave `LIMS_BASE_URL` empty to use the deterministic in-process mock.

    Pass ``settings`` when calling from LangGraph so configuration matches the compiled graph (avoids a fresh `get_settings()` lookup).
    """
    s = settings if settings is not None else get_settings()
    base = (s.lims_base_url or "").strip()

    if base:
        try:
            return await _fetch_prior_authorizations_http(
                base,
                patient_id,
                cpt_codes,
                payer_hint=payer_hint,
            )
        except (httpx.HTTPError, TypeError, ValueError) as exc:
            return {
                "lims_system": "LabVantage (HTTP mock — error)",
                "patient_id": patient_id,
                "payer_hint": payer_hint,
                "prior_auth_document_ids": [],
                "cpt_with_documented_auth": [],
                "cpt_without_documented_auth": list(cpt_codes),
                "raw_rows_returned": 0,
                "error": str(exc),
            }

    return await _fetch_prior_authorizations_inline(patient_id, cpt_codes, payer_hint=payer_hint)
