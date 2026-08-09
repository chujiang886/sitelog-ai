"""Enterprise Intelligence Dashboard Layer —— 测试2：指标组件事实型约束（任务2，Phase 3.8.5）。

覆盖：
- DashboardWidget 支持 metric / chart / table / risk 四种类型。
- widget_type_value 正确返回类型字符串。
- **只展示事实**：facts 中出现决策性/建议性键（decision / recommendation / approval /
  quote / pricing / engineering_approved）即抛红线违例（红线③/⑥）。
- facts 必须为 dict。
- 正常事实 widget 可构造且不触发红线。
"""

from __future__ import annotations

import pytest

from agents.enterprise.dashboard import DashboardWidget, WidgetType
from agents.enterprise.red_line import EnterpriseRedLineViolationError


def test_widget_supports_four_types() -> None:
    for wt in (WidgetType.METRIC, WidgetType.CHART, WidgetType.TABLE, WidgetType.RISK):
        w = DashboardWidget(widget_id="w", widget_type=wt, title="t", facts={"v": 1})
        assert w.widget_type_value() == wt.value


def test_widget_type_value_from_string() -> None:
    w = DashboardWidget(widget_id="w", widget_type="metric", title="t", facts={"v": 1})
    assert w.widget_type_value() == "metric"


def test_widget_fact_only_not_decision() -> None:
    w = DashboardWidget(
        widget_id="w",
        widget_type=WidgetType.METRIC,
        title="项目总数",
        facts={"total_projects": 42},
        source="project_analytics",
    )
    assert w.facts == {"total_projects": 42}


@pytest.mark.parametrize(
    "bad_key",
    ["decision", "recommendation", "approval", "approved", "quote", "pricing", "engineering_approved"],
)
def test_widget_rejects_decision_fact_keys(bad_key: str) -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        DashboardWidget(
            widget_id="w",
            widget_type=WidgetType.METRIC,
            title="t",
            facts={bad_key: "x"},
        )


def test_widget_facts_must_be_dict() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        DashboardWidget(widget_id="w", widget_type=WidgetType.METRIC, title="t", facts=["not", "a", "dict"])  # type: ignore[arg-type]


def test_risk_widget_carries_human_confirmation_fact() -> None:
    w = DashboardWidget(
        widget_id="w",
        widget_type=WidgetType.RISK,
        title="风险清单",
        facts={"risks": [], "total": 0},
        source="operation_risk",
    )
    assert w.widget_type_value() == "risk"
    assert w.facts["total"] == 0
