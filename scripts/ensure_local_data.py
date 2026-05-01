#!/usr/bin/env python
"""Ensure Postgres has pgvector schema + seeded payer rules (run without starting the API)."""

from __future__ import annotations

import asyncio
import os
import sys

# Repo root on PYTHONPATH when run as: python scripts/ensure_local_data.py
_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


async def main() -> int:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print(
            "[ensure_local_data] FAILED: OPENAI_API_KEY is required to embed payer rules (OpenAI embeddings).",
            file=sys.stderr,
        )
        print("Hint: copy .env.example → .env and set OPENAI_API_KEY, then retry.", file=sys.stderr)
        return 1

    from rcm_guardian.bootstrap import seed_payer_rules_if_empty
    from rcm_guardian.config import get_settings
    from rcm_guardian.services.rag_service import dispose_engine, get_rag

    get_settings.cache_clear()
    settings = get_settings()

    try:
        rag = await get_rag(settings)
        await seed_payer_rules_if_empty(settings, rag)
        n = await rag.count_rules()
        print(f"[ensure_local_data] payer_rules rows: {n}")
        print("[ensure_local_data] OK — database is seeded and ready.")
        return 0 if n > 0 else 2
    except Exception as exc:
        print(f"[ensure_local_data] FAILED: {exc}")
        print("Hint: start Postgres first, e.g. `docker compose up -d postgres`")
        return 1
    finally:
        await dispose_engine()
        get_settings.cache_clear()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
