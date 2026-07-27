"""Phase 2.2 / 2.2.5 RAG 基础建设测试。

覆盖：mock embedding 确定性 / 分块 / 溯源强制 / InMemory 检索 / 入库 API /
检索 API / mode / Qdrant 未配置 fail-fast / fake-qdrant 逻辑 / embedding 工厂。
CI 默认 mock embedding + InMemory 向量库，不依赖外部 Qdrant 或真实 Embedding。
"""

from __future__ import annotations

import json
import sys
import types
import urllib.request

import pytest

from app.core.rag.embeddings import get_embedding_provider, reset_embedding_provider
from app.core.rag.ingestion import IngestionError, ingest_document
from app.core.rag.vector_store import (
    InMemoryVectorStore,
    VectorItem,
    VectorStoreConfigError,
    get_vector_store,
    reset_vector_store,
)


@pytest.fixture
def rag_isolated(monkeypatch: pytest.MonkeyPatch):
    """隔离 RAG 单例：强制 mock/memory 并清空缓存。"""

    monkeypatch.setenv("BOIP_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("BOIP_VECTOR_STORE", "memory")
    reset_embedding_provider()
    reset_vector_store()
    yield
    reset_embedding_provider()
    reset_vector_store()


# --------------------------------------------------------------------------- #
# embedding                                                                   #
# --------------------------------------------------------------------------- #


def test_mock_embedding_deterministic() -> None:
    from app.core.rag.embeddings import MockEmbeddingProvider

    p = MockEmbeddingProvider(dim=32)
    v1 = p.embed(["建筑开口防火规范"])[0]
    v2 = p.embed(["建筑开口防火规范"])[0]
    assert v1 == v2  # 确定性
    assert len(v1) == 32
    v_other = p.embed(["烹饪菜谱"])[0]
    assert v1 != v_other  # 不同输入不同向量


def test_embedding_factory_unknown_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.rag.embeddings import EmbeddingConfigError

    monkeypatch.setenv("BOIP_EMBEDDING_PROVIDER", "unknown-x")
    reset_embedding_provider()
    with pytest.raises(EmbeddingConfigError):
        get_embedding_provider()
    reset_embedding_provider()


def test_build_embedding_provider_config() -> None:
    """复用 ProviderRole.EMBEDDING：disabled→None，mock→MockEmbeddingProvider。"""

    from agents.llm.embedding import MockEmbeddingProvider, OpenAICompatEmbeddingProvider
    from agents.llm.router import build_embedding_provider

    cfg_disabled = {"providers": {"embedding": {"provider": "disabled"}}}
    assert build_embedding_provider(cfg_disabled) is None

    cfg_mock = {"providers": {"embedding": {"provider": "mock", "dim": 16}}}
    prov = build_embedding_provider(cfg_mock)
    assert isinstance(prov, MockEmbeddingProvider)
    assert prov.dim == 16

    # openai_compat + 已解析凭据 → 真实 provider 实例（不联网，仅构造）。
    cfg_real = {
        "providers": {
            "embedding": {
                "provider": "openai_compat",
                "base_url": "http://embed.local",
                "api_key": "k",
                "model": "m",
            }
        }
    }
    real = build_embedding_provider(cfg_real)
    assert isinstance(real, OpenAICompatEmbeddingProvider)

    # openai_compat + 未解析凭据（占位）→ 安全回落 mock（不崩溃）。
    cfg_unresolved = {
        "providers": {
            "embedding": {
                "provider": "openai_compat",
                "base_url": "${EMB_BASE:pending_verification}",
                "api_key": "pending_verification",
                "model": "pending_verification",
            }
        }
    }
    assert isinstance(build_embedding_provider(cfg_unresolved), MockEmbeddingProvider)


def test_openai_compat_embedding_constructor_requires_creds() -> None:
    from agents.llm.embedding import EmbeddingConfigError, OpenAICompatEmbeddingProvider

    # 空 base_url / api_key / model 必须报错（占位 pending_verification 由工厂层拦截）。
    with pytest.raises(EmbeddingConfigError):
        OpenAICompatEmbeddingProvider(base_url="", api_key="k", model="m")
    with pytest.raises(EmbeddingConfigError):
        OpenAICompatEmbeddingProvider(base_url="http://x", api_key="", model="m")
    with pytest.raises(EmbeddingConfigError):
        OpenAICompatEmbeddingProvider(base_url="http://x", api_key="k", model="")


def test_openai_compat_embedding_real_path_via_fake_urlopen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """覆盖真实 embedding HTTP 路径（fake urlopen，不联网）。"""

    from agents.llm.embedding import OpenAICompatEmbeddingProvider

    class _FakeResp:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return json.dumps({"data": [{"embedding": [0.1, 0.2, 0.3]}]}).encode()

    def _fake_urlopen(req, timeout=None):  # noqa: ANN001
        return _FakeResp()

    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)
    prov = OpenAICompatEmbeddingProvider(
        base_url="http://embed.local", api_key="k", model="m"
    )
    vecs = prov.embed(["hello"])
    assert vecs == [[0.1, 0.2, 0.3]]
    assert prov.dim == 3  # 首次请求后从响应推断维度


