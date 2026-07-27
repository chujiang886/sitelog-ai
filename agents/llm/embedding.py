"""Embedding Provider（Phase 2.2 / 2.2.5 RAG 基础建设）。

复用 ``agents.llm.router.ProviderRole.EMBEDDING`` 语义角色，作为向量/检索
预留角色的落地实现。**不新建并行 LLM 体系**——Embedding 是单 provider（非双轨），
与现有 ``LLMProvider`` 同处 ``agents.llm`` 包，共用其约定与 ``urllib`` 同步
POST 模式（``openai_compat.py``）。

默认 ``MockEmbeddingProvider``：确定性、内容敏感的哈希向量，零外部依赖，
供 Dev / CI 使用；真实 ``OpenAICompatEmbeddingProvider`` 仅在显式配置后启用。
"""

from __future__ import annotations

import hashlib
import json
import math
import urllib.request
from abc import ABC, abstractmethod
from typing import Sequence

from .router import ProviderRole


class EmbeddingConfigError(ValueError):
    """Embedding provider 配置错误（未知 provider / 缺 base_url 等）。"""


class EmbeddingProvider(ABC):
    """向量化抽象：批量文本 → 向量列表。"""

    @property
    @abstractmethod
    def dim(self) -> int:
        """向量维度；ingestion 与 search 必须同实例同维度。"""

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """批量向量化；返回与 ``texts`` 等长的向量列表。"""


def _role_is_embedding() -> ProviderRole:
    """语义角色标识：本模块服务 ``ProviderRole.EMBEDDING``。"""

    return ProviderRole.EMBEDDING


class MockEmbeddingProvider(EmbeddingProvider):
    """确定性、内容敏感的 mock embedding（默认）。

    采用字符 bigram 哈希分桶（hashing trick）+ L2 归一化：相同文本→相同向量，
    文本共享字符片段→余弦更高。零外部依赖，CI / Dev 默认使用。
    """

    def __init__(self, dim: int = 64) -> None:
        if dim <= 0:
            raise ValueError("dim must be positive")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(t) for t in texts]

    def _embed_one(self, text: str) -> list[float]:
        vec = [0.0] * self._dim
        if not text:
            return vec
        # 字符 bigram 序列（含首尾哨兵）。
        grams = [text[i : i + 2] for i in range(len(text) - 1)] or [text]
        for g in grams:
            h = int.from_bytes(
                hashlib.sha256(g.encode("utf-8")).digest()[:8], "big"
            )
            bucket = h % self._dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


class OpenAICompatEmbeddingProvider(EmbeddingProvider):
    """OpenAI 兼容 ``/embeddings`` 端点的真实 embedding provider。

    复用 ``openai_compat.py`` 的 ``urllib`` 同步 POST + ``asyncio.to_thread``
    模式，**不引入 httpx / openai SDK**。base_url/api_key/model 来自配置/环境变量。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 30.0,
    ) -> None:
        if not base_url.strip():
            raise EmbeddingConfigError("OpenAI 兼容 embedding 需要 base_url")
        if not api_key.strip():
            raise EmbeddingConfigError("OpenAI 兼容 embedding 需要 api_key")
        if not model.strip():
            raise EmbeddingConfigError("OpenAI 兼容 embedding 需要 model")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = float(timeout)
        self._dim: int | None = None  # 首次请求后从响应推断

    @property
    def dim(self) -> int:
        if self._dim is None:
            raise RuntimeError(
                "dim 尚未确定：请先调用一次 embed()（从真实端点响应推断维度）"
            )
        return self._dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        import asyncio

        return asyncio.run(self._aembed(list(texts)))

    async def _aembed(self, texts: list[str]) -> list[list[float]]:
        import asyncio

        def _sync() -> list[list[float]]:
            url = self._base_url + "/embeddings"
            body = json.dumps({"input": texts, "model": self._model}).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    raw = resp.read().decode("utf-8")
            except Exception as exc:  # noqa: BLE001 - 网络错误透传为配置/运行时错误
                raise EmbeddingConfigError(
                    f"embedding 请求失败（{self._base_url}）：{type(exc).__name__}: {exc}"
                ) from exc
            payload = json.loads(raw)
            data = payload.get("data")
            if not isinstance(data, list) or not data:
                raise EmbeddingConfigError("embedding 响应缺少 data")
            vectors = [d.get("embedding") for d in data]
            if any(not isinstance(v, list) for v in vectors):
                raise EmbeddingConfigError("embedding 响应含非法向量")
            if self._dim is None:
                self._dim = len(vectors[0])
            return [list(v) for v in vectors]

        return await asyncio.to_thread(_sync)


__all__ = [
    "EmbeddingConfigError",
    "EmbeddingProvider",
    "MockEmbeddingProvider",
    "OpenAICompatEmbeddingProvider",
    "_role_is_embedding",
]
