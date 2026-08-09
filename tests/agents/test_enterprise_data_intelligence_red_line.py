"""Enterprise Data Intelligence & Decision Support Layer —— 测试8：红线守约聚合（Phase 3.8.6）。

覆盖（6 条 fail-closed，跨 4 个新服务 + EnterpriseOperationLayer 装配）：
① 不开 engineering_enabled（四个服务与聚合层构造即断言）。
② 不输出 engineering_approved（forbidden 方法名被拦截）。
③ 不自动报价/经营决策（quote / pricing / auto_business_decision / make_management_decision /
   optimize_business_strategy / execute_strategy / recommend / decide 被拦截）。
④ 不自动审批（approve / sign / authorize 被拦截）。
⑤ 不绕过 UnifiedActivationGate（以 safety_invariants_ok 统一前置）。
⑥ 不 AI 代责（record_human_approval 被拦截；异常检测器不提供 resolve/fix 等处置入口）。

绝不修改 verified.json / engineering_enabled；仅内存 monkeypatch 护栏信号。
"""

from __future__ import annotations

import pytest

from agents.enterprise.anomaly_detection import AnomalyDetector
from agents.enterprise.data_insight import DataInsightService
from agents.enterprise.management_report import ManagementReportService
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.service import EnterpriseOperationLayer
from agents.enterprise.trend_analysis import TrendAnalyzer


def test_all_service_constructions_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    for factory in (DataInsightService, TrendAnalyzer, AnomalyDetector, ManagementReportService):
        with pytest.raises(EnterpriseRedLineViolationError):
            factory(org_id="org-1")


def test_aggregate_layer_wires_new_services() -> None:
    # 默认（未启用）下应成功装配四个新服务。
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.data_insights, DataInsightService)
    assert isinstance(layer.trend_analysis, TrendAnalyzer)
    assert isinstance(layer.anomaly_detection, AnomalyDetector)
    assert isinstance(layer.management_reports, ManagementReportService)
    # 共享同一审计实例（联动记录）。
    assert layer.data_insights._audit is layer.audit


def test_aggregate_layer_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr("agents.enterprise.red_line.load_engineering_enabled", lambda: True)
    with pytest.raises(EnterpriseRedLineViolationError):
        EnterpriseOperationLayer(org_id="org-1")


@pytest.mark.parametrize(
    "forbidden",
    ["approve", "engineering_approved", "quote", "pricing", "sign", "authorize", "record_human_approval"],
)
def test_base_forbidden_methods_blocked(forbidden: str) -> None:
    svc = DataInsightService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(svc, forbidden)


@pytest.mark.parametrize(
    "forbidden",
    [
        "auto_business_decision", "make_management_decision", "recommend_management_action",
        "optimize_business_strategy", "execute_strategy", "decide_operation", "auto_decision",
        "recommend", "decide",
    ],
)
def test_decision_forbidden_methods_blocked(forbidden: str) -> None:
    svc = DataInsightService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(svc, forbidden)


def test_anomaly_detector_no_resolution_entrypoints() -> None:
    svc = AnomalyDetector(org_id="org-1")
    for name in ("resolve", "mitigate", "fix", "close"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, name)


def test_no_real_forbidden_methods_on_services() -> None:
    # 结构性确认：实例上不存在这些「真实」方法（仅 __getattr__ 拦截）。
    for svc in (
        DataInsightService(org_id="org-1"),
        TrendAnalyzer(org_id="org-1"),
        AnomalyDetector(org_id="org-1"),
        ManagementReportService(org_id="org-1"),
    ):
        for name in ("approve", "engineering_approved", "quote", "pricing", "sign", "authorize"):
            assert not hasattr(type(svc), name), f"{name} 不应作为真实方法存在"
