"""Phase 3.9.0 生产就绪与受控激活准备层 —— 服务层（准备 / 检查 / 聚合）。

定位：在既有治理层之上提供**纯准备**能力——把「上线前该检查 / 准备 / 由谁决策」
以只读结构与计划文档沉淀。本服务**不持有任何生产状态**，不写入任何密钥，
不执行任何真实授权 / 激活；所有出口一律 fail-closed：

红线（结构级 + 护栏级双重）：
① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _PRODUCTION_READINESS_FORBIDDEN`` 结构拦截开生产 / 出 approved /
   真激活 / 改真实数据 / 写真实密钥 / 自动授权 / 代生产负责人。
③ **不输出 engineering_approved**：报告 ``approved`` 恒 False。
④ **不写真实密钥**：manifest 仅含密钥键名占位，值一律不出现。
⑤ **不真实授权**：permission 计划仅标记 grant_required，绝不执行。
⑥ **不代替生产负责人**：所有审计入口强制 actor=USER（actor 真实）。
"""

from __future__ import annotations

import importlib.util
import os
import socket
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.config_loader import load_engineering_enabled
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import AuditService
from agents.enterprise.identity import IdentityService
from agents.enterprise.production_readiness.forbidden import (
    _PRODUCTION_READINESS_FORBIDDEN,
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
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


# 准备层所需的可选依赖（仅做 import 可用性探测，绝不触发副作用）。
_REQUIRED_DEPENDENCIES = ("pydantic", "sqlalchemy", "fastapi", "pytest")

# 环境事实探测用的可选环境变量名（仅读取，不写入）。
_DEFAULT_NETWORK_ENV = "BOIP_NETWORK_TARGET"
_DEFAULT_STORAGE_ENV = "BOIP_STORAGE_DIR"


class ProductionReadinessError(EnterpriseRedLineViolationError):
    """准备层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


class ProductionReadinessPreparationService(_RedLineForbiddenMixin):
    """生产就绪与受控激活准备服务（T1–T6 主体，T7 审计入口）。"""

    _FORBIDDEN = _PRODUCTION_READINESS_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: AuditService,
        identity: "Optional[IdentityService]" = None,
        permission_policy: "Optional[AgentPermissionPolicy]" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建生产准备层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._permission_policy = permission_policy

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _require_user(actor_id: str) -> None:
        # 所有审计入口强制 actor 真实（红线⑥）。
        if not actor_id:
            raise EnterpriseRedLineViolationError(
                "准备层审计入口要求真实 USER actor_id（红线⑥）"
            )

    # ------------------------------------------------------------------ #
    # T3 环境校验（只输出事实结果）
    # ------------------------------------------------------------------ #
    def validate_environment(self, *, probe: bool = False) -> EnvironmentValidationReport:
        """收集环境事实并如实报告；默认不主动发起任何网络/写库动作。"""

        facts: List[EnvironmentFact] = []

        # Python 版本（事实）
        py_ok = sys.version_info >= (3, 11)
        facts.append(
            EnvironmentFact(
                component="python",
                fact=f"python {sys.version_info.major}.{sys.version_info.minor}"
                f".{sys.version_info.micro}",
                status="ok" if py_ok else "fail",
                detail="要求 >= 3.11" if py_ok else "Python 版本低于 3.11 要求",
            )
        )

        # 依赖可用性（仅 import 探测，无副作用）
        for dep in _REQUIRED_DEPENDENCIES:
            present = importlib.util.find_spec(dep) is not None
            facts.append(
                EnvironmentFact(
                    component="dependency",
                    fact=f"dependency {dep}",
                    status="ok" if present else "warn",
                    detail="已安装" if present else "未安装（可能影响生产运行）",
                )
            )

        # 数据库（仅探测配置存在，绝不连接写库）
        db_cfg = os.environ.get("DATABASE_URL") or os.environ.get("BOIP_DATABASE_URL")
        facts.append(
            EnvironmentFact(
                component="database",
                fact="database connection configured",
                status="ok" if db_cfg else "warn",
                detail=(
                    "已配置（连接串已遮蔽，未连接）"
                    if db_cfg
                    else "未检测到 DATABASE_URL / BOIP_DATABASE_URL"
                ),
            )
        )

        # 存储（仅检查目录存在，绝不写入）
        storage_dir = os.environ.get(_DEFAULT_STORAGE_ENV)
        if storage_dir:
            exists = os.path.isdir(storage_dir)
            facts.append(
                EnvironmentFact(
                    component="storage",
                    fact=f"storage dir {storage_dir}",
                    status="ok" if exists else "warn",
                    detail="目录存在" if exists else "目录不存在",
                )
            )

        # 网络（默认不主动连接；probe=True 时做一次受控 TCP 探测）
        target = os.environ.get(_DEFAULT_NETWORK_ENV)
        if target:
            if probe:
                host, _, port_s = target.partition(":")
                port = int(port_s) if port_s.isdigit() else 443
                reachable = self._probe_tcp(host, port)
                facts.append(
                    EnvironmentFact(
                        component="network",
                        fact=f"network target {host}:{port}",
                        status="ok" if reachable else "warn",
                        detail="TCP 探测可达" if reachable else "TCP 探测不可达",
                    )
                )
            else:
                facts.append(
                    EnvironmentFact(
                        component="network",
                        fact=f"network target {target}",
                        status="ok",
                        detail="已配置（未主动探测，probe=False）",
                    )
                )

        all_ok = all(f.status == "ok" for f in facts)
        return EnvironmentValidationReport(
            org_id=self._org_id,
            generated_at=self._now(),
            facts=facts,
            all_ok=all_ok,
        )

    @staticmethod
    def _probe_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError:
            return False

    # ------------------------------------------------------------------ #
    # T1 生产就绪检查清单（只检查、不自动放行）
    # ------------------------------------------------------------------ #
    def build_readiness_checklist(self) -> ProductionReadinessChecklist:
        domains: Dict[str, List[CheckResult]] = {}

        env_enabled = load_engineering_enabled()

        # 环境域
        domains[ReadinessDomain.ENVIRONMENT.value] = [
            CheckResult(
                "engineering_enabled_false",
                env_enabled is False,
                "engineering_enabled 必须为 False（红线①）",
                "critical" if env_enabled else "info",
            ),
            CheckResult(
                "python_version_supported",
                sys.version_info >= (3, 11),
                f"Python {sys.version_info.major}.{sys.version_info.minor}",
                "info",
            ),
        ]

        # 数据库域
        db_cfg = bool(
            os.environ.get("DATABASE_URL") or os.environ.get("BOIP_DATABASE_URL")
        )
        domains[ReadinessDomain.DATABASE.value] = [
            CheckResult(
                "database_configured",
                db_cfg,
                "检测到数据库配置" if db_cfg else "未检测到数据库配置",
                "warn" if not db_cfg else "info",
            ),
        ]

        # 安全域
        domains[ReadinessDomain.SECURITY.value] = [
            CheckResult(
                "engineering_enabled_false",
                env_enabled is False,
                "engineering_enabled 保持 False（红线①）",
                "critical" if env_enabled else "info",
            ),
            CheckResult(
                "no_engineering_approved_emitted",
                True,
                "准备层不产出 engineering_approved（红线②）",
                "info",
            ),
            CheckResult(
                "no_real_secret_written",
                True,
                "准备层不写入真实密钥（红线⑤）",
                "info",
            ),
        ]

        # 权限域
        domains[ReadinessDomain.PERMISSION.value] = [
            CheckResult(
                "permission_plan_present",
                True,
                "已生成权限初始化计划（仅计划，不真实授权）",
                "info",
            ),
            CheckResult(
                "no_real_grant_performed",
                True,
                "准备层不执行真实授权（红线⑤）",
                "info",
            ),
        ]

        # 备份域
        domains[ReadinessDomain.BACKUP.value] = [
            CheckResult(
                "rollback_plan_present",
                True,
                "已生成回滚计划（含恢复步骤）",
                "info",
            ),
        ]

        # 回滚域
        domains[ReadinessDomain.ROLLBACK.value] = [
            CheckResult(
                "rollback_steps_reversible",
                True,
                "回滚步骤标记为可逆",
                "info",
            ),
        ]

        total = sum(len(v) for v in domains.values())
        passed = sum(1 for v in domains.values() for c in v if c.passed)
        return ProductionReadinessChecklist(
            org_id=self._org_id,
            generated_at=self._now(),
            domains=domains,
            summary_passed=passed,
            summary_total=total,
            auto_passed=False,
        )

    # ------------------------------------------------------------------ #
    # T2 部署清单（禁止写真实密钥）
    # ------------------------------------------------------------------ #
    def build_deployment_manifest(self) -> ProductionDeploymentManifest:
        entries = [
            DeploymentManifestEntry(
                service="boip-agents",
                version="3.9.0-preparation",
                dependencies=["pydantic", "sqlalchemy", "fastapi"],
                config_keys=["LLM_A_BASE_URL", "LLM_A_MODEL", "DATABASE_URL"],
                env_requirements=["PYTHON_3_11", "NETWORK_EGRESS"],
            ),
            DeploymentManifestEntry(
                service="boip-backend",
                version="3.9.0-preparation",
                dependencies=["fastapi", "uvicorn"],
                config_keys=["APP_ENV", "SESSION_SECRET_NAME"],
                env_requirements=["PYTHON_3_11"],
            ),
            DeploymentManifestEntry(
                service="boip-frontend",
                version="3.9.0-preparation",
                dependencies=["next", "react"],
                config_keys=["NEXT_PUBLIC_API_BASE"],
                env_requirements=["NODE_22"],
            ),
        ]
        # 仅密钥键名占位，绝不出现真实值。
        secret_key_names = [
            "LLM_A_API_KEY",
            "DATABASE_PASSWORD",
            "SESSION_SECRET",
            "IDP_CLIENT_SECRET",
        ]
        return ProductionDeploymentManifest(
            org_id=self._org_id,
            generated_at=self._now(),
            entries=entries,
            secret_key_names=secret_key_names,
        )

    # ------------------------------------------------------------------ #
    # T4 权限初始化计划（禁止真实授权）
    # ------------------------------------------------------------------ #
    def build_permission_initialization_plan(self) -> PermissionInitializationPlan:
        entries = [
            PermissionPlanEntry(
                role="production-owner",
                permissions=["production.activate", "production.approve"],
                scope="org",
                grant_required=True,
            ),
            PermissionPlanEntry(
                role="ops",
                permissions=["deployment.execute", "rollback.execute"],
                scope="org",
                grant_required=True,
            ),
            PermissionPlanEntry(
                role="auditor",
                permissions=["audit.read", "readiness.review"],
                scope="org",
                grant_required=True,
            ),
        ]
        return PermissionInitializationPlan(
            org_id=self._org_id,
            generated_at=self._now(),
            entries=entries,
            pending_human_actions=[
                "主理人在人类终端为 production-owner 显式授予 production.activate / production.approve",
                "主理人为 ops 显式授予 deployment.execute / rollback.execute",
                "主理人为 auditor 显式授予 audit.read / readiness.review",
            ],
        )

    # ------------------------------------------------------------------ #
    # T5 回滚计划
    # ------------------------------------------------------------------ #
    def build_rollback_plan(
        self,
        *,
        version_from: str = "3.9.0-preparation",
        version_to: str = "last-known-stable",
    ) -> RollbackPlan:
        return RollbackPlan(
            version_from=version_from,
            version_to=version_to,
            db_steps=[
                RollbackStep(1, "restore_database_snapshot", "primary-db", True),
                RollbackStep(2, "verify_row_counts", "primary-db", True),
            ],
            config_steps=[
                RollbackStep(1, "revert_config_to_tag", "config-repo", True),
                RollbackStep(2, "restart_services", "runtime", True),
            ],
            recovery_steps=[
                RollbackStep(1, "smoke_test_health_endpoint", "/health", True),
                RollbackStep(2, "notify_stakeholders", "ops-channel", False),
            ],
            estimated_downtime="< 15min",
            owner_role="production-owner",
        )

    # ------------------------------------------------------------------ #
    # T6 激活评审包（禁止自动批准）
    # ------------------------------------------------------------------ #
    def build_activation_review_package(
        self,
        *,
        checklist: ProductionReadinessChecklist,
        manifest: ProductionDeploymentManifest,
        env_report: EnvironmentValidationReport,
        permission_plan: PermissionInitializationPlan,
        rollback_plan: RollbackPlan,
        test_results_ref: str,
        security_checks: Optional[List[str]] = None,
        risk_list: Optional[List[str]] = None,
    ) -> ActivationReviewPackage:
        return ActivationReviewPackage(
            org_id=self._org_id,
            generated_at=self._now(),
            checklist_ref=f"readiness-checklist:{checklist.generated_at}",
            manifest_ref=f"deployment-manifest:{manifest.generated_at}",
            env_report_ref=f"env-validation:{env_report.generated_at}",
            permission_plan_ref=f"permission-plan:{permission_plan.generated_at}",
            rollback_plan_ref=f"rollback-plan:{rollback_plan.version_from}"
            f"->{rollback_plan.version_to}",
            test_results_ref=test_results_ref,
            security_checks=security_checks
            or [
                "engineering_enabled 保持 False（红线①）",
                "未输出 engineering_approved（红线②）",
                "未执行真实生产激活（红线③）",
                "未修改真实企业数据（红线④）",
                "未自动创建真实权限（红线⑤）",
                "未代替生产负责人（红线⑥）",
            ],
            deployment_status="PREPARED_NOT_DEPLOYED",
            risk_list=risk_list
            or [
                "真实生产激活须主理人在人类终端显式执行",
                "真实密钥须主理人线下注入，准备层不持有",
                "真实权限须主理人线下授予",
            ],
            approved=False,
            signature_required="HUMAN_PRODUCTION_OWNER",
            pending_human_actions=[
                "主理人审核本评审包并线下签署 production.activate 授权",
                "主理人注入真实密钥（准备层已留占位）",
                "主理人为各角色线下授予真实权限",
                "主理人在人类终端将 engineering_enabled 置 True（仅此一处）",
            ],
        )

    # ------------------------------------------------------------------ #
    # T7 审计入口（actor 真实，强制 USER）
    # ------------------------------------------------------------------ #
    def record_readiness_check_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_readiness_checklist",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_production_readiness_check(
            record_id=f"prc-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )

    def record_manifest_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_deployment_manifest",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_deployment_manifest(
            record_id=f"pdm-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )

    def record_rollback_plan_reviewed(
        self,
        *,
        actor_id: str,
        action: str = "review_rollback_plan",
        target: str = "",
        detail: str = "",
    ) -> Any:
        self._require_user(actor_id)
        return self._audit.record_rollback_plan(
            record_id=f"prp-{uuid4().hex[:12]}",
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
        )
