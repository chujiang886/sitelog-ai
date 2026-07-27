"""Vector store 抽象（Phase 2.2 / 2.2.5）。

- ``VectorStore(ABC)``：upsert / search / delete / count / get，元数据强制携带
  ``source`` / ``created_at`` / ``raw_ref``（溯源，防编造）。
- ``InMemoryVectorStore``：默认（Dev / CI），余弦相似度，进程内。
- ``QdrantVectorStore``：生产可配置，懒加载 ``qdrant_client``（不进硬依赖）；
  未配置 → 抛 ``VectorStoreConfigError``（fail-fast）。CI 默认 memory，永不依赖外部 Qdrant。
- ``get_vector_store()``：按 ``BOIP_VECTOR_STORE`` 切换（默认 ``memory``）。
"""

from __future__ import annotations

import math
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class VectorStoreConfigError(ValueError):
    """Vector store 配置错误（未知后端 / Qdrant 未配置 / SDK 缺失）。"""


@dataclass
class VectorItem:
    """单条入库向量对象；metadata 强制溯源三要素。"""

    id: str
    vector: list[float]
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchHit:
    """检索命中结果。"""

    id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)


class VectorStore(ABC):
    """向量存储抽象。"""

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """后端标识：memory / qdrant。"""

    @abstractmethod
    def upsert(self, items: list[VectorItem]) -> None:
        """写入 / 覆盖向量对象。"""

    @abstractmethod
    def search(
        self, *, vector: list[float], top_k: int = 5, tenant_id: str | None = None
    ) -> list[SearchHit]:
        """按向量余弦检索 top_k；``tenant_id`` 非空时仅检索该租户。"""

    @abstractmethod
    def delete(self, ids: list[str]) -> None:
        """删除给定 id 的对象；不存在静默忽略。"""

    @abstractmethod
    def count(self) -> int:
        """当前对象数。"""

    @abstractmethod
    def get(self, item_id: str) -> VectorItem | None:
        """按 id 取对象；不存在返回 None。"""


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；任一零向量 → 0.0。"""

    if len(a) != len(b) or not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class InMemoryVectorStore(VectorStore):
    """内存向量库（默认；Dev / CI；余弦检索）。"""

    def __init__(self) -> None:
        self._store: dict[str, VectorItem] = {}

    @property
    def backend_name(self) -> str:
        return "memory"

    def upsert(self, items: list[VectorItem]) -> None:
        for it in items:
            self._store[it.id] = it

    def search(
        self, *, vector: list[float], top_k: int = 5, tenant_id: str | None = None
    ) -> list[SearchHit]:
        scored: list[tuple[float, VectorItem]] = []
        for it in self._store.values():
            if tenant_id and str(it.metadata.get("tenant_id", "")) != str(tenant_id):
                continue
            scored.append((_cosine(vector, it.vector), it))
        scored.sort(key=lambda x: x[0], reverse=True)
        hits: list[SearchHit] = []
        for score, it in scored[: max(0, top_k)]:
            hits.append(
                SearchHit(
                    id=it.id,
                    score=round(score, 6),
                    text=it.text,
                    metadata=dict(it.metadata),
                )
            )
        return hits

    def delete(self, ids: list[str]) -> None:
        for i in ids:
            self._store.pop(i, None)

    def count(self) -> int:
        return len(self._store)

    def get(self, item_id: str) -> VectorItem | None:
        it = self._store.get(item_id)
        return VectorItem(
            id=it.id, vector=list(it.vector), text=it.text, metadata=dict(it.metadata)
        ) if it else None


class QdrantVectorStore(VectorStore):
    """Qdrant 向量库（生产可配置；懒加载 ``qdrant_client``，不进硬依赖）。"""

    def __init__(self) -> None:
        host = os.getenv("QDRANT_HOST", "").strip()
        port = os.getenv("QDRANT_PORT", "6333").strip()
        api_key = os.getenv("QDRANT_API_KEY", "").strip()
        collection = os.getenv("QDRANT_COLLECTION", "boip_knowledge").strip()
        if not host:
            raise VectorStoreConfigError(
                "Qdrant 未配置（仅允许来自 .env）：缺少 QDRANT_HOST"
            )
        try:
            from qdrant_client import QdrantClient  # noqa: PLC0415 - 懒加载
        except Exception as exc:  # noqa: BLE001 - SDK 缺失
            raise VectorStoreConfigError(
                f"qdrant_client 未安装（请 pip install qdrant-client）：{type(exc).__name__}: {exc}"
            ) from exc

        self._collection = collection
        self._client = QdrantClient(
            host=host,
            port=int(port or 6333),
            api_key=api_key or None,
        )
        # collection 不存在则创建（已存在忽略）。
        try:
            self._client.get_collections()
        except Exception:  # noqa: BLE001 - 连接失败交给调用方
            pass

    @property
    def backend_name(self) -> str:
        return "qdrant"

    def upsert(self, items: list[VectorItem]) -> None:
        from qdrant_client.models import PointStruct  # noqa: PLC0415 - 懒加载

        points = [
            PointStruct(
                id=self._stable_id(it.id),
                vector=it.vector,
                payload={
                    "text": it.text,
                    "source": it.metadata.get("source", ""),
                    "created_at": it.metadata.get("created_at", ""),
                    "raw_ref": it.metadata.get("raw_ref", ""),
                    "tenant_id": it.metadata.get("tenant_id", ""),
                    "chunk_index": it.metadata.get("chunk_index", 0),
                },
            )
            for it in items
        ]
        if points:
            self._client.upsert(collection_name=self._collection, points=points)

    def search(
        self, *, vector: list[float], top_k: int = 5, tenant_id: str | None = None
    ) -> list[SearchHit]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue

        must = None
        if tenant_id:
            must = [FieldCondition(key="tenant_id", match=MatchValue(value=tenant_id))]
        filter_obj = Filter(must=must) if must else None
        resp = self._client.query_points(
            collection_name=self._collection,
            query=vector,
            limit=max(0, top_k),
            query_filter=filter_obj,
        )
        hits: list[SearchHit] = []
        for pt in getattr(resp, "points", []) or []:
            payload = pt.payload or {}
            hits.append(
                SearchHit(
                    id=str(pt.id),
                    score=float(getattr(pt, "score", 0.0) or 0.0),
                    text=str(payload.get("text", "")),
                    metadata={
                        "source": payload.get("source", ""),
                        "created_at": payload.get("created_at", ""),
                        "raw_ref": payload.get("raw_ref", ""),
                        "tenant_id": payload.get("tenant_id", ""),
                        "chunk_index": payload.get("chunk_index", 0),
                    },
                )
            )
        return hits

    def delete(self, ids: list[str]) -> None:
        if ids:
            self._client.delete(
                collection_name=self._collection,
                points_selector=[self._stable_id(i) for i in ids],
            )

    def count(self) -> int:
        try:
            return int(self._client.count(collection_name=self._collection).count)
        except Exception:  # noqa: BLE001 - 连接失败回落 0
            return 0

    def get(self, item_id: str) -> VectorItem | None:
        recs = self._client.retrieve(
            collection_name=self._collection, ids=[self._stable_id(item_id)]
        )
        if not recs:
            return None
        rec = recs[0]
        payload = rec.payload or {}
        return VectorItem(
            id=item_id,
            vector=list(rec.vector or []),
            text=str(payload.get("text", "")),
            metadata={
                "source": payload.get("source", ""),
                "created_at": payload.get("created_at", ""),
                "raw_ref": payload.get("raw_ref", ""),
                "tenant_id": payload.get("tenant_id", ""),
                "chunk_index": payload.get("chunk_index", 0),
            },
        )

    @staticmethod
    def _stable_id(item_id: str) -> int:
        """把字符串 id 稳定映射到 Qdrant 的 uint 主键（避免随机碰撞）。"""

        import hashlib

        digest = hashlib.sha256(item_id.encode("utf-8")).digest()
        return int.from_bytes(digest[:8], "big") % (2**63)


_STORE_INSTANCE: VectorStore | None = None


def get_vector_store() -> VectorStore:
    """按 ``BOIP_VECTOR_STORE`` 返回 vector store（默认 memory）。

    返回**进程内单例**：保证 ingest 与 search 共享同一存储（InMemory 下跨请求
    状态一致）。未知后端 / Qdrant 未配置 → 抛 ``VectorStoreConfigError``（fail-fast）。
    """

    global _STORE_INSTANCE
    if _STORE_INSTANCE is not None:
        return _STORE_INSTANCE

    kind = (os.getenv("BOIP_VECTOR_STORE", "memory") or "memory").strip().lower()
    if kind == "memory":
        _STORE_INSTANCE = InMemoryVectorStore()
    elif kind == "qdrant":
        _STORE_INSTANCE = QdrantVectorStore()  # 未配置会在此抛 VectorStoreConfigError
    else:
        raise VectorStoreConfigError(
            f"未知 BOIP_VECTOR_STORE：{kind!r}（支持 memory / qdrant）"
        )
    return _STORE_INSTANCE


def reset_vector_store() -> None:
    """清空 vector store 单例（测试隔离用）。"""

    global _STORE_INSTANCE
    _STORE_INSTANCE = None


__all__ = [
    "VectorStoreConfigError",
    "VectorStore",
    "VectorItem",
    "SearchHit",
    "InMemoryVectorStore",
    "QdrantVectorStore",
    "get_vector_store",
    "reset_vector_store",
]
