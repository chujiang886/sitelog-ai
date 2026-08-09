"""Enterprise Analytics & Operation Intelligence Layer —— 测试5：风险预警（任务5，Phase 3.8.4）。

覆盖：
- detect_risks 输出 risk_candidate，**要求人工确认**（requires_human_confirmation 恒 True）。
- **禁止 AI 代管理责任**：decide / resolve / mitigate / manage 被拦截（红线③/⑥）。
- 审计如实标注检测由 AI 发起（actor=AI）。
- 构造 fail-closed（红线①/⑤）。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize（红线②/③/④）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory
from agents.enterprise.operation_risk import (
    OperationRiskDetector,
    RiskCandidate,
    RiskSeverity,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_detect_risks_requires_human_confirmation() -> None:
    svc = OperationRiskDetector(org_id="org-1")
    signals = [
        {
            "risk_id": "R-1",
            "risk_type": "sla_overdue",
            "severity": "high",
            "description": "SLA 逾期",
            "evidence": "overdue=2",
        },
        {"risk_type": "low_completion", "severity": "medium", "evidence": "completion=0.2"},
    ]
    cands = svc.detect_risks(signals=signals, detected_at="t0")
    assert len(cands) == 2
    assert cands[0].risk_id == "R-1"
    assert cands[0].severity == RiskSeverity.HIGH
    assert cands[1].risk_id.startswith("RISK-")
    # 红线③/⑥：每个候选都必须人工确认
    assert all(c.requires_human_confirmation for c in cands)


def test_risk_candidate_forces_human_confirmation() -> None:
    # 即便传入 False，__post_init__ 也强制置 True（AI 不代管理决策）
    c = RiskCandidate(risk_id="R-9", org_id="org-1", risk_type="sla_overdue", requires_human_confirmation=False)
    assert c.requires_human_confirmation is True


def test_no_decision_entrypoint() -> None:
    svc = OperationRiskDetector(org_id="org-1")
    # 红线③/⑥：风险处置/决策入口一律拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.decide
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.resolve
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.mitigate
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.manage


def test_audit_records_ai_detection() -> None:
    from agents.enterprise.audit import AuditService

    audit = AuditService(org_id="org-1")
    svc = OperationRiskDetector(org_id="org-1", audit=audit)
    svc.detect_risks(signals=[{"risk_type": "sla_overdue", "severity": "high"}], detected_at="t0")
    recs = audit.query(category=AuditActionCategory.AI_ACTION)
    assert any(r.action == "detect_operation_risks" for r in recs)


def test_service_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        OperationRiskDetector(org_id="org-1")
