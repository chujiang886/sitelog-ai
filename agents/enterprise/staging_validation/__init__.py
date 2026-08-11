"""Phase 3.9.1 预生产验证与灾难恢复演练层（包入口）。

本包是**纯验证 / 演练**层，对外只暴露：

- 模型：``StagingValidationChecklist``（T1）/ ``DeploymentSimulationReport``（T2）/
  ``RollbackDrillReport``（T3）/ ``RecoveryValidation``（T4）/
  ``FailureScenarioCatalog``（T5）；
- 服务：``StagingValidationDisasterRecoveryService``（T1–T5 执行体 + T6 审计入口）；
- 结构级禁名集：``_STAGING_VALIDATION_FORBIDDEN``（供测试与审计取证）。

本包**不导出**任何真实部署 / 真实数据覆盖 / 真实密钥写入 / 真实授权 /
代生产负责人的能力——因为它们根本不存在（红线①~⑦）。
"""

from agents.enterprise.staging_validation.forbidden import (
    _STAGING_VALIDATION_EXTRA_FORBIDDEN,
    _STAGING_VALIDATION_FORBIDDEN,
    STAGING_VALIDATION_FORBIDDEN_COUNT,
)
from agents.enterprise.staging_validation.models import (
    BackupValidation,
    CheckResult,
    DependencyCheck,
    FailurePoint,
    FailureScenario,
    FailureScenarioCatalog,
    IntegrityValidation,
    RecoveryValidation,
    RestoreValidation,
    RollbackDrillReport,
    RollbackDrillStep,
    SimulationStep,
    StagingValidationChecklist,
    ValidationDomain,
)
from agents.enterprise.staging_validation.service import (
    StagingValidationDisasterRecoveryService,
    StagingValidationError,
)

__all__ = [
    # 模型
    "ValidationDomain",
    "CheckResult",
    "StagingValidationChecklist",
    "SimulationStep",
    "DependencyCheck",
    "FailurePoint",
    "DeploymentSimulationReport",
    "RollbackDrillStep",
    "RollbackDrillReport",
    "BackupValidation",
    "RestoreValidation",
    "IntegrityValidation",
    "RecoveryValidation",
    "FailureScenario",
    "FailureScenarioCatalog",
    # 服务
    "StagingValidationDisasterRecoveryService",
    "StagingValidationError",
    # 红线取证
    "_STAGING_VALIDATION_FORBIDDEN",
    "_STAGING_VALIDATION_EXTRA_FORBIDDEN",
    "STAGING_VALIDATION_FORBIDDEN_COUNT",
]
