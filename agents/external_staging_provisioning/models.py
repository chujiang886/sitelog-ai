"""Phase 3.9.12 External Staging Provisioning Operator Readiness —— 核心模型（Tasks 18-19）。

定义「外部预生产环境供给算子就绪层」的核心数据模型。

本层在 3.9.10「资格认定」与 3.9.11「执行资格」之上，把 8 类真实外部资源从
``pending_external_staging_resource`` 推进到「**可被真人/运维按明确 Runbook 与 IaC
模板实际 Provision**」的就绪状态（**不实际 Provision**）。

复用（治理 复用纪律，不重造第二套）：
- ``agents.external_staging_qualification.models``：ResourceType / RESOURCE_TYPE_ORDER /
  ResourceQualificationStatus / GateStatus / CredentialReference /
  ExternalStagingResourceRegistry / ExternalStagingEnvironmentIdentity / _FORBIDDEN_STATES。
- ``agents.external_staging_qualification.credential_scanner``：assert_no_credential_leak。
- ``agents.external_staging_execution.package``：build_execution_package / package_hash
  确定性哈希范式。
- ``agents.external_staging_execution.adapters``：AdapterProbeResult / 契约测试范式。

本层新增边界（不重造）：
- ``StagingProvisioningExecutionMode``：仅 PLAN / VALIDATE / DRY_RUN /
  HUMAN_AUTHORIZED_APPLY（**禁** AUTO / PRODUCTION）。
- ``OperatorGateStatus``：**独立** 3 态闸门（BLOCKED / PENDING_HUMAN_INPUT /
  READY_FOR_HUMAN_PROVISIONING_REVIEW，**禁** GO / APPROVED / PRODUCTION_READY）。
- ``ProvisioningPlan`` / ``ProvisioningStep``：供给计划（plan-only / dry-run / 待真人）。

fail-closed 红线：
- 本模块**不**打开 ``engineering_enabled``、**不**输出 ``engineering_approved``；
- 任何供给步**不得**声明真实执行/真实开通（mode=PLAN/VALIDATE/DRY_RUN 均非真实执行；
  仅 HUMAN_AUTHORIZED_APPLY 预留给真人，AI 不代执行），**绝不**伪造
  ``PROVISIONED`` / ``DEPLOYED_PRODUCTION`` / ``GO``；
- 凭据引用**绝不**持有明文 Secret / Token / 私钥 / 含密码 DSN。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_qualification.models import (
    EXTERNAL_STAGING_ENVIRONMENT,
    ExternalStagingEnvironmentIdentity,
    ExternalStagingResourceRegistry,
    ResourceQualificationStatus,
    ResourceType,
    RESOURCE_TYPE_ORDER,
)

# 本阶段语义态常量（仅在 External Staging 范畴内，禁止 Production 语义）。
EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE = (
    "EXTERNAL_STAGING_PROVISIONING_OPERATOR_READY_BUILT_NO_GO"
)


class StagingProvisioningExecutionMode(str, Enum):
    """供给执行模式（Task 18，fail-closed 枚举）。

    - ``PLAN``：仅生成供给计划（tofu plan 等价），不真实开通。
    - ``VALIDATE``：校验 IaC 模板 / 变量 / 契约自洽，不真实开通。
    - ``DRY_RUN``：干跑（不落真实资源，确认 plan 输出），不真实开通。
    - ``HUMAN_AUTHORIZED_APPLY``：**仅预留给真人**在离线授权后执行 apply；
      AI 永不进入此模式、永不代执行。

    被禁止模式（任何代码路径不得落入）：``AUTO`` / ``PRODUCTION``。
    """

    PLAN = "plan"
    VALIDATE = "validate"
    DRY_RUN = "dry_run"
    HUMAN_AUTHORIZED_APPLY = "human_authorized_apply"

    @property
    def is_real_provisioning(self) -> bool:
        """本阶段任何 mode 都不得被 AI 视作真实开通。

        HUMAN_AUTHORIZED_APPLY 仅为真人预留，AI 不进入。
        """

        return False


# 被明确禁止的供给模式（任何代码路径不得落入）。
_FORBIDDEN_PROVISIONING_MODES = frozenset(
    {
        "auto",
        "automatic",
        "production",
        "production_apply",
        "AUTO",
        "AUTOMATIC",
        "PRODUCTION",
        "PRODUCTION_APPLY",
    }
)


class OperatorGateStatus(str, Enum):
    """Operator 闸门状态（Task 18，**独立** 3 态，禁止 GO/APPROVED/PRODUCTION_READY）。

    与 3.9.10/3.9.11 的 4 态 ``GateStatus`` **正交**——本态仅描述「真人供给前」的
    算子就绪闸门，不含任何「已通过/可上线」语义。

    - ``BLOCKED``：存在硬 violation（凭据泄漏 / 隔离失效 / 闸门自检失败）。
    - ``PENDING_HUMAN_INPUT``：等待真人提供 8 资源真实输入/密钥/授权。
    - ``READY_FOR_HUMAN_PROVISIONING_REVIEW``：就绪，等待真人供给评审与（离线）授权。
    """

    BLOCKED = "blocked"
    PENDING_HUMAN_INPUT = "pending_human_input"
    READY_FOR_HUMAN_PROVISIONING_REVIEW = "ready_for_human_provisioning_review"

    @property
    def is_go_or_approved(self) -> bool:
        """是否落入被禁止的「已通过/可上线」语义（恒 False）。"""

        return False


# 被明确禁止的 Operator 闸门态（任何代码路径不得落入）。
_FORBIDDEN_OPERATOR_GATE_STATES = frozenset(
    {
        "go",
        "approved",
        "production_ready",
        "ready",
        "GO",
        "APPROVED",
        "PRODUCTION_READY",
        "READY",
    }
)


class ProvisioningStepStatus(str, Enum):
    """供给步状态（fail-closed，禁止 PROVISIONED/DEPLOYED_PRODUCTION/GO/APPROVED）。

    - ``NOT_STARTED``：未开始。
    - ``PLAN_ONLY``：仅生成计划，未真实开通。
    - ``VALIDATE_PASSED``：模板/契约校验通过（无真实资源）。
    - ``DRY_RUN_PASSED``：干跑通过（plan 输出确认，无真实资源）。
    - ``PENDING_HUMAN_INPUT``：等待真人输入/授权。
    - ``BLOCKED`` / ``FAILED``：失败/阻断。
    """

    NOT_STARTED = "not_started"
    PLAN_ONLY = "plan_only"
    VALIDATE_PASSED = "validate_passed"
    DRY_RUN_PASSED = "dry_run_passed"
    PENDING_HUMAN_INPUT = "pending_human_input"
    BLOCKED = "blocked"
    FAILED = "failed"

    @property
    def is_real_execution(self) -> bool:
        """本阶段任何步都不得声明真实开通。plan/validate/dry_run 均非真实执行。"""

        return False


# 被明确禁止的供给步态（任何步均不得落入）。
_FORBIDDEN_PROVISIONING_STEP_STATES = frozenset(
    {
        "provisioned",
        "executed",
        "deployed_production",
        "go",
        "approved",
        "production_ready",
        "PROVISIONED",
        "EXECUTED",
        "DEPLOYED_PRODUCTION",
        "GO",
        "APPROVED",
        "PRODUCTION_READY",
    }
)


class ExternalStagingProvisioningError(ValueError):
    """外部预生产供给违例（fail-closed 阻断）。"""


@dataclass
class ProvisioningStep:
    """单供给步结果。"""

    resource_type: ResourceType
    mode: StagingProvisioningExecutionMode
    status: ProvisioningStepStatus
    detail: str = ""
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    last_checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "mode": self.mode.value,
            "status": self.status.value,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "last_checked_at": self.last_checked_at,
            "is_real_execution": False,
            "contains_real_secret": False,
        }


@dataclass
class ProvisioningPlan:
    """供给计划（plan-only / validate / dry-run / 待真人）。

    所有步 ``is_real_execution`` 恒 False，``any_real_execution`` 恒 False——
    这是 fail-closed 的「计划/干跑」而非「真实开通」。
    """

    steps: tuple[ProvisioningStep, ...] = field(default_factory=tuple)

    @classmethod
    def build_default(cls) -> "ProvisioningPlan":
        """建立默认 8 资源供给计划（全 plan-only / 待真人）。"""

        steps = tuple(
            ProvisioningStep(
                resource_type=rtype,
                mode=StagingProvisioningExecutionMode.PLAN,
                status=ProvisioningStepStatus.PLAN_ONLY,
                detail=(
                    "Plan-only provisioning step; no real resource opened. "
                    "Real provisioning requires human input + offline authorization."
                ),
            )
            for rtype in RESOURCE_TYPE_ORDER
        )
        return cls(steps=tuple(steps))

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.steps),
            "modes": sorted({s.mode.value for s in self.steps}),
            "statuses": sorted({s.status.value for s in self.steps}),
            "any_real_execution": False,
            "all_plan_only": all(
                s.status is ProvisioningStepStatus.PLAN_ONLY for s in self.steps
            ),
        }


def assert_not_forbidden_provisioning_state(state: str) -> None:
    """断言供给态不落入禁止态（fail-closed）。"""

    if state in _FORBIDDEN_PROVISIONING_STEP_STATES:
        raise ExternalStagingProvisioningError(
            f"供给步状态 {state!r} 落入禁止态（PROVISIONED/EXECUTED/GO 等），拒绝。"
        )
    if state in _FORBIDDEN_OPERATOR_GATE_STATES:
        raise ExternalStagingProvisioningError(
            f"Operator 闸门态 {state!r} 落入禁止态（GO/APPROVED/PRODUCTION_READY 等），拒绝。"
        )
    if state in _FORBIDDEN_PROVISIONING_MODES:
        raise ExternalStagingProvisioningError(
            f"供给模式 {state!r} 落入禁止态（AUTO/PRODUCTION 等），拒绝。"
        )


__all__ = [
    "EXTERNAL_STAGING_PROVISIONING_TERMINAL_STATE",
    "StagingProvisioningExecutionMode",
    "OperatorGateStatus",
    "ProvisioningStepStatus",
    "ProvisioningStep",
    "ProvisioningPlan",
    "ExternalStagingProvisioningError",
    "assert_not_forbidden_provisioning_state",
]
