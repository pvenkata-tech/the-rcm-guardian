from typing import Any, NotRequired, TypedDict


class RCMGraphState(TypedDict, total=False):
    """LangGraph state for the RCM Guardian workflow."""

    raw_text: str
    extracted_billing_data: dict[str, Any]
    payer_rules: list[dict[str, Any]]
    audit_report: dict[str, Any]
    is_human_required: bool
    # Inputs / routing (extensions for persistence + edges)
    document_base64: NotRequired[str]
    document_media_type: NotRequired[str]
    thread_id: NotRequired[str]
    human_feedback: NotRequired[dict[str, Any]]
