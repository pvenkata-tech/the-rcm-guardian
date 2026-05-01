"""Prometheus metrics for Grafana (scrape /metrics on the API)."""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

AUDITOR_CONFIDENCE = Histogram(
    "rcm_auditor_confidence",
    "Auditor confidence score after forensic audit (0–1)",
    buckets=(0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0),
)

FINDING_TOTAL = Counter(
    "rcm_finding_total",
    "Structured audit findings",
    ["finding_kind", "status"],
)

HUMAN_REVIEW_TOTAL = Counter(
    "rcm_route_human_review_total",
    "Runs routed to human-in-the-loop (interrupt before completion)",
)

GRAPH_NODE_SECONDS = Histogram(
    "rcm_graph_duration_seconds",
    "LangGraph node wall time",
    ["node"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
)


def metrics_response() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
