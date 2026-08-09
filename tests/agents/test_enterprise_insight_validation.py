"""Enterprise Knowledge Feedback & Continuous Improvement Layer —— 测试2：洞察验证（任务2，Phase 3.8.7）。

覆盖（InsightValidationService）：
- InsightValidation / ValidationResult 建模（valid / invalid / needs_revision）。
- create_validation 必须由真实 USER 发起（红线⑥：AI 不得自动验证）。
- get / list_validations 按 insight_id / result 过滤；跨域隔离。
- 不持有 auto_validate / ai_validate 等 forbidden 方法（红线⑥核心拦截）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditActorKind, AuditService
from agents.enterprise.insight_validation import (
    InsightValidation,
    InsightValidationService,
    ValidationResult,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def _svc(org_id: str = "org-1") -> InsightValidationService:
    return InsightValidationService(org_id=org_id, audit=AuditService(org_id=org_id))


def test_validation_result_enum() -> None:
    assert ValidationResult.VALID.value == "valid"
    assert ValidationResult.INVALID.value == "invalid"
    assert ValidationResult.NEEDS_REVISION.value == "needs_revision"


def test_create_validation_requires_human() -> None:
    svc = _svc()
    # AI 不得自动验证（红线⑥）
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.create_validation(
            validation_id="v1",
            insight_id="I-1",
            validator="ai",
            result=ValidationResult.VALID,
            actor_kind=AuditActorKind.AI,
        )
    # 真实 USER 可验证
    val = svc.create_validation(
        validation_id="v1",
        insight_id="I-1",
        validator="expert-1",
        result=ValidationResult.VALID,
        comment="确认无误",
        actor_kind=AuditActorKind.USER,
    )
    assert isinstance(val, InsightValidation)
    assert val.result == ValidationResult.VALID
    assert val.validator == "expert-1"


def test_validation_audit_recorded_as_user() -> None:
    svc = _svc()
    svc.create_validation(
        validation_id="v1",
        insight_id="I-1",
        validator="expert-1",
        result=ValidationResult.INVALID,
        actor_kind=AuditActorKind.USER,
    )
    recs = svc._audit.query(category=AuditActionCategory.VALIDATION)
    assert len(recs) == 1
    assert recs[0].actor_kind == AuditActorKind.USER
    assert recs[0].action == "create_validation"


def test_list_validations_filters() -> None:
    svc = _svc()
    svc.create_validation(
        validation_id="v1", insight_id="I-1", validator="e1",
        result=ValidationResult.VALID, actor_kind=AuditActorKind.USER,
    )
    svc.create_validation(
        validation_id="v2", insight_id="I-2", validator="e2",
        result=ValidationResult.NEEDS_REVISION, actor_kind=AuditActorKind.USER,
    )
    assert len(svc.list_validations(insight_id="I-1")) == 1
    assert len(svc.list_validations(result=ValidationResult.NEEDS_REVISION)) == 1
    assert svc.get(validation_id="v2").insight_id == "I-2"


def test_forbidden_ai_auto_validate_methods() -> None:
    svc = _svc()
    for name in ("auto_validate", "ai_validate"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_validation_forbidden_knowledge_and_decision_methods() -> None:
    svc = _svc()
    for name in (
        "auto_update_knowledge",
        "auto_merge_knowledge",
        "auto_approve_knowledge",
        "approve",
        "engineering_approved",
        "record_human_approval",
        "recommend",
        "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_cross_org_isolation() -> None:
    svc_a = _svc("org-a")
    svc_b = _svc("org-b")
    svc_a.create_validation(
        validation_id="v1", insight_id="I-1", validator="e1",
        result=ValidationResult.VALID, actor_kind=AuditActorKind.USER,
    )
    from agents.enterprise.organization import EnterpriseIsolationError

    with pytest.raises(EnterpriseIsolationError):
        svc_b.get(validation_id="v1")
