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


def build_router_from_config(config: Mapping[str, object]) -> DualTrackRouter:
    """根据 ``agents/config.yaml::llm`` 节构造双轨路由器。

    任何一条 track 缺 API key 时自动替换为 ``MockProvider``，
    满足 16 第五章 "未连接真实 LLM 时不崩溃" 要求。
    """

    strategy_raw = str(config.get("strategy", RouterStrategy.FASTEST.value))
    timeout_raw = config.get("timeout", DualTrackRouter.DEFAULT_TIMEOUT_SECONDS)
    try:
        timeout = float(timeout_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"llm.router.timeout 非法：{timeout_raw!r}") from exc

    track_a = _build_provider(config.get("track_a", {}), default_name="track_a")
    track_b = _build_provider(config.get("track_b", {}), default_name="track_b")
    return DualTrackRouter(
        track_a_provider=track_a,
        track_b_provider=track_b,
        strategy=RouterStrategy(strategy_raw),
        timeout=timeout,
    )


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


__all__ = ["DualTrackRouter", "RouterStrategy", "build_router_from_config"]