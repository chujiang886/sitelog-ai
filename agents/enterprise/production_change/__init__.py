"""Phase 3.9.7 企业生产变更管控平面（包入口）。

本包是**纯变更管控 / 仿真 / 证据包 / 候选 / 清单 / 回滚引用 / 中止策略**层，对外只暴露：

- 模型：``ChangeRequest``（T1）/ ``ChangePlan``（T2）/ ``ChangeWindow``（T3）/
  ``ChangePreflightResult``（T4）/ ``ChangeCheckpoint``（T5）/ ``ChangeAbortPolicy``（T6）/
  ``ChangeRollbackReference``（T7）/ ``PostChangeVerification``（T8）/ ``ChangeEvidence``（T9）/
  ``ChangeSimulationResult``（T23）/ ``FailureScenarioEvaluation``（T24）/
  ``ControlledChangePackage``（T25）/ ``ChangeDecisionDraft``（T9-决策）；
- 枚举：``ChangeExecutionMode``（禁 AI_AUTOMATIC）/ ``ChangeState``（禁 AUTO_EXECUTING /
  AUTO_COMPLETED / AI_APPROVED）/ ``ChangePreflightStatus`` / ``ChangeVerificationStatus`` /
  ``ChangeDecisionDraftStatus`` / ``ChangeSimulationOutcome``；
- 子域构建器：change_request / plan / window / preflight / checkpoint / abort_policy /
  rollback_reference / post_change / evidence / simulation / failure_scenarios / package；
- 服务：``ProductionChangeControlService``（T1–T9 / T23–T25 编排）；
- 权限边界：``ChangeOperation`` / ``require_change_operation`` / ``ChangePermissionBoundary``；
- 门禁：``check_change_control_invariants``（fail-closed 不变量校验）；
- API 契约 SSOT：``build_api_contract`` / ``write_api_contract_json``；
- 结构级禁名集：``_PRODUCTION_CHANGE_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何真实变更执行 / 真实部署 / 真实回滚 / 真实迁移 / 真实应用 / 真实密钥写入 /
真实授权 / 代生产负责人签署 / 宣布变更 GO 的能力——因为它们根本不存在（红线①~⑦/⑧/⑨/⑩）。
"""

from agents.enterprise.production_change.forbidden import (
    _PRODUCTION_CHANGE_EXTRA_FORBIDDEN,
    _PRODUCTION_CHANGE_FORBIDDEN,
    PRODUCTION_CHANGE_FORBIDDEN_COUNT,
)
from agents.enterprise.production_change.models import (
    ChangeAbortPolicy,
    ChangeCheckpoint,
    ChangeDecisionDraft,
    ChangeDecisionDraftStatus,
    ChangeExecutionMode,
    ChangeEvidence,
    ChangePlan,
    ChangePreflightResult,
    ChangePreflightStatus,
    ChangeRequest,
    ChangeRollbackReference,
    ChangeSimulationOutcome,
    ChangeSimulationResult,
    ChangeState,
    ChangeVerificationStatus,
    ChangeWindow,
    ControlledChangePackage,
    FailureScenarioEvaluation,
    PostChangeVerification,
)
from agents.enterprise.production_change.permission_boundary import (
    ChangeOperation,
    ChangePermissionBoundary,
    ChangePermissionBoundaryError,
    is_write_operation,
    require_change_operation,
)
from agents.enterprise.production_change.service import (
    ProductionChangeControlError,
    ProductionChangeControlService,
)
from agents.enterprise.production_change.validator import (
    check_change_control_invariants,
)

__all__ = [
    # 模型
    "ChangeRequest",
    "ChangePlan",
    "ChangeWindow",
    "ChangePreflightResult",
    "ChangeCheckpoint",
    "ChangeAbortPolicy",
    "ChangeRollbackReference",
    "PostChangeVerification",
    "ChangeEvidence",
    "ChangeSimulationResult",
    "FailureScenarioEvaluation",
    "ControlledChangePackage",
    "ChangeDecisionDraft",
    # 枚举
    "ChangeExecutionMode",
    "ChangeState",
    "ChangePreflightStatus",
    "ChangeVerificationStatus",
    "ChangeDecisionDraftStatus",
    "ChangeSimulationOutcome",
    # 权限边界
    "ChangeOperation",
    "ChangePermissionBoundary",
    "ChangePermissionBoundaryError",
    "is_write_operation",
    "require_change_operation",
    # 服务
    "ProductionChangeControlService",
    "ProductionChangeControlError",
    # 门禁
    "check_change_control_invariants",
    # 红线取证
    "_PRODUCTION_CHANGE_EXTRA_FORBIDDEN",
    "_PRODUCTION_CHANGE_FORBIDDEN",
    "PRODUCTION_CHANGE_FORBIDDEN_COUNT",
]
