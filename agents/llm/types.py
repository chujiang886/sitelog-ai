"""LLM request/response 数据类型（Phase 1 / T06a）。

仅作为消息结构 + 元数据容器，不引入任何具体 provider 依赖，
便于在双轨路由、缓存、重试和评测层之间复用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class LLMRole(str, Enum):
    """对话角色枚举，与 OpenAI / Anthropic 协议字段名一致。"""

    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class LLMMessage:
    """单条对话消息；role + content 必备，name 等可选扩展字段放在 metadata。"""

    role: LLMRole
    content: str | list[dict[str, Any]]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """拒绝空内容或包含换行符以外的非法控制字符，保持消息可序列化。"""

        if not isinstance(self.role, LLMRole):
            raise TypeError(f"LLMMessage.role must be LLMRole, got {type(self.role).__name__}")
        if not isinstance(self.content, (str, list)):
            raise TypeError("LLMMessage.content must be str or list of content blocks")
        if not self.content:
            raise ValueError("LLMMessage.content must not be empty")
        if isinstance(self.content, list):
            if not all(isinstance(block, dict) for block in self.content):
                raise TypeError("LLMMessage content blocks must be dictionaries")
            object.__setattr__(self, "content", [dict(block) for block in self.content])
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of this message."""

        return {
            "role": self.role.value,
            "content": self.content,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """调用 LLM 所需的请求参数；messages 必有，model/options 可选。"""

    messages: tuple[LLMMessage, ...]
    model: str = ""
    max_tokens: int = 0
    temperature: float = 0.0
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """规范化 messages 与 options，校验基本边界。"""

        if not self.messages:
            raise ValueError("LLMRequest.messages must not be empty")
        if self.max_tokens < 0:
            raise ValueError("LLMRequest.max_tokens must be >= 0")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("LLMRequest.temperature must be within [0, 2]")
        object.__setattr__(self, "messages", tuple(self.messages))
        object.__setattr__(self, "options", MappingProxyType(dict(self.options)))

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of this request."""

        return {
            "messages": [m.to_dict() for m in self.messages],
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "options": dict(self.options),
        }


@dataclass(frozen=True, slots=True)
class LLMResponse:
    """标准 LLM 响应信封（success/data 双字段结构与 16 第七章一致）。"""

    content: str
    model: str
    finish_reason: str
    usage: Mapping[str, int] = field(default_factory=dict)
    raw: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """冻结 usage 与 raw，防止下游误改。"""

        if not isinstance(self.content, str):
            raise TypeError("LLMResponse.content must be str")
        if not isinstance(self.model, str):
            raise TypeError("LLMResponse.model must be str")
        if not isinstance(self.finish_reason, str):
            raise TypeError("LLMResponse.finish_reason must be str")
        if not self.model:
            raise ValueError("LLMResponse.model must not be empty")
        object.__setattr__(self, "usage", MappingProxyType(dict(self.usage)))
        object.__setattr__(self, "raw", MappingProxyType(dict(self.raw)))

    def to_envelope(self) -> dict[str, Any]:
        """Return the BOIP standard envelope representation."""

        return {
            "success": True,
            "data": {
                "content": self.content,
                "model": self.model,
                "finish_reason": self.finish_reason,
                "usage": dict(self.usage),
            },
        }


@dataclass(frozen=True, slots=True)
class LLMRouteResult:
    """双轨路由器在一次调用中产出的中间结果（用于 evidence + fallback 决策）。"""

    provider_name: str
    track: str  # "track_a" / "track_b"
    response: LLMResponse | None
    error: str | None = None
    latency_ms: int = 0
    pending_verification: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot, hiding raw response details by default."""

        return {
            "provider": self.provider_name,
            "track": self.track,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "pending_verification": self.pending_verification,
            "content": self.response.content if self.response else None,
            "model": self.response.model if self.response else None,
        }


__all__ = [
    "LLMMessage",
    "LLMRequest",
    "LLMResponse",
    "LLMRole",
    "LLMRouteResult",
]