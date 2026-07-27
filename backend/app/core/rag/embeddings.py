"""Embedding provider 工厂（Phase 2.2 / 2.2.5）。

运行时按 ``BOIP_EMBEDDING_PROVIDER`` 环境变量选择 provider，**默认 ``mock``**
（不直连真实 Embedding 服务）。真实 ``openai_compat`` 仅在显式配置后启用。
底层复用 ``agents.llm.embedding`` 的 ``EmbeddingProvider`` 抽象与
``ProviderRole.EMBEDDING`` 语义角色（不新建 LLM 体系）。
"""

from __future__ import annotations

import os

from agents.llm.embedding import (
    EmbeddingConfigError,
    EmbeddingProvider,
    MockEmbeddingProvider,
    OpenAICompatEmbeddingProvider,
)


_PROVIDER_INSTANCE: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """按环境变量返回 embedding provider（默认 mock）。

    返回**进程内单例**（与 vector store 同一会话维度一致，保证 ingest/search
    同 provider 同维度）。env 变更后请调用 ``reset_embedding_provider()``。

    - ``BOIP_EMBEDDING_PROVIDER=mock``（默认）→ ``MockEmbeddingProvider``
    - ``BOIP_EMBEDDING_PROVIDER=openai_compat`` → 真实端点；读
      ``EMBEDDING_BASE_URL/API_KEY/MODEL``，缺省回落 ``LLM_A_*`` 同源
      （因 TokenHub 兼服 embeddings）；凭据缺失则回落 mock（不崩溃）
    - 未知值 → 抛 ``EmbeddingConfigError``（fail-fast）
    """

    global _PROVIDER_INSTANCE
    if _PROVIDER_INSTANCE is not None:
        return _PROVIDER_INSTANCE

    kind = (os.getenv("BOIP_EMBEDDING_PROVIDER", "mock") or "mock").strip().lower()
    dim = _safe_int(os.getenv("BOIP_EMBEDDING_DIM", "64"), default=64)

    if kind == "mock":
        _PROVIDER_INSTANCE = MockEmbeddingProvider(dim=dim)
    elif kind == "openai_compat":
        base_url = _first_env("EMBEDDING_BASE_URL", "LLM_A_BASE_URL")
        api_key = _first_env("EMBEDDING_API_KEY", "LLM_A_API_KEY")
        model = _first_env("EMBEDDING_MODEL", "LLM_A_MODEL")
        is_unresolved = (
            base_url.startswith("${")
            or api_key.startswith("${")
            or base_url in ("", "pending_verification")
            or api_key in ("", "pending_verification")
            or model in ("", "pending_verification")
        )
        if is_unresolved:
            _PROVIDER_INSTANCE = MockEmbeddingProvider(dim=dim)
        else:
            try:
                _PROVIDER_INSTANCE = OpenAICompatEmbeddingProvider(
                    base_url=base_url, api_key=api_key, model=model
                )
            except EmbeddingConfigError:
                _PROVIDER_INSTANCE = MockEmbeddingProvider(dim=dim)
    else:
        raise EmbeddingConfigError(
            f"未知 BOIP_EMBEDDING_PROVIDER：{kind!r}（支持 mock / openai_compat）"
        )
    return _PROVIDER_INSTANCE


def reset_embedding_provider() -> None:
    """清空 embedding provider 单例（测试隔离用）。"""

    global _PROVIDER_INSTANCE
    _PROVIDER_INSTANCE = None


def _first_env(*names: str) -> str:
    for name in names:
        val = os.getenv(name, "").strip()
        if val:
            return val
    return ""


def _safe_int(val: str | None, *, default: int) -> int:
    try:
        return int(str(val).strip())
    except (TypeError, ValueError):
        return default


__all__ = [
    "get_embedding_provider",
    "reset_embedding_provider",
    "EmbeddingConfigError",
    "EmbeddingProvider",
]
