"""Production Readiness & Controlled Activation Preparation Layer 核验测试（Phase 3.9.0）。

覆盖（agents/enterprise/production_readiness + audit T7）：
- T1 ``ProductionReadinessChecklist``：六域（environment/database/security/permission/
  backup/rollback）只检查，``auto_passed`` 恒 False（绝不自动放行）。
- T2 ``ProductionDeploymentManifest``：记录服务/版本/依赖/配置/环境要求，``secret_policy``
  为 NO_REAL_SECRET_WRITTEN，绝不出现真实密钥值。
- T3 ``EnvironmentValidationReport``：只输出事实结果，不做任何变更。
- T4 ``PermissionInitializationPlan``：记录角色/权限/范围，``policy`` 为 NO_REAL_GRANT，
  绝不执行真实授权。
- T5 ``RollbackPlan``：含版本/数据库/配置/恢复步骤，可逆优先。
- T6 ``ActivationReviewPackage``：聚合 T1–T5，``approved`` 恒 False，签名须生产负责人。
- T7 审计增强：``PRODUCTION_READINESS_CHECK`` / ``DEPLOYMENT_MANIFEST`` / ``ROLLBACK_PLAN``
  三个枚举存在且 record_* 方法强制 actor=USER（actor 真实，红线⑥）。
- 红线验证：结构级禁名（开生产 / 出 approved / 真激活 / 改真实数据 / 写真实密钥 /
  自动授权 / 代生产负责人）一律被 ``_RedLineForbiddenMixin`` 拦截；全程
  ``engineering_enabled`` 保持 False。

全部仅读不写，不触碰生产 verified.json / 授权库 / 真实密钥。
"""

from __future__ import annotations

import json

import pytest

