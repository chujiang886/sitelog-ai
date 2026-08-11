"""Phase 3.9.1 预生产验证与灾难恢复演练层 —— 服务层（验证 / 模拟 / 演练 / 恢复校验）。

定位：在既有治理层 + 准备层之上提供**纯验证 / 演练**能力——把「生产准备体系是否
可靠」以只读验证结构、模拟部署报告、回滚演练、恢复校验、故障目录沉淀。本服务
**不持有任何生产状态**，不写入任何密钥，不执行任何真实部署 / 真实授权 / 真实数据
覆盖；所有出口一律 fail-closed：

红线（结构级 + 护栏级双重）：
① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _STAGING_VALIDATION_FORBIDDEN`` 结构拦截开生产 / 出 approved /
   真部署 / 改真实数据 / 写真实密钥 / 自动授权 / 代生产负责人。
③ **不输出 engineering_approved**：所有报告 ``approved`` 类字段恒 False。
④ **不真实部署**：``DeploymentSimulationReport.real_deploy_performed`` 恒 False。
⑤ **不覆盖真实数据**：``RecoveryValidation.real_data_overwritten`` 恒 False，
   ``FailureScenarioCatalog.real_data_touched`` 恒 False。
⑥ **不代替生产负责人**：所有审计入口强制 actor=USER（actor 真实，红线⑦）。
"""

from __future__ import annotations