def test_embedding_factory_openai_compat_unresolved_falls_back_to_mock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.rag.embeddings import MockEmbeddingProvider, get_embedding_provider

    monkeypatch.setenv("BOIP_EMBEDDING_PROVIDER", "openai_compat")
    monkeypatch.setenv("EMBEDDING_BASE_URL", "pending_verification")
    monkeypatch.setenv("EMBEDDING_API_KEY", "pending_verification")
    monkeypatch.setenv("EMBEDDING_MODEL", "pending_verification")
    monkeypatch.delenv("LLM_A_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_A_API_KEY", raising=False)
    monkeypatch.delenv("LLM_A_MODEL", raising=False)
    reset_embedding_provider()
    prov = get_embedding_provider()
    assert isinstance(prov, MockEmbeddingProvider)
    reset_embedding_provider()


# --------------------------------------------------------------------------- #
# chunking                                                                     #
# --------------------------------------------------------------------------- #


def test_chunk_text_windows_and_overlap() -> None:
    from app.core.rag.chunking import ChunkConfigError, chunk_text

    assert chunk_text("   ") == []  # 空文本 → []
    long_text = ("建筑开口设计规范条款一。\n" * 5) + "门窗气密性要求条款二。"
    chunks = chunk_text(long_text, chunk_size=40, overlap=10)
    assert len(chunks) >= 2
    # overlap 不为 0 时相邻 chunk 有重叠前缀
    assert chunks[1].startswith(chunks[0][-10:])
    with pytest.raises(ChunkConfigError):
        chunk_text("x", chunk_size=10, overlap=10)  # overlap >= chunk_size


# --------------------------------------------------------------------------- #
# ingestion 溯源强制                                                          #
# --------------------------------------------------------------------------- #


def test_ingest_requires_source_and_raw_ref() -> None:
    store = InMemoryVectorStore()
    from app.core.rag.embeddings import MockEmbeddingProvider

    prov = MockEmbeddingProvider(dim=32)
    base = dict(text="正文内容", tenant_id="t1", embedding_provider=prov, vector_store=store)
    with pytest.raises(IngestionError):
        ingest_document(source="", raw_ref="r1", **base)  # 空 source
    with pytest.raises(IngestionError):
        ingest_document(source="s1", raw_ref="", **base)  # 空 raw_ref
    with pytest.raises(IngestionError):
        ingest_document(source="s1", raw_ref="r1", text="", embedding_provider=prov, vector_store=store)


def test_ingest_stores_metadata_with_provenance() -> None:
    store = InMemoryVectorStore()
    from app.core.rag.embeddings import MockEmbeddingProvider

    prov = MockEmbeddingProvider(dim=32)
    result = ingest_document(
        source="doc-A",
        raw_ref="chap3",
        text="建筑开口的防火规范要求在高层住宅中设置避难层。\n门窗气密性应符合节能设计标准。",
        tenant_id="t1",
        embedding_provider=prov,
        vector_store=store,
    )
    assert result.chunk_count >= 1
    assert result.source == "doc-A"
    assert result.raw_ref == "chap3"
    assert result.created_at  # 自动打 UTC 时间
    # 取出的对象 metadata 含三要素
    item = store.get(result.ids[0])
    assert item is not None
    assert item.metadata["source"] == "doc-A"
    assert item.metadata["raw_ref"] == "chap3"
    assert item.metadata["created_at"] == result.created_at
    assert item.metadata["tenant_id"] == "t1"
    assert item.metadata["chunk_index"] == 0


def test_memory_search_returns_relevant_chunk() -> None:
    store = InMemoryVectorStore()
    from app.core.rag.embeddings import MockEmbeddingProvider

    prov = MockEmbeddingProvider(dim=64)
    ingest_document(
        source="fire", raw_ref="p1",
        text="建筑开口防火规范：高层住宅须设避难层与防火间距。",
        tenant_id="t1", embedding_provider=prov, vector_store=store,
    )
    ingest_document(
        source="window", raw_ref="p2",
        text="门窗气密性等级与节能设计标准中的传热系数要求。",
        tenant_id="t1", embedding_provider=prov, vector_store=store,
    )
    query_vec = prov.embed(["防火规范 避难层"])[0]
    hits = store.search(vector=query_vec, top_k=1, tenant_id="t1")
    assert hits
    assert hits[0].metadata["source"] == "fire"
    assert "防火" in hits[0].text


# --------------------------------------------------------------------------- #
# InMemoryVectorStore CRUD                                                     #
# --------------------------------------------------------------------------- #


def test_memory_vector_store_crud() -> None:
    store = InMemoryVectorStore()
    store.upsert([
        VectorItem(id="a", vector=[1.0, 0.0], text="A", metadata={"source": "s", "created_at": "t", "raw_ref": "r"}),
        VectorItem(id="b", vector=[0.0, 1.0], text="B", metadata={"source": "s", "created_at": "t", "raw_ref": "r"}),
    ])
    assert store.count() == 2
    assert store.get("a") is not None
    hits = store.search(vector=[1.0, 0.0], top_k=1)
    assert hits[0].id == "a"
    store.delete(["a"])
    assert store.count() == 1
    assert store.get("a") is None


# --------------------------------------------------------------------------- #
# API                                                                          #
# --------------------------------------------------------------------------- #


def test_rag_ingest_and_search_api(rag_isolated) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    # 先确认 mode 默认可观测
    mode_resp = client.get("/api/rag/mode")
    assert mode_resp.status_code == 200
    mode_data = mode_resp.json()["data"]
    assert mode_data["embedding_provider"] == "MockEmbeddingProvider"
    assert mode_data["vector_store"] == "memory"

    # 入库
    ingest_resp = client.post(
        "/api/rag/ingest",
        json={"source": "doc-x", "raw_ref": "sec2", "text": "建筑开口防火规范：高层住宅须设避难层。"},
    )
    assert ingest_resp.status_code == 200
    body = ingest_resp.json()
    assert body["success"] is True
    assert body["data"]["chunk_count"] >= 1

    # 检索
    search_resp = client.post(
        "/api/rag/search", json={"query": "防火规范 避难层", "top_k": 3}
    )
    assert search_resp.status_code == 200
    items = search_resp.json()["data"]["items"]
    assert items
    top = items[0]
    assert top["source"] == "doc-x"
    assert top["raw_ref"] == "sec2"
    assert top["created_at"]  # 溯源时间存在


def test_rag_ingest_rejects_missing_source(rag_isolated) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/rag/ingest",
        json={"source": "", "raw_ref": "r", "text": "正文"},
    )
    # 空 source 被 ingest_document 拒绝，返回统一 INGESTION_REJECTED 信封。
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert body["code"] == "INGESTION_REJECTED"


# --------------------------------------------------------------------------- #
# Qdrant（fail-fast + fake client，不依赖真实服务）                            #
# --------------------------------------------------------------------------- #


def test_qdrant_fail_fast_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOIP_VECTOR_STORE", "qdrant")
    monkeypatch.delenv("QDRANT_HOST", raising=False)
    reset_vector_store()
    with pytest.raises(VectorStoreConfigError):
        get_vector_store()
    reset_vector_store()


