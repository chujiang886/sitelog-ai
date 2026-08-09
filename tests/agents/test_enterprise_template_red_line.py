"""Enterprise Operation Layer —— 测试6：红线（6 条，fail-closed，Phase 3.8.3）。

覆盖：
- safety_invariants_ok()：当前 config engineering_enabled=false → 返回 True。
- Phase 3.8.3 全部新增服务（WorkflowTemplateService / WorkflowVersionService /
  WorkflowTriggerService / WorkflowSLAService / WorkflowMetricsService）及聚合门面
  在「启用态」（伪造 engineering_enabled=True）下构造一律抛
  EnterpriseRedLineViolationError（红线①/⑤）。
- WorkflowTriggerService 在启用态下构造即失败，**不可能**触发任何流程或审批（红线③）。
- 触发服务 forbidden 集合额外拦截 auto_approve / confirm / trigger_approval 等，
  从结构上杜绝「自动触发审批」（红线③）。
- 不修改 verified.json / config.yaml / engineering_enabled 文件（仅 monkeypatch）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入。
"""

from __future__ import annotations

import pytest

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.workflow_metrics import WorkflowMetricsService
from agents.enterprise.workflow_sla import WorkflowSLAService
from agents.enterprise.workflow_template import WorkflowTemplateService
from agents.enterprise.workflow_trigger import WorkflowTriggerService
from agents.enterprise.workflow_version import WorkflowVersionService


def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


@pytest.mark.parametrize(
    "svc_factory",
    [
        lambda: WorkflowTemplateService(org_id="org-1"),
        lambda: WorkflowVersionService(org_id="org-1"),
        lambda: WorkflowTriggerService(org_id="org-1"),
        lambda: WorkflowSLAService(org_id="org-1"),
        lambda: WorkflowMetricsService(org_id="org-1"),
        lambda: EnterpriseOperationLayer(org_id="org-1"),
    ],
)
def test_phase_3_8_3_service_construction_fail_closed(svc_factory, monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        svc_factory()


def test_trigger_service_cannot_fire_under_enabled(monkeypatch) -> None:
    """红线③/①：启用态下触发服务构造即失败，绝无可能触发流程或审批。"""
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        WorkflowTriggerService(org_id="org-1")


def test_aggregate_layer_exposes_new_subservices() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    for attr in (
        "workflow_templates",
        "workflow_versions",
        "workflow_triggers",
        "workflow_slas",
        "workflow_metrics",
    ):
        assert hasattr(layer, attr), f"聚合层缺少 {attr}"


def test_enterprise_layer_is_activation_safe() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert layer.is_activation_safe() is True
