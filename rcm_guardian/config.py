from __future__ import annotations

from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://rcm:rcm@localhost:5432/rcm_guardian"
    openai_api_key: str = ""
    openai_vision_model: str = "gpt-4o"
    openai_embedding_model: str = "text-embedding-3-small"

    # Optional: vision fallback when OpenAI multimodal fails (same extraction prompt path).
    anthropic_api_key: str = ""
    anthropic_vision_model: str = "claude-3-5-sonnet-20241022"

    otel_service_name: str = "rcm-guardian"

    # When set (e.g. http://lims-mock:8080 in Docker), auditor calls HTTP instead of in-process mock.
    lims_base_url: str = ""

    # Local “object storage”: bind-mount ./uploads → /uploads in Docker (see docker-compose.yml).
    uploads_dir: str = "/uploads"
    persist_uploads: bool = False

    # Interview / Terraform hook: Fargate task role grants s3:* on this bucket (see terraform/s3.tf).
    documents_s3_bucket: str = ""

    @model_validator(mode="after")
    def openai_required(self) -> Settings:
        if not (self.openai_api_key or "").strip():
            raise ValueError(
                "OPENAI_API_KEY is required (embeddings / pgvector RAG). "
                "Optional ANTHROPIC_API_KEY is used only as a vision fallback after OpenAI."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
