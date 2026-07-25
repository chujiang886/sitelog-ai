"""Anthropic 兼容 provider（Phase 1 / T06a）。

遵循 Anthropic Messages API 协议，字段命名 ``system / messages``，
``x-api-key`` 头携带认证。同步 ``urllib`` + ``asyncio.to_thread``，
避免引入 ``anthropic`` SDK。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import LLMProvider, LLMProviderError
from .types import LLMMessage, LLMRequest, LLMResponse, LLMRole


def _split_system_and_messages(
    messages: tuple[LLMMessage, ...],
) -> tuple[str, list[dict[str, Any]]]:
    """Anthropic 协议要求 ``system`` 字段独立，其余消息仅 role + content。"""

    system_parts: list[str] = []
    converted: list[dict[str, Any]] = []
    for message in messages:
        if message.role is LLMRole.SYSTEM:
            system_parts.append(message.content)
            continue
        converted.append({"role": message.role.value, "content": message.content})
    return "\n\n".join(system_parts), converted


def _build_request_body(request: LLMRequest, *, model: str) -> dict[str, Any]:
    """构造 Anthropic Messages API 请求体。"""

    system_text, converted = _split_system_and_messages(request.messages)
    body: dict[str, Any] = {
        "model": model or request.model,
        "messages": converted,
        "max_tokens": request.max_tokens or 1024,
    }
    if system_text:
        body["system"] = system_text
    if request.temperature:
        body["temperature"] = request.temperature
    if request.options:
        body.update(dict(request.options))
    return body


def _parse_response_body(body: Any, *, default_model: str) -> LLMResponse:
    """解析 Anthropic Messages API 响应。"""

    if not isinstance(body, dict):
        raise LLMProviderError("Anthropic 端点返回非 JSON 对象")
    content_blocks = body.get("content")
    if not isinstance(content_blocks, list) or not content_blocks:
        raise LLMProviderError("Anthropic 端点响应缺少 content")
    parts: list[str] = []
    for block in content_blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    if not parts:
        raise LLMProviderError("Anthropic 端点响应缺少 text 块")
    usage_raw = body.get("usage") or {}
    usage: dict[str, int] = (
        {str(k): int(v) for k, v in usage_raw.items() if isinstance(v, (int, float))}
        if isinstance(usage_raw, dict)
        else {}
    )
    return LLMResponse(
        content="".join(parts),
        model=str(body.get("model") or default_model),
        finish_reason=str(body.get("stop_reason") or "end_turn"),
        usage=usage,
        raw=body,
    )


class AnthropicCompatibleProvider(LLMProvider):
    """Anthropic Messages API 兼容 provider。"""

    DEFAULT_MAX_TOKENS: int = 1024

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = LLMProvider.DEFAULT_TIMEOUT_SECONDS,
        extra_path: str = "/v1/messages",
        anthropic_version: str = "2023-06-01",
    ) -> None:
        """初始化；要求 base_url + api_key + model 非空。"""

        super().__init__(name=name, base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        if not base_url.strip():
            raise ValueError(f"{name}: base_url must not be empty for Anthropic 兼容 provider")
        if not api_key.strip():
            raise ValueError(f"{name}: api_key must not be empty for Anthropic 兼容 provider")
        if not model.strip():
            raise ValueError(f"{name}: model must not be empty for Anthropic 兼容 provider")
        if not extra_path.startswith("/"):
            raise ValueError("extra_path must start with '/'")
        self._extra_path: str = extra_path
        self._anthropic_version: str = anthropic_version.strip() or "2023-06-01"

    @property
    def enabled(self) -> bool:
        """需要 base_url + api_key 同时非空。"""

        return bool(self._base_url) and bool(self._api_key)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """异步调用 Anthropic Messages API。"""

        if not self.enabled:
            raise LLMProviderError(
                f"{self._name}: base_url / api_key 缺失，处于 pending_verification 状态",
                provider=self._name,
            )
        body = _build_request_body(request, model=self._model)
        endpoint = self._base_url.rstrip("/") + self._extra_path
        try:
            raw = await asyncio.wait_for(
                asyncio.to_thread(self._sync_post, endpoint, body),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError as exc:
            raise LLMProviderError(
                f"{self._name}: 调用 {endpoint} 超时（{self._timeout}s）",
                provider=self._name,
            ) from exc
        return _parse_response_body(raw, default_model=self._model)

    def _sync_post(self, endpoint: str, body: dict[str, Any]) -> Any:
        """阻塞 POST 调用；通过 ``x-api-key`` + ``anthropic-version`` 头鉴权。"""

        try:
            import urllib.request  # noqa: PLC0415 - 延迟导入，便于单测 patch
        except ImportError as exc:  # pragma: no cover - 极不可能
            raise LLMProviderError("缺少 urllib，无法发起 HTTP 调用") from exc
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": self._anthropic_version,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))


__all__ = ["AnthropicCompatibleProvider"]