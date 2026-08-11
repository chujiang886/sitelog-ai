"""Phase 3.9.1 预生产验证与灾难恢复演练层 —— 数据模型（T1–T5）。

全部为**只读验证 / 模拟演练 / 恢复校验结构**：本模块不持有任何生产状态，不写入
任何密钥，不执行任何真实部署 / 真实授权 / 真实数据覆盖。所有 ``deployed`` /
``real_deploy_performed`` / ``executed_for_real`` / ``real_data_overwritten`` /
``real_data_touched`` 类放行字段恒为 ``False``，结论只能源于真实人工（主理人 /
生产负责人）线下采纳。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ValidationDomain(str, Enum):
    """预生产验证六域（T1）。"""

    ENVIRONMENT = "environment"
    DATABASE = "database"
    STORAGE = "storage"
    DEPENDENCY = "dependency"
    SECURITY = "security"
    ROLLBACK = "rollback"


@dataclass(frozen=True)
class CheckResult:
    """单条验证事实（只描述，不决策）。"""

    name: str
    passed: bool
    detail: str = ""
    severity: str = "info"  # info | warn | critical

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class StagingValidationChecklist:
    """T1 预生产验证检查清单：六域验证，只检查、不自动放行。"""

    org_id: str
    generated_at: str
    domains: Dict[str, List[CheckResult]]
    summary_passed: int
    summary_total: int
    deployed: bool = False  # 恒 False：演练层绝不进入部署态
    note: str = "STAGING_ONLY: 仅验证，不自动放行；生产放行须主理人线下决策"

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "domains": {
                k: [c.to_dict() for c in v] for k, v in self.domains.items()
            },
            "summary_passed": self.summary_passed,
            "summary_total": self.summary_total,
            "deployed": self.deployed,
            "note": self.note,
        }


@dataclass(frozen=True)
class SimulationStep:
    """模拟部署单步：仅描述动作与预期结果，标记 simulated。"""

    order: int
    action: str
    target: str
    expected_result: str
    simulated: bool = True  # 恒 True：所有步骤均为模拟

    def to_dict(self) -> Dict[str, object]:
        return {
            "order": self.order,
            "action": self.action,
            "target": self.target,
            "expected_result": self.expected_result,
            "simulated": self.simulated,
        }


@dataclass(frozen=True)
class DependencyCheck:
    """依赖检查单条：仅记录可用性事实。"""

    name: str
    required: bool
    available: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "name": self.name,
            "required": self.required,
            "available": self.available,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class FailurePoint:
    """失败点：触发条件 / 影响 / 恢复路径（仅记录，不执行）。"""

    scenario: str
    trigger: str
    impact: str
    recovery_path: str

    def to_dict(self) -> Dict[str, object]:
        return {
            "scenario": self.scenario,
            "trigger": self.trigger,
            "impact": self.impact,
            "recovery_path": self.recovery_path,
        }


@dataclass(frozen=True)
class DeploymentSimulationReport:
    """T2 部署模拟报告：模拟步骤 / 依赖检查 / 失败点，禁止真实部署。"""

    org_id: str
    generated_at: str
    steps: List[SimulationStep]
    dependency_checks: List[DependencyCheck]
    failure_points: List[FailurePoint]
    real_deploy_performed: bool = False  # 恒 False：仅模拟
    note: str = (
        "SIMULATION_ONLY: 禁止真实部署；本报告仅描述模拟步骤、依赖检查与失败点"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "steps": [s.to_dict() for s in self.steps],
            "dependency_checks": [d.to_dict() for d in self.dependency_checks],
            "failure_points": [f.to_dict() for f in self.failure_points],
            "real_deploy_performed": self.real_deploy_performed,
            "note": self.note,
        }


@dataclass(frozen=True)
class RollbackDrillStep:
    """回滚演练单步：可逆优先。"""

    order: int
    action: str
    target: str
    reversible: bool = True

    def to_dict(self) -> Dict[str, object]:
        return {
            "order": self.order,
            "action": self.action,
            "target": self.target,
            "reversible": self.reversible,
        }


@dataclass(frozen=True)
class RollbackDrillReport:
    """T3 回滚演练报告：版本 / 配置 / 数据库回滚，只模拟、不真实执行。"""

    org_id: str
    generated_at: str
    version_rollback: List[RollbackDrillStep] = field(default_factory=list)
    config_rollback: List[RollbackDrillStep] = field(default_factory=list)
    database_rollback: List[RollbackDrillStep] = field(default_factory=list)
    executed_for_real: bool = False  # 恒 False：仅演练
    owner_role: str = "production-owner"
    note: str = "DRILL_ONLY: 仅模拟演练，不真实执行任何回滚动作"

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "version_rollback": [s.to_dict() for s in self.version_rollback],
            "config_rollback": [s.to_dict() for s in self.config_rollback],
            "database_rollback": [s.to_dict() for s in self.database_rollback],
            "executed_for_real": self.executed_for_real,
            "owner_role": self.owner_role,
            "note": self.note,
        }


@dataclass(frozen=True)
class BackupValidation:
    """备份校验单条：仅确认备份存在与位置，不读取/覆盖真实数据。"""

    component: str
    backup_present: bool
    backup_location: str
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "component": self.component,
            "backup_present": self.backup_present,
            "backup_location": self.backup_location,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RestoreValidation:
    """恢复校验单条：仅模拟恢复，标记 restore_simulated。"""

    component: str
    restore_simulated: bool
    restore_target: str
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "component": self.component,
            "restore_simulated": self.restore_simulated,
            "restore_target": self.restore_target,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class IntegrityValidation:
    """完整性校验单条：仅校验 checksum，不改动真实数据。"""

    component: str
    checksum_verified: bool
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "component": self.component,
            "checksum_verified": self.checksum_verified,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class RecoveryValidation:
    """T4 恢复校验：备份 / 恢复 / 完整性，禁止覆盖真实数据。"""

    org_id: str
    generated_at: str
    backups: List[BackupValidation] = field(default_factory=list)
    restores: List[RestoreValidation] = field(default_factory=list)
    integrity_checks: List[IntegrityValidation] = field(default_factory=list)
    real_data_overwritten: bool = False  # 恒 False：绝不覆盖真实数据
    note: str = (
        "VALIDATION_ONLY: 仅校验备份/恢复/完整性，绝不覆盖真实数据"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "backups": [b.to_dict() for b in self.backups],
            "restores": [r.to_dict() for r in self.restores],
            "integrity_checks": [i.to_dict() for i in self.integrity_checks],
            "real_data_overwritten": self.real_data_overwritten,
            "note": self.note,
        }


@dataclass(frozen=True)
class FailureScenario:
    """故障场景单条：场景 / 触发 / 影响 / 恢复路径 / 严重度，不触碰真实数据。"""

    id: str
    title: str
    category: str
    trigger: str
    impact: str
    recovery_path: str
    severity: str = "medium"  # low | medium | high | critical
    real_data_touched: bool = False  # 恒 False：仅记录，不触碰真实数据

    def to_dict(self) -> Dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "trigger": self.trigger,
            "impact": self.impact,
            "recovery_path": self.recovery_path,
            "severity": self.severity,
            "real_data_touched": self.real_data_touched,
        }


@dataclass(frozen=True)
class FailureScenarioCatalog:
    """T5 故障场景目录：场景 / 影响 / 恢复路径，仅记录、不触碰真实数据。"""

    org_id: str
    generated_at: str
    scenarios: List[FailureScenario] = field(default_factory=list)
    real_data_touched: bool = False  # 恒 False：仅登记
    note: str = (
        "CATALOG_ONLY: 仅记录故障场景/影响/恢复路径，不触碰真实数据"
    )

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "scenarios": [s.to_dict() for s in self.scenarios],
            "real_data_touched": self.real_data_touched,
            "note": self.note,
        }
