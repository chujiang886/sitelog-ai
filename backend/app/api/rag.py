"""RAG 检索 API（Phase 2.2 / 2.2.5 基础设施）。

提供：
- ``POST /api/rag/ingest``：带溯源知识入库（强制 source/raw_ref）；
- ``POST /api/rag/search``：向量检索，返回带溯源的命中片段；
- ``GET /api/rag/mode``：可观测当前 embedding/vector store 后端类型。

本 Sprint 仅建基础设施，不做 LLM 生成问答。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.rag.embeddings import get_embedding_provider
from app.core.rag.ingestion import IngestionError, ingest_document
from app.core.rag.vector_store import get_vector_store

router = APIRouter(prefix="/api/rag", tags=["rag"])


class IngestRequest(BaseModel):
    # 不在此层用 min_length 拦截：空 source/raw_ref 交由 ingest_document 抛出
    # IngestionError 并返回 INGESTION_REJECTED 信封（统一错误形态，落实"禁止无来源入库"）。
    source: str = Field(..., description="知识来源标识")
    raw_ref: str = Field(..., description="原始引用键")
    text: str = Field(..., min_length=1, description="正文")
    tenant_id: str | None = None
    chunk_size: int = 500
    overlap: int = 50


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索语句")
    top_k: int = Field(5, ge=1, le=50)
    tenant_id: str | None = None


@router.post("/ingest")
async def ingest(req: IngestRequest) -> dict[str, object]:
    """带溯源知识入库；缺 source/raw_ref 返回 400（禁止无来源入库）。"""

    try:
        result = ingest_document(
            source=req.source,
            raw_ref=req.raw_ref,
            text=req.text,
            tenant_id=req.tenant_id,
            chunk_size=req.chunk_size,
            overlap=req.overlap,
        )
    except IngestionError as exc:
        return {"success": False, "error": str(exc), "code": "INGESTION_REJECTED"}

    return {
        "success": True,
        "data": {
            "chunk_count": result.chunk_count,
            "ids": result.ids,
            "source": result.source,
            "raw_ref": result.raw_ref,
            "created_at": result.created_at,
            "tenant_id": result.tenant_id,
        },
    }


@router.post("/search")
async def search(req: SearchRequest) -> dict[str, object]:
    """向量检索：embed(query) → vector store search → 带溯源命中。"""

    provider = get_embedding_provider()
    store = get_vector_store()
    query_vec = provider.embed([req.query])[0]
    hits = store.search(vector=query_vec, top_k=req.top_k, tenant_id=req.tenant_id)
    items = [
        {
            "id": h.id,
            "score": h.score,
            "text": h.text,
            "source": h.metadata.get("source", ""),
            "created_at": h.metadata.get("created_at", ""),
            "raw_ref": h.metadata.get("raw_ref", ""),
            "chunk_index": h.metadata.get("chunk_index", 0),
        }
        for h in hits
    ]
    return {"success": True, "data": {"items": items, "total": len(items)}}


@router.get("/mode")
async def mode() -> dict[str, object]:
    """可观测：当前 embedding / vector store 后端类型。"""

    embedding = get_embedding_provider()
    store = get_vector_store()
    return {
        "success": True,
        "data": {
            "embedding_provider": type(embedding).__name__,
            "embedding_dim": embedding.dim,
            "vector_store": store.backend_name,
        },
    }


__all__ = ["router"]
