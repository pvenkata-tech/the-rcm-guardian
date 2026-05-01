"""Multimodal billing extraction: OpenAI (primary) with Anthropic Claude fallback."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from rcm_guardian.agents.prompts import EXTRACTOR_SYSTEM_PROMPT
from rcm_guardian.config import Settings

logger = logging.getLogger(__name__)


def _pdf_first_page_as_png_base64(pdf_bytes: bytes) -> tuple[str, str]:
    import fitz

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    page = doc.load_page(0)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
    png = pix.tobytes("png")
    return base64.b64encode(png).decode("ascii"), "image/png"


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        return json.loads(text[start:end])
    except (ValueError, json.JSONDecodeError):
        return {
            "provider_name": None,
            "npi": None,
            "patient_id": None,
            "cpt_codes": [],
            "billed_amount": None,
            "notes": "extractor_json_parse_error",
        }


async def _extract_openai(
    settings: Settings,
    *,
    raw_text_prefix: str,
    image_b64: str,
    img_media: str,
) -> tuple[str, dict[str, Any]]:
    llm = ChatOpenAI(
        model=settings.openai_vision_model,
        api_key=settings.openai_api_key,
        temperature=0,
    )
    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Extract the billing fields using the instructions. "
                        "Prioritize tabular / line-item sections over narrative text."
                    ),
                },
                {"type": "image_url", "image_url": {"url": f"data:{img_media};base64,{image_b64}"}},
            ]
        ),
    ]
    resp = await llm.ainvoke(messages)
    text_content = resp.content if isinstance(resp.content, str) else str(resp.content)
    parsed = _parse_json_object(text_content)
    combined_raw = f"{raw_text_prefix}\n{text_content}".strip()
    return combined_raw[:32000], parsed


async def _extract_anthropic(
    settings: Settings,
    *,
    raw_text_prefix: str,
    image_b64: str,
    img_media: str,
) -> tuple[str, dict[str, Any]]:
    llm = ChatAnthropic(
        model=settings.anthropic_vision_model,
        api_key=settings.anthropic_api_key,
        temperature=0,
        max_tokens=8192,
    )
    messages = [
        SystemMessage(content=EXTRACTOR_SYSTEM_PROMPT),
        HumanMessage(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Extract the billing fields using the instructions. "
                        "Prioritize tabular / line-item sections over narrative text."
                    ),
                },
                {"type": "image_url", "image_url": {"url": f"data:{img_media};base64,{image_b64}"}},
            ]
        ),
    ]
    resp = await llm.ainvoke(messages)
    text_content = resp.content if isinstance(resp.content, str) else str(resp.content)
    parsed = _parse_json_object(text_content)
    combined_raw = f"{raw_text_prefix}\n{text_content}".strip()
    return combined_raw[:32000], parsed


async def run_vision_extractor(settings: Settings, media_type: str, document_b64: str) -> tuple[str, dict[str, Any]]:
    """
    Primary: OpenAI multimodal. Fallback: Anthropic Claude vision when OpenAI errors or returns unusable output.

    Embeddings/RAG always use OpenAI separately (`bootstrap.embed_query`); OPENAI_API_KEY remains mandatory in Settings.
    """
    raw_bytes = base64.b64decode(document_b64)
    image_b64 = document_b64
    img_media = media_type or "image/png"

    if "pdf" in (media_type or "").lower():
        image_b64, img_media = _pdf_first_page_as_png_base64(raw_bytes)
        raw_text_prefix = "[rendered_pdf_page_1_as_image]"
    else:
        raw_text_prefix = f"[image media_type={media_type}]"

    errors: list[Exception] = []

    if (settings.openai_api_key or "").strip():
        try:
            return await _extract_openai(
                settings,
                raw_text_prefix=raw_text_prefix,
                image_b64=image_b64,
                img_media=img_media,
            )
        except Exception as exc:
            logger.warning("OpenAI vision extraction failed; trying Anthropic if configured: %s", exc)
            errors.append(exc)

    if (settings.anthropic_api_key or "").strip():
        try:
            return await _extract_anthropic(
                settings,
                raw_text_prefix=raw_text_prefix,
                image_b64=image_b64,
                img_media=img_media,
            )
        except Exception as exc:
            errors.append(exc)
            raise RuntimeError(
                "Vision extraction failed on both OpenAI and Anthropic: "
                + "; ".join(str(e) for e in errors)
            ) from exc

    if errors:
        raise RuntimeError(f"OpenAI vision extraction failed and no ANTHROPIC_API_KEY set: {errors[0]}") from errors[0]
    raise RuntimeError("OPENAI_API_KEY is required for embeddings; configure Anthropic only as vision fallback after OpenAI attempts.")
