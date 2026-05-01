"""Bootstrap payer rules + OpenAI embeddings."""

from __future__ import annotations

import json

from langchain_openai import OpenAIEmbeddings

from rcm_guardian.config import Settings
from rcm_guardian.services.rag_service import PayerRulesRAG


async def embed_query(settings: Settings, text: str) -> list[float]:
    emb = OpenAIEmbeddings(model=settings.openai_embedding_model, api_key=settings.openai_api_key)
    return await emb.aembed_query(text)


async def seed_payer_rules_if_empty(settings: Settings, rag: PayerRulesRAG) -> None:
    if await rag.count_rules() > 0:
        return

    samples: list[dict] = [
        {
            "payer_name": "Acme Health",
            "rule_key": "acme-pa-emergency-high-level",
            "cpt_codes": ["99285", "99291"],
            "body": (
                "Emergency department high complexity E/M CPT 99285 requires documented medical necessity "
                "and **prior authorization for non-emergent repeat visits within 7 days**. "
                "If prior authorization cannot be located in the payer portal or LIMS, flag as "
                "**High Risk of Denial**."
            ),
            "metadata": {"prior_auth_required": True, "risk_focus": "prior_auth"},
        },
        {
            "payer_name": "Acme Health",
            "rule_key": "acme-radiology-extremity",
            "cpt_codes": ["73560", "73562"],
            "body": (
                "Radiology extremity X-ray codes (73560 family) require ordering provider NPI on claim "
                "and site-of-service consistency; unrelated bilateral studies may trigger prepayment review."
            ),
            "metadata": {"prior_auth_required": False, "risk_focus": "documentation"},
        },
        {
            "payer_name": "National Payer Plus",
            "rule_key": "npp-lab-panel",
            "cpt_codes": ["80053", "85025"],
            "body": (
                "Bundled lab panels may deny if component CPTs are unbundled without modifier justification."
            ),
            "metadata": {"prior_auth_required": False, "risk_focus": "unbundling"},
        },
        {
            "payer_name": "National Payer Plus",
            "rule_key": "npp-molecular-pathology-prior-auth",
            "cpt_codes": ["81479"],
            "body": (
                "Molecular pathology CPT **81479** (unique genomic sequence analysis) typically requires "
                "**advance prior authorization** aligned with the clinical order in LIMS. "
                "Billing without a matching PA record should be flagged as **High Risk of Denial** "
                "and held for genetic counseling / auth verification workflows."
            ),
            "metadata": {"prior_auth_required": True, "risk_focus": "prior_auth_genomics"},
        },
    ]

    for s in samples:
        vec_source = s["payer_name"] + " " + s["body"] + " " + json.dumps(s["cpt_codes"])
        embedding = await embed_query(settings, vec_source)
        await rag.insert_rule(
            payer_name=s["payer_name"],
            rule_key=s["rule_key"],
            cpt_codes=list(s["cpt_codes"]),
            body=s["body"],
            embedding=embedding,
            metadata=s["metadata"],
        )
