"""Phase 3.9.0 生产就绪与受控激活准备层（包入口）。

本包是**纯准备**层，对外只暴露：

- 模型：``ProductionReadinessChecklist``（T1）/ ``ProductionDeploymentManifest``（T2）/
  ``EnvironmentValidationReport``（T3）/ ``PermissionInitializationPlan``（T4）/
  ``RollbackPlan``（T5）/ ``ActivationReviewPackage``（T6）；
- 服务：``ProductionReadinessPreparationService``（T1–T6 执行体 + T7 审计入口）；
- 结构级禁名集：``_PRODUCTION_READINESS_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何写生产状态 / 写真实密钥 / 真实授权 / 真实激活的能力——因为它们
根本不存在（红线①~⑥）。
"""

from agents.enterprise.production_readiness.forbidden import (
    _PRODUCTION_READINESS_EXTRA_FORBIDDEN,
    _PRODUCTION_READINESS_FORBIDDEN,
    PRODUCTION_READINESS_FORBIDDEN_COUNT,
)
from agents.enterprise.production_readiness.models import (
    ActivationReviewPackage,
    CheckResult,
    DeploymentManifestEntry,
    EnvironmentFact,
    EnvironmentValidationReport,
    PermissionInitializationPlan,
    PermissionPlanEntry,
    ProductionDeploymentManifest,
    ProductionReadinessChecklist,
    ReadinessDomain,
    RollbackPlan,
    RollbackStep,
)
from agents.enterprise.production_readiness.service import (
    ProductionReadinessError,
    ProductionReadinessPreparationService,
)

__all__ = [
    # 模型
    "ReadinessDomain",
    "CheckResult",
    "ProductionReadinessChecklist",
    "DeploymentManifestEntry",
    "ProductionDeploymentManifest",
    "EnvironmentFact",
    "EnvironmentValidationReport",
    "PermissionPlanEntry",
    "PermissionInitializationPlan",
    "RollbackStep",
    "RollbackPlan",
    "ActivationReviewPackage",
    # 服务
    "ProductionReadinessPreparationService",
    "ProductionReadinessError",
    # 红线取证
    "_PRODUCTION_READINESS_FORBIDDEN",
    "_PRODUCTION_READINESS_EXTRA_FORBIDDEN",
    "PRODUCTION_READINESS_FORBIDDEN_COUNT",
]
