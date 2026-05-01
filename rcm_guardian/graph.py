"""LangGraph orchestration: extractor → Rule Oracle (RAG) → forensic auditor → optional HITL."""

from __future__ import annotations

import json
from typing import Any, Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from langgraph.types import Command, interrupt

import rcm_guardian.bootstrap as bootstrap
from rcm_guardian.agents import vision_extract
from rcm_guardian.config import Settings
from rcm_guardian.services.lims_service import fetch_prior_authorizations
from rcm_guardian.services.rag_service import PayerRulesRAG
from rcm_guardian.state import RCMGraphState


def _finding_prior_auth_gap(*, missing_pa: list[str], rule_key: str | None) -> dict[str, Any]:
    """Structured PA gap — billing for services without a documented auth in LIMS."""
    cpt_label = ", ".join(missing_pa)
    reason = (
        f"CPT code(s) [{cpt_label}] present on the extracted billing line items but "
        "missing from LIMS Prior Authorization records for this patient — cannot defend medical necessity / auth."
    )
    rk = rule_key or "unknown_rule"
    return {
        "severity": "HIGH",
        "finding_kind": "PRIOR_AUTH_GAP",
        "status": "REJECTED",
        "reason": reason,
        "message": (
            f"**Prior-authorization gap:** {reason} "
            f"(policy rule `{rk}`). Treat as **high risk of denial** until PA is verified or appealed."
        ),
        "rule_reference": rule_key,
        "cpt_codes": list(missing_pa),
    }


def _finding_npi_gap() -> dict[str, Any]:
    reason = (
        "Ordering / billing NPI missing from extraction — payer routing, credentialing, "
        "and policy-to-provider matching may be unreliable."
    )
    return {
        "severity": "MEDIUM",
        "finding_kind": "NPI_GAP",
        "status": "FLAGGED",
        "reason": reason,
        "message": f"**Provider identifier gap:** {reason}",
        "rule_reference": None,
    }


def _finding_no_cpt() -> dict[str, Any]:
    reason = "No billable CPT / HCPCS codes extracted — cannot reconcile payer rules or LIMS prior auth."
    return {
        "severity": "HIGH",
        "finding_kind": "CPT_EXTRACTION_GAP",
        "status": "REJECTED",
        "reason": reason,
        "message": f"**Extraction failure:** {reason}",
        "rule_reference": None,
    }


def compile_rcm_graph(settings: Settings, rag: PayerRulesRAG):
    async def extractor(state: RCMGraphState) -> dict[str, Any]:
        b64 = state.get("document_base64") or ""
        mt = state.get("document_media_type") or "application/pdf"
        raw_text, extracted = await vision_extract.run_vision_extractor(settings, mt, b64)
        return {"raw_text": raw_text, "extracted_billing_data": extracted}

    async def rule_oracle(state: RCMGraphState) -> dict[str, Any]:
        extracted = state.get("extracted_billing_data") or {}
        provider = str(extracted.get("provider_name") or "")
        cpts = extracted.get("cpt_codes") or []
        cpt_part = ", ".join(str(c) for c in cpts)
        query = f"Payer medical policy rules for provider '{provider}' and CPT codes [{cpt_part}]. Prior authorization and denial risk."
        emb = await bootstrap.embed_query(settings, query)
        rules = await rag.similarity_search(emb, k=8, payer_name=None)
        return {"payer_rules": rules}

    async def forensic_auditor(state: RCMGraphState) -> dict[str, Any]:
        extracted = state.get("extracted_billing_data") or {}
        rules = state.get("payer_rules") or []
        patient_id = extracted.get("patient_id")
        cpt_list = [str(c) for c in (extracted.get("cpt_codes") or []) if c is not None]

        lims = await fetch_prior_authorizations(
            patient_id, cpt_list, payer_hint=None, settings=settings
        )

        findings: list[dict[str, Any]] = []
        confidence = 1.0
        prior_auth_gap_cpts: list[str] = []

        extracted_cpt_upper = {str(c).strip().upper(): str(c) for c in cpt_list}
        documented_in_lims = {str(x).strip().upper() for x in lims.get("cpt_with_documented_auth", [])}

        for rule in rules:
            meta = rule.get("metadata") or {}
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except json.JSONDecodeError:
                    meta = {}
            rule_cpts_raw = rule.get("cpt_codes") or []
            rule_cpts = {str(c).strip().upper() for c in rule_cpts_raw}
            overlap = sorted(rule_cpts.intersection(extracted_cpt_upper.keys()))
            if not overlap:
                continue

            body_lower = str(rule.get("body") or "").lower()
            requires_pa = bool(meta.get("prior_auth_required")) or (
                "prior authorization" in body_lower and "high risk of denial" in body_lower
            )

            if requires_pa:
                missing_pa = [extracted_cpt_upper[c] for c in overlap if c not in documented_in_lims]
                if missing_pa:
                    prior_auth_gap_cpts.extend(missing_pa)
                    findings.append(
                        _finding_prior_auth_gap(
                            missing_pa=missing_pa,
                            rule_key=str(rule.get("rule_key")) if rule.get("rule_key") else None,
                        )
                    )
                    confidence -= 0.35

        if not extracted.get("npi"):
            findings.append(_finding_npi_gap())
            confidence -= 0.08

        if not cpt_list:
            findings.append(_finding_no_cpt())
            confidence -= 0.25

        confidence = max(0.0, min(1.0, float(confidence)))

        pa_gap_unique = sorted(set(prior_auth_gap_cpts), key=lambda x: str(x).upper())

        audit_report = {
            "confidence": confidence,
            "findings": findings,
            "lims_snapshot": lims,
            "rules_considered": len(rules),
            "prior_authorization_reconciliation": {
                "patient_id": patient_id,
                "cpts_on_claim": list(cpt_list),
                "cpts_documented_in_lims": sorted(documented_in_lims),
                "cpts_flagged_missing_pa": pa_gap_unique,
            },
        }
        return {"audit_report": audit_report, "is_human_required": False}

    def route_after_auditor(state: RCMGraphState) -> Literal["waiting_for_human", "done"]:
        report = state.get("audit_report") or {}
        try:
            conf = float(report.get("confidence", 0.0))
        except (TypeError, ValueError):
            conf = 0.0
        if conf < 0.85:
            return "waiting_for_human"
        return "done"

    async def waiting_for_human(state: RCMGraphState) -> dict[str, Any]:
        payload = {
            "reason": "auditor_confidence_below_threshold",
            "audit_report": state.get("audit_report"),
            "extracted_billing_data": state.get("extracted_billing_data"),
        }
        feedback = interrupt(payload)
        merged: dict[str, Any]
        if isinstance(feedback, dict):
            merged = feedback
        else:
            merged = {"value": feedback}
        return {"is_human_required": True, "human_feedback": merged}

    workflow = StateGraph(RCMGraphState)
    workflow.add_node("extractor", extractor)
    workflow.add_node("rule_oracle", rule_oracle)
    workflow.add_node("forensic_auditor", forensic_auditor)
    workflow.add_node("waiting_for_human", waiting_for_human)

    workflow.set_entry_point("extractor")
    workflow.add_edge("extractor", "rule_oracle")
    workflow.add_edge("rule_oracle", "forensic_auditor")
    workflow.add_conditional_edges(
        "forensic_auditor",
        route_after_auditor,
        {"waiting_for_human": "waiting_for_human", "done": END},
    )
    workflow.add_edge("waiting_for_human", END)

    checkpointer = MemorySaver()
    return workflow.compile(checkpointer=checkpointer)


__all__ = ["compile_rcm_graph", "Command"]
