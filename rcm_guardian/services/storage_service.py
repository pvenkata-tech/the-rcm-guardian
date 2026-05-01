"""Local document persistence (Docker volume) — production analogue: S3 with SSE-KMS."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from rcm_guardian.config import Settings


def _safe_suffix(media_type: str) -> str:
    mt = (media_type or "").lower()
    if "pdf" in mt:
        return ".pdf"
    if "png" in mt:
        return ".png"
    if "jpeg" in mt or "jpg" in mt:
        return ".jpg"
    return ".bin"


def _safe_segment(thread_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", thread_id).strip("._-")
    return cleaned or "unknown-thread"


def maybe_persist_inbound_document(
    settings: Settings,
    *,
    thread_id: str,
    document_base64: str,
    document_media_type: str,
) -> str | None:
    """
    Write inbound artifact to UPLOADS_DIR (Compose: bind-mount ./samples/generated → /uploads).

    On AWS Fargate, swap this for S3 PutObject using the task IAM role and SSE.
    """
    if not settings.persist_uploads:
        return None

    root = Path(settings.uploads_dir)
    root.mkdir(parents=True, exist_ok=True)

    path = root / f"{_safe_segment(thread_id)}{_safe_suffix(document_media_type)}"
    raw = base64.b64decode(document_base64)
    path.write_bytes(raw)
    return str(path)
