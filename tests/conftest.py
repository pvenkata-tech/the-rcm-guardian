"""Pytest defaults so Settings() loads (OpenAI + LangSmith keys; integration tests opt into live APIs)."""

from __future__ import annotations

import os


def pytest_configure() -> None:
    os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY") or "sk-pytest-placeholder-no-live-calls-unless-run-openai-integration")
    os.environ.setdefault("LANGCHAIN_API_KEY", os.environ.get("LANGCHAIN_API_KEY") or "lsv2_pt_pytest_placeholder_key")
    os.environ.setdefault("LANGCHAIN_TRACING_V2", os.environ.get("LANGCHAIN_TRACING_V2") or "true")
    try:
        from rcm_guardian.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
