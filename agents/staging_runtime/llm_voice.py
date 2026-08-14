"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Staging LLM & Voice Validation（Task 24-25）。

- Task 24 StagingLLMValidation：描述 staging 下 LLM 接入验证（非生产 endpoint），
  拒绝复用 Production LLM endpoint / 真实生产推理路径。
- Task 25 StagingVoiceValidation：描述 staging 下 Voice 接入验证（非生产），拒绝生产语音链路。

fail-closed：staging 的 LLM/Voice 验证绝不指向 production；本模块只描述验证形态，
不发起真实推理/语音调用。真实接入由人工在授权后执行。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard


class StagingLLMVoiceError(Exception):
    """Staging LLM/Voice 验证违例（fail-closed）。"""


@dataclass(frozen=True)
class ValidationDescriptor:
    endpoint_present: bool
    is_production: bool = False
    non_production: bool = True
    target: str = "local_staging"

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_present": self.endpoint_present,
            "is_production": self.is_production,
            "non_production": self.non_production,
            "target": self.target,
        }


class StagingLLMValidation:
    """本地预生产 LLM 接入验证（只描述形态，绝不指向生产 endpoint）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_endpoint_refs: Iterable[str] = (),
        staging_endpoint: str | None = None,
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_endpoint_refs = frozenset(production_endpoint_refs)
        self._staging_endpoint = staging_endpoint

    def describe(self) -> ValidationDescriptor:
        ep = self._staging_endpoint
        if ep is not None and ep in self._production_endpoint_refs:
            raise StagingLLMVoiceError(
                "staging LLM endpoint 命中 Production endpoint 引用集合，拒绝复用。"
            )
        present = ep is not None and ep != "pending_verification"
        return ValidationDescriptor(endpoint_present=present)

    def invoke(self) -> ValidationDescriptor:
        """**永不**发起真实推理；调用即抛。"""

        raise StagingLLMVoiceError(
            "StagingLLMValidation.invoke() 被调用：系统禁止在 staging 发起真实推理。"
        )


class StagingVoiceValidation:
    """本地预生产 Voice 接入验证（只描述形态，绝不指向生产语音链路）。"""

    def __init__(
        self,
        identity: EnvironmentIdentity,
        *,
        production_voice_refs: Iterable[str] = (),
        staging_voice: str | None = None,
    ) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity
        self._production_voice_refs = frozenset(production_voice_refs)
        self._staging_voice = staging_voice

    def describe(self) -> ValidationDescriptor:
        v = self._staging_voice
        if v is not None and v in self._production_voice_refs:
            raise StagingLLMVoiceError(
                "staging Voice 链路命中 Production 语音引用集合，拒绝复用。"
            )
        present = v is not None and v != "pending_verification"
        return ValidationDescriptor(endpoint_present=present)

    def synthesize(self) -> ValidationDescriptor:
        """**永不**发起真实语音合成；调用即抛。"""

        raise StagingLLMVoiceError(
            "StagingVoiceValidation.synthesize() 被调用：系统禁止在 staging 发起真实语音合成。"
        )


__all__ = [
    "StagingLLMVoiceError",
    "ValidationDescriptor",
    "StagingLLMValidation",
    "StagingVoiceValidation",
]
