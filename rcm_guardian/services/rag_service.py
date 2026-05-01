"""PostgreSQL + pgvector RAG for payer rules."""

from __future__ import annotations

import json
from typing import Any, Sequence

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from rcm_guardian.config import Settings, get_settings


def _vec_literal(embedding: Sequence[float]) -> str:
    return "[" + ",".join(str(float(x)) for x in embedding) + "]"


class PayerRulesRAG:
    """Vector search over embedded payer policy snippets."""

    def __init__(self, engine: AsyncEngine, embedding_dim: int = 1536) -> None:
        self._engine = engine
        self._embedding_dim = embedding_dim

    async def ensure_schema(self) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS payer_rules (
                        id SERIAL PRIMARY KEY,
                        payer_name TEXT NOT NULL,
                        rule_key TEXT NOT NULL UNIQUE,
                        cpt_codes TEXT NOT NULL,
                        body TEXT NOT NULL,
                        embedding vector({self._embedding_dim}),
                        metadata JSONB DEFAULT '{{}}'::jsonb
                    )
                    """
                )
            )
            await conn.execute(text("CREATE INDEX IF NOT EXISTS payer_rules_rule_key_idx ON payer_rules (rule_key)"))

    async def count_rules(self) -> int:
        async with self._engine.connect() as conn:
            result = await conn.execute(text("SELECT COUNT(*) AS c FROM payer_rules"))
            row = result.mappings().first()
            return int(row["c"]) if row else 0

    async def insert_rule(
        self,
        *,
        payer_name: str,
        rule_key: str,
        cpt_codes: list[str],
        body: str,
        embedding: Sequence[float],
        metadata: dict[str, Any] | None = None,
    ) -> None:
        codes = json.dumps(cpt_codes)
        meta = json.dumps(metadata or {})
        emb = _vec_literal(embedding)
        async with self._engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO payer_rules (payer_name, rule_key, cpt_codes, body, embedding, metadata)
                    VALUES (
                        :payer_name,
                        :rule_key,
                        CAST(:cpt_codes AS TEXT),
                        :body,
                        CAST(:embedding AS vector),
                        CAST(:metadata AS JSONB)
                    )
                    ON CONFLICT (rule_key) DO UPDATE SET
                        payer_name = EXCLUDED.payer_name,
                        cpt_codes = EXCLUDED.cpt_codes,
                        body = EXCLUDED.body,
                        embedding = EXCLUDED.embedding,
                        metadata = EXCLUDED.metadata
                    """
                ),
                {
                    "payer_name": payer_name,
                    "rule_key": rule_key,
                    "cpt_codes": codes,
                    "body": body,
                    "embedding": emb,
                    "metadata": meta,
                },
            )

    async def similarity_search(
        self,
        query_embedding: Sequence[float],
        *,
        k: int = 6,
        payer_name: str | None = None,
    ) -> list[dict[str, Any]]:
        emb = _vec_literal(query_embedding)
        payer_filter = ""
        params: dict[str, Any] = {"embedding": emb, "k": k}
        if payer_name:
            payer_filter = "AND payer_name ILIKE :payer_pat"
            params["payer_pat"] = f"%{payer_name}%"

        stmt = text(
            f"""
            SELECT payer_name, rule_key, cpt_codes, body, metadata,
                   1 - (embedding <=> CAST(:embedding AS vector)) AS score
            FROM payer_rules
            WHERE 1=1 {payer_filter}
            ORDER BY embedding <=> CAST(:embedding AS vector)
            LIMIT :k
            """
        )
        rows: list[dict[str, Any]] = []
        async with self._engine.connect() as conn:
            result = await conn.execute(stmt, params)
            for r in result.mappings().all():
                row = dict(r)
                try:
                    row["cpt_codes"] = json.loads(row["cpt_codes"])
                except (json.JSONDecodeError, TypeError):
                    row["cpt_codes"] = []
                rows.append(row)
        return rows


_engine_cache: AsyncEngine | None = None


def get_engine(settings: Settings | None = None) -> AsyncEngine:
    global _engine_cache
    if _engine_cache is None:
        s = settings or get_settings()
        _engine_cache = create_async_engine(s.database_url, pool_pre_ping=True)
    return _engine_cache


async def dispose_engine() -> None:
    global _engine_cache
    if _engine_cache is not None:
        await _engine_cache.dispose()
        _engine_cache = None


async def get_rag(settings: Settings | None = None) -> PayerRulesRAG:
    s = settings or get_settings()
    engine = get_engine(s)
    rag = PayerRulesRAG(engine)
    await rag.ensure_schema()
    return rag
