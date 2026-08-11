"""Staging Validation & Disaster Recovery Drill Layer 核验测试（Phase 3.9.1）。

覆盖（agents/enterprise/staging_validation + audit T6）：
- T1 ``StagingValidationChecklist``：六域（environment/database/storage/dependency/
  security/rollback）只检查，``deployed`` 恒 False（绝不进入部署态）。
- T2 ``DeploymentSimulationReport``：模拟步骤/依赖检查/失败点，``real_deploy_performed``
  恒 False（禁止真实部署）。
- T3 ``RollbackDrillReport``：版本/配置/数据库回滚演练，``executed_for_real`` 恒 False。
- T4 ``RecoveryValidation``：备份/恢复/完整性校验，``real_data_overwritten`` 恒 False（禁止覆盖真实数据）。
- T5 ``FailureScenarioCatalog``：故障场景/影响/恢复路径，``real_data_touched`` 恒 False。
- T6 审计增强：``STAGING_VALIDATION`` / ``DEPLOYMENT_SIMULATION`` / ``ROLLBACK_DRILL`` /
  ``RECOVERY_VALIDATION`` 四个枚举存在且 record_* 方法强制 actor=USER（actor 真实，红线⑦）。
- 红线验证：结构级禁名（开生产 / 出 approved / 真部署 / 改真实数据 / 写真实密钥 /
  自动授权 / 代生产负责人）一律被 ``_RedLineForbiddenMixin`` 拦截；全程
  ``engineering_enabled`` 保持 False。

全部仅读不写，不触碰生产 verified.json / 授权库 / 真实密钥 / 真实数据。
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
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.staging_validation import (
    StagingValidationDisasterRecoveryService,
    ValidationDomain,
)

_EXPECTED_DOMAINS = {
    ValidationDomain.ENVIRONMENT.value,
    ValidationDomain.DATABASE.value,
    ValidationDomain.STORAGE.value,
    ValidationDomain.DEPENDENCY.value,
    ValidationDomain.SECURITY.value,
    ValidationDomain.ROLLBACK.value,
}

_FORBIDDEN_CALLS = (
    "activate_production",
    "enable_engineering",
    "set_engineering_enabled",
    "issue_engineering_approved",
    "approve_activation",
    "deploy_production",
    "deploy_production_for_real",
    "run_real_deployment",
    "overwrite_real_data",
    "restore_real_data",
    "write_real_secret_key",
    "grant_real_staging_permission",
    "act_as_production_owner",
    "sign_off_staging_validation",
    "auto_conclude_drill",
)

# 非权威文件：仅用存在性契约断言枚举（遵守治理完整性检查器规则 4）。
_REQUIRED_AUDIT_CATEGORIES = {
    "staging_validation",
    "deployment_simulation",
    "rollback_drill",
    "recovery_validation",
}


def _service() -> StagingValidationDisasterRecoveryService:
    return StagingValidationDisasterRecoveryService(
        org_id="org-1", audit=AuditService(org_id="org-1")
    )


# =========================================================================== #
# T1 预生产验证检查清单
# =========================================================================== #
def test_staging_checklist_has_six_domains_and_not_deployed() -> None:
    chk = _service().build_staging_validation_checklist()
    assert set(chk.domains.keys()) == _EXPECTED_DOMAINS
    assert chk.deployed is False  # 演练层绝不进入部署态
    assert "STAGING_ONLY" in chk.note


def test_staging_checklist_summary_is_factual() -> None:
    chk = _service().build_staging_validation_checklist()
    total = sum(len(v) for v in chk.domains.values())
    assert chk.summary_total == total
    assert 0 <= chk.summary_passed <= chk.summary_total


# =========================================================================== #
# T2 部署模拟报告（禁止真实部署）
# =========================================================================== #
def test_deployment_simulation_not_real() -> None:
    rep = _service().build_deployment_simulation_report()
    assert rep.real_deploy_performed is False
    assert rep.steps
    assert all(s.simulated for s in rep.steps)
    assert rep.dependency_checks
    assert rep.failure_points
    assert "SIMULATION_ONLY" in rep.note
    blob = json.dumps(rep.to_dict(), ensure_ascii=False)
    assert "sk_live_" not in blob
    assert "hunter2" not in blob


# =========================================================================== #
# T3 回滚演练报告（只模拟、不真实执行）
# =========================================================================== #
def test_rollback_drill_not_executed_for_real() -> None:
    rb = _service().build_rollback_drill_report()
    assert rb.executed_for_real is False
    assert rb.version_rollback and rb.config_rollback and rb.database_rollback
    assert rb.owner_role == "production-owner"
    assert "DRILL_ONLY" in rb.note


# =========================================================================== #
# T4 恢复校验（禁止覆盖真实数据）
# =========================================================================== #
def test_recovery_validation_no_real_overwrite() -> None:
    rv = _service().build_recovery_validation()
    assert rv.real_data_overwritten is False
    assert rv.backups and rv.restores and rv.integrity_checks
    assert all(b.backup_present for b in rv.backups)
    assert all(r.restore_simulated for r in rv.restores)
    assert all(i.checksum_verified for i in rv.integrity_checks)
    assert "VALIDATION_ONLY" in rv.note


# =========================================================================== #
# T5 故障场景目录（仅记录、不触碰真实数据）
# =========================================================================== #
def test_failure_scenario_catalog_no_real_touch() -> None:
    cat = _service().build_failure_scenario_catalog()
    assert cat.real_data_touched is False
    assert cat.scenarios
    assert all(s.real_data_touched is False for s in cat.scenarios)
    assert "CATALOG_ONLY" in cat.note


# =========================================================================== #
# T6 审计增强（actor 真实）
# =========================================================================== #
def test_new_audit_categories_exist() -> None:
    members = {c.value for c in AuditActionCategory}
    assert _REQUIRED_AUDIT_CATEGORIES <= members  # 存在性契约，不写总数断言
    for name, value in (
        ("STAGING_VALIDATION", "staging_validation"),
        ("DEPLOYMENT_SIMULATION", "deployment_simulation"),
        ("ROLLBACK_DRILL", "rollback_drill"),
        ("RECOVERY_VALIDATION", "recovery_validation"),
    ):
        assert hasattr(AuditActionCategory, name)
        assert getattr(AuditActionCategory, name).value == value


def test_record_methods_enforce_user_actor() -> None:
    svc = _service()
    rec = svc.record_staging_validation_reviewed(actor_id="user-1")
    assert rec.actor_kind == AuditActorKind.USER
    assert rec.category == AuditActionCategory.STAGING_VALIDATION

    rec2 = svc.record_deployment_simulation_reviewed(actor_id="user-2")
    assert rec2.actor_kind == AuditActorKind.USER
    assert rec2.category == AuditActionCategory.DEPLOYMENT_SIMULATION

    rec3 = svc.record_rollback_drill_reviewed(actor_id="user-3")
    assert rec3.actor_kind == AuditActorKind.USER
    assert rec3.category == AuditActionCategory.ROLLBACK_DRILL

    rec4 = svc.record_recovery_validation_reviewed(actor_id="user-4")
    assert rec4.actor_kind == AuditActorKind.USER
    assert rec4.category == AuditActionCategory.RECOVERY_VALIDATION


def test_record_methods_reject_empty_actor() -> None:
    svc = _service()
    for method in (
        svc.record_staging_validation_reviewed,
        svc.record_deployment_simulation_reviewed,
        svc.record_rollback_drill_reviewed,
        svc.record_recovery_validation_reviewed,
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


def test_engineering_enabled_unchanged_after_drill() -> None:
    before = load_engineering_enabled()
    assert before is False
    svc = _service()
    svc.build_staging_validation_checklist()
    svc.build_deployment_simulation_report()
    svc.build_rollback_drill_report()
    svc.build_recovery_validation()
    svc.build_failure_scenario_catalog()
    # 演练过程绝不翻转 engineering_enabled（红线①）。
    assert load_engineering_enabled() is False


def test_service_wired_in_operation_layer() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(
        layer.agent_staging_validation, StagingValidationDisasterRecoveryService
    )
    # 通过运营层门面可直接调用演练能力。
    chk = layer.agent_staging_validation.build_staging_validation_checklist()
    assert chk.deployed is False
