"""Phase 3.9.10 —— Failure & Recovery Scenarios（Tasks 31-32）。

定义至少 10 类故障场景与对应恢复场景，**全部 fail-closed**：

故障：DB 不可达 / Secret Provider 不可用 / IdP issuer 非法 / storage 权限拒绝 /
telemetry 不可用 / alert 投递失败 / TLS 无效 / target 误判为 production /
环境指纹碰撞 / credential namespace 碰撞。

恢复：DB / IdP / telemetry / alert / deployment rollback / runtime revalidation。
恢复结论固定 ``EXTERNAL_STAGING_RECOVERED_CANDIDATE``，**不得**表示 Production recovery。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ExternalStagingIdentityError,
)


class FailureScenario(str, Enum):
    """故障场景枚举（10 类）。"""

    DB_UNREACHABLE = "db_unreachable"
    SECRET_PROVIDER_UNAVAILABLE = "secret_provider_unavailable"
    IDP_INVALID_ISSUER = "idp_invalid_issuer"
    STORAGE_PERMISSION_DENIED = "storage_permission_denied"
    TELEMETRY_UNAVAILABLE = "telemetry_unavailable"
    ALERT_DELIVERY_FAILED = "alert_delivery_failed"
    TLS_INVALID = "tls_invalid"
    TARGET_MISCLASSIFIED_AS_PRODUCTION = "target_misclassified_as_production"
    ENVIRONMENT_FINGERPRINT_COLLISION = "environment_fingerprint_collision"
    CREDENTIAL_NAMESPACE_COLLISION = "credential_namespace_collision"


class RecoveryOutcome(str, Enum):
    """恢复结论（仅 External Staging 范畴）。"""

    EXTERNAL_STAGING_RECOVERED_CANDIDATE = "external_staging_recovered_candidate"
    RECOVERY_BLOCKED = "recovery_blocked"
    RECOVERY_PENDING = "recovery_pending"


@dataclass
class FailureEvaluation:
    """单故障场景评估（fail-closed）。"""

    scenario: FailureScenario
    triggered: bool
    safe_response: str
    blocked_production_impact: bool = True  # 故障不得波及 Production
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "triggered": self.triggered,
            "safe_response": self.safe_response,
            "blocked_production_impact": self.blocked_production_impact,
            "detail": self.detail,
        }


@dataclass
class RecoveryEvaluation:
    """单恢复场景评估。"""

    scenario: FailureScenario
    outcome: RecoveryOutcome
    represents_production_recovery: bool = False  # 恒为 False
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "outcome": self.outcome.value,
            "represents_production_recovery": self.represents_production_recovery,
            "detail": self.detail,
        }


class ExternalStagingFailureSimulator:
    """故障场景模拟器（只读评估，不真实触发）。"""

    def evaluate(self, *, triggered: set[FailureScenario]) -> tuple[FailureEvaluation, ...]:
        results: list[FailureEvaluation] = []
        for sc in FailureScenario:
            on = sc in triggered
            results.append(
                FailureEvaluation(
                    scenario=sc,
                    triggered=on,
                    safe_response=(
                        "系统 fail-closed：停止依赖该资源，标记 PENDING/BLOCKED，"
                        "不 fallback Production，不伪造连通性/验证。"
                    ),
                    blocked_production_impact=True,
                    detail="故障隔离在 External Staging 域，不波及 Production。"
                    if on
                    else "未触发。",
                )
            )
        return tuple(results)


class ExternalStagingRecoverySimulator:
    """恢复场景模拟器（恢复结论不得表示 Production recovery）。"""

    def evaluate(
        self, *, recoverable: set[FailureScenario]
    ) -> tuple[RecoveryEvaluation, ...]:
        results: list[RecoveryEvaluation] = []
        for sc in FailureScenario:
            if sc in recoverable:
                outcome = RecoveryOutcome.EXTERNAL_STAGING_RECOVERED_CANDIDATE
                detail = "External Staging 恢复候选（非 Production recovery）。"
            else:
                outcome = RecoveryOutcome.RECOVERY_PENDING
                detail = "恢复待真实资源/人工确认。"
            results.append(
                RecoveryEvaluation(
                    scenario=sc,
                    outcome=outcome,
                    represents_production_recovery=False,
                    detail=detail,
                )
            )
        return tuple(results)


def assert_no_production_recovery(outcome: RecoveryOutcome) -> None:
    """防御：任何恢复结论不得声称 Production recovery（红线）。"""

    if outcome.represents_production_recovery:
        raise ExternalStagingIdentityError(
            "恢复结论不得表示 Production recovery（红线）。"
        )


__all__ = [
    "FailureScenario",
    "RecoveryOutcome",
    "FailureEvaluation",
    "RecoveryEvaluation",
    "ExternalStagingFailureSimulator",
    "ExternalStagingRecoverySimulator",
    "assert_no_production_recovery",
]
