"""MockProvider (Phase 1 / T06a).

占位 provider：当 ``llm_enabled=false`` 或 API key 缺失时由 router 自动降级。
它**不产出假响应**——改为声明 ``pending_verification``（抛错），让
``DualTrackRouter`` 的双轨选择策略（fastest/first）只采纳真实 track 的响应，
避免即时返回的假响应污染真实链路。
"""

from __future__ import annotations


from .base import LLMProvider, LLMProviderError
from .types import LLMRequest, LLMResponse


DEFAULT_MODEL: str = "mock-llm-v0"
DEFAULT_LATENCY_MS: int = 5  # Fast but not instant for latency tests


class MockProvider(LLMProvider):
    """No-network placeholder provider; useful for local dev and CI.

    When ``config.yaml`` has ``llm.enabled=true`` but no real API key,
    the router automatically falls back to this provider.
    """

    def __init__(
        self,
        *,
        model: str = DEFAULT_MODEL,
        latency_ms: int = DEFAULT_LATENCY_MS,
        mock_response: str | None = None,
    ) -> None:
        """Initialize with optional custom response and simulated latency."""
        super().__init__(name="mock", base_url="", api_key="", model=model)
        self._simulated_latency_s: float = (
            latency_ms / 1000.0 if latency_ms > 0 else 0.0
        )
        self._mock_response: str = mock_response or "(no response)"

    @property
    def enabled(self) -> bool:
        """Mock provider is always available."""
        return True

    async def complete(self, request: LLMRequest) -> LLMResponse:
        # Mock provider 表示「未接入真实 LLM」的占位；它不应产出假响应
        # 污染双轨选择（fastest/first 策略会误选即时返回的假响应）。
        # 改为声明 pending_verification：抛错让 DualTrackRouter._run_track
        # 标记为失败（response=None），使策略只采纳真实 track 的响应。
        raise LLMProviderError(
            "mock provider 未接入真实 LLM（pending_verification）"
        )

    def set_mock_response(self, text: str) -> None:
        """Update the mock response (for testing)."""
        self._mock_response = text


__all__ = ["MockProvider", "DEFAULT_MODEL", "DEFAULT_LATENCY_MS"]