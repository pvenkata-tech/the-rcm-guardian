"""
LangGraph checkpoint state for RCM Guardian.

Each ``ainvoke`` / resume updates this TypedDict-shaped object; MemorySaver (or PostgresSaver)
persists it keyed by ``configurable.thread_id`` so workflows survive restarts and human review queues.
"""

from typing import Any, NotRequired, TypedDict


class RCMGraphState(TypedDict, total=False):
    """LangGraph state for the RCM Guardian workflow."""

    # --- Document ingestion (inputs; typically present on first invoke) ---
    document_base64: NotRequired[str]
    """Base64-encoded artifact (PDF rasterized page-1 or image) submitted for extraction."""

    document_media_type: NotRequired[str]
    """MIME hint for the extractor (e.g. ``application/pdf``, ``image/png``)."""

    thread_id: NotRequired[str]
    """Client-supplied or generated id; must align with LangGraph ``configurable.thread_id`` for checkpointing."""

    # --- Pipeline artifacts ---
    raw_text: str
    """Concatenated extractor output (OCR / vision text caps) plus structured notes."""

    extracted_billing_data: dict[str, Any]
    """Structured billing payload from multimodal extraction (CPT, NPI, patient/member id, amounts, …)."""

    payer_rules: list[dict[str, Any]]
    """Top-k payer policy snippets from pgvector similarity search (Rule Oracle)."""

    audit_report: dict[str, Any]
    """
    Forensic auditor output: ``confidence`` score, ``findings`` (structured denial-risk signals),
    optional ``prior_authorization_reconciliation`` (claim CPTs vs LIMS PA coverage), and metadata.
    """

    # --- Human-in-the-loop (HITL) ---
    is_human_required: bool
    """
    After resume from ``interrupt()``, set when an analyst has acknowledged review.

    When ``True``, downstream APIs/reporting know this thread paused for **HIPAA-aligned human oversight**
    (minimum necessary disclosure, accountable decision on contested PHI-derived billing judgments).
    The LangGraph ``interrupt`` itself fires earlier based on confidence routing—not via this flag alone.
    """

    human_feedback: NotRequired[dict[str, Any]]
    """Opaque payload returned from ``Command(resume=…)`` (reviewer id, decision, notes)."""

