"""FastAPI ASGI entrypoint for RCM Guardian (async API + LangGraph checkpointer)."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

# --- OpenTelemetry placeholder -------------------------------------------------
# Production wiring typically enables:
# - OTEL_RESOURCE_ATTRIBUTES / OTEL_SERVICE_NAME
# - OTLP exporters (gRPC/HTTP) via OTEL_EXPORTER_OTLP_ENDPOINT
# - FastAPI auto-instrumentation: opentelemetry-instrumentation-fastapi
# Example (commented intentionally — avoids mandatory exporter deps in this prototype):
# from opentelemetry import trace
# from opentelemetry.sdk.resources import Resource
# from opentelemetry.sdk.trace import TracerProvider
# provider = TracerProvider(resource=Resource.create({"service.name": settings.otel_service_name}))
# trace.set_tracer_provider(provider)

from rcm_guardian.bootstrap import seed_payer_rules_if_empty
from rcm_guardian.config import apply_langsmith_env, get_settings
from rcm_guardian.graph import Command, create_rcm_graph_with_postgres
from rcm_guardian.metrics import metrics_response
from rcm_guardian.models.schemas import (
    HumanResumeRequest,
    HumanReviewAcceptedResponse,
    ProcessDocumentRequest,
    ProcessDocumentResponse,
)
from rcm_guardian.services.lims_service import LIMSIntegrationError
from rcm_guardian.services.rag_service import dispose_engine, get_rag
from rcm_guardian.services.storage_service import maybe_persist_inbound_document


def _snapshot(values: dict[str, Any], thread_id: str) -> ProcessDocumentResponse:
    return ProcessDocumentResponse(
        thread_id=thread_id,
        raw_text=str(values.get("raw_text") or ""),
        extracted_billing_data=dict(values.get("extracted_billing_data") or {}),
        payer_rules=list(values.get("payer_rules") or []),
        audit_report=dict(values.get("audit_report") or {}),
        is_human_required=bool(values.get("is_human_required")),
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    apply_langsmith_env(settings)
    rag = await get_rag(settings)
    await seed_payer_rules_if_empty(settings, rag)
    app.state.settings = settings
    app.state.rag = rag
    graph, pool = await create_rcm_graph_with_postgres(settings, rag)
    app.state.graph = graph
    app.state.checkpoint_pool = pool
    yield
    await pool.close()
    await dispose_engine()


app = FastAPI(title="RCM Guardian", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def prometheus_metrics():
    """Prometheus scrape target (Grafana datasource in Docker Compose)."""
    body, ctype = metrics_response()
    return Response(content=body, media_type=ctype)


@app.get("/v1/ready")
async def ready(request: Request):
    """
    Confirms Postgres is reachable and payer-rules seed data exists (loaded at API startup).
    After `docker compose up`, open http://localhost:8000/v1/ready — expect `seeded: true`.
    """
    settings = request.app.state.settings
    rag = request.app.state.rag
    try:
        count = await rag.count_rules()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database_unavailable: {exc}") from exc

    seeded = count > 0
    return {
        "status": "ready" if seeded else "degraded",
        "database_ok": True,
        "payer_rules_count": count,
        "seeded": seeded,
        "openai_configured": bool((settings.openai_api_key or "").strip()),
        "anthropic_vision_fallback_configured": bool((settings.anthropic_api_key or "").strip()),
        "ai_models": {
            "openai_vision_model": settings.openai_vision_model,
            "openai_embedding_model": settings.openai_embedding_model,
            "openai_embedding_dimensions": settings.openai_embedding_dimensions,
            "anthropic_vision_model": settings.anthropic_vision_model,
        },
        "lims_base_url": (settings.lims_base_url or "").strip() or None,
        "persist_uploads": settings.persist_uploads,
        "uploads_dir": settings.uploads_dir,
        "langsmith_tracing": settings.langchain_tracing_v2,
        "langsmith_api_key_configured": bool((settings.langchain_api_key or "").strip()),
        "langsmith_project": settings.langchain_project,
    }


@app.post("/v1/process")
async def process_document(request: Request, body: ProcessDocumentRequest):
    graph = request.app.state.graph
    settings = request.app.state.settings
    thread_id = body.thread_id or str(uuid.uuid4())
    maybe_persist_inbound_document(
        settings,
        thread_id=thread_id,
        document_base64=body.document_base64,
        document_media_type=body.document_media_type,
    )
    config = {"configurable": {"thread_id": thread_id}}
    initial: dict[str, Any] = {
        "document_base64": body.document_base64,
        "document_media_type": body.document_media_type,
        "thread_id": thread_id,
    }
    try:
        result = await graph.ainvoke(initial, config)
    except LIMSIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if "__interrupt__" in result:
        intr = result["__interrupt__"][0]
        payload: dict[str, Any]
        raw_val = getattr(intr, "value", intr)
        if isinstance(raw_val, dict):
            payload = raw_val
        else:
            payload = {"value": raw_val}

        snap = await graph.aget_state(config)
        vals = dict(snap.values) if snap.values else {}
        hr = HumanReviewAcceptedResponse(
            thread_id=thread_id,
            interrupt_payload=payload,
            raw_text=vals.get("raw_text"),
            extracted_billing_data=vals.get("extracted_billing_data"),
            payer_rules=vals.get("payer_rules"),
            audit_report=vals.get("audit_report"),
        )
        return JSONResponse(status_code=202, content=hr.model_dump(mode="json"))

    snap = await graph.aget_state(config)
    vals = dict(snap.values) if snap.values else {}
    merged = {**vals, **{k: v for k, v in result.items() if k != "__interrupt__"}}
    return _snapshot(merged, thread_id)


@app.post("/v1/resume")
async def resume_human(request: Request, body: HumanResumeRequest):
    graph = request.app.state.graph
    config = {"configurable": {"thread_id": body.thread_id}}
    try:
        await graph.ainvoke(Command(resume=body.human_feedback), config)
    except LIMSIntegrationError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    snap = await graph.aget_state(config)
    vals = dict(snap.values) if snap.values else {}
    return _snapshot(vals, body.thread_id)