def _install_fake_qdrant(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入 fake qdrant_client 模块，覆盖 QdrantVectorStore 逻辑（无真实服务）。"""

    import math

    fake = types.ModuleType("qdrant_client")

    class _Point:
        def __init__(self, id, vector, payload):
            self.id = id
            self.vector = vector
            self.payload = payload
            self.score = 0.0

    class _Resp:
        def __init__(self, points):
            self.points = points

    class _Count:
        def __init__(self, n):
            self.count = n

    class QdrantClient:
        def __init__(self, host, port=6333, api_key=None):  # noqa: ANN001
            self._store: dict[int, _Point] = {}
            self.host = host

        def get_collections(self):
            return {}

        def upsert(self, collection_name, points):  # noqa: ANN001
            for p in points:
                self._store[p.id] = p

        def query_points(self, collection_name, query, limit, query_filter=None):  # noqa: ANN001
            def cos(a, b):
                dot = sum(x * y for x, y in zip(a, b))
                na = math.sqrt(sum(x * x for x in a))
                nb = math.sqrt(sum(y * y for y in b))
                return dot / (na * nb) if na and nb else 0.0

            pts = list(self._store.values())
            if query_filter and query_filter.must:
                cond = query_filter.must[0]
                want = cond.match.value
                pts = [p for p in pts if p.payload.get(cond.key) == want]
            scored = []
            for p in pts:
                p2 = _Point(p.id, p.vector, p.payload)
                p2.score = cos(query, p.vector)
                scored.append(p2)
            scored.sort(key=lambda x: x.score, reverse=True)
            return _Resp(scored[:limit])

        def delete(self, collection_name, points_selector):  # noqa: ANN001
            for pid in points_selector:
                self._store.pop(pid, None)

        def count(self, collection_name):  # noqa: ANN001
            return _Count(len(self._store))

        def retrieve(self, collection_name, ids):  # noqa: ANN001
            return [self._store[i] for i in ids if i in self._store]

    fake.QdrantClient = QdrantClient

    models = types.ModuleType("qdrant_client.models")

    class PointStruct:
        def __init__(self, id, vector, payload):  # noqa: ANN001
            self.id = id
            self.vector = vector
            self.payload = payload

    class Filter:
        def __init__(self, must=None):  # noqa: ANN001
            self.must = must

    class FieldCondition:
        def __init__(self, key, match):  # noqa: ANN001
            self.key = key
            self.match = match

    class MatchValue:
        def __init__(self, value):  # noqa: ANN001
            self.value = value

    models.PointStruct = PointStruct
    models.Filter = Filter
    models.FieldCondition = FieldCondition
    models.MatchValue = MatchValue

    monkeypatch.setitem(sys.modules, "qdrant_client", fake)
    monkeypatch.setitem(sys.modules, "qdrant_client.models", models)


def test_qdrant_upsert_search_delete_with_fake_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_qdrant(monkeypatch)
    monkeypatch.setenv("BOIP_VECTOR_STORE", "qdrant")
    monkeypatch.setenv("QDRANT_HOST", "localhost")
    monkeypatch.setenv("QDRANT_COLLECTION", "boip_knowledge")
    reset_vector_store()

    store = get_vector_store()
    assert store.backend_name == "qdrant"

    from app.core.rag.embeddings import MockEmbeddingProvider

    prov = MockEmbeddingProvider(dim=32)
    v_fire = prov.embed(["防火规范"])[0]
    v_win = prov.embed(["门窗气密性"])[0]
    store.upsert([
        VectorItem(id="f1", vector=v_fire, text="防火规范条款", metadata={"source": "s", "created_at": "t", "raw_ref": "r", "tenant_id": "t1", "chunk_index": 0}),
        VectorItem(id="w1", vector=v_win, text="气密性条款", metadata={"source": "s", "created_at": "t", "raw_ref": "r", "tenant_id": "t1", "chunk_index": 0}),
    ])
    assert store.count() == 2
    hits = store.search(vector=v_fire, top_k=1, tenant_id="t1")
    assert hits and hits[0].text == "防火规范条款"
    got = store.get("f1")
    assert got is not None and got.metadata["source"] == "s"
    store.delete(["f1"])
    assert store.count() == 1

    # 清理 fake 模块，避免污染其他测试
    reset_vector_store()
    sys.modules.pop("qdrant_client", None)
    sys.modules.pop("qdrant_client.models", None)


__all__: list[str] = []
