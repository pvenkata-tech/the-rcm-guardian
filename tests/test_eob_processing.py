"""
End-to-end EOB-style workflow checks:

- LangGraph MemorySaver checkpoint + interrupt/resume (human-in-the-loop)
- pgvector-backed payer rule retrieval (requires Postgres with `vector` extension)

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
async def test_lims_labvantage_mock_contract() -> None:
    from rcm_guardian.services.lims_service import fetch_prior_authorizations

    payload = await fetch_prior_authorizations("MEMBER-1", ["99285", "99213"])
    assert "in-process" in str(payload["lims_system"]).lower()
    assert "99285" in payload["cpt_without_documented_auth"]
    assert "99213" in payload["cpt_with_documented_auth"]


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
    from rcm_guardian.graph import Command, compile_rcm_graph
    from rcm_guardian.services.rag_service import dispose_engine

    settings, rag = await _require_postgres_stack()
    graph = compile_rcm_graph(settings, rag)

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
        await dispose_engine()
        get_settings.cache_clear()


@pytest.mark.asyncio
async def test_fastapi_process_resume_roundtrip() -> None:
    from rcm_guardian.config import get_settings
    from rcm_guardian.services.rag_service import dispose_engine

    await _require_postgres_stack()

    # TestClient runs the app's lifespan on a different asyncio loop than this async test.
    # Drop the cached engine/settings so FastAPI creates a fresh pool on the correct loop.
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
    _apply_demo_llm_stubs()

    from rcm_guardian.bootstrap import seed_payer_rules_if_empty
    from rcm_guardian.config import get_settings
    from rcm_guardian.graph import Command, compile_rcm_graph
    from rcm_guardian.services.rag_service import dispose_engine, get_rag

    get_settings.cache_clear()
    settings = get_settings()

    try:
        rag = await get_rag(settings)
    except Exception as exc:
        print(f"[demo] Postgres not reachable ({exc}). Bring up `docker compose up -d postgres`.")
        return

    await seed_payer_rules_if_empty(settings, rag)
    graph = compile_rcm_graph(settings, rag)

    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
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
    await dispose_engine()
    get_settings.cache_clear()


if __name__ == "__main__":
    asyncio.run(_demo_cli())
