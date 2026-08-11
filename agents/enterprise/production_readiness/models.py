"""Phase 3.9.0 生产就绪与受控激活准备层 —— 数据模型（T1–T6）。

全部为**只读计划 / 事实结构**：本模块不持有任何生产状态，不写入任何密钥，
不执行任何真实授权。所有 ``approved`` / ``granted`` 类字段恒为 ``False``，
放行与授权只能源于真实人工（主理人 / 生产负责人）线下决策。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ReadinessDomain(str, Enum):
    """生产就绪检查六域（T1）。"""

    ENVIRONMENT = "environment"
    DATABASE = "database"
    SECURITY = "security"
    PERMISSION = "permission"
    BACKUP = "backup"
    ROLLBACK = "rollback"


@dataclass(frozen=True)
class CheckResult:
    """单条检查事实（只描述，不决策）。"""

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
class ProductionReadinessChecklist:
    """T1 生产就绪检查清单：六域检查，只检查、不自动放行。"""

    org_id: str
    generated_at: str
    domains: Dict[str, List[CheckResult]]
    summary_passed: int
    summary_total: int
    auto_passed: bool = False  # 恒 False：准备层绝不自动放行
    note: str = "PREPARATION_ONLY: 仅检查，不自动放行；生产放行须主理人线下决策"

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "domains": {
                k: [c.to_dict() for c in v] for k, v in self.domains.items()
            },
            "summary_passed": self.summary_passed,
            "summary_total": self.summary_total,
            "auto_passed": self.auto_passed,
            "note": self.note,
        }


@dataclass(frozen=True)
class DeploymentManifestEntry:
    """部署清单单条：服务 / 版本 / 依赖 / 配置键名（值不出现）。"""

    service: str
    version: str
    dependencies: List[str] = field(default_factory=list)
    config_keys: List[str] = field(default_factory=list)  # 仅键名，值一律不出现
    env_requirements: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "service": self.service,
            "version": self.version,
            "dependencies": list(self.dependencies),
            "config_keys": list(self.config_keys),
            "env_requirements": list(self.env_requirements),
        }


@dataclass(frozen=True)
class ProductionDeploymentManifest:
    """T2 生产部署清单：记录服务 / 版本 / 依赖 / 配置 / 环境要求，禁止写真实密钥。"""

    org_id: str
    generated_at: str
    entries: List[DeploymentManifestEntry]
    secret_policy: str = "NO_REAL_SECRET_WRITTEN"
    secret_key_names: List[str] = field(default_factory=list)  # 仅键名占位
    note: str = "PREPARATION_ONLY: 禁止写入真实密钥；真实密钥由主理人线下注入"

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "entries": [e.to_dict() for e in self.entries],
            "secret_policy": self.secret_policy,
            "secret_key_names": list(self.secret_key_names),
            "note": self.note,
        }


@dataclass(frozen=True)
class EnvironmentFact:
    """单条环境事实（T3，只输出事实结果）。"""

    component: str  # python | database | storage | network | dependency
    fact: str
    status: str  # ok | warn | fail
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {
            "component": self.component,
            "fact": self.fact,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class EnvironmentValidationReport:
    """T3 环境校验报告：只输出事实结果，不做任何变更。"""

    org_id: str
    generated_at: str
    facts: List[EnvironmentFact]
    all_ok: bool  # 仅事实聚合，不用于放行
    note: str = "PREPARATION_ONLY: 仅输出事实结果，不做任何变更"

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "facts": [f.to_dict() for f in self.facts],
            "all_ok": self.all_ok,
            "note": self.note,
        }


@dataclass(frozen=True)
class PermissionPlanEntry:
    """权限计划单条：角色 / 权限 / 范围，仅标记 grant_required，不执行。"""

    role: str
    permissions: List[str] = field(default_factory=list)
    scope: str = ""
    grant_required: bool = True  # 仅标记，不执行

    def to_dict(self) -> Dict[str, object]:
        return {
            "role": self.role,
            "permissions": list(self.permissions),
            "scope": self.scope,
            "grant_required": self.grant_required,
        }


@dataclass(frozen=True)
class PermissionInitializationPlan:
    """T4 权限初始化计划：记录角色 / 权限 / 范围，禁止真实授权。"""

    org_id: str
    generated_at: str
    entries: List[PermissionPlanEntry]
    policy: str = "NO_REAL_GRANT"
    pending_human_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "entries": [e.to_dict() for e in self.entries],
            "policy": self.policy,
            "pending_human_actions": list(self.pending_human_actions),
        }


@dataclass(frozen=True)
class RollbackStep:
    """回滚单步：可逆优先。"""

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
class RollbackPlan:
    """T5 回滚计划：版本 / 数据库 / 配置 / 恢复步骤。"""

    version_from: str
    version_to: str
    db_steps: List[RollbackStep] = field(default_factory=list)
    config_steps: List[RollbackStep] = field(default_factory=list)
    recovery_steps: List[RollbackStep] = field(default_factory=list)
    estimated_downtime: str = ""
    owner_role: str = "production-owner"

    def to_dict(self) -> Dict[str, object]:
        return {
            "version_from": self.version_from,
            "version_to": self.version_to,
            "db_steps": [s.to_dict() for s in self.db_steps],
            "config_steps": [s.to_dict() for s in self.config_steps],
            "recovery_steps": [s.to_dict() for s in self.recovery_steps],
            "estimated_downtime": self.estimated_downtime,
            "owner_role": self.owner_role,
        }


@dataclass(frozen=True)
class ActivationReviewPackage:
    """T6 激活评审包：聚合 T1–T5 + 测试结果 + 安全检查 + 风险列表，禁止自动批准。"""

    org_id: str
    generated_at: str
    checklist_ref: str
    manifest_ref: str
    env_report_ref: str
    permission_plan_ref: str
    rollback_plan_ref: str
    test_results_ref: str
    security_checks: List[str] = field(default_factory=list)
    deployment_status: str = "PREPARED_NOT_DEPLOYED"
    risk_list: List[str] = field(default_factory=list)
    approved: bool = False  # 恒 False：仅真实人工可批准
    signature_required: str = "HUMAN_PRODUCTION_OWNER"
    pending_human_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "org_id": self.org_id,
            "generated_at": self.generated_at,
            "checklist_ref": self.checklist_ref,
            "manifest_ref": self.manifest_ref,
            "env_report_ref": self.env_report_ref,
            "permission_plan_ref": self.permission_plan_ref,
            "rollback_plan_ref": self.rollback_plan_ref,
            "test_results_ref": self.test_results_ref,
            "security_checks": list(self.security_checks),
            "deployment_status": self.deployment_status,
            "risk_list": list(self.risk_list),
            "approved": self.approved,
            "signature_required": self.signature_required,
            "pending_human_actions": list(self.pending_human_actions),
        }
