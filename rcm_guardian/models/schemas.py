"""API request/response models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProcessDocumentRequest(BaseModel):
    """Submit a base64-encoded billing PDF or image for agentic review."""

    document_base64: str = Field(..., description="Base64 payload (no data: URI prefix required).")
    document_media_type: str = Field(
        default="application/pdf",
        description="MIME type, e.g. application/pdf or image/png.",
    )
    thread_id: str | None = Field(
        default=None,
        description="Stable id for LangGraph checkpoint resume (defaults to server-generated).",
    )


class HumanResumeRequest(BaseModel):
    """Resume a paused graph after human review."""

    thread_id: str
    human_feedback: dict[str, Any] = Field(default_factory=dict)


class AuditFinding(BaseModel):
    severity: str
    message: str
    rule_reference: str | None = None


class HumanReviewAcceptedResponse(BaseModel):
    """Workflow paused for human review (LangGraph interrupt + MemorySaver checkpoint)."""

    status: Literal["human_review_required"] = "human_review_required"
    thread_id: str
    interrupt_payload: dict[str, Any]
    raw_text: str | None = None
    extracted_billing_data: dict[str, Any] | None = None
    payer_rules: list[dict[str, Any]] | None = None
    audit_report: dict[str, Any] | None = None


class ProcessDocumentResponse(BaseModel):
    thread_id: str
    raw_text: str
    extracted_billing_data: dict[str, Any]
    payer_rules: list[dict[str, Any]]
    audit_report: dict[str, Any]
    is_human_required: bool
