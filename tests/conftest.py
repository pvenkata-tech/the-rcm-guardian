"""Pytest defaults: valid OPENAI_API_KEY shape so Settings loads; integration tests opt into live APIs."""

from __future__ import annotations

import os


def pytest_configure() -> None:
    os.environ.setdefault("OPENAI_API_KEY", os.environ.get("OPENAI_API_KEY") or "sk-pytest-placeholder-no-live-calls-unless-run-openai-integration")
    try:
        from rcm_guardian.config import get_settings

        get_settings.cache_clear()
    except Exception:
        pass
