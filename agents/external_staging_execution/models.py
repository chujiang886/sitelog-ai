"""Phase 3.9.11 External Staging Execution & Qualification Layer —— 核心模型（Tasks 2-5）。

定义外部预生产环境**执行**层的核心数据模型。本层在 3.9.10「资格认定」之上，执行
（plan-only / contract-test / 待真实资源）真实外部预生产环境的部署、运行时、隔离、
E2E、故障注入、恢复、回滚、证据与闸门。

复用（治理 复用纪律，不重造第二套）：
- ``agents.external_staging_qualification.models``：ResourceType / RESOURCE_TYPE_ORDER /
  ResourceQualificationStatus / GateStatus / RuntimeHealthStatus / 环境身份 / 登记簿。
- ``agents.staging_runtime.environment``：RuntimeEnvironment（恒 EXTERNAL_STAGING）。
- 闸门沿用 qualification 的 4 态 GateStatus（禁 APPROVED/PRODUCTION_READY/GO）。

fail-closed 红线：
- 本模块**不**打开 ``engineering_enabled``、**不**输出 ``engineering_approved``；
- 任何执行步**不得**声明真实执行（deploy=plan-only、runtime/isolation/e2e=待真实资源、
  failure/recovery=契约模拟）；绝不伪造 ``EXECUTED`` / ``DEPLOYED_PRODUCTION`` / ``GO``；
- 凭据引用**绝不**持有明文 Secret / Token / 私钥 / 含密码 DSN。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from agents.external_staging_qualification.models import (
    EXTERNAL_STAGING_ENVIRONMENT,
    ExternalStagingEnvironmentIdentity,
    ExternalStagingResourceRegistry,
    GateStatus,
    ResourceQualificationStatus,
    ResourceType,
    RESOURCE_TYPE_ORDER,
    RuntimeHealthStatus,
)

# 本阶段语义态常量（仅在 External Staging 范畴内，禁止 Production 语义）。
EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE = (
    "EXTERNAL_STAGING_EXECUTION_QUALIFICATION_BUILT_NO_GO"
)


class ExecutionStepKind(str, Enum):
    """执行步种类（Task 15-24 编排）。"""

    PREFLIGHT = "preflight"
    DEPLOY = "deploy"
    RUNTIME = "runtime"
    ISOLATION = "isolation"
    E2E = "e2e"
    FAILURE = "failure"
    RECOVERY = "recovery"
    ROLLBACK = "rollback"
    EVIDENCE = "evidence"
    GATE = "gate"


class ExecutionStepStatus(str, Enum):
    """执行步状态（fail-closed，禁止 EXECUTED/DEPLOYED_PRODUCTION/GO/APPROVED）。

    - ``PLAN_ONLY``：仅生成计划，未真实执行（deploy / rollback）。
    - ``CONTRACT_TEST_PASSED``：对契约的模拟执行通过（fake adapter），无真实资源。
    - ``PENDING_EXTERNAL_STAGING_RESOURCE``：等待 Track B 真实资源/人工。
    - ``BLOCKED`` / ``FAILED``：失败/阻断。
    """

    NOT_STARTED = "not_started"
    PLAN_ONLY = "plan_only"
    CONTRACT_TEST_PASSED = "contract_test_passed"
    PENDING_EXTERNAL_STAGING_RESOURCE = "pending_external_staging_resource"
    BLOCKED = "blocked"
    FAILED = "failed"

    @property
    def is_real_execution(self) -> bool:
        """本阶段任何步都不得声明真实执行。plan_only / contract_test 均非真实执行。"""

        return False


# 被明确禁止的执行态（任何步均不得落入）。
_FORBIDDEN_STEP_STATES = frozenset(
    {
        "executed",
        "executed_go",
        "deployed_production",
        "go",
        "approved",
        "production_ready",
        "PRODUCTION_GO",
        "APPROVED",
    }
)


@dataclass
class ExecutionStep:
    """单执行步结果。"""

    kind: ExecutionStepKind
    status: ExecutionStepStatus
    detail: str = ""
    evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    last_checked_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "status": self.status.value,
            "detail": self.detail,
            "evidence_refs": list(self.evidence_refs),
            "last_checked_at": self.last_checked_at,
            "is_real_execution": False,
            "contains_real_secret": False,
        }


@dataclass
class ExecutionPlan:
    """执行计划（编排产物）。"""

    environment: str
    steps: tuple[ExecutionStep, ...] = field(default_factory=tuple)
    production_activation_prohibited: bool = True
    engineering_enabled: bool = False

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for s in self.steps:
            by_status[s.status.value] = by_status.get(s.status.value, 0) + 1
        return {
            "environment": self.environment,
            "total_steps": len(self.steps),
            "by_status": by_status,
            "any_real_execution": False,
            "production_activation_prohibited": self.production_activation_prohibited,
            "engineering_enabled": self.engineering_enabled,
        }


def build_default_execution_plan() -> ExecutionPlan:
    """建立默认执行计划（plan-only / contract-test / 待真实资源，诚实不伪造）。

    Track B 真实资源 PENDING → deploy=plan-only、runtime/isolation/e2e/evidence=
    PENDING、failure/recovery=契约模拟通过、rollback=plan-only、gate=PENDING。
    """

    now = _dt.datetime.now(_dt.timezone.utc).isoformat()
    steps = [
        ExecutionStep(
            ExecutionStepKind.PREFLIGHT,
            ExecutionStepStatus.CONTRACT_TEST_PASSED,
            "预检引擎运行：分支/身份/凭据安全/资源 pending 核验通过（plan-only 安全）。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.DEPLOY,
            ExecutionStepStatus.PLAN_ONLY,
            "部署计划已生成（plan-only），未真实部署；真实 External Staging 部署需 Track B 资源。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.RUNTIME,
            ExecutionStepStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            "运行时健康未接入（Track B 资源 PENDING）；不伪造 HEALTHY。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.ISOLATION,
            ExecutionStepStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            "跨环境隔离 0/9 待证（Track B 资源 PENDING）。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.E2E,
            ExecutionStepStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            "端到端执行验证待真实资源（Track B PENDING）；契约测试通过但不宣称真实执行。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.FAILURE,
            ExecutionStepStatus.CONTRACT_TEST_PASSED,
            "故障注入为契约模拟（fake adapter），无真实资源；不宣称真实故障。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.RECOVERY,
            ExecutionStepStatus.CONTRACT_TEST_PASSED,
            "恢复演练为契约模拟（fake adapter），无真实资源。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.ROLLBACK,
            ExecutionStepStatus.PLAN_ONLY,
            "回滚计划已生成（plan-only），未真实回滚；真实回滚需 Track B 资源与人工确认。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.EVIDENCE,
            ExecutionStepStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            "证据链待真实执行回填（Track B PENDING）；当前仅 plan/contract 证据。",
            last_checked_at=now,
        ),
        ExecutionStep(
            ExecutionStepKind.GATE,
            ExecutionStepStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            "资格闸门维持 PENDING_EXTERNAL_STAGING_RESOURCE；不越级至 READY/GO。",
            last_checked_at=now,
        ),
    ]
    return ExecutionPlan(
        environment=EXTERNAL_STAGING_ENVIRONMENT.value,
        steps=tuple(steps),
    )


def assert_not_forbidden_step_state(state: str) -> None:
    """断言执行态不落入禁止态（fail-closed）。"""

    if state in _FORBIDDEN_STEP_STATES:
        raise ExternalStagingExecutionError(
            f"执行步状态 {state!r} 落入禁止态（EXECUTED/DEPLOYED_PRODUCTION/GO/APPROVED 等），拒绝。"
        )


class ExternalStagingExecutionError(ValueError):
    """外部预生产执行层违例。"""


__all__ = [
    "EXTERNAL_STAGING_ENVIRONMENT",
    "EXTERNAL_STAGING_EXECUTION_TERMINAL_STATE",
    "ExecutionStepKind",
    "ExecutionStepStatus",
    "ExecutionStep",
    "ExecutionPlan",
    "build_default_execution_plan",
    "assert_not_forbidden_step_state",
    "ExternalStagingExecutionError",
    # 再导出常用 qualification 契约，供同层子模块直接引用
    "ExternalStagingEnvironmentIdentity",
    "ExternalStagingResourceRegistry",
    "GateStatus",
    "ResourceType",
    "RESOURCE_TYPE_ORDER",
    "ResourceQualificationStatus",
    "RuntimeHealthStatus",
]
