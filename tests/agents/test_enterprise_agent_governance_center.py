"""Enterprise Agent Governance Intelligence & Control Center Layer —— 测试（任务8，Phase 3.8.20）。

八类测试：dashboard / overview（健康总览）/ risk（风险总览）/ report /
insight / permission / audit / red_line。

最高红线（fail-closed，6 条，与主理人 Phase 3.8.20 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动控制 Agent（auto_disable / auto_modify / auto_upgrade /
   auto_policy_change 等被拦截；看板只展示事实；健康总览禁止自动评级）；
④ 禁止 AI 自动处理风险（auto_handle_risk / auto_resolve_risk 等被拦截；
   风险总览 requires_human_handling 恒为 True，构造期只能 pending_human_review，
   处置强制 require_human_actor(USER)）；
⑤ 禁止 AI 自动判定合规（auto_judge_compliance / auto_certify_compliance 等被拦截；
   洞察枚举只有 fact_trend / anomaly_candidate，无任何判定或建议态）；
⑥ AI 不代替治理责任人（audit 禁止 record_human_approval；widget 须有 source；
   报告/洞察无来源链即拒绝；decision / conclusion 必须人工填写）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_governance_center import (
    AgentGovernanceAggregator,
    AgentGovernanceCenterService,
    AgentGovernanceDashboard,
    AgentGovernanceInsight,
    AgentGovernanceReport,
    AgentHealthOverview,
    AgentRiskOverview,
    GovernanceInsightKind,
    GovernanceTrendDirection,
    GovernanceVisibility,
    GovernanceWidget,
    GovernanceWidgetKind,
    RiskOverviewStatus,
)
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_security_risk import SourceTrace
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.organization import EnterpriseIsolationError
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
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _admin(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="adm", name="A", role_kind=RoleKind.ADMIN
    )


def _reviewer(org_id: str = "org-1"):
    """REVIEWER 只在 knowledge 作用域内，对 data 类治理数据默认拒绝。"""
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


class _FakeUpstream:
    """上游治理层只读替身（只暴露 list_* 查询，绝不提供任何写方法）。"""

    def __init__(self, **buckets):
        self._buckets = buckets

    def __getattr__(self, name: str):
        if not name.startswith("list_"):
            raise AttributeError(name)
        items = self._buckets.get(name, [])

        def _list(*, user, agent_id: str = "", resource_category: str = "data", **_kw):
            return list(items)

        return _list


class _Obj:
    """带任意属性的最小事实替身。"""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _upstreams():
    """构造五层上游只读替身（含 2 条安全风险候选 + 1 条合规风险候选）。"""
    observability = _FakeUpstream(
        list_executions=[_Obj(log_id="ex1"), _Obj(log_id="ex2")],
        list_metrics=[_Obj(metric_id="m1")],
        list_traces=[_Obj(trace_id="t1")],
    )
    quality = _FakeUpstream(
        list_quality_metrics=[_Obj(metric_id="qm1")],
        list_evaluations=[_Obj(evaluation_id="ev1")],
        list_feedbacks=[],
    )
    cost = _FakeUpstream(
        list_resource_usages=[_Obj(usage_id="u1")],
        list_cost_metrics=[_Obj(metric_id="cm1")],
    )
    security = _FakeUpstream(
        list_security_events=[_Obj(event_id="se1")],
        list_risk_candidates=[_Obj(risk_id="sr1"), _Obj(risk_id="sr2")],
    )
    compliance = _FakeUpstream(
        list_compliance_checks=[_Obj(check_id="cc1")],
        list_risk_candidates=[_Obj(risk_id="cr1")],
    )
    return observability, quality, cost, security, compliance


def _svc(org_id: str = "org-1", audit: "AuditService | None" = None, wired: bool = True):
    """治理中枢服务（默认接好五层只读上游替身）。"""
    o, q, c, s, cp = _upstreams() if wired else (None, None, None, None, None)
    return AgentGovernanceCenterService(
        org_id=org_id,
        audit=audit if audit is not None else _audit(org_id),
        identity=_identity(org_id),
        visibility=None,
        permission_policy=_policy(org_id),
        observability=o,
        quality=q,
        cost=c,
        security=s,
        compliance=cp,
    )


def _widget(widget_id: str = "w1", **kw) -> GovernanceWidget:
    base = dict(
        kind=GovernanceWidgetKind.OBSERVABILITY_FACT,
        title="近 7 日执行次数",
        source="observability:a1",
        facts={"execution_count": 2},
    )
    base.update(kw)
    return GovernanceWidget(widget_id=widget_id, **base)


def _dashboard(dashboard_id: str = "db1", **kw) -> AgentGovernanceDashboard:
    base = dict(
        widgets=[_widget()],
        visibility=GovernanceVisibility.ORG,
        created_at="2026-08-06T10:00:00",
        name="Agent 治理总览",
    )
    base.update(kw)
    return AgentGovernanceDashboard(dashboard_id=dashboard_id, **base)


def _trace(trace_id: str = "tr1", entries=("check:cc1",)) -> SourceTrace:
    return SourceTrace(trace_id=trace_id, entries=list(entries))


# ===========================================================================
# 类别 1：dashboard（治理看板，只展示事实）
# ===========================================================================

def test_widget_requires_source() -> None:
    # 红线⑥：无 source 即拒绝落库，看板不得展示不可溯源内容
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceWidget(widget_id="w-x", title="执行次数", source="")


def test_widget_requires_title() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceWidget(widget_id="w-x", title="", source="observability:a1")


def test_widget_title_rejects_control_semantics() -> None:
    # 红线③：看板只展示事实，标题不得含「自动禁用」等控制语义
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceWidget(
            widget_id="w-x", title="自动禁用低分 Agent", source="observability:a1"
        )


def test_widget_facts_reject_control_semantics() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceWidget(
            widget_id="w-x",
            title="运行事实",
            source="observability:a1",
            facts={"next_step": "auto disable"},
        )


def test_widget_kind_has_no_action_type() -> None:
    """看板组件类型刻意只有事实型，无任何可操作类型（红线③）。"""
    values = {k.value for k in GovernanceWidgetKind}
    assert values == {
        "observability_fact", "quality_fact", "cost_fact",
        "security_fact", "compliance_fact", "risk_candidate_fact",
    }
    for banned in ("action", "control", "approval", "execute", "disable"):
        assert not any(banned in v for v in values)


def test_dashboard_rejects_empty_widgets() -> None:
    # 红线⑥：禁止落库没有任何事实依据的空看板
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceDashboard(dashboard_id="db-x", widgets=[])


def test_dashboard_rejects_non_widget_member() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceDashboard(dashboard_id="db-x", widgets=["not-a-widget"])


def test_dashboard_fields_match_spec() -> None:
    """字段严格对应主理人要求：dashboard_id / org_id / widgets / visibility / created_at。"""
    d = _dashboard()
    for f in ("dashboard_id", "org_id", "widgets", "visibility", "created_at"):
        assert hasattr(d, f)
    assert d.widget_count == 1
    assert d.visibility is GovernanceVisibility.ORG


def test_dashboard_has_no_execution_capability() -> None:
    """看板对象结构上无任何执行/控制能力（红线③）。"""
    d = _dashboard()
    for banned in ("execute", "control", "disable", "upgrade", "apply"):
        assert not hasattr(d, banned)


def test_create_dashboard_binds_org_and_creator() -> None:
    s = _svc()
    d = s.create_dashboard(dashboard=_dashboard(), actor_id="ai")
    assert d.org_id == "org-1"
    assert d.created_by == "ai"


def test_dashboard_default_visibility_is_private() -> None:
    """默认最小可见范围（与默认拒绝一致）。"""
    d = AgentGovernanceDashboard(dashboard_id="db-p", widgets=[_widget()])
    assert d.visibility is GovernanceVisibility.PRIVATE


# ===========================================================================
# 类别 2：overview（健康总览，禁止自动评级）
# ===========================================================================

def test_health_overview_requires_agent_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentHealthOverview(overview_id="ho-x", agent_id="")


def test_health_overview_rejects_rating_fact_keys() -> None:
    """红线③：任一事实键名命中评级语义即拒绝。"""
    for key in ("health_rating", "grade", "rank_level", "verdict", "综合评级"):
        with pytest.raises(EnterpriseRedLineViolationError):
            AgentHealthOverview(
                overview_id="ho-x", agent_id="a1", quality_facts={key: 1}
            )


def test_health_overview_allows_raw_metric_facts() -> None:
    """原始度量事实（非定级）正常通过，不被误伤。"""
    o = AgentHealthOverview(
        overview_id="ho-1",
        agent_id="a1",
        runtime_facts={"execution_count": 2, "latency_ms": 120},
        cost_facts={"cost_metric_count": 1},
    )
    assert o.fact_count() == 3


def test_health_overview_model_has_no_rating_fields() -> None:
    o = AgentHealthOverview(overview_id="ho-1", agent_id="a1")
    for banned in ("rating", "grade", "health_level", "overall_score", "rank"):
        assert not hasattr(o, banned)


def test_build_health_overview_aggregates_four_fact_groups() -> None:
    s = _svc()
    o = s.build_health_overview(
        overview_id="ho-1", agent_id="a1", user=_admin(),
        generated_at="2026-08-06T10:00:00",
    )
    assert o.runtime_facts["execution_count"] == 2
    assert o.quality_facts["quality_metric_count"] == 1
    assert o.cost_facts["cost_metric_count"] == 1
    assert o.security_facts["security_risk_count"] == 2
    assert o.is_traceable is True


def test_build_health_overview_requires_agent_id() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.build_health_overview(overview_id="ho-x", agent_id="", user=_admin())


def test_build_health_overview_summary_has_no_rating() -> None:
    s = _svc()
    o = s.build_health_overview(overview_id="ho-1", agent_id="a1", user=_admin())
    text = o.summary().lower()
    for banned in ("rating", "grade", "rank", "verdict", "健康良好", "不健康"):
        assert banned not in text


def test_aggregator_returns_empty_when_upstream_missing() -> None:
    """上游缺失即返回空事实，**绝不编造数据**（红线⑥）。"""
    agg = AgentGovernanceAggregator(org_id="org-1")
    facts = agg.collect_observability_facts(user=_admin())
    assert facts["execution_count"] == 0
    assert facts["metric_ids"] == []


# ===========================================================================
# 类别 3：risk（风险总览，禁止自动处理）
# ===========================================================================

def test_risk_overview_forces_requires_human_handling() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentRiskOverview(
            overview_id="ro-x", agent_id="a1", requires_human_handling=False
        )


def test_risk_overview_construct_handled_is_forbidden() -> None:
    """红线④：构造期禁止直接落人工处置态。"""
    for st in (
        RiskOverviewStatus.UNDER_HUMAN_REVIEW,
        RiskOverviewStatus.HANDLED_BY_HUMAN,
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            AgentRiskOverview(overview_id="ro-x", agent_id="a1", status=st)


def test_risk_overview_status_enum_has_no_ai_terminal() -> None:
    """状态枚举中不存在任何 AI 可达的处置终态（红线④）。"""
    values = {s.value for s in RiskOverviewStatus}
    assert values == {
        "pending_human_review", "under_human_review", "handled_by_human"
    }
    for banned in ("auto", "resolved_by_ai", "dismissed", "closed"):
        assert not any(banned in v for v in values)


def test_risk_overview_has_no_resolve_methods() -> None:
    o = AgentRiskOverview(overview_id="ro-1", agent_id="a1")
    for banned in ("resolve", "close", "dismiss", "mitigate", "remediate"):
        assert not hasattr(o, banned)


def test_build_risk_overview_collects_both_candidate_sources() -> None:
    s = _svc()
    o = s.build_risk_overview(
        overview_id="ro-1", agent_id="a1", user=_admin(),
        generated_at="2026-08-06T10:00:00",
    )
    assert o.security_risk_ids == ["sr1", "sr2"]
    assert o.compliance_risk_ids == ["cr1"]
    assert o.risk_count == 3
    assert o.status is RiskOverviewStatus.PENDING_HUMAN_REVIEW
    assert o.requires_human_handling is True
    assert o.is_handled is False


def test_human_handle_risk_overview_requires_real_user() -> None:
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    for kind in (AuditActorKind.AI, AuditActorKind.SYSTEM, None):
        with pytest.raises(EnterpriseRedLineViolationError):
            s.human_handle_risk_overview(
                overview_id="ro-1", actor_kind=kind, actor_id="ai", decision="ok"
            )


def test_human_handle_risk_overview_requires_decision() -> None:
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-1", decision="   ",
        )


def test_human_handle_risk_overview_requires_actor_id() -> None:
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-1", actor_kind=AuditActorKind.USER,
            actor_id="", decision="已线下核实",
        )


def test_human_handle_risk_overview_success_and_no_repeat() -> None:
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    o = s.human_handle_risk_overview(
        overview_id="ro-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-1", decision="已线下核实并留档",
        handled_at="2026-08-06T11:00:00",
    )
    assert o.status is RiskOverviewStatus.HANDLED_BY_HUMAN
    assert o.handled_by == "owner-1"
    assert o.is_handled is True
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-1", decision="再处置一次",
        )


def test_human_handle_risk_overview_cannot_rollback() -> None:
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-1", decision="退回",
            status=RiskOverviewStatus.PENDING_HUMAN_REVIEW,
        )


def test_human_handle_unknown_risk_overview_is_rejected() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-none", actor_kind=AuditActorKind.USER,
            actor_id="owner-1", decision="d",
        )


# ===========================================================================
# 类别 4：report（治理报告，五段事实 + 强可溯源）
# ===========================================================================

def test_report_requires_source_trace() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceReport(report_id="rp-x", source_trace=None)


def test_report_rejects_empty_source_trace() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceReport(
            report_id="rp-x", source_trace=SourceTrace(trace_id="t", entries=[])
        )


def test_report_rejects_advice_in_sections() -> None:
    """红线⑤/⑥：报告不得夹带任何治理建议。"""
    for section in ("observability", "quality", "cost", "security", "compliance"):
        with pytest.raises(EnterpriseRedLineViolationError):
            AgentGovernanceReport(
                report_id="rp-x",
                source_trace=_trace(),
                **{section: {"note": "建议禁用该 Agent"}},
            )


def test_report_has_five_sections() -> None:
    r = AgentGovernanceReport(report_id="rp-1", source_trace=_trace())
    counts = r.section_counts()
    assert set(counts) == {
        "observability", "quality", "cost", "security", "compliance"
    }


def test_generate_governance_report_aggregates_five_sections() -> None:
    s = _svc()
    r = s.generate_governance_report(
        report_id="rp-1", user=_admin(), agent_id="a1",
        generated_at="2026-08-06T10:00:00",
    )
    assert r.observability["execution_count"] == 2
    assert r.quality["quality_metric_count"] == 1
    assert r.cost["cost_metric_count"] == 1
    assert r.security["security_risk_count"] == 2
    assert r.compliance["compliance_risk_count"] == 1
    assert r.is_traceable is True
    assert r.generated_by == "ai"


def test_generate_governance_report_without_facts_is_rejected() -> None:
    """无任何事实来源即拒绝生成（红线⑥）。"""
    s = _svc(wired=False)
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_governance_report(report_id="rp-x", user=_admin())


def test_report_summary_has_no_conclusion_or_approval() -> None:
    s = _svc()
    r = s.generate_governance_report(report_id="rp-1", user=_admin(), agent_id="a1")
    text = r.summary().lower()
    for banned in ("approve", "engineering_approved", "建议", "违规", "处罚"):
        assert banned not in text


# ===========================================================================
# 类别 5：insight（治理洞察，只输出事实趋势 / 异常候选 / 来源）
# ===========================================================================

def test_insight_kind_has_no_recommendation() -> None:
    """红线⑤/⑥：洞察类型刻意只有两种事实型。"""
    values = {k.value for k in GovernanceInsightKind}
    assert values == {"fact_trend", "anomaly_candidate"}
    for banned in ("recommend", "advice", "suggest", "verdict", "action"):
        assert not any(banned in v for v in values)


def test_insight_trend_direction_is_neutral() -> None:
    values = {t.value for t in GovernanceTrendDirection}
    assert values == {"up", "down", "flat", "unknown"}
    for banned in ("good", "bad", "worse", "better", "risky"):
        assert not any(banned in v for v in values)


def test_insight_requires_source_trace() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceInsight(insight_id="in-x", subject="执行次数", source_trace=None)


def test_insight_requires_subject() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceInsight(insight_id="in-x", subject="", source_trace=_trace())


def test_insight_forces_human_confirmation() -> None:
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceInsight(
            insight_id="in-x", subject="执行次数",
            source_trace=_trace(), requires_human_confirmation=False,
        )


def test_insight_rejects_advice_text() -> None:
    """红线⑤/⑥：洞察文本命中建议语义即拒绝。"""
    for kw in ("建议扩容", "应当下线", "recommend disabling", "suggest rollback"):
        with pytest.raises(EnterpriseRedLineViolationError):
            AgentGovernanceInsight(
                insight_id="in-x", subject=kw, source_trace=_trace()
            )


def test_insight_model_has_no_advice_fields() -> None:
    i = AgentGovernanceInsight(
        insight_id="in-1", subject="执行次数", source_trace=_trace()
    )
    for banned in ("recommendation", "advice", "suggestion", "action_plan"):
        assert not hasattr(i, banned)


def test_generate_fact_trend_insight_directions() -> None:
    s = _svc()
    cases = (
        ([1.0, 2.0, 5.0], GovernanceTrendDirection.UP),
        ([5.0, 2.0, 1.0], GovernanceTrendDirection.DOWN),
        ([3.0, 9.0, 3.0], GovernanceTrendDirection.FLAT),
        ([3.0], GovernanceTrendDirection.UNKNOWN),
    )
    for idx, (series, expected) in enumerate(cases):
        i = s.generate_fact_trend_insight(
            insight_id=f"in-{idx}", subject="执行次数", series=series,
            source_entries=["metric:m1"],
        )
        assert i.trend is expected
        assert i.kind is GovernanceInsightKind.FACT_TREND
        assert i.requires_human_confirmation is True


def test_generate_fact_trend_insight_requires_source() -> None:
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_fact_trend_insight(
            insight_id="in-x", subject="执行次数", series=[1.0, 2.0],
            source_entries=[],
        )


def test_generate_anomaly_candidate_insight_ok() -> None:
    s = _svc()
    i = s.generate_anomaly_candidate_insight(
        insight_id="in-a", subject="调用频次偏离",
        anomaly_candidates=["metric:m1", "metric:m2"],
        source_entries=["observability:a1"], agent_id="a1",
    )
    assert i.kind is GovernanceInsightKind.ANOMALY_CANDIDATE
    assert len(i.anomaly_candidates) == 2
    assert i.requires_human_confirmation is True
    assert i.is_traceable is True


def test_generate_anomaly_candidate_insight_rejects_fabrication() -> None:
    """无任何候选事实即拒绝产出（红线⑥：禁止编造异常）。"""
    s = _svc()
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_anomaly_candidate_insight(
            insight_id="in-x", subject="调用频次偏离",
            anomaly_candidates=[], source_entries=["observability:a1"],
        )


def test_human_confirm_insight_requires_real_user_and_conclusion() -> None:
    s = _svc()
    s.generate_fact_trend_insight(
        insight_id="in-1", subject="执行次数", series=[1.0, 2.0],
        source_entries=["metric:m1"],
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_confirm_insight(
            insight_id="in-1", actor_kind=AuditActorKind.AI,
            actor_id="ai", conclusion="ok",
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_confirm_insight(
            insight_id="in-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-1", conclusion="  ",
        )
    i = s.human_confirm_insight(
        insight_id="in-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-1", conclusion="已确认为正常波动",
    )
    # 被人工看过也不会升格为结论，仍恒为「待人工确认」的事实型洞察
    assert i.requires_human_confirmation is True


# ===========================================================================
# 类别 6：permission（治理数据隔离，默认拒绝）
# ===========================================================================

def test_reviewer_is_denied_on_governance_data() -> None:
    s = _svc()
    rev = _reviewer()
    for call in (
        lambda: s.list_dashboards(user=rev),
        lambda: s.list_health_overviews(user=rev),
        lambda: s.list_risk_overviews(user=rev),
        lambda: s.list_governance_reports(user=rev),
        lambda: s.list_governance_insights(user=rev),
    ):
        with pytest.raises(EnterpriseIsolationError):
            call()


def test_write_paths_also_enforce_isolation() -> None:
    s = _svc()
    rev = _reviewer()
    with pytest.raises(EnterpriseIsolationError):
        s.build_health_overview(overview_id="ho-x", agent_id="a1", user=rev)
    with pytest.raises(EnterpriseIsolationError):
        s.build_risk_overview(overview_id="ro-x", agent_id="a1", user=rev)
    with pytest.raises(EnterpriseIsolationError):
        s.generate_governance_report(report_id="rp-x", user=rev)


def test_admin_can_read_all_governance_data() -> None:
    s = _svc()
    adm = _admin()
    s.create_dashboard(dashboard=_dashboard())
    s.build_health_overview(overview_id="ho-1", agent_id="a1", user=adm)
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=adm)
    s.generate_governance_report(report_id="rp-1", user=adm, agent_id="a1")
    s.generate_fact_trend_insight(
        insight_id="in-1", subject="执行次数", series=[1.0, 2.0],
        source_entries=["metric:m1"],
    )
    assert len(s.list_dashboards(user=adm)) == 1
    assert len(s.list_health_overviews(user=adm, agent_id="a1")) == 1
    assert len(s.list_risk_overviews(user=adm)) == 1
    assert len(s.list_governance_reports(user=adm)) == 1
    assert len(s.list_governance_insights(user=adm)) == 1


def test_query_filters_work() -> None:
    s = _svc()
    adm = _admin()
    s.create_dashboard(dashboard=_dashboard())
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=adm)
    s.generate_anomaly_candidate_insight(
        insight_id="in-a", subject="偏离", anomaly_candidates=["m1"],
        source_entries=["observability:a1"],
    )
    assert len(s.list_dashboards(user=adm, visibility=GovernanceVisibility.ORG)) == 1
    assert len(s.list_dashboards(user=adm, visibility=GovernanceVisibility.PRIVATE)) == 0
    assert len(s.list_risk_overviews(
        user=adm, status=RiskOverviewStatus.PENDING_HUMAN_REVIEW)) == 1
    assert len(s.list_governance_insights(
        user=adm, kind=GovernanceInsightKind.FACT_TREND)) == 0


def test_cross_org_isolation() -> None:
    """跨组织读不到彼此的治理数据。"""
    s1 = _svc("org-1")
    s1.create_dashboard(dashboard=_dashboard())
    s2 = _svc("org-2")
    assert s2.list_dashboards(user=_admin("org-2")) == []


def test_layer_wires_governance_center_with_shared_deps() -> None:
    """EnterpriseOperationLayer 装配共享审计/身份/权限实例（任务7）。"""
    layer = EnterpriseOperationLayer(org_id="org-1")
    center = layer.agent_governance_center
    assert isinstance(center, AgentGovernanceCenterService)
    assert center._audit is layer.audit
    assert center._identity is layer.identity
    assert center._permission_policy is layer.agent_permission_policy
    assert center._runtime_policy is layer.agent_runtime_governance


# ===========================================================================
# 类别 7：audit（+3 类别，actor 真实）
# ===========================================================================

def test_audit_has_three_new_categories() -> None:
    """本层只对**自己新增的 3 类**负责；总数权威断言唯一保留在
    ``test_enterprise_knowledge_governance_audit.py``（Phase 3.8.31 Task 9）。
    """
    names = set(AuditActionCategory.__members__)
    assert {
        "AGENT_GOVERNANCE_DASHBOARD",
        "AGENT_GOVERNANCE_REPORT",
        "AGENT_GOVERNANCE_INSIGHT",
    } <= names


def test_audit_category_values() -> None:
    assert AuditActionCategory.AGENT_GOVERNANCE_DASHBOARD.value == (
        "agent_governance_dashboard"
    )
    assert AuditActionCategory.AGENT_GOVERNANCE_REPORT.value == (
        "agent_governance_report"
    )
    assert AuditActionCategory.AGENT_GOVERNANCE_INSIGHT.value == (
        "agent_governance_insight"
    )


def test_audit_dashboard_action_actor_is_ai_by_default() -> None:
    a = _audit()
    s = _svc(audit=a)
    s.create_dashboard(dashboard=_dashboard(), actor_id="ai")
    recs = a.query(category=AuditActionCategory.AGENT_GOVERNANCE_DASHBOARD)
    assert len(recs) == 1
    assert recs[0].actor_kind is AuditActorKind.AI
    assert recs[0].action == "create_governance_dashboard"


def test_audit_report_actions_recorded() -> None:
    a = _audit()
    s = _svc(audit=a)
    adm = _admin()
    s.build_health_overview(overview_id="ho-1", agent_id="a1", user=adm)
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=adm)
    s.generate_governance_report(report_id="rp-1", user=adm, agent_id="a1")
    recs = a.query(category=AuditActionCategory.AGENT_GOVERNANCE_REPORT)
    actions = {r.action for r in recs}
    assert actions == {
        "build_agent_health_overview",
        "build_agent_risk_overview",
        "generate_agent_governance_report",
    }
    assert all(r.actor_kind is AuditActorKind.AI for r in recs)


def test_audit_human_handling_actor_is_user() -> None:
    a = _audit()
    s = _svc(audit=a)
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    s.human_handle_risk_overview(
        overview_id="ro-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-1", decision="已线下核实",
    )
    recs = [
        r for r in a.query(category=AuditActionCategory.AGENT_GOVERNANCE_REPORT)
        if r.action == "human_handle_risk_overview"
    ]
    assert len(recs) == 1
    assert recs[0].actor_kind is AuditActorKind.USER
    assert recs[0].actor_id == "owner-1"


def test_audit_insight_actions_recorded() -> None:
    a = _audit()
    s = _svc(audit=a)
    s.generate_fact_trend_insight(
        insight_id="in-1", subject="执行次数", series=[1.0, 2.0],
        source_entries=["metric:m1"],
    )
    s.human_confirm_insight(
        insight_id="in-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-1", conclusion="已确认",
    )
    recs = a.query(category=AuditActionCategory.AGENT_GOVERNANCE_INSIGHT)
    assert len(recs) == 2
    kinds = {r.action: r.actor_kind for r in recs}
    assert kinds["generate_fact_trend_insight"] is AuditActorKind.AI
    assert kinds["human_confirm_governance_insight"] is AuditActorKind.USER


def test_audit_service_has_no_record_human_approval() -> None:
    """红线⑥：审计服务不得把 AI 动作记录为人工审批。"""
    with pytest.raises(EnterpriseRedLineViolationError):
        getattr(_audit(), "record_human_approval")


# ===========================================================================
# 类别 8：red_line（六条最高红线，fail-closed）
# ===========================================================================

def test_red_line_1_engineering_enabled_stays_false() -> None:
    assert safety_invariants_ok() is True


def test_red_line_1_enabled_state_blocks_construction(monkeypatch) -> None:
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceCenterService(org_id="org-1")
    with pytest.raises(EnterpriseRedLineViolationError):
        AgentGovernanceAggregator(org_id="org-1")


def test_red_line_1_enabled_state_blocks_writes(monkeypatch) -> None:
    s = _svc()
    adm = _admin()
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.create_dashboard(dashboard=_dashboard("db-x"))
    with pytest.raises(EnterpriseRedLineViolationError):
        s.build_health_overview(overview_id="ho-x", agent_id="a1", user=adm)
    with pytest.raises(EnterpriseRedLineViolationError):
        s.build_risk_overview(overview_id="ro-x", agent_id="a1", user=adm)
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_governance_report(report_id="rp-x", user=adm)
    with pytest.raises(EnterpriseRedLineViolationError):
        s.generate_fact_trend_insight(
            insight_id="in-x", subject="s", series=[1.0, 2.0],
            source_entries=["metric:m1"],
        )


def test_red_line_2_no_engineering_approved() -> None:
    s = _svc()
    agg = AgentGovernanceAggregator(org_id="org-1")
    for target in (s, agg):
        for forbidden in (
            "approve", "engineering_approved", "quote", "pricing",
            "sign", "authorize", "record_human_approval",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_3_no_auto_agent_control() -> None:
    s = _svc()
    agg = AgentGovernanceAggregator(org_id="org-1")
    for target in (s, agg):
        for forbidden in (
            "auto_disable", "auto_modify", "auto_upgrade", "auto_policy_change",
            "auto_disable_agent", "disable_agent", "auto_enable_agent",
            "enable_agent", "auto_modify_agent", "modify_agent",
            "auto_upgrade_agent", "upgrade_agent", "auto_downgrade_agent",
            "downgrade_agent", "auto_restart_agent", "restart_agent",
            "auto_stop_agent", "stop_agent", "auto_control_agent",
            "control_agent", "auto_deploy_agent", "deploy_agent",
            "auto_rollback_agent", "rollback_agent", "auto_change_policy",
            "change_policy", "auto_modify_policy", "modify_policy",
            "auto_update_policy", "update_policy", "auto_apply_policy",
            "apply_policy",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_4_no_auto_risk_handling() -> None:
    s = _svc()
    agg = AgentGovernanceAggregator(org_id="org-1")
    for target in (s, agg):
        for forbidden in (
            "auto_handle_risk", "handle_risk", "auto_resolve_risk",
            "resolve_risk", "auto_close_risk", "close_risk",
            "auto_dismiss_risk", "dismiss_risk", "auto_mitigate",
            "mitigate_risk", "auto_remediate", "remediate_risk",
            "auto_triage_risk", "triage_risk", "auto_accept_risk",
            "accept_risk", "auto_waive_risk", "waive_risk",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_5_no_auto_compliance_judgement() -> None:
    s = _svc()
    agg = AgentGovernanceAggregator(org_id="org-1")
    for target in (s, agg):
        for forbidden in (
            "auto_judge_compliance", "judge_compliance",
            "auto_determine_compliance", "determine_compliance",
            "auto_certify_compliance", "certify_compliance", "auto_attest",
            "attest_compliance", "auto_clear_compliance", "clear_compliance",
            "auto_declare_compliant", "declare_compliant", "auto_violate",
            "auto_penalty",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_6_no_ai_as_governance_owner() -> None:
    s = _svc()
    agg = AgentGovernanceAggregator(org_id="org-1")
    for target in (s, agg):
        for forbidden in (
            "act_as_governance_owner", "take_governance_ownership",
            "assume_governance_responsibility", "auto_govern",
            "auto_govern_agent", "auto_decide_governance", "decide_governance",
            "auto_recommend", "recommend_action", "auto_advise",
            "advise_governance", "auto_suggest", "suggest_governance_action",
        ):
            with pytest.raises(EnterpriseRedLineViolationError):
                getattr(target, forbidden)


def test_red_line_6_human_nodes_are_mandatory() -> None:
    """两个人工节点（风险处置 / 洞察确认）均强制真实 USER。"""
    s = _svc()
    s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=_admin())
    s.generate_fact_trend_insight(
        insight_id="in-1", subject="执行次数", series=[1.0, 2.0],
        source_entries=["metric:m1"],
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_handle_risk_overview(
            overview_id="ro-1", actor_kind=AuditActorKind.AI,
            actor_id="ai", decision="d",
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        s.human_confirm_insight(
            insight_id="in-1", actor_kind=AuditActorKind.AI,
            actor_id="ai", conclusion="c",
        )


def test_red_line_no_engineering_approved_in_any_output() -> None:
    """所有对外输出文本中都不出现 engineering_approved（红线②）。"""
    s = _svc()
    adm = _admin()
    d = s.create_dashboard(dashboard=_dashboard())
    ho = s.build_health_overview(overview_id="ho-1", agent_id="a1", user=adm)
    ro = s.build_risk_overview(overview_id="ro-1", agent_id="a1", user=adm)
    rp = s.generate_governance_report(report_id="rp-1", user=adm, agent_id="a1")
    ins = s.generate_fact_trend_insight(
        insight_id="in-1", subject="执行次数", series=[1.0, 2.0],
        source_entries=["metric:m1"],
    )
    for obj in (d, ho, ro, rp, ins):
        assert "engineering_approved" not in obj.summary()


def test_red_line_aggregator_is_read_only() -> None:
    """汇聚器只有 collect_* 只读方法，无任何写上游能力（红线③）。"""
    agg = AgentGovernanceAggregator(org_id="org-1")
    public = [
        m for m in dir(agg)
        if not m.startswith("_") and callable(getattr(agg, m, None))
    ]
    assert set(public) == {
        "collect_observability_facts",
        "collect_quality_facts",
        "collect_cost_facts",
        "collect_security_facts",
        "collect_compliance_facts",
    }
