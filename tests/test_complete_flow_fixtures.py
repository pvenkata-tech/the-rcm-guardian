"""
End-to-end LangGraph flow with:
- Sample EOB payload from JSON fixtures (vision + embeddings patched)
- In-memory payer rules via FakeRAG (no Postgres / pgvector)
- In-process **LIMS mock** when `lims_base_url` is empty (`MemorySaver` checkpointer in these tests)

Run:

    pytest tests/test_complete_flow_fixtures.py -v
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from langgraph.checkpoint.memory import MemorySaver

from rcm_guardian.config import Settings
from rcm_guardian.graph import Command, compile_rcm_graph

FIXTURES = Path(__file__).resolve().parent / "fixtures"

_EMB_STUB = [1.0 / 1536.0] * 1536


async def _fake_embed_query(_settings: Settings, text: str) -> list[float]:
    del _settings, text
    return list(_EMB_STUB)


def _load_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeRAG:
    """Fixture-backed payer rules without Postgres."""

    def __init__(self, rules: list[dict[str, Any]]) -> None:
        self._rules = rules

    async def ensure_schema(self) -> None:
        return None

    async def count_rules(self) -> int:
        return len(self._rules)

    async def similarity_search(
        self,
        query_embedding,
        *,
        k: int = 6,
        payer_name: str | None = None,
    ) -> list[dict[str, Any]]:
        del query_embedding, payer_name
        return list(self._rules)[:k]


@pytest.fixture
def sample_eob() -> dict[str, Any]:
    return _load_json("sample_eob.json")


@pytest.fixture
def sample_payer_rules() -> list[dict[str, Any]]:
    data = _load_json("sample_payer_rules.json")
    assert isinstance(data, list)
    return data


@pytest.mark.asyncio
async def test_complete_flow_hitl_path_with_fixture_eob_and_rules(
    monkeypatch: pytest.MonkeyPatch,
    sample_eob: dict[str, Any],
    sample_payer_rules: list[dict[str, Any]],
) -> None:
    extracted = sample_eob["extracted_billing_data"]

    async def fake_extract(_settings: Settings, media_type: str, document_b64: str) -> tuple[str, dict[str, Any]]:
        del media_type, document_b64
        raw = f"[fixture_sample_eob]{sample_eob.get('scenario', '')}\n"
        return raw, dict(extracted)

    monkeypatch.setattr("rcm_guardian.agents.vision_extract.run_vision_extractor", fake_extract)
    monkeypatch.setattr("rcm_guardian.bootstrap.embed_query", _fake_embed_query)

    settings = Settings(
        openai_api_key="sk-test-local-graph-flow",
        database_url="postgresql+asyncpg://unused:unused@127.0.0.1:5432/unused",
        lims_base_url="",
        langchain_api_key="lsv2_pt_test_fixture_langsmith",
    )
    graph = compile_rcm_graph(settings, FakeRAG(sample_payer_rules), MemorySaver())

    thread_id = str(uuid.uuid4())
    cfg: dict[str, Any] = {"configurable": {"thread_id": thread_id}}
    initial = {
        "document_base64": sample_eob["document_base64"],
        "document_media_type": sample_eob["document_media_type"],
        "thread_id": thread_id,
    }

    first = await graph.ainvoke(initial, cfg)
    assert "__interrupt__" in first

    snap = await graph.aget_state(cfg)
    vals = dict(snap.values or {})
    assert vals.get("extracted_billing_data") == extracted
    assert len(vals.get("payer_rules") or []) == len(sample_payer_rules)

    audit = vals.get("audit_report") or {}
    assert float(audit.get("confidence", 1.0)) < 0.85
    findings = audit.get("findings") or []
    assert any(str(f.get("severity")).upper() == "HIGH" for f in findings)
    assert any(f.get("finding_kind") == "PRIOR_AUTH_GAP" for f in findings)
    assert any(f.get("status") == "REJECTED" for f in findings)
    assert any("99285" in str(f.get("cpt_codes", [])) for f in findings)
    pa_rec = audit.get("prior_authorization_reconciliation") or {}
    assert "99285" in " ".join(str(x) for x in (pa_rec.get("cpts_flagged_missing_pa") or []))

    await graph.ainvoke(Command(resume={"reviewer": "test", "decision": "acknowledged"}), cfg)
    final_snap = await graph.aget_state(cfg)
    final_vals = dict(final_snap.values or {})
    assert final_vals.get("is_human_required") is True


@pytest.mark.asyncio
async def test_complete_flow_no_hitl_when_rules_relaxed(
    monkeypatch: pytest.MonkeyPatch,
    sample_eob: dict[str, Any],
) -> None:
    extracted = {
        **sample_eob["extracted_billing_data"],
        "cpt_codes": ["99213"],
    }

    async def fake_extract(_settings: Settings, media_type: str, document_b64: str) -> tuple[str, dict[str, Any]]:
        del media_type, document_b64
        return "[fixture_relaxed]", dict(extracted)

    monkeypatch.setattr("rcm_guardian.agents.vision_extract.run_vision_extractor", fake_extract)
    monkeypatch.setattr("rcm_guardian.bootstrap.embed_query", _fake_embed_query)

    relaxed_rules = [
        {
            "payer_name": "Fixture Payor",
            "rule_key": "fixture-office-visits",
            "cpt_codes": ["99213"],
            "body": "Office visit coding guidelines.",
            "metadata": {"prior_auth_required": False},
            "score": 0.9,
        }
    ]

    settings = Settings(
        openai_api_key="sk-test-local-graph-flow",
        database_url="postgresql+asyncpg://unused:unused@127.0.0.1:5432/unused",
        lims_base_url="",
        langchain_api_key="lsv2_pt_test_fixture_langsmith",
    )
    graph = compile_rcm_graph(settings, FakeRAG(relaxed_rules), MemorySaver())

    thread_id = str(uuid.uuid4())
    cfg = {"configurable": {"thread_id": thread_id}}
    initial = {
        "document_base64": sample_eob["document_base64"],
        "document_media_type": sample_eob["document_media_type"],
        "thread_id": thread_id,
    }

    out = await graph.ainvoke(initial, cfg)
    assert "__interrupt__" not in out

    snap = await graph.aget_state(cfg)
    vals = dict(snap.values or {})
    audit = vals.get("audit_report") or {}
    assert float(audit.get("confidence", 0.0)) >= 0.85
    assert vals.get("is_human_required") is False
