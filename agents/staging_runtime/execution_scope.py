"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Execution Scope（Task 9）。

``StagingExecutionScope`` 把「22 条最高红线」落到**动作令牌**层：明确本地预生产验证
允许做什么、禁止（即 production / 越权）做什么。

fail-closed：未知动作默认拒绝；出现在 ``FORBIDDEN_PRODUCTION_ACTIONS`` 的动作永远拒绝；
仅 ``ALLOWED_STAGING_ACTIONS`` 显式列出的动作才允许（不靠文档约定兜底）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.isolation_guard import EnvironmentIsolationGuard

# 禁止（即 production / 越权）动作令牌 —— 覆盖 22 条最高红线核心。
FORBIDDEN_PRODUCTION_ACTIONS = frozenset(
    {
        "deploy_production",
        "migrate_production_db",
        "write_production_secret",
        "activate_production",
        "modify_production_config",
        "real_production_db_change",
        "rollback_production",
        "run_runbook",
        "close_incident",
        "skip_failure",
        "delete_assertion_for_green",
        "forge_result",
        "derive_production_approved",
        "mark_staging_as_production",
        "reuse_production_resource",
        "auto_signoff_four_roles",
        "output_go",
        "enable_engineering",
        "output_engineering_approved",
        "real_external_staging_without_verification",
        "register_production_identity_as_staging",
        "auto_close_event",
    }
)

# 允许（本地预生产验证）动作令牌。
ALLOWED_STAGING_ACTIONS = frozenset(
    {
        "validate_local_staging",
        "run_local_staging_healthcheck",
        "collect_staging_telemetry",
        "inject_synthetic_fault_local",
        "simulate_recovery_local",
        "build_evidence_package",
        "run_isolation_guard",
        "classify_environment",
        "compute_fingerprint",
        "snapshot_secret_presence",
        "build_staging_manifest",
        "plan_local_staging_deploy",
    }
)


class StagingExecutionScopeViolation(Exception):
    """动作超出本地预生产验证允许范围（fail-closed 拒绝）。"""


@dataclass(frozen=True)
class StagingExecutionVerdict:
    """动作许可结论（结构化）。"""

    action: str
    permitted: bool
    reason: str

    def require_permitted(self) -> None:
        if not self.permitted:
            raise StagingExecutionScopeViolation(
                f"动作 {self.action!r} 超出本地预生产验证允许范围：{self.reason}"
            )


class StagingExecutionScope:
    """本地预生产验证的执行边界（动作令牌白名单 + 红线黑名单）。"""

    def __init__(self, identity: EnvironmentIdentity) -> None:
        guard = EnvironmentIsolationGuard()
        guard.assert_staging_integration_permitted(identity)
        self._identity = identity

    def check(self, action: str) -> StagingExecutionVerdict:
        """判定某动作是否允许。fail-closed：未知动作默认拒绝。"""

        if action in FORBIDDEN_PRODUCTION_ACTIONS:
            return StagingExecutionVerdict(
                action=action,
                permitted=False,
                reason="命中禁止动作（production / 越权红线），永远拒绝。",
            )
        if action in ALLOWED_STAGING_ACTIONS:
            return StagingExecutionVerdict(
                action=action,
                permitted=True,
                reason="显式列入本地预生产验证允许动作白名单。",
            )
        return StagingExecutionVerdict(
            action=action,
            permitted=False,
            reason="未知动作默认拒绝（fail-closed，不靠文档约定兜底）。",
        )

    def assert_permitted(self, action: str) -> None:
        """不通过即抛 ``StagingExecutionScopeViolation``。"""

        self.check(action).require_permitted()

    def is_permitted(self, action: str) -> bool:
        return self.check(action).permitted

    def allowed_actions(self) -> frozenset[str]:
        return frozenset(ALLOWED_STAGING_ACTIONS)

    def forbidden_actions(self) -> frozenset[str]:
        return frozenset(FORBIDDEN_PRODUCTION_ACTIONS)


__all__ = [
    "FORBIDDEN_PRODUCTION_ACTIONS",
    "ALLOWED_STAGING_ACTIONS",
    "StagingExecutionScopeViolation",
    "StagingExecutionVerdict",
    "StagingExecutionScope",
]
