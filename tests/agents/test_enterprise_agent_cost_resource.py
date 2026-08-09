"""Enterprise Agent Cost & Resource Intelligence Layer —— 测试（任务8，Phase 3.8.16）。

八类测试：resource_usage / cost_metric / cost_attribution / analyzer / report /
permission / audit / red_line。

最高红线（fail-closed，6 条，与 Phase 3.8.0 指令一致 + 3.8.16 细化）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被拦截）；
③ 禁止 AI 自动关闭/停止 Agent（auto_disable_agent / auto_stop_agent / stop_agent /
   disable_agent / kill_agent / terminate_agent 等被拦截）；成本高 ≠ AI 可以关停它；
④ 禁止 AI 自动修改 Agent 配置（auto_modify_agent / modify_agent_config /
   configure_agent / set_agent_config 等被拦截）；
⑤ 禁止 AI 自动优化资源策略（auto_optimize / optimize_cost / auto_scale /
   set_budget / enforce_budget 等被拦截）；
⑥ 不 AI 代替管理责任（审计禁 record_human_approval；单价须外部台账，AI 不得编造；
   成本归属/报告必须可溯源，禁 AI 创造无源数据；成本报告不作优化/削减建议）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_cost_resource import (
    AgentCostAttribution,
    AgentCostMetric,
    AgentCostReport,
    AgentCostResourceService,
    AgentCostType,
    AgentResourceAnalyzer,
    AgentResourceType,
    AgentResourceUsage,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.data_insight import SourceTrace
from agents.enterprise.identity import IdentityService, Permission, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)
from agents.enterprise.service import EnterpriseOperationLayer


# ---------------------------------------------------------------------------
# 共享构造器（不修改任何持久化配置，仅内存构造）
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①/⑤），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _svc(org_id: str = "org-1") -> AgentCostResourceService:
    return AgentCostResourceService(
        org_id=org_id,
        audit=_audit(org_id),
        identity=_identity(org_id),
        visibility=None,
        permission_policy=_policy(org_id),
    )


def _admin(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )


def _expert(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="exp", name="E", role_kind=RoleKind.EXPERT
    )


# ===========================================================================
# 类别 1：AgentResourceUsage（事实型，只记录，禁优化/处置）
# ===========================================================================

def test_resource_usage_negative_amount_clamped_to_zero() -> None:
    u = AgentResourceUsage(
        usage_id="u1", agent_id="a1",
        resource_type=AgentResourceType.TOKEN, amount=-50.0,
    )
    # 仅范围约束，不评价：负值裁剪为 0
    assert u.amount == 0.0


def test_resource_usage_type_enum_coercion_and_default_unit() -> None:
    u = AgentResourceUsage(
        usage_id="u2", agent_id="a1",
        resource_type="compute", amount=120.0,
    )
    # 字符串归一为枚举；空单位按类型补默认单位
    assert u.resource_type is AgentResourceType.COMPUTE
    assert u.unit == "seconds"


def test_resource_usage_has_no_optimization_fields() -> None:
    u = AgentResourceUsage(
        usage_id="u3", agent_id="a1",
        resource_type=AgentResourceType.STORAGE, amount=10.0,
    )
    # 红线⑤/⑥：结构上禁优化/处置，不得携带任何 budget/quota/limit/verdict/
    # optimization/threshold 语义
    for bad in (
        "budget", "quota", "limit", "threshold", "verdict", "optimization",
        "recommendation", "decision",
    ):
        assert not hasattr(u, bad), f"AgentResourceUsage 不应含优化/处置字段 {bad}"


def test_resource_usage_recorded_and_listable() -> None:
    svc = _svc("org-1")
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="u4", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=1000.0,
            execution_id="ex-1", timestamp="2026-08",
        )
    )
    out = svc.list_resource_usages(user=_admin())
    assert len(out) == 1 and out[0].usage_id == "u4"
    # 登记即归属当前组织
    assert out[0].org_id == "org-1"


# ===========================================================================
# 类别 2：AgentCostMetric（事实型，只记录，禁报价/审批）
# ===========================================================================

def test_cost_metric_negative_value_clamped_to_zero() -> None:
    m = AgentCostMetric(
        metric_id="cm1", agent_id="a1",
        cost_type=AgentCostType.TOKEN, value=-3.0,
    )
    # 仅范围约束，不评价：负值裁剪为 0
    assert m.value == 0.0


def test_cost_metric_type_enum_coercion() -> None:
    m = AgentCostMetric(
        metric_id="cm2", agent_id="a1",
        cost_type="external_api", value=2.0,
    )
    # 字符串归一为枚举
    assert m.cost_type is AgentCostType.EXTERNAL_API


def test_cost_metric_has_no_quote_or_approval_fields() -> None:
    m = AgentCostMetric(
        metric_id="cm3", agent_id="a1",
        cost_type=AgentCostType.COMPUTE, value=5.0,
    )
    # 红线②/③/⑥：结构上禁报价/审批，不得携带任何 approved/quoted/verdict 语义
    for bad in (
        "approved", "quote", "quoted", "verdict", "budget", "authorize",
        "sign", "pricing",
    ):
        assert not hasattr(m, bad), f"AgentCostMetric 不应含报价/审批字段 {bad}"


def test_cost_metric_recorded_and_listable() -> None:
    svc = _svc("org-1")
    svc.record_cost_metric(
        metric=AgentCostMetric(
            metric_id="cm4", agent_id="a1",
            cost_type=AgentCostType.TOKEN, value=10.0,
            period="2026-08", source="finance_ledger",
        )
    )
    out = svc.list_cost_metrics(user=_admin())
    assert len(out) == 1 and out[0].metric_id == "cm4"


# ===========================================================================
# 类别 3：AgentCostAttribution（可追踪归属，禁 AI 创造无源/无对象归属）
# ===========================================================================

def test_cost_attribution_requires_object_and_source() -> None:
    # 无归属对象（缺 project_id / task_id）→ 拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentCostAttribution(attribution_id="ca1", agent_id="a1")
    # 有对象但无来源（source 空且 source_trace 不可追溯）→ 拒绝（禁 AI 编造）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentCostAttribution(
            attribution_id="ca2", agent_id="a1", project_id="p1",
        )
    # 有对象 + 有 source → 通过
    ok = AgentCostAttribution(
        attribution_id="ca3", agent_id="a1", project_id="p1",
        cost=12.0, source="finance_ledger",
    )
    assert ok.is_traceable is True


def test_cost_attribution_accepts_traceable_source_trace() -> None:
    # 无 source 文本，但 source_trace 可追溯 → 红线⑥下可接收
    ok = AgentCostAttribution(
        attribution_id="ca4", agent_id="a1", task_id="t1",
        cost=8.0, source_trace=SourceTrace(raw_refs=["usage-x"]),
    )
    assert ok.is_traceable is True


def test_cost_attribution_recorded_and_listable() -> None:
    svc = _svc("org-1")
    svc.record_cost_attribution(
        attribution=AgentCostAttribution(
            attribution_id="ca5", agent_id="a1", project_id="p1",
            cost=20.0, source="finance_ledger",
        )
    )
    out = svc.list_cost_attributions(user=_admin(), project_id="p1")
    assert len(out) == 1 and out[0].attribution_id == "ca5"


# ===========================================================================
# 类别 4：AgentResourceAnalyzer（纯事实分析，禁自动优化/编造单价）
# ===========================================================================

def test_analyzer_aggregate_usage_only_sums() -> None:
    a = AgentResourceAnalyzer(org_id="org-1")
    usages = [
        AgentResourceUsage(
            usage_id="a1", agent_id="x",
            resource_type=AgentResourceType.TOKEN, amount=100.0,
        ),
        AgentResourceUsage(
            usage_id="a2", agent_id="x",
            resource_type=AgentResourceType.TOKEN, amount=50.0,
        ),
        AgentResourceUsage(
            usage_id="a3", agent_id="y",
            resource_type=AgentResourceType.COMPUTE, amount=10.0,
        ),
    ]
    by_agent = a.aggregate_usage(usages=usages, group_by="agent_id")
    assert by_agent["x"]["total_amount"] == 150.0
    assert by_agent["x"]["count"] == 2
    assert by_agent["y"]["total_amount"] == 10.0
    # 维度过滤同样可用
    by_type = a.aggregate_usage(usages=usages, group_by="resource_type")
    assert by_type["token"]["total_amount"] == 150.0


def test_analyzer_calculate_cost_uses_external_rate_card() -> None:
    a = AgentResourceAnalyzer(org_id="org-1")
    usages = [
        AgentResourceUsage(
            usage_id="c1", agent_id="x",
            resource_type=AgentResourceType.TOKEN, amount=1000.0,
            timestamp="2026-08",
        ),
    ]
    # 单价来自外部台账（不得编造），产出成本指标 source 携带 usage 链
    metrics = a.calculate_cost(
        usages=usages,
        rate_card={AgentResourceType.TOKEN: 0.000012},
        period="2026-08",
    )
    assert len(metrics) == 1
    assert metrics[0].value == 0.012
    assert "c1" in metrics[0].source


def test_analyzer_calculate_cost_rejects_missing_rate_card() -> None:
    a = AgentResourceAnalyzer(org_id="org-1")
    usages = [
        AgentResourceUsage(
            usage_id="c2", agent_id="x",
            resource_type=AgentResourceType.TOKEN, amount=100.0,
        ),
    ]
    # 红线⑥：缺单价台账即拒绝，AI 不得编造单价或以 0 充数
    with pytest.raises(EnterpriseRedLineViolationError):
        a.calculate_cost(usages=usages, rate_card={})
    with pytest.raises(EnterpriseRedLineViolationError):
        a.calculate_cost(
            usages=usages,
            rate_card={AgentResourceType.COMPUTE: 0.02},  # token 单价缺失
        )


def test_analyzer_compare_period_only_computes_delta() -> None:
    a = AgentResourceAnalyzer(org_id="org-1")
    ma = [
        AgentCostMetric(
            metric_id="m-a", agent_id="x",
            cost_type=AgentCostType.TOKEN, value=10.0, period="2026-07",
        ),
    ]
    mb = [
        AgentCostMetric(
            metric_id="m-b", agent_id="x",
            cost_type=AgentCostType.TOKEN, value=16.0, period="2026-08",
        ),
    ]
    res = a.compare_period(
        period_a="2026-07", period_b="2026-08", metrics_a=ma, metrics_b=mb
    )
    # 只算 delta 事实：token a=10;b=16;delta=6
    assert res["totals"]["delta"] == 6.0
    assert any("token:a=10.0;b=16.0;delta=6.0" in f for f in res["facts"])
    # 不含任何 recommendation / verdict / action 字段
    for bad in ("recommendation", "verdict", "action", "decision"):
        assert bad not in res, f"compare_period 不应含 {bad}"


# ===========================================================================
# 类别 5：AgentCostReport（事实汇编，来源可追溯）
# ===========================================================================

def test_cost_report_requires_traceable_source() -> None:
    # 无 source_trace → 红线违例（禁 AI 创造无源报告）
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentCostReport(report_id="cr1", org_id="org-1")
    # source_trace 不可追溯 → 同样违例
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentCostReport(
            report_id="cr2", org_id="org-1",
            source_trace=SourceTrace(raw_refs=[]),
        )


def test_generate_cost_report_assembles_facts_only() -> None:
    svc = _svc("org-1")
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r1", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=1000.0,
            timestamp="2026-08",
        )
    )
    svc.record_cost_metric(
        metric=AgentCostMetric(
            metric_id="m1", agent_id="a1",
            cost_type=AgentCostType.TOKEN, value=0.012,
            period="2026-08", source="finance_ledger",
        )
    )
    svc.record_cost_attribution(
        attribution=AgentCostAttribution(
            attribution_id="ca6", agent_id="a1", project_id="p1",
            cost=0.012, source="finance_ledger",
        )
    )
    report = svc.generate_cost_report(
        report_id="cr3", user=_admin(), period="2026-08",
    )
    assert report.source_trace is not None and report.source_trace.is_traceable
    assert "r1" in report.resource_usages
    assert "m1" in report.cost_metrics
    assert "ca6" in report.attributions
    # 仅汇编事实，无处置/优化/削减语义字段
    for bad in (
        "approved", "optimize", "optimization", "reduce", "cut", "disable",
        "stop", "decision", "recommendation",
    ):
        assert not hasattr(report, bad), f"AgentCostReport 不应含 {bad}"


def test_generate_cost_report_requires_facts() -> None:
    svc = _svc("org-1")
    # 禁 AI 创造空的无源报告
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.generate_cost_report(report_id="cr4", user=_admin(), period="2026-08")


# ===========================================================================
# 类别 6：权限隔离（默认拒绝，AgentPermissionPolicy 接入）
# ===========================================================================

def test_cost_data_list_denied_by_default_for_expert() -> None:
    svc = _svc("org-1")
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r2", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=1.0,
        )
    )
    # EXPERT 访问 data 类别 → 默认拒绝（红线⑥：成本数据受控访问）
    with pytest.raises(Exception):
        svc.list_resource_usages(user=_expert(), resource_category="data")


def test_cost_data_list_allowed_for_admin() -> None:
    svc = _svc("org-1")
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r3", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=1.0,
        )
    )
    out = svc.list_resource_usages(user=_admin(), resource_category="data")
    assert len(out) == 1 and out[0].usage_id == "r3"


def test_permission_policy_default_deny_cost_data_for_expert() -> None:
    policy = AgentPermissionPolicy(org_id="org-1", identity=_identity())
    expert = _expert()
    # EXPERT 仅 knowledge，访问 data 默认拒绝
    assert policy.check_agent_access(
        user=expert, resource_category="data",
        required_permission=Permission.READ_RESOURCE,
    ) is False
    # ADMIN 访问 data 允许
    assert policy.check_agent_access(
        user=_admin(), resource_category="data",
        required_permission=Permission.READ_RESOURCE,
    ) is True


# ===========================================================================
# 类别 7：审计（AGENT_RESOURCE / AGENT_COST / AGENT_COST_REPORT，任务6）
# ===========================================================================

def test_audit_categories_present_and_count_53() -> None:
    # 任务6（3.8.16 → 41；3.8.17 +3 → 44；3.8.18 +3 → 47；
    # 3.8.19 +3（agent_compliance_rule/check/risk）→ 50；
    # 3.8.20 +3（agent_governance_dashboard/report/insight）→ 53；
    # 3.8.21 +3（agent_governance_task/action/closure）→ 累计 56；
    # 3.8.22 +3 → 59；3.8.23 +3 → 62。
    assert len(list(AuditActionCategory)) == 69
    for cat in ("AGENT_RESOURCE", "AGENT_COST", "AGENT_COST_REPORT"):
        assert hasattr(AuditActionCategory, cat)
        assert getattr(AuditActionCategory, cat).value in (
            "agent_resource", "agent_cost", "agent_cost_report"
        )


def test_audit_resource_cost_report_recorded() -> None:
    audit = _audit("org-1")
    svc = AgentCostResourceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r4", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=10.0,
        )
    )
    svc.record_cost_metric(
        metric=AgentCostMetric(
            metric_id="m2", agent_id="a1",
            cost_type=AgentCostType.TOKEN, value=0.1,
            period="2026-08", source="finance_ledger",
        )
    )
    svc.record_cost_attribution(
        attribution=AgentCostAttribution(
            attribution_id="ca7", agent_id="a1", project_id="p1",
            cost=0.1, source="finance_ledger",
        )
    )
    svc.generate_cost_report(report_id="cr5", user=_admin(), period="2026-08")

    # AGENT_RESOURCE 1 条；AGENT_COST 2 条（metric + attribution）；
    # AGENT_COST_REPORT 1 条。
    assert len(audit.query(category=AuditActionCategory.AGENT_RESOURCE)) == 1
    assert len(audit.query(category=AuditActionCategory.AGENT_COST)) == 2
    assert len(audit.query(category=AuditActionCategory.AGENT_COST_REPORT)) == 1


def test_audit_no_record_human_approval() -> None:
    audit = _audit("org-1")
    svc = AgentCostResourceService(
        org_id="org-1", audit=audit,
        identity=_identity("org-1"), permission_policy=_policy("org-1"),
    )
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r5", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=1.0,
        )
    )
    # 红线⑥：审计不提供 record_human_approval（AI 不伪造人工批准）；访问即拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(audit, "record_human_approval")


# ===========================================================================
# 类别 8：红线（fail-closed，6 条）
# ===========================================================================

def test_safety_invariants_ok_true_when_disabled() -> None:
    assert safety_invariants_ok() is True


def test_cost_resource_construction_fail_closed(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentCostResourceService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentResourceAnalyzer(org_id="org-1")


def test_cost_resource_forbidden_methods_raise() -> None:
    svc = _svc("org-1")
    # 红线②/③/④/⑤/⑥：聚合服务不得持有任何批准/报价/审批/关停 Agent/修改配置/
    # 优化资源策略/管理决策方法；访问即触发红线拦截
    for meth in (
        "approve", "engineering_approved", "quote", "pricing", "sign",
        "authorize", "record_human_approval",
        # 红线③：关停/停止 Agent
        "auto_disable_agent", "auto_stop_agent", "disable_agent",
        "stop_agent", "auto_shutdown_agent", "shutdown_agent",
        "kill_agent", "terminate_agent", "auto_suspend_agent", "suspend_agent",
        "auto_deactivate", "deactivate_agent",
        # 红线④：修改配置
        "auto_modify_agent", "modify_agent", "modify_agent_config",
        "auto_configure_agent", "configure_agent", "set_agent_config",
        "update_agent_config", "auto_update_agent", "update_agent", "change_agent",
        # 红线⑤：优化资源策略
        "auto_optimize", "auto_optimize_resource", "optimize_resource",
        "optimize_cost", "optimize_agent", "auto_tune", "tune_resource",
        "auto_scale", "scale_agent", "auto_throttle", "throttle_agent",
        "reduce_cost", "cut_cost", "set_budget", "enforce_budget",
        "allocate_budget", "auto_allocate", "apply_resource_policy",
        "set_resource_policy",
        # 红线⑥：管理决策
        "make_management_decision", "recommend", "decide",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, meth)


def test_no_engineering_approved_output() -> None:
    svc = _svc("org-1")
    # 红线②：访问 engineering_approved 必须被红线拦截（绝不输出）
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(svc, "engineering_approved")
    cr = __import__(
        "agents.enterprise.agent_cost_resource", fromlist=["__all__"]
    )
    assert "engineering_approved" not in cr.__all__
    ent = __import__("agents.enterprise", fromlist=["__all__"])
    assert "engineering_approved" not in ent.__all__


def test_layer_wires_agent_cost_resource() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert isinstance(layer.agent_cost_resource, AgentCostResourceService)
    assert layer.is_activation_safe() is True


def test_end_to_end_cost_resource_respects_red_lines() -> None:
    layer = EnterpriseOperationLayer(org_id="org-1")
    svc = layer.agent_cost_resource
    svc.record_resource_usage(
        usage=AgentResourceUsage(
            usage_id="r6", agent_id="a1",
            resource_type=AgentResourceType.TOKEN, amount=2000.0,
            execution_id="ex-9", timestamp="2026-08",
        )
    )
    # 单价来自外部台账（finance_ledger 提供的 0.000012 /token），AI 不编造
    metrics = svc.calculate_cost(
        rate_card={AgentResourceType.TOKEN: 0.000012},
        period="2026-08",
    )
    assert len(metrics) == 1 and metrics[0].value == 0.024
    admin = layer.identity.make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )
    svc.record_cost_attribution(
        attribution=AgentCostAttribution(
            attribution_id="ca8", agent_id="a1", task_id="t1",
            cost=0.024, source="finance_ledger",
        )
    )
    report = svc.generate_cost_report(
        report_id="cr6", user=admin, period="2026-08",
    )
    assert report.source_trace is not None and report.source_trace.is_traceable
    # 全程未触发红线：engineering_enabled 仍为 False
    assert safety_invariants_ok() is True
