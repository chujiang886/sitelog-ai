"""OpenAI 兼容 provider（Phase 1 / T06a）。

涵盖 OpenAI / 通义 / DeepSeek / Ollama / vLLM 等所有 OpenAI 协议兼容端点。
底层通过 ``urllib.request`` 实现同步 HTTP 调用，由 provider 在
``asyncio.to_thread`` 中调度，避免引入 ``httpx`` / ``openai`` SDK。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .base import LLMProvider, LLMProviderError
from .types import LLMMessage, LLMRequest, LLMResponse


def _to_payload_messages(messages: tuple[LLMMessage, ...]) -> list[dict[str, Any]]:
    """把内部 ``LLMMessage`` 转换为 OpenAI 兼容协议 ``messages`` 字段。"""

    payload: list[dict[str, Any]] = []
    for message in messages:
        payload.append({"role": message.role.value, "content": message.content})
    return payload


def _build_request_body(request: LLMRequest, *, model: str) -> dict[str, Any]:
    """构造 OpenAI 兼容协议请求体；temperature/max_tokens 按需裁剪。"""

    body: dict[str, Any] = {
        "model": model or request.model,
        "messages": _to_payload_messages(request.messages),
    }
    if request.temperature:
        body["temperature"] = request.temperature
    if request.max_tokens:
        body["max_tokens"] = request.max_tokens
    if request.options:
        body.update(dict(request.options))
    return body


def _parse_response_body(body: Any, *, default_model: str) -> LLMResponse:
    """解析 OpenAI 协议响应；缺字段时抛 ``LLMProviderError``。"""

    if not isinstance(body, dict):
        raise LLMProviderError("OpenAI 兼容端点返回非 JSON 对象")
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMProviderError("OpenAI 兼容端点响应缺少 choices")
    first = choices[0]
    if not isinstance(first, dict):
        raise LLMProviderError("OpenAI 兼容端点 choices[0] 非法")
    message = first.get("message") or {}
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str):
        raise LLMProviderError("OpenAI 兼容端点响应缺少 message.content")
    finish_reason = str(first.get("finish_reason") or "stop")
    usage_raw = body.get("usage") or {}
    usage: dict[str, int] = (
        {str(k): int(v) for k, v in usage_raw.items() if isinstance(v, (int, float))}
        if isinstance(usage_raw, dict)
        else {}
    )
    return LLMResponse(
        content=content,
        model=str(body.get("model") or default_model),
        finish_reason=finish_reason,
        usage=usage,
        raw=body,
    )


class OpenAICompatibleProvider(LLMProvider):
    """OpenAI 兼容协议的 LLM provider；本地默认不真正联网。"""

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = LLMProvider.DEFAULT_TIMEOUT_SECONDS,
        extra_path: str = "/chat/completions",
    ) -> None:
        """初始化；要求 base_url + api_key + model 非空。"""

        super().__init__(name=name, base_url=base_url, api_key=api_key, model=model, timeout=timeout)
        if not base_url.strip():
            raise ValueError(f"{name}: base_url must not be empty for OpenAI 兼容 provider")
        if not api_key.strip():
            raise ValueError(f"{name}: api_key must not be empty for OpenAI 兼容 provider")
        if not model.strip():
            raise ValueError(f"{name}: model must not be empty for OpenAI 兼容 provider")
        if not extra_path.startswith("/"):
            raise ValueError("extra_path must start with '/'")
        self._extra_path: str = extra_path

    @property
    def enabled(self) -> bool:
        """需要 base_url + api_key 同时非空。"""

        return bool(self._base_url) and bool(self._api_key)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        """异步调用 OpenAI 兼容端点；超时由 ``LLMProvider.timeout`` 约束。"""

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
        """阻塞 POST 调用；用于 ``asyncio.to_thread``。

        Phase 1 / T06a 默认不真正发出请求——本方法被设计为可被单测 mock，
        真实联网等待轩哥填入 API key 后再做端到端验证。
        """

        try:
            import urllib.request  # noqa: PLC0415 - 延迟导入，便于单测 patch
        except ImportError as exc:  # pragma: no cover - 极不可能
            raise LLMProviderError("缺少 urllib，无法发起 HTTP 调用") from exc
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))


__all__ = ["OpenAICompatibleProvider"]