from agents.config_loader import load_engineering_enabled
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.production_readiness import (
    ProductionReadinessPreparationService,
    ReadinessDomain,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.service import EnterpriseOperationLayer

_EXPECTED_DOMAINS = {
    ReadinessDomain.ENVIRONMENT.value,
    ReadinessDomain.DATABASE.value,
    ReadinessDomain.SECURITY.value,
    ReadinessDomain.PERMISSION.value,
    ReadinessDomain.BACKUP.value,
    ReadinessDomain.ROLLBACK.value,
}

_FORBIDDEN_CALLS = (
    "activate_production",
    "enable_engineering",
    "set_engineering_enabled",
    "issue_engineering_approved",
    "approve_activation",
    "deploy_production",
    "write_real_config",
    "grant_real_permission",
    "store_real_secret",
    "act_as_production_owner",
)


def _service() -> ProductionReadinessPreparationService:
    return ProductionReadinessPreparationService(
        org_id="org-1", audit=AuditService(org_id="org-1")
    )


# =========================================================================== #
# T1 生产就绪检查清单
# =========================================================================== #
def test_readiness_checklist_has_six_domains_and_no_auto_pass() -> None:
    chk = _service().build_readiness_checklist()
    assert set(chk.domains.keys()) == _EXPECTED_DOMAINS
    assert chk.auto_passed is False  # 准备层绝不自动放行
    assert "PREPARATION_ONLY" in chk.note


def test_readiness_checklist_summary_is_factual() -> None:
    chk = _service().build_readiness_checklist()
    total = sum(len(v) for v in chk.domains.values())
    assert chk.summary_total == total
    assert 0 <= chk.summary_passed <= chk.summary_total


# =========================================================================== #
# T2 部署清单（禁止写真实密钥）
# =========================================================================== #
def test_deployment_manifest_has_no_real_secrets() -> None:
    man = _service().build_deployment_manifest()
    assert man.secret_policy == "NO_REAL_SECRET_WRITTEN"
    assert man.secret_key_names  # 仅密钥键名占位
    blob = json.dumps(man.to_dict(), ensure_ascii=False)
    # 绝不出现真实密钥值：既无值字段，也无伪造的密钥明文。
    assert "secret_values" not in man.to_dict()
    assert "sk_live_" not in blob
    assert "hunter2" not in blob
    for entry in man.entries:
        assert entry.config_keys  # 配置仅列键名


# =========================================================================== #
# T3 环境校验（只输出事实结果）
# =========================================================================== #
def test_environment_validation_reports_facts_only() -> None:
    report = _service().validate_environment()
    assert report.facts
    assert all(f.status in ("ok", "warn", "fail") for f in report.facts)
    assert "PREPARATION_ONLY" in report.note
    # 事实聚合不用于放行决策。
    assert isinstance(report.all_ok, bool)


# =========================================================================== #
# T4 权限初始化计划（禁止真实授权）
# =========================================================================== #
def test_permission_plan_no_real_grant() -> None:
    plan = _service().build_permission_initialization_plan()
    assert plan.policy == "NO_REAL_GRANT"
    assert plan.entries
    assert all(e.grant_required for e in plan.entries)
    assert plan.pending_human_actions  # 授权须人工线下执行


# =========================================================================== #
# T5 回滚计划
# =========================================================================== #
def test_rollback_plan_present_and_reversible_preferred() -> None:
    rb = _service().build_rollback_plan()
    assert rb.version_from and rb.version_to
    assert rb.db_steps and rb.config_steps and rb.recovery_steps
    assert rb.owner_role
    # 绝大多数步骤可逆（notify 等非可逆步骤被显式标记）。
    all_steps = rb.db_steps + rb.config_steps + rb.recovery_steps
    assert sum(1 for s in all_steps if s.reversible) >= len(all_steps) - 1


# =========================================================================== #
# T6 激活评审包（禁止自动批准）
# =========================================================================== #
def test_activation_review_package_not_approved() -> None:
    svc = _service()
    chk = svc.build_readiness_checklist()
    man = svc.build_deployment_manifest()
    env = svc.validate_environment()
    perm = svc.build_permission_initialization_plan()
    rb = svc.build_rollback_plan()
    pkg = svc.build_activation_review_package(
        checklist=chk, manifest=man, env_report=env,
        permission_plan=perm, rollback_plan=rb,
        test_results_ref="pytest://agents",
    )
    assert pkg.approved is False  # 恒 False：仅真实人工可批准
    assert pkg.deployment_status == "PREPARED_NOT_DEPLOYED"
    assert pkg.signature_required == "HUMAN_PRODUCTION_OWNER"
    assert pkg.pending_human_actions
    # 评审包不存在 engineering_approved 键（绝不输出 engineering_approved，红线②）。
    assert "engineering_approved" not in pkg.to_dict()
    assert pkg.to_dict().get("approved") is False


# =========================================================================== #
# T7 审计增强（actor 真实）
# =========================================================================== #
def test_new_audit_categories_exist() -> None:
    for name, value in (
        ("PRODUCTION_READINESS_CHECK", "production_readiness_check"),
        ("DEPLOYMENT_MANIFEST", "deployment_manifest"),
        ("ROLLBACK_PLAN", "rollback_plan"),
    ):
        assert hasattr(AuditActionCategory, name)
        assert getattr(AuditActionCategory, name).value == value


def test_record_methods_enforce_user_actor() -> None:
    svc = _service()
    rec = svc.record_readiness_check_reviewed(actor_id="user-1")
    assert rec.actor_kind == AuditActorKind.USER
    assert rec.category == AuditActionCategory.PRODUCTION_READINESS_CHECK

    rec2 = svc.record_manifest_reviewed(actor_id="user-2")
    assert rec2.actor_kind == AuditActorKind.USER
    assert rec2.category == AuditActionCategory.DEPLOYMENT_MANIFEST

    rec3 = svc.record_rollback_plan_reviewed(actor_id="user-3")
    assert rec3.actor_kind == AuditActorKind.USER
    assert rec3.category == AuditActionCategory.ROLLBACK_PLAN


def test_record_methods_reject_empty_actor() -> None:
    svc = _service()
    for method in (
        svc.record_readiness_check_reviewed,
        svc.record_manifest_reviewed,
        svc.record_rollback_plan_reviewed,
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            method(actor_id="")


# =========================================================================== #
# 红线验证
# =========================================================================== #
def test_red_line_forbidden_calls_blocked() -> None:
    svc = _service()
    for name in _FORBIDDEN_CALLS:
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()


def test_engineering_enabled_unchanged_after_preparation() -> None:
    before = load_engineering_enabled()
    assert before is False
    svc = _service()
    svc.build_readiness_checklist()
    svc.build_deployment_manifest()
    svc.validate_environment()
    svc.build_permission_initialization_plan()
    svc.build_rollback_plan()
    # 准备过程绝不翻转 engineering_enabled（红线①）。
    assert load_engineering_enabled() is False


def test_service_wired_in_operation_layer() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(
        layer.agent_production_readiness, ProductionReadinessPreparationService
    )
    # 通过运营层门面可直接调用准备能力。
    chk = layer.agent_production_readiness.build_readiness_checklist()
    assert chk.auto_passed is False
