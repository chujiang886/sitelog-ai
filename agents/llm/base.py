"""LLMProvider 抽象类（Phase 1 / T06a）。

所有具体 provider（OpenAI 兼容 / Anthropic 兼容 / Mock / 未来 vLLM 等）
必须实现 ``complete`` 与 ``name`` 属性，并通过 ``enabled`` 决定路由是否
允许选中该 provider。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .types import LLMRequest, LLMResponse


class LLMProviderError(RuntimeError):
    """LLM provider 在调用过程中发生的可诊断错误。"""

    def __init__(self, message: str, *, provider: str = "") -> None:
        super().__init__(message)
        self.provider = provider


class LLMRouterError(RuntimeError):
    """双轨路由器在选路 / 合并结果时遇到不可恢复错误。"""


class LLMProvider(ABC):
    """异步 LLM 抽象类。"""

    #: 默认 max_tokens 上限；具体 provider 可覆盖。
    DEFAULT_TIMEOUT_SECONDS: float = 30.0

    def __init__(
        self,
        *,
        name: str,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """保存 provider 标识与连接参数；不做网络握手。"""

        normalized_name: str = name.strip()
        if not normalized_name:
            raise ValueError("LLMProvider.name must not be empty")
        if timeout <= 0:
            raise ValueError("LLMProvider.timeout must be > 0")
        self._name: str = normalized_name
        self._base_url: str = base_url.strip()
        self._api_key: str = api_key.strip()
        self._model: str = model.strip()
        self._timeout: float = float(timeout)

    @property
    def name(self) -> str:
        """Return the provider identifier (matches the registered track name)."""

        return self._name

    @property
    def base_url(self) -> str:
        """Return the configured base URL (may be empty for mock)."""

        return self._base_url

    @property
    def api_key(self) -> str:
        """Return the configured API key (may be empty when pending_verification)."""

        return self._api_key

    @property
    def model(self) -> str:
        """Return the default model identifier configured on this provider."""

        return self._model

    @property
    def timeout(self) -> float:
        """Return the per-call timeout in seconds."""

        return self._timeout

    @property
    def enabled(self) -> bool:
        """Whether the provider has the minimum credentials to be invoked.

        Default: requires non-empty ``api_key``. Subclasses may override
        (for example, ``MockProvider`` always returns ``True``).
        """

        return bool(self._api_key)

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion and return the standard response."""

        raise NotImplementedError("Concrete LLMProvider must implement complete")

    async def aclose(self) -> None:  # pragma: no cover - 默认空实现
        """Close any pooled resources. Default is a no-op."""

        return None

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        masked_key: str = "***" if self._api_key else ""
        return (
            f"<LLMProvider name={self._name!r} base_url={self._base_url!r} "
            f"model={self._model!r} api_key={masked_key}>"
        )


__all__ = ["LLMProvider", "LLMProviderError", "LLMRouterError"]