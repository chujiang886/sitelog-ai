"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Read-only Status / Contract（Task 39-40）。

提供**只读**的本地预生产状态自省入口，供 API / 前端 / CI 消费：

- ``current_staging_status()``：返回当前终端态、环境、Gate 结论摘要、证据包哈希。
- ``build_staging_contract()``：返回机器可读契约（环境边界、红线集合、终端态约束）。

read-only 语义：本模块**不**执行任何动作、**不**连接、**不**修改状态；仅聚合已有
staging_runtime 组件的结论。任何写/执行/部署端点均不在此提供（红线：不真实部署/激活）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.environment import EnvironmentIdentity, RuntimeEnvironment
from agents.staging_runtime.gate import StagingValidationGate, TERMINAL_STATE
from agents.staging_runtime.packet import build_staging_packet

# 本阶段契约级红线集合（用于契约 SSOT 与前端展示）。
_STAGING_CONTRACT_RED_LINES = (
    "engineering_enabled 恒为 false",
    "不输出 engineering_approved",
    "不真实部署 / 不真实 DB migration / 不改 Production 配置 / 不写真实 Secret",
    "不把 Staging 说成 Production",
    "不复用 Production 的 database/secret/identity_provider/storage/alert",
    "不自动关 Incident / 不跑 Runbook / 不 skip 掩盖失败 / 不删断言换绿 / 不伪造结果",
    "不推导 Production Approved / 不输出 GO",
    "终端态恒为 PHASE_3_9_9_REAL_STAGING_RUNTIME_VALIDATION_BUILT_NO_GO",
)


@dataclass(frozen=True)
class StagingStatusSummary:
    """只读状态摘要。"""

    terminal_state: str
    environment: str
    is_production: bool
    gate_passed: bool
    external_pending: bool
    human_verification_required: bool
    evidence_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "terminal_state": self.terminal_state,
            "environment": self.environment,
            "is_production": self.is_production,
            "gate_passed": self.gate_passed,
            "external_pending": self.external_pending,
            "human_verification_required": self.human_verification_required,
            "evidence_hash": self.evidence_hash,
            "reads_only": True,
        }


def current_staging_status(
    identity: EnvironmentIdentity | None = None,
    *,
    secret_names: tuple[str, ...] = (),
) -> StagingStatusSummary:
    """只读：聚合当前本地预生产状态（不执行任何动作）。"""

    ident = identity or load_staging_identity()
    gate = StagingValidationGate(ident).run(secret_names=list(secret_names))
    return StagingStatusSummary(
        terminal_state=gate.terminal_state,
        environment=ident.kind.value,
        is_production=ident.kind.is_production,
        gate_passed=gate.passed,
        external_pending=gate.external_pending,
        human_verification_required=gate.human_verification_required,
        evidence_hash=gate.evidence_hash,
    )


def build_staging_contract() -> dict[str, Any]:
    """返回机器可读契约（环境边界 + 红线集合 + 终端态约束）。"""

    return {
        "phase": "3.9.9",
        "layer": "Real Staging Runtime Integration & Validation",
        "schema_version": "1.0.0",
        "allowed_environments": [
            RuntimeEnvironment.LOCAL_STAGING.value,
            RuntimeEnvironment.EXTERNAL_STAGING.value,
        ],
        "forbidden_environment": RuntimeEnvironment.PRODUCTION.value,
        "terminal_state": TERMINAL_STATE,
        "terminal_state_constraints": {
            "never": ["PRODUCTION_READY", "APPROVED", "GO", "PRODUCTION_ACTIVATED"],
        },
        "red_lines": list(_STAGING_CONTRACT_RED_LINES),
        "reads_only": True,
        "no_execution_endpoints": True,
    }


__all__ = [
    "StagingStatusSummary",
    "current_staging_status",
    "build_staging_contract",
]
