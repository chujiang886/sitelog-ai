"""知识入库（Phase 2.2 / 2.2.5）。

``ingest_document``：校验来源 → 分块 → 向量化 → 写入 vector store。
**硬约束**：每条知识必须携带 ``source`` / ``created_at`` / ``raw_ref``，三者任一
缺失即拒绝入库（抛 ``IngestionError``），落实"禁止无来源知识入库"。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .chunking import chunk_text
from .embeddings import EmbeddingProvider, get_embedding_provider
from .vector_store import VectorItem, VectorStore, get_vector_store


class IngestionError(ValueError):
    """入库错误（来源缺失 / 分块参数非法等）。"""


@dataclass
class IngestionResult:
    """入库结果摘要。"""

    chunk_count: int
    ids: list[str]
    source: str
    raw_ref: str
    created_at: str
    tenant_id: str | None


def ingest_document(
    *,
    source: str,
    raw_ref: str,
    text: str,
    tenant_id: str | None = None,
    chunk_size: int = 500,
    overlap: int = 50,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> IngestionResult:
    """把一篇带溯源的文档分块入库。

    参数：
    - ``source``：知识来源标识（文件名 / URL / 规则 id）；
    - ``raw_ref``：原始引用键（行号 / 外部 doc key / 记录 id）；
    - ``text``：正文；
    - ``tenant_id``：租户隔离（可选）；
    - ``chunk_size`` / ``overlap``：分块参数。

    返回 ``IngestionResult``；所有入库 chunk 的 metadata 含
    ``source`` / ``created_at`` / ``raw_ref`` / ``tenant_id`` / ``chunk_index``。
    """

    source = (source or "").strip()
    raw_ref = (raw_ref or "").strip()
    if not source:
        raise IngestionError("禁止无来源知识入库：source 不能为空")
    if not raw_ref:
        raise IngestionError("禁止无来源知识入库：raw_ref 不能为空")
    if not text or not text.strip():
        raise IngestionError("text 不能为空")

    provider = embedding_provider or get_embedding_provider()
    store = vector_store or get_vector_store()

    chunks = chunk_text(text, chunk_size=chunk_size, overlap=overlap)
    if not chunks:
        raise IngestionError("分块结果为空（文本可能仅含空白）")

    created_at = datetime.now(timezone.utc).isoformat()

    embeddings = provider.embed(chunks)

    items: list[VectorItem] = []
    ids: list[str] = []
    safe_tenant = (tenant_id or "unknown").strip() or "unknown"
    for idx, (chunk, vec) in enumerate(zip(chunks, embeddings)):
        item_id = _stable_id(safe_tenant, source, raw_ref, idx)
        items.append(
            VectorItem(
                id=item_id,
                vector=vec,
                text=chunk,
                metadata={
                    "source": source,
                    "created_at": created_at,
                    "raw_ref": raw_ref,
                    "tenant_id": safe_tenant,
                    "chunk_index": idx,
                },
            )
        )
        ids.append(item_id)

    store.upsert(items)
    return IngestionResult(
        chunk_count=len(items),
        ids=ids,
        source=source,
        raw_ref=raw_ref,
        created_at=created_at,
        tenant_id=safe_tenant,
    )


def _stable_id(tenant: str, source: str, raw_ref: str, chunk_index: int) -> str:
    """稳定 id（同文档同 chunk → 同 id → upsert 幂等去重）。"""

    base = f"{tenant}|{source}|{raw_ref}|{chunk_index}"
    return str(uuid.uuid5(uuid.NAMESPACE_URL, base))


__all__ = [
    "IngestionError",
    "IngestionResult",
    "ingest_document",
]
