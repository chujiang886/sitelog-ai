"""DualTrackRouter（Phase 1 / T06a 双轨 LLM 路由器）。

双轨策略：
- 同时启动 track_a / track_b 两个 provider；
- 按 strategy 选最终响应（fastest / first / consensus / fallback）；
- 永远记录两条 track 的执行结果（含失败原因），便于证据链追踪；
- 任何一条 track 缺 API key 时自动降级到 MockProvider。
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Mapping

from .base import LLMRouterError
from .mock import MockProvider
from .types import LLMRequest, LLMResponse, LLMRouteResult


class RouterStrategy(str, Enum):
    """双轨选路策略。"""

    FASTEST = "fastest"      # 谁先返回用谁（含成功 / 失败）
    FIRST = "first"          # 严格首个返回的结果（成功优先，失败则用另一条）
    CONSENSUS = "consensus"  # 两条 track 内容一致才通过，否则用 track_a
    FALLBACK = "fallback"    # track_a 失败时用 track_b


class ProviderRole(str, Enum):
    """LLM provider 语义角色（Phase 2.1.6 provider 解耦）。

    - ``TEXT``：文本推理主轨；
    - ``VISION``：视觉推理主轨（多模态）；
    - ``EMBEDDING``：向量/检索预留角色（不进入 DualTrackRouter，当前 disabled）；
    - ``FALLBACK``：文本/视觉共用的容灾副轨；
    - ``UNKNOWN``：防御状态。传入非法/未知角色字符串时不抛异常，安全回落
      ``FALLBACK``（mock 容灾），避免配置错误导致路由构造崩溃。
    """

    TEXT = "text"
    VISION = "vision"
    EMBEDDING = "embedding"
    FALLBACK = "fallback"
    UNKNOWN = "unknown"


def _now_ms() -> int:
    """单调时钟当前毫秒数。"""

    return int(time.monotonic() * 1000)


class DualTrackRouter:
    """并行调用两个 provider 并按策略选出最终响应。"""

    DEFAULT_TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        *,
        track_a_provider,
        track_b_provider,
        strategy: RouterStrategy | str = RouterStrategy.FASTEST,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        consensus_match_strict: bool = True,
    ) -> None:
        """注入两个 provider；strategy 接受枚举或字符串。"""

        from .base import LLMProvider  # noqa: PLC0415 - 局部导入避免循环

        if not isinstance(track_a_provider, LLMProvider):
            raise TypeError("track_a_provider must be an LLMProvider")
        if not isinstance(track_b_provider, LLMProvider):
            raise TypeError("track_b_provider must be an LLMProvider")
        if timeout <= 0:
            raise ValueError("timeout must be > 0")
        normalized_strategy: RouterStrategy = (
            strategy if isinstance(strategy, RouterStrategy) else RouterStrategy(str(strategy))
        )
        self._track_a = track_a_provider
        self._track_b = track_b_provider
        self._strategy: RouterStrategy = normalized_strategy
        self._timeout: float = float(timeout)
        self._consensus_match_strict: bool = bool(consensus_match_strict)

    @property
    def strategy(self) -> RouterStrategy:
        """Return the configured routing strategy."""

        return self._strategy

    @property
    def track_a(self):  # pragma: no cover - 简单访问器
        """Return the track_a provider (mainly for diagnostics)."""

        return self._track_a

    @property
    def track_b(self):  # pragma: no cover - 简单访问器
        """Return the track_b provider (mainly for diagnostics)."""

        return self._track_b

    async def route(self, request: LLMRequest) -> tuple[LLMResponse, list[LLMRouteResult]]:
        """执行双轨调用并返回 ``(选定响应, 双轨原始结果)``。

        当两条 track 全部失败时抛 ``LLMRouterError``，便于上游 fallback。
        """

        if not request.messages:
            raise ValueError("LLMRequest.messages must not be empty")

        start = _now_ms()
        coros = (
            self._run_track(self._track_a, "track_a", request, start),
            self._run_track(self._track_b, "track_b", request, start),
        )
        results = await asyncio.gather(*coros, return_exceptions=False)
        chosen = self._select(results)
        return chosen, results

    async def _run_track(
        self,
        provider,
        track: str,
        request: LLMRequest,
        started_ms: int,
    ) -> LLMRouteResult:
        """执行单条 track；失败时记录错误并回填占位响应。"""

        started = _now_ms()
        try:
            response = await asyncio.wait_for(provider.complete(request), timeout=self._timeout)
            return LLMRouteResult(
                provider_name=provider.name,
                track=track,
                response=response,
                error=None,
                latency_ms=_now_ms() - started,
                pending_verification=False,
            )
        except Exception as exc:  # noqa: BLE001 - 记录并回退
            return LLMRouteResult(
                provider_name=provider.name,
                track=track,
                response=None,
                error=f"{type(exc).__name__}: {exc}",
                latency_ms=_now_ms() - started,
                pending_verification=True,
            )

    def _select(self, results: list[LLMRouteResult]) -> LLMResponse:
        """按 strategy 选出最终响应；任何失败路径均显式记录在 results 中。"""

        a, b = results
        if self._strategy is RouterStrategy.FASTEST:
            candidates = [r for r in (a, b) if r.response is not None]
            if not candidates:
                raise LLMRouterError(self._error_message(a, b))
            return min(candidates, key=lambda r: r.latency_ms).response  # type: ignore[return-value]
        if self._strategy is RouterStrategy.FIRST:
            ordered = sorted((a, b), key=lambda r: r.latency_ms)
            for track in ordered:
                if track.response is not None:
                    return track.response  # type: ignore[return-value]
            raise LLMRouterError(self._error_message(a, b))
        if self._strategy is RouterStrategy.CONSENSUS:
            if a.response is not None and b.response is not None:
                equal: bool = (a.response.content == b.response.content) if self._consensus_match_strict else (
                    a.response.content.strip() == b.response.content.strip()
                )
                if equal:
                    return a.response  # 两条一致，使用 track_a
            # 任意一条缺失 / 不一致时回退 track_a；若 track_a 缺失则用 track_b；都不行则报错
            if a.response is not None:
                return a.response
            if b.response is not None:
                return b.response
            raise LLMRouterError(self._error_message(a, b))
        # FALLBACK：优先 track_a，失败时回退 track_b
        if a.response is not None:
            return a.response
        if b.response is not None:
            return b.response
        raise LLMRouterError(self._error_message(a, b))

    @staticmethod
    def _error_message(a: LLMRouteResult, b: LLMRouteResult) -> str:
        """汇总两条 track 的失败原因。"""

        return f"双轨调用均失败：track_a={a.error!r}; track_b={b.error!r}"

    async def aclose(self) -> None:
        """关闭底层 provider（若有连接池）。"""

        await self._track_a.aclose()
        await self._track_b.aclose()


def build_router_from_config(
    config: Mapping[str, object],
    role: "ProviderRole | str" = ProviderRole.TEXT,
    modality: str | None = None,
) -> DualTrackRouter:
    """根据 ``agents/config.yaml::llm`` 节构造双轨路由器。

    任何一条 track 缺 API key 时自动替换为 ``MockProvider``，
    满足 16 第五章 "未连接真实 LLM 时不崩溃" 要求。

    Phase 2.1.6 provider 解耦：
    - ``role``：语义角色，取值 ``ProviderRole.TEXT / VISION / FALLBACK``
      （embedding 不进入 DualTrackRouter）。主轨 = role 对应 provider，
      副轨恒为 ``ProviderRole.FALLBACK``（mock 容灾）。
    - ``modality``：**已弃用兼容参数**，仅保留向后兼容；``"vision"`` 映射
      到 ``VISION`` 角色，其余映射 ``TEXT``。新代码请使用 ``role=``。
    """

    # 兼容旧 modality= 软开关（deprecated since 2.1.6）。
    if modality is not None:
        role = _modality_to_role(modality)
    if not isinstance(role, ProviderRole):
        try:
            role = ProviderRole(str(role).strip().lower())
        except ValueError:
            # 非法/未知角色字符串：防御性回落 UNKNOWN，绝不抛异常。
            role = ProviderRole.UNKNOWN

    router_cfg = config.get("router", {})
    if not isinstance(router_cfg, Mapping):
        router_cfg = {}
    strategy_raw = str(router_cfg.get("strategy", RouterStrategy.FASTEST.value))
    timeout_raw = router_cfg.get("timeout", DualTrackRouter.DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"llm.router.timeout 非法：{timeout_raw!r}") from exc

    primary = resolve_provider(config, role)
    fallback = resolve_provider(config, ProviderRole.FALLBACK)
    return DualTrackRouter(
        track_a_provider=primary,  # type: ignore[arg-type]
        track_b_provider=fallback,  # type: ignore[arg-type]
        strategy=RouterStrategy(strategy_raw),
        timeout=timeout,
    )


def _modality_to_role(modality: str) -> ProviderRole:
    """把旧 ``modality=`` 软开关映射为 ``ProviderRole``（deprecated）。"""

    return ProviderRole.VISION if str(modality).strip().lower() == "vision" else ProviderRole.TEXT


def resolve_provider(config: Mapping[str, object], role: ProviderRole) -> object:
    """解析某角色的 provider。

    回落规则（语义化 ``providers`` 块与旧 ``track_a``/``track_b`` 键并存）：
    - ``VISION`` 缺块 → 回落 ``TEXT`` 块；
    - 新 ``providers`` 块缺配置时，回落旧 ``track_a`` / ``track_b`` 键；
    - 仍无配置 → ``MockProvider``（不崩溃）；
    - ``EMBEDDING`` 且 ``provider=disabled`` → 返回 ``None``（无消费者）。
    """

    providers = config.get("providers") or {}
    if not isinstance(providers, Mapping):
        providers = {}

    # 防御：UNKNOWN 角色安全回落 FALLBACK，绝不抛异常。
    if role is ProviderRole.UNKNOWN:
        return resolve_provider(config, ProviderRole.FALLBACK)

    block = providers.get(role.value) or {}
    if not isinstance(block, Mapping):
        block = {}

    # VISION 缺块 → 回落 TEXT 块（保持视觉/文本同源的向后兼容）。
    if role is ProviderRole.VISION and not block:
        block = providers.get("text") or {}
        if not isinstance(block, Mapping):
            block = {}

    # 新 providers 块缺失时，回落旧 track_a / track_b 键（兼容解析，不作新入口）。
    if not block:
        if role in (ProviderRole.TEXT, ProviderRole.VISION):
            block = config.get("track_a") or {}
        elif role is ProviderRole.FALLBACK:
            block = config.get("track_b") or {}
        if not isinstance(block, Mapping):
            block = {}

    # EMBEDDING 为预留角色：disabled → None；未来接具体向量服务时在此构造。
    if role is ProviderRole.EMBEDDING:
        provider_kind = str(block.get("provider", "disabled")).strip().lower()
        if provider_kind in ("disabled", ""):
            return None
        return _build_provider(block, default_name="embedding")

    if not block:
        model = str(block.get("model", "")).strip()
        return MockProvider(model=model or "mock-llm-v0")

    return _build_provider(block, default_name=role.value)


def build_embedding_provider(config: Mapping[str, object]):
    """构建 embedding provider（Phase 2.2 / 2.2.5，复用 ``ProviderRole.EMBEDDING``）。

    - ``provider: disabled`` / 缺省 → 返回 ``None``（无消费者，保持旧行为）；
    - ``provider: mock`` → ``MockEmbeddingProvider``（确定性、零依赖）；
    - ``provider: openai_compat`` 且凭据已解析 → ``OpenAICompatEmbeddingProvider``；
      凭据缺失（``${VAR}`` 占位 / ``pending_verification`` / 空）→ 回落 mock（不崩溃）。
    """

    from .embedding import (  # noqa: PLC0415 - 懒加载，避免未用时引入
        EmbeddingConfigError,
        MockEmbeddingProvider,
        OpenAICompatEmbeddingProvider,
    )

    providers = config.get("providers") or {}
    if not isinstance(providers, Mapping):
        providers = {}
    block = providers.get("embedding") or {}
    if not isinstance(block, Mapping):
        block = {}
    provider_kind = str(block.get("provider", "disabled")).strip().lower()
    if provider_kind in ("disabled", ""):
        return None

    try:
        dim = int(str(block.get("dim", 64)).strip() or 64)
    except (TypeError, ValueError):
        dim = 64

    if provider_kind == "mock":
        return MockEmbeddingProvider(dim=dim)

    if provider_kind == "openai_compat":
        base_url = str(block.get("base_url", "")).strip()
        api_key = str(block.get("api_key", "")).strip()
        model = str(block.get("model", "")).strip()
        is_unresolved = (
            base_url.startswith("${")
            or api_key.startswith("${")
            or base_url in ("", "pending_verification")
            or api_key in ("", "pending_verification")
            or model in ("", "pending_verification")
        )
        if is_unresolved:
            return MockEmbeddingProvider(dim=dim)
        try:
            return OpenAICompatEmbeddingProvider(
                base_url=base_url, api_key=api_key, model=model
            )
        except EmbeddingConfigError:
            return MockEmbeddingProvider(dim=dim)

    # 未知 provider：安全回落 mock，绝不抛异常。
    return MockEmbeddingProvider(dim=dim)


def _build_provider(track_cfg: Mapping[str, object], *, default_name: str):
    """根据单条 track 配置构造 provider；缺 key 时退化为 MockProvider。"""

    from .anthropic_compat import AnthropicCompatibleProvider  # noqa: PLC0415
    from .openai_compat import OpenAICompatibleProvider  # noqa: PLC0415

    provider_kind = str(track_cfg.get("provider", "mock")).strip().lower() or "mock"
    api_key = str(track_cfg.get("api_key", "")).strip()
    base_url = str(track_cfg.get("base_url", "")).strip()
    model = str(track_cfg.get("model", "")).strip()

    # 未解析的 ${VAR:default} 占位 / 显式声明的 pending_verification / 空值都视为未接入。
    is_unresolved_placeholder = (
        api_key.startswith("${") or api_key == "pending_verification" or not api_key
    )

    if provider_kind == "mock" or is_unresolved_placeholder:
        return MockProvider(model=model or "mock-llm-v0")

    if provider_kind == "openai_compat":
        return OpenAICompatibleProvider(
            name=default_name,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    if provider_kind == "anthropic_compat":
        return AnthropicCompatibleProvider(
            name=default_name,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )
    raise ValueError(f"未知 llm.provider：{provider_kind}")


__all__ = [
    "DualTrackRouter",
    "RouterStrategy",
    "ProviderRole",
    "build_router_from_config",
    "resolve_provider",
    "build_embedding_provider",
    "build_embedding_provider",
]