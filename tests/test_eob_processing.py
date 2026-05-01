"""
End-to-end EOB-style workflow checks:

- LangGraph checkpoints in Postgres + interrupt/resume (human-in-the-loop)
- pgvector-backed payer rule retrieval (requires Postgres with `vector` extension)
- LIMS: in-process mock or HTTP patch (no live LIMS required for these tests)

Default pytest runs stub embeddings + stub vision (no API calls). Set RUN_OPENAI_INTEGRATION=1 to exercise live OpenAI.

Run Postgres locally:

    docker compose up -d postgres

Then:

    pytest tests/test_eob_processing.py -q

Or run this file directly:

    python tests/test_eob_processing.py
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
from typing import Any

import pytest
from sqlalchemy import text

# 1×1 transparent PNG — vision is stubbed unless RUN_OPENAI_INTEGRATION=1.
MINIMAL_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _default_lims_stub_response(
    patient_id: str | None, cpt_codes: list[str], *, payer_hint: str | None
) -> dict[str, Any]:
    """Synthetic LIMS JSON (no PA on claim CPTs → drives HIGH-risk audit path in seeded rules)."""
    del payer_hint
    return {
        "lims_system": "LabVantage",
        "patient_id": patient_id,
        "payer_hint": None,
        "prior_auth_document_ids": [],
        "cpt_with_documented_auth": [],
        "cpt_without_documented_auth": list(cpt_codes),
        "raw_rows_returned": 0,
    }


@pytest.fixture(autouse=True)
def _patch_lims_http_for_eob_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_http(
        base_url: str,
        patient_id: str | None,
        cpt_codes: list[str],
        *,
        payer_hint: str | None,
    ) -> dict[str, Any]:
        del base_url
        return _default_lims_stub_response(patient_id, cpt_codes, payer_hint=payer_hint)

    monkeypatch.setattr(
        "rcm_guardian.services.lims_service._fetch_prior_authorizations_http",
        fake_http,
    )


def _deterministic_embedding(text: str, dim: int = 1536) -> list[float]:
    h = hashlib.sha256(text.encode("utf-8")).digest()
    out: list[float] = []
    seed = int.from_bytes(h[:8], "big")
    for i in range(dim):
        seed = (seed * 1103515245 + 12345 + i) & 0x7FFFFFFF
        out.append((seed % 10000) / 10000.0)
    norm = sum(x * x for x in out) ** 0.5 or 1.0
    return [x / norm for x in out]


async def _stub_embed_query(settings: Any, text: str) -> list[float]:
    del settings
    return _deterministic_embedding(text)


async def _stub_run_vision_extractor(
    settings: Any, media_type: str, document_b64: str
) -> tuple[str, dict[str, Any]]:
    del settings, media_type, document_b64
    return "[pytest_stub]", {
        "provider_name": "Demo Regional Medical Center",
        "npi": None,
        "patient_id": "MEMBER-1",
        "cpt_codes": ["99285"],
        "billed_amount": 100.0,
        "notes": "pytest_stub",
    }


@pytest.fixture(autouse=True)
def _stub_llm_for_tests_without_live_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.environ.get("RUN_OPENAI_INTEGRATION") == "1":
        return
    monkeypatch.setattr("rcm_guardian.bootstrap.embed_query", _stub_embed_query)
    monkeypatch.setattr(
        "rcm_guardian.agents.vision_extract.run_vision_extractor",
        _stub_run_vision_extractor,
    )




@pytest.mark.asyncio
async def test_lims_http_success_path_parses_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from rcm_guardian.config import Settings
    from rcm_guardian.services.lims_service import fetch_prior_authorizations

    async def fake_http(
        base_url: str,
        patient_id: str | None,
        cpt_codes: list[str],
        *,
        payer_hint: str | None,
    ) -> dict[str, Any]:
        del base_url, payer_hint
        return {
            "lims_system": "LabVantage",
            "patient_id": patient_id,
            "prior_auth_document_ids": ["PA-1"],
            "cpt_with_documented_auth": ["99213"],
            "cpt_without_documented_auth": ["99285"],
            "raw_rows_returned": 1,
        }

    monkeypatch.setattr(
        "rcm_guardian.services.lims_service._fetch_prior_authorizations_http",
        fake_http,
    )

    settings = Settings(
        openai_api_key="sk-test",
        lims_base_url="https://lims.example",
        langchain_api_key="lsv2_pt_test_http_parse",
    )
    payload = await fetch_prior_authorizations("MEMBER-1", ["99285", "99213"], settings=settings)
    assert payload["cpt_with_documented_auth"] == ["99213"]
    assert "99285" in payload["cpt_without_documented_auth"]


async def _require_postgres_stack() -> tuple[Any, Any]:
    from rcm_guardian.bootstrap import seed_payer_rules_if_empty
    from rcm_guardian.config import get_settings
    from rcm_guardian.services.rag_service import dispose_engine, get_engine, get_rag

    get_settings.cache_clear()
    settings = get_settings()

    engine = get_engine(settings)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        await dispose_engine()
        get_settings.cache_clear()
        pytest.skip(f"PostgreSQL unavailable ({exc}). Start `docker compose up -d postgres` and retry.")

    rag = await get_rag(settings)
    await seed_payer_rules_if_empty(settings, rag)
    return settings, rag


@pytest.mark.asyncio
async def test_langgraph_eob_pipeline_interrupt_and_resume() -> None:
    from rcm_guardian.config import get_settings
    from rcm_guardian.graph import Command, create_rcm_graph_with_postgres
    from rcm_guardian.services.rag_service import dispose_engine

    settings, rag = await _require_postgres_stack()
    graph, pool = await create_rcm_graph_with_postgres(settings, rag)

    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    initial = {
        "document_base64": MINIMAL_PNG_B64,
        "document_media_type": "image/png",
        "thread_id": thread_id,
    }

    try:
        first = await graph.ainvoke(initial, cfg)
        assert "__interrupt__" in first

        await graph.ainvoke(Command(resume={"reviewer": "Jane Doe", "decision": "acknowledged"}), cfg)
        snap = await graph.aget_state(cfg)
        vals = dict(snap.values or {})

        assert vals.get("is_human_required") is True
        audit = vals.get("audit_report") or {}
        assert float(audit.get("confidence", 1.0)) < 0.85
        findings = audit.get("findings") or []
        assert any(str(f.get("severity")).upper() == "HIGH" for f in findings)
    finally:
        await pool.close()
        await dispose_engine()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fastapi_process_resume_roundtrip() -> None:
    from rcm_guardian.config import get_settings
    from rcm_guardian.services.rag_service import dispose_engine

    await _require_postgres_stack()

    await dispose_engine()
    get_settings.cache_clear()

    from fastapi.testclient import TestClient

    from rcm_guardian.app import app

    try:
        with TestClient(app) as client:
            thread_id = str(uuid.uuid4())
            resp = client.post(
                "/v1/process",
                json={
                    "document_base64": MINIMAL_PNG_B64,
                    "document_media_type": "image/png",
                    "thread_id": thread_id,
                },
            )
            assert resp.status_code == 202, resp.text
            body = resp.json()
            assert body["status"] == "human_review_required"

            resume = client.post(
                "/v1/resume",
                json={"thread_id": thread_id, "human_feedback": {"decision": "approved"}},
            )
            assert resume.status_code == 200, resume.text
            final = resume.json()
            assert final["is_human_required"] is True
            assert float(final["audit_report"]["confidence"]) < 0.85
    finally:
        await dispose_engine()
        get_settings.cache_clear()


def _apply_demo_llm_stubs() -> None:
    """Script entrypoint does not load pytest fixtures — stub LLM entrypoints on modules."""
    import rcm_guardian.agents.vision_extract as vx
    import rcm_guardian.bootstrap as boot

    boot.embed_query = _stub_embed_query  # type: ignore[method-assign]
    vx.run_vision_extractor = _stub_run_vision_extractor  # type: ignore[method-assign]


async def _demo_cli() -> None:
    os.environ.setdefault("OPENAI_API_KEY", "sk-local-script-demo-placeholder")
    os.environ.setdefault("LANGCHAIN_API_KEY", "lsv2_pt_local-demo-placeholder-set-real-key-for-langsmith")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
    _apply_demo_llm_stubs()

    from rcm_guardian.bootstrap import seed_payer_rules_if_empty
    from rcm_guardian.config import get_settings
    from rcm_guardian.graph import Command, create_rcm_graph_with_postgres
    from rcm_guardian.services.rag_service import dispose_engine, get_rag

    get_settings.cache_clear()
    settings = get_settings()

    try:
        rag = await get_rag(settings)
    except Exception as exc:
        print(f"[demo] Postgres not reachable ({exc}). Bring up `docker compose up -d postgres`.")
        return

    await seed_payer_rules_if_empty(settings, rag)
    graph, pool = await create_rcm_graph_with_postgres(settings, rag)

    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    try:
        first = await graph.ainvoke(
            {
                "document_base64": MINIMAL_PNG_B64,
                "document_media_type": "image/png",
                "thread_id": thread_id,
            },
            cfg,
        )
        print("[demo] First step keys:", sorted(first.keys()))
        await graph.ainvoke(Command(resume={"demo": True}), cfg)
        snap = await graph.aget_state(cfg)
        print("[demo] Final audit_report confidence:", (snap.values or {}).get("audit_report", {}).get("confidence"))
    finally:
        await pool.close()
        await dispose_engine()
        get_settings.cache_clear()


if __name__ == "__main__":
    asyncio.run(_demo_cli())