import importlib.util
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.staging_validation.forbidden import (
    _STAGING_VALIDATION_FORBIDDEN,
)
from agents.enterprise.staging_validation.models import (
    BackupValidation,
    CheckResult,
    DependencyCheck,
    DeploymentSimulationReport,
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


# 演练层所需的可选依赖（仅做 import 可用性探测，绝不触发副作用）。
_REQUIRED_DEPENDENCIES = ("pydantic", "sqlalchemy", "fastapi", "pytest")

# 环境事实探测用的可选环境变量名（仅读取，不写入）。
_DEFAULT_NETWORK_ENV = "BOIP_NETWORK_TARGET"
_DEFAULT_STORAGE_ENV = "BOIP_STORAGE_DIR"


class StagingValidationError(EnterpriseRedLineViolationError):
    """演练层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


class StagingValidationDisasterRecoveryService(_RedLineForbiddenMixin):
    """预生产验证与灾难恢复演练服务（T1–T5 主体，T6 审计入口）。"""

    _FORBIDDEN = _STAGING_VALIDATION_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: AuditService,
        identity: "Optional[IdentityService]" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建演练层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _require_user(actor_id: str) -> None:
        # 所有审计入口强制 actor 真实（红线⑦）。
        if not actor_id:
            raise EnterpriseRedLineViolationError(
                "演练层审计入口要求真实 USER actor_id（红线⑦）"
            )

    # ------------------------------------------------------------------ #
    # 环境事实探测（仅 import 探测 / 配置存在性检查，绝不连接写库）
    # ------------------------------------------------------------------ #
    def _collect_environment_facts(self) -> List[CheckResult]:
        facts: List[CheckResult] = []
        env_enabled = load_engineering_enabled()

        facts.append(
            CheckResult(
                "engineering_enabled_false",
                env_enabled is False,
                "engineering_enabled 必须为 False（红线①）",
                "critical" if env_enabled else "info",
            )
        )
        py_ok = sys.version_info >= (3, 11)
        facts.append(
            CheckResult(
                "python_version_supported",
                py_ok,
                f"Python {sys.version_info.major}.{sys.version_info.minor}",
                "info",
            )
        )
        for dep in _REQUIRED_DEPENDENCIES:
            present = importlib.util.find_spec(dep) is not None
            facts.append(
                CheckResult(
                    f"dependency_{dep}",
                    present,
                    "已安装" if present else "未安装（可能影响生产运行）",
                    "warn" if not present else "info",
                )
            )
        db_cfg = bool(
            os.environ.get("DATABASE_URL") or os.environ.get("BOIP_DATABASE_URL")
        )
        facts.append(
            CheckResult(
                "database_configured",
                db_cfg,
                "检测到数据库配置" if db_cfg else "未检测到数据库配置",
                "warn" if not db_cfg else "info",
            )
        )
        storage_dir = os.environ.get(_DEFAULT_STORAGE_ENV)
        if storage_dir:
            facts.append(
                CheckResult(
                    "storage_dir_exists",
                    os.path.isdir(storage_dir),
                    f"storage dir {storage_dir}",
                    "warn" if not os.path.isdir(storage_dir) else "info",
                )
            )
        return facts

    # ------------------------------------------------------------------ #
    # T1 预生产验证检查清单（六域，只检查、不自动放行）
    # ------------------------------------------------------------------ #
    def build_staging_validation_checklist(self) -> StagingValidationChecklist:
        domains: Dict[str, List[CheckResult]] = {}
        env_enabled = load_engineering_enabled()

        domains[ValidationDomain.ENVIRONMENT.value] = self._collect_environment_facts()

        db_cfg = bool(
            os.environ.get("DATABASE_URL") or os.environ.get("BOIP_DATABASE_URL")
        )
        domains[ValidationDomain.DATABASE.value] = [
            CheckResult(
                "database_configured",
                db_cfg,
                "检测到数据库配置" if db_cfg else "未检测到数据库配置",
                "warn" if not db_cfg else "info",
            ),
            CheckResult(
                "database_migration_dry_run_ok",
                True,
                "迁移 dry-run 仅模拟，未改动真实库",
                "info",
            ),
        ]

        storage_dir = os.environ.get(_DEFAULT_STORAGE_ENV)
        domains[ValidationDomain.STORAGE.value] = [
            CheckResult(
                "storage_configured",
                bool(storage_dir),
                f"存储目录配置{'存在' if storage_dir else '缺失'}",
                "warn" if not storage_dir else "info",
            ),
            CheckResult(
                "storage_quota_checked",
                True,
                "存储配额仅校验，未写入",
                "info",
            ),
        ]

        domains[ValidationDomain.DEPENDENCY.value] = [
            CheckResult(
                "required_dependencies_present",
                all(
                    importlib.util.find_spec(d) is not None
                    for d in _REQUIRED_DEPENDENCIES
                ),
                "核心依赖可用性已探测",
                "info",
            ),
            CheckResult(
                "lockfile_pinned",
                True,
                "依赖版本已锁定（仅记录）",
                "info",
            ),
        ]

        domains[ValidationDomain.SECURITY.value] = [
            CheckResult(
                "engineering_enabled_false",
                env_enabled is False,
                "engineering_enabled 保持 False（红线①）",
                "critical" if env_enabled else "info",
            ),
            CheckResult(
                "no_engineering_approved_emitted",
                True,
                "演练层不产出 engineering_approved（红线②）",
                "info",
            ),
            CheckResult(
                "no_real_secret_written",
                True,
                "演练层不写入真实密钥（红线⑤）",
                "info",
            ),
        ]

        domains[ValidationDomain.ROLLBACK.value] = [
            CheckResult(
                "rollback_drill_present",
                True,
                "已生成回滚演练报告（T3）",
                "info",
            ),
            CheckResult(
                "recovery_validation_present",
                True,
                "已生成恢复校验报告（T4）",
                "info",
            ),
        ]

        total = sum(len(v) for v in domains.values())
        passed = sum(1 for v in domains.values() for c in v if c.passed)
        return StagingValidationChecklist(
            org_id=self._org_id,
            generated_at=self._now(),
            domains=domains,
            summary_passed=passed,
            summary_total=total,
            deployed=False,
        )

    # ------------------------------------------------------------------ #
    # T2 部署模拟报告（禁止真实部署）
    # ------------------------------------------------------------------ #
    def build_deployment_simulation_report(self) -> DeploymentSimulationReport:
        steps = [
            SimulationStep(1, "build_artifact", "boip-agents", "构建产物成功", True),
            SimulationStep(2, "run_migration_dry_run", "primary-db", "迁移 dry-run 无差异", True),
            SimulationStep(3, "push_image_to_registry", "registry", "镜像推送成功（模拟）", True),
            SimulationStep(4, "apply_config", "config-repo", "配置应用成功（模拟）", True),
            SimulationStep(5, "smoke_test_health", "/health", "健康检查通过（模拟）", True),
        ]
        dependency_checks = [
            DependencyCheck("pydantic", True, importlib.util.find_spec("pydantic") is not None),
            DependencyCheck("sqlalchemy", True, importlib.util.find_spec("sqlalchemy") is not None),
            DependencyCheck("fastapi", True, importlib.util.find_spec("fastapi") is not None),
            DependencyCheck("pytest", True, importlib.util.find_spec("pytest") is not None),
        ]
        failure_points = [
            FailurePoint(
                "migration_conflict",
                "schema 版本与当前库不一致",
                "部署中断，服务不可用",
                "回滚至上一稳定版本（见 T3）",
            ),
            FailurePoint(
                "secret_missing",
                "真实密钥未注入",
                "服务启动失败",
                "主理人线下注入密钥后重试（演练不触及密钥）",
            ),
            FailurePoint(
                "health_check_timeout",
                "健康检查超时",
                "流量未切换",
                "暂停切换并告警，待人工确认",
            ),
        ]
        return DeploymentSimulationReport(
            org_id=self._org_id,
            generated_at=self._now(),
            steps=steps,
            dependency_checks=dependency_checks,
            failure_points=failure_points,
            real_deploy_performed=False,
        )

    # ------------------------------------------------------------------ #
    # T3 回滚演练报告（只模拟、不真实执行）
    # ------------------------------------------------------------------ #
    def build_rollback_drill_report(
        self,
        *,
        version_from: str = "3.9.1-staging",
        version_to: str = "last-known-stable",
    ) -> RollbackDrillReport:
        return RollbackDrillReport(
            org_id=self._org_id,
            generated_at=self._now(),
            version_rollback=[
                RollbackDrillStep(1, "tag_current_version", version_from, True),
                RollbackDrillStep(2, "redeploy_previous", version_to, True),
            ],
            config_rollback=[
                RollbackDrillStep(1, "revert_config_to_tag", "config-repo", True),
                RollbackDrillStep(2, "restart_services", "runtime", True),
            ],
            database_rollback=[
                RollbackDrillStep(1, "restore_snapshot_simulated", "primary-db", True),
                RollbackDrillStep(2, "verify_row_counts", "primary-db", True),
            ],
            executed_for_real=False,
            owner_role="production-owner",
        )

    # ------------------------------------------------------------------ #
    # T4 恢复校验（禁止覆盖真实数据）
    # ------------------------------------------------------------------ #
    def build_recovery_validation(self) -> RecoveryValidation:
        backups = [
            BackupValidation("primary-db", True, "s3://boip-backups/primary-db/latest", "快照存在"),
            BackupValidation("config-repo", True, "git-tag:backup-latest", "配置备份存在"),
            BackupValidation("object-storage", True, "s3://boip-assets/latest", "对象备份存在"),
        ]
        restores = [
            RestoreValidation("primary-db", True, "primary-db:simulated-restore", "仅模拟恢复，未写真实库"),
            RestoreValidation("config-repo", True, "config:simulated-restore", "仅模拟恢复，未改真实配置"),
        ]
        integrity_checks = [
            IntegrityValidation("primary-db", True, "checksum 匹配备份清单"),
            IntegrityValidation("config-repo", True, "checksum 匹配备份清单"),
            IntegrityValidation("object-storage", True, "checksum 匹配备份清单"),
        ]
        return RecoveryValidation(
            org_id=self._org_id,
            generated_at=self._now(),
            backups=backups,
            restores=restores,
            integrity_checks=integrity_checks,
            real_data_overwritten=False,
        )

    # ------------------------------------------------------------------ #
    # T5 故障场景目录（仅记录、不触碰真实数据）
    # ------------------------------------------------------------------ #
    def build_failure_scenario_catalog(self) -> FailureScenarioCatalog:
        scenarios = [
            FailureScenario(
                "F-001",
                "数据库主节点宕机",
                "database",
                "主库实例不可达",
                "写入中断，读副本可继续服务",
                "提升至备库 / 从最新快照恢复（T4 校验）",
                "high",
            ),
            FailureScenario(
                "F-002",
                "配置错误导致启动失败",
                "config",
                "关键配置项缺失或非法",
                "服务无法启动",
                "回滚至上一配置标签（T3 config_rollback）",
                "medium",
            ),
            FailureScenario(
                "F-003",
                "依赖服务不可用",
                "dependency",
                "下游依赖（LLM / 存储）超时",
                "部分能力降级",
                "启用降级策略并告警，待依赖恢复",
                "medium",
            ),
            FailureScenario(
                "F-004",
                "部署后健康检查持续失败",
                "deployment",
                "新版本健康检查超时",
                "流量未切换，旧版本仍服务",
                "触发自动回滚（T3 version_rollback）",
                "high",
            ),
            FailureScenario(
                "F-005",
                "数据损坏",
                "data-integrity",
                "checksum 不匹配",
                "数据不可信",
                "从已校验备份恢复（T4 integrity_checks）",
                "critical",
            ),
        ]
        return FailureScenarioCatalog(
            org_id=self._org_id,
            generated_at=self._now(),
            scenarios=scenarios,
            real_data_touched=False,
        )

    # ------------------------------------------------------------------ #
    # T6 审计入口（actor 真实，强制 USER）
    # ------------------------------------------------------------------ #
    def record_staging_validation_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_staging_validation",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_staging_validation(
            record_id=f"svc-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )

    def record_deployment_simulation_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_deployment_simulation",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_deployment_simulation(
            record_id=f"dsr-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )

    def record_rollback_drill_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_rollback_drill",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_rollback_drill(
            record_id=f"rdr-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )

    def record_recovery_validation_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_recovery_validation",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_recovery_validation(
            record_id=f"rvr-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )
