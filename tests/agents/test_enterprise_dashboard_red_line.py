"""Enterprise Intelligence Dashboard Layer —— 测试6：红线守约（Phase 3.8.5）。

覆盖（6 条 fail-closed）：
① 不开 engineering_enabled（构造即断言，monkeypatch load_engineering_enabled=True 即抛）。
② 不输出 engineering_approved（forbidden 方法名被拦截）。
③ 不自动报价（quote / pricing 被拦截）；驾驶舱只展示事实（widget 决策键被拦截）。
④ 不自动审批（approve / sign / authorize 被拦截）。
⑤ 不绕过 UnifiedActivationGate（以 safety_invariants_ok 统一前置）。
⑥ 不 AI 代责（record_human_approval 被拦截；运营/风险等决策入口 evaluate_quality /
   auto_business_decision / make_management_decision 被拦截）。

绝不修改 verified.json / engineering_enabled；仅内存 monkeypatch 护栏信号。
"""

from __future__ import annotations

import pytest

from agents.enterprise.dashboard import (
    DashboardService,
    DashboardWidget,
    WidgetType,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        DashboardService(org_id="org-1")


@pytest.mark.parametrize(
    "forbidden",
    ["approve", "engineering_approved", "quote", "pricing", "sign", "authorize", "record_human_approval"],
)
def test_base_forbidden_methods_blocked(forbidden: str) -> None:
    svc = DashboardService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(svc, forbidden)


@pytest.mark.parametrize(
    "forbidden",
    ["auto_business_decision", "make_management_decision", "decide_operation", "evaluate_quality"],
)
def test_decision_forbidden_methods_blocked(forbidden: str) -> None:
    svc = DashboardService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(svc, forbidden)


def test_widget_decision_fact_key_blocked_red_line() -> None:
    # 红线③/⑥：驾驶舱组件不得承载决策/建议事实键
    with pytest.raises(EnterpriseRedLineViolationError):
        DashboardWidget(
            widget_id="w",
            widget_type=WidgetType.METRIC,
            title="t",
            facts={"decision": "auto-approve"},
        )


def test_service_has_no_real_forbidden_methods() -> None:
    # 结构性确认：实例上不存在这些「真实」方法（仅 __getattr__ 拦截）。
    svc = DashboardService(org_id="org-1")
    for name in ("approve", "engineering_approved", "quote", "pricing", "sign", "authorize"):
        assert not hasattr(type(svc), name), f"{name} 不应作为真实方法存在"
