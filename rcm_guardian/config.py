from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian"
    openai_api_key: str = ""
    # Env: OPENAI_VISION_MODEL — multimodal extraction (see vision_extract.py).
    openai_vision_model: str = Field(default="gpt-4o")
    # Env: OPENAI_EMBEDDING_MODEL — RAG query/rule embeddings (see bootstrap.py).
    openai_embedding_model: str = Field(default="text-embedding-3-small")
    # Env: OPENAI_EMBEDDING_DIMENSIONS — pgvector column width; must match the embedding model output (e.g. 1536 for text-embedding-3-small).
    openai_embedding_dimensions: int = Field(default=1536, ge=8, le=8192)

    # Optional: vision fallback when OpenAI multimodal fails (same extraction prompt path).
    anthropic_api_key: str = ""
    # Env: ANTHROPIC_VISION_MODEL
    anthropic_vision_model: str = Field(default="claude-3-5-sonnet-20241022")

    otel_service_name: str = "rcm-guardian"

    # Optional: empty = in-process LIMS mock; Compose uses http://lims-mock:8080; production = real LIMS URL.
    lims_base_url: str = ""

    # Local “object storage”: Compose bind-mounts ./samples/generated → /uploads (see docker-compose.yml).
    uploads_dir: str = "/uploads"
    persist_uploads: bool = False

    # Interview / Terraform hook: Fargate task role grants s3:* on this bucket (see terraform/s3.tf).
    documents_s3_bucket: str = ""

    # Required: LangSmith tracing for LangChain / LangGraph (https://smith.langchain.com).
    langchain_tracing_v2: bool = True
    langchain_api_key: str = ""
    langchain_project: str = "rcm-guardian"
    langchain_endpoint: str = "https://api.smith.langchain.com"

    @model_validator(mode="after")
    def required_integrations(self) -> Settings:
        if not (self.openai_api_key or "").strip():
            raise ValueError(
                "OPENAI_API_KEY is required (embeddings / pgvector RAG). "
                "Optional ANTHROPIC_API_KEY is used only as a vision fallback after OpenAI."
            )
        if not self.langchain_tracing_v2:
            raise ValueError(
                "LANGCHAIN_TRACING_V2 must be true — LangSmith tracing is required for all runs."
            )
        if not (self.langchain_api_key or "").strip():
            raise ValueError(
                "LANGCHAIN_API_KEY is required — create a key at https://smith.langchain.com and set it in the environment."
            )
        return self


def apply_langsmith_env(settings: Settings) -> None:
    """Sync LangSmith-related settings into os.environ so LangChain sends traces to the real LangSmith API."""

    key = (settings.langchain_api_key or "").strip()
    if key:
        os.environ["LANGCHAIN_API_KEY"] = key
    else:
        os.environ.pop("LANGCHAIN_API_KEY", None)
    os.environ["LANGCHAIN_TRACING_V2"] = "true" if settings.langchain_tracing_v2 else "false"
    project = (settings.langchain_project or "").strip()
    if project:
        os.environ["LANGCHAIN_PROJECT"] = project
    endpoint = (settings.langchain_endpoint or "").strip()
    if endpoint:
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint


@lru_cache
def get_settings() -> Settings:
    return Settings()
