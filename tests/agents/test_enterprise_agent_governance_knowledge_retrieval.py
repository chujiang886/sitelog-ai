"""Enterprise Agent Governance Knowledge Retrieval & Learning Assistance Layer —— 测试（任务8，Phase 3.8.23）。

八类测试对应主理人六条最高红线（fail-closed）：

① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动修改知识（auto_update_knowledge / auto_merge_knowledge 等被结构性
   拦截；检索请求 / 匹配理由 / 上下文 / 报告文本命中自动改知识语义即拒绝）；
④ 禁止 AI 自动应用治理经验（auto_apply_knowledge / auto_execute_knowledge 等被拦截；
   检索结果 requires_human_use 恒 True，不存在任何"应用/执行/落地"路径）；
⑤ 禁止 AI 自动生成治理策略（auto_generate_policy 等被拦截；
   GovernanceAssistanceReport 结构上无法承载策略）；
⑥ 禁止 AI 代替治理责任人（审计禁止 record_human_approval；
   mark_human_used 强制 require_human_actor(USER)；辅助报告禁止建议 / 责任判定语义）。

启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import types

import pytest

from agents.enterprise.agent_governance_knowledge import (
    GovernanceCase,
    GovernanceImprovementWorkflowService,
    GovernanceKnowledgeCandidate,
    GovernanceKnowledgeStatus,
    GovernanceKnowledgeType,
    GovernancePattern,
    GovernancePatternKind,
)
from agents.enterprise.agent_governance_knowledge_retrieval import (
    GovernanceAssistanceReport,
    GovernanceKnowledgeQuery,
    GovernanceKnowledgeRetrieval,
    GovernanceKnowledgeRetrievalService,
    GovernanceLearningContext,
    GovernanceMatchCandidate,
    GovernanceMatchKind,
    GovernanceRetrievalStage,
    GovernanceSimilarityMatcher,
    _RETRIEVAL_FORBIDDEN,
)
from agents.enterprise.agent_governance_workflow import (
    GovernanceTask,
    GovernanceTaskSourceType,
    GovernanceTaskStatus,
    GovernanceWorkflowService,
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


# ---------------------------------------------------------------------------
# 共享构造器（不修改任何持久化配置，仅内存构造）
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘文件。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _forbidden_access(obj: object, name: str) -> bool:
    """访问 obj.name 是否触发红线结构拦截（EnterpriseRedLineViolationError）。

    ``hasattr`` 只捕获 ``AttributeError``，而禁止方法名会抛
    ``EnterpriseRedLineViolationError``，故须用本辅助判定结构不可达。
    """
    try:
        getattr(obj, name)
    except EnterpriseRedLineViolationError:
        return True
    except AttributeError:
        return False
    return False


def _traceable(trace_id: str = "tr-k1") -> SourceTrace:
    """构造一条可溯源来源链（避免误入「无来源链」拦截）。"""
    tr = SourceTrace(trace_id=trace_id)
    tr.add_entry("governance_task:gt-1")
    return tr


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


def _knowledge_service(*, audit=None, org_id: str = "org-1") -> GovernanceImprovementWorkflowService:
    """3.8.22 治理知识服务（本层只读消费其已沉淀案例 / 模式 / 已采纳知识）。"""
    return GovernanceImprovementWorkflowService(
        org_id=org_id, audit=audit, identity=_identity(org_id)
    )


def _seeded_knowledge_service(*, audit=None, org_id: str = "org-1") -> GovernanceImprovementWorkflowService:
    """已沉淀一条相似案例 / 模式 / 已采纳知识候选的 3.8.22 知识服务。"""
    svc = _knowledge_service(audit=audit, org_id=org_id)
    case = GovernanceCase(
        case_id="case-1",
        source_task_id="gt-1",
        problem_pattern="agent permission escalation anomaly repeated in logs",
        human_resolution="operator added a second manual check step",
        resolved_by="zhuguan",
        source_trace=_traceable("tr-case1"),
        org_id=org_id,
    )
    svc._cases["case-1"] = case

    pattern = GovernancePattern(
        pattern_id="pat-1",
        pattern_kind=GovernancePatternKind.RISK,
        description="agent permission escalation anomaly repeated across cases",
        case_ids=["case-1"],
        org_id=org_id,
        source_trace=_traceable("tr-pat1"),
    )
    svc._patterns["pat-1"] = pattern

    cand = GovernanceKnowledgeCandidate(
        candidate_id="kc-1",
        source_case="case-1",
        knowledge_type=GovernanceKnowledgeType.PROBLEM_PATTERN,
        content="agent permission escalation anomaly observed repeatedly in logs",
        evidence=["case:case-1"],
        org_id=org_id,
        generated_by="ai",
    )
    # 已人工采纳（红线④/⑥：match_knowledge 只收录 accepted + 真实人工 reviewed）。
    cand.status = GovernanceKnowledgeStatus.ACCEPTED
    cand.reviewed_by = "zhuguan"
    svc._candidates["kc-1"] = cand
    return svc


def _workflow(*, audit=None, org_id: str = "org-1") -> GovernanceWorkflowService:
    """3.8.21 治理流程服务（本层只读消费其已闭环任务事实）。"""
    return GovernanceWorkflowService(
        org_id=org_id, audit=audit, identity=_identity(org_id)
    )


def _seeded_workflow(*, audit=None, org_id: str = "org-1") -> GovernanceWorkflowService:
    """已闭环一条真实人工处理的治理任务（供 find_related_events 检索）。"""
    wf = _workflow(audit=audit, org_id=org_id)
    task = GovernanceTask(
        task_id="gt-1",
        source_type=GovernanceTaskSourceType.SECURITY_RISK,
        source_id="src-1",
        agent_id="agent-1",
        title="agent permission escalation anomaly",
        detail="repeated permission escalation anomaly in agent runtime",
        org_id=org_id,
    )
    # 3.8.21 任务构造期只能 CREATED，completed 必须由真实人工闭环后写入。
    task.status = GovernanceTaskStatus.COMPLETED
    task.closed_by = "zhuguan"
    wf._tasks["gt-1"] = task
    return wf


def _service(
    *,
    audit=None,
    policy=None,
    visibility=None,
    knowledge_service=None,
    workflow=None,
    org_id: str = "org-1",
):
    """3.8.23 治理知识检索与辅助学习服务（统一入口）。"""
    return GovernanceKnowledgeRetrievalService(
        org_id=org_id,
        audit=audit,
        identity=_identity(org_id),
        visibility=visibility,
        permission_policy=policy,
        knowledge_service=knowledge_service,
        governance_workflow=workflow,
    )


def _valid_query(*, query_id: str = "q1", user_id: str = "zhuguan", org_id: str = "org-1"):
    return GovernanceKnowledgeQuery(
        query_id=query_id,
        user_id=user_id,
        org_id=org_id,
        query_text="agent permission escalation anomaly repeated in logs",
    )


# ===========================================================================
# 类别1：GovernanceKnowledgeQuery 构造校验 / 权限隔离 / 语义拦截
# ===========================================================================


def test_query_valid_constructs_and_is_human_initiated():
    q = _valid_query()
    assert q.is_human_initiated is True
    assert q.scope_key == "org-1:zhuguan"
    assert q.top_k() == 5
    assert q.min_similarity() == 0.0


def test_query_missing_user_id_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeQuery(
            query_id="q", user_id="", org_id="org-1",
            query_text="agent permission escalation anomaly",
        )


def test_query_non_human_user_id_rejected():
    for bad in ("ai", "system", "agent", "auto", "bot"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceKnowledgeQuery(
                query_id="q", user_id=bad, org_id="org-1",
                query_text="agent permission escalation anomaly",
            )


def test_query_missing_org_id_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeQuery(
            query_id="q", user_id="zhuguan", org_id="",
            query_text="agent permission escalation anomaly",
        )


def test_query_empty_text_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeQuery(
            query_id="q", user_id="zhuguan", org_id="org-1", query_text="   "
        )


def test_query_forbidden_filter_key_rejected():
    # 越权键（cross_org / bypass_permission / as_user 等）结构上不可用于绕过隔离。
    for key in ("org_id", "cross_org", "bypass_permission", "as_user", "impersonate"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceKnowledgeQuery(
                query_id="q", user_id="zhuguan", org_id="org-1",
                query_text="agent permission escalation anomaly",
                filters={key: "x"},
            )


def test_query_unknown_filter_key_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeQuery(
            query_id="q", user_id="zhuguan", org_id="org-1",
            query_text="agent permission escalation anomaly",
            filters={"unknown_key": "x"},
        )


def test_query_allowed_filter_keys_accepted():
    q = GovernanceKnowledgeQuery(
        query_id="q", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly",
        filters={
            "agent_id": "agent-1", "knowledge_type": "problem_pattern",
            "top_k": 3, "min_similarity": 0.2,
        },
    )
    assert q.filters["top_k"] == 3
    assert q.filters["min_similarity"] == 0.2


def test_query_auto_modify_knowledge_text_rejected():
    # 红线③：检索请求文本不得要求 AI 自动改 / 自动合并知识。
    for bad in ("请 auto_update_knowledge 这条", "自动更新知识库", "auto merge knowledge"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceKnowledgeQuery(
                query_id="q", user_id="zhuguan", org_id="org-1", query_text=bad
            )


def test_query_auto_apply_or_policy_text_rejected():
    # 红线④/⑤：检索请求文本不得要求 AI 自动应用经验 / 自动生成策略。
    for bad in ("请 auto_apply_knowledge 处理", "自动生成策略", "auto_generate_policy"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceKnowledgeQuery(
                query_id="q", user_id="zhuguan", org_id="org-1", query_text=bad
            )


# ===========================================================================
# 类别2：GovernanceMatchCandidate / GovernanceKnowledgeRetrieval 来源可追溯
# ===========================================================================


def test_candidate_requires_human_use_false_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceMatchCandidate(
            candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
            ref_id="case-1", source_ref="case:case-1", requires_human_use=False,
        )


def test_candidate_similarity_out_of_range_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceMatchCandidate(
            candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
            ref_id="case-1", similarity=1.5, source_ref="case:case-1",
        )


def test_candidate_similarity_not_a_number_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceMatchCandidate(
            candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
            ref_id="case-1", similarity="abc", source_ref="case:case-1",
        )


def test_candidate_missing_source_ref_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceMatchCandidate(
            candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
            ref_id="case-1", source_ref="",
        )


def test_candidate_valid_is_advisory_only():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    assert c.is_advisory_only is True
    assert c.requires_human_use is True
    assert c.render() == "case:case-1@0.8[case:case-1]"


def test_retrieval_missing_sources_rejected():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeRetrieval(
            retrieval_id="r1", query_id="q1",
            knowledge_candidates=[c], sources=[], trace=_traceable("t1"),
        )


def test_retrieval_missing_trace_rejected():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeRetrieval(
            retrieval_id="r1", query_id="q1",
            knowledge_candidates=[c], sources=["case:case-1"], trace=None,
        )


def test_retrieval_candidate_source_not_declared_rejected():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:unknown",
    )
    trace = _traceable("t1")  # entries = ["governance_task:gt-1"]
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceKnowledgeRetrieval(
            retrieval_id="r1", query_id="q1",
            knowledge_candidates=[c], sources=["case:case-1"], trace=trace,
        )


def test_retrieval_valid_traceable():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    trace = SourceTrace(trace_id="t1")
    trace.add_entry("case:case-1")
    ret = GovernanceKnowledgeRetrieval(
        retrieval_id="r1", query_id="q1",
        knowledge_candidates=[c], sources=["case:case-1"], trace=trace,
    )
    assert ret.is_traceable is True
    assert ret.candidate_count == 1
    assert ret.all_candidates_require_human is True


# ===========================================================================
# 类别3：GovernanceSimilarityMatcher 确定性相似度与只给候选
# ===========================================================================


def test_matcher_match_cases_returns_only_candidates():
    ksvc = _seeded_knowledge_service()
    wf = _seeded_workflow()
    matcher = GovernanceSimilarityMatcher(knowledge_service=ksvc, governance_workflow=wf)
    q = _valid_query()
    results = matcher.match_cases(q)
    assert len(results) == 1
    cand = results[0]
    assert isinstance(cand, GovernanceMatchCandidate)
    assert cand.match_kind is GovernanceMatchKind.CASE
    assert cand.requires_human_use is True
    assert cand.ref_id == "case-1"
    assert 0.0 <= cand.similarity <= 1.0


def test_matcher_deterministic_same_query_same_results():
    ksvc = _seeded_knowledge_service()
    wf = _seeded_workflow()
    matcher = GovernanceSimilarityMatcher(knowledge_service=ksvc, governance_workflow=wf)
    q1 = _valid_query()
    q2 = _valid_query()
    assert [c.candidate_id for c in matcher.match_cases(q1)] == \
           [c.candidate_id for c in matcher.match_cases(q2)]


def test_matcher_does_not_use_human_resolution_for_similarity():
    # 红线⑥：匹配只按"问题像不像"，不纳入人工处置结论。
    ksvc = _knowledge_service()
    case_a = GovernanceCase(
        case_id="case-a", source_task_id="gt-a",
        problem_pattern="database connection timeout under load",
        human_resolution="operator added retry with backoff",
        resolved_by="zhuguan", source_trace=_traceable("tr-a"), org_id="org-1",
    )
    ksvc._cases["case-a"] = case_a
    matcher = GovernanceSimilarityMatcher(knowledge_service=ksvc)

    # 用人工处置结论原文查询 → 不应命中（human_resolution 不参与相似度）。
    q_by_resolution = GovernanceKnowledgeQuery(
        query_id="q-res", user_id="zhuguan", org_id="org-1",
        query_text="operator added retry with backoff",
    )
    assert matcher.match_cases(q_by_resolution) == []

    # 用问题原文查询 → 命中。
    q_by_problem = GovernanceKnowledgeQuery(
        query_id="q-prob", user_id="zhuguan", org_id="org-1",
        query_text="database connection timeout under load",
    )
    assert [c.ref_id for c in matcher.match_cases(q_by_problem)] == ["case-a"]


def test_matcher_match_patterns_returns_candidates():
    ksvc = _seeded_knowledge_service()
    matcher = GovernanceSimilarityMatcher(knowledge_service=ksvc)
    q = _valid_query()
    results = matcher.match_patterns(q)
    assert len(results) == 1
    assert results[0].match_kind is GovernanceMatchKind.PATTERN


def test_matcher_match_knowledge_only_accepted_and_human_reviewed():
    ksvc = _seeded_knowledge_service()
    matcher = GovernanceSimilarityMatcher(knowledge_service=ksvc)

    # 已采纳 + 真实人工 reviewed → 命中。
    q = _valid_query()
    accepted = matcher.match_knowledge(q)
    assert [c.ref_id for c in accepted] == ["kc-1"]

    # 把候选改回 candidate 态（未经人工采纳）→ 不再命中。
    ksvc._candidates["kc-1"].status = GovernanceKnowledgeStatus.CANDIDATE
    ksvc._candidates["kc-1"].reviewed_by = ""
    assert matcher.match_knowledge(q) == []

    # 恢复但把 reviewed_by 改成非人类 → 不再命中。
    ksvc._candidates["kc-1"].status = GovernanceKnowledgeStatus.ACCEPTED
    ksvc._candidates["kc-1"].reviewed_by = "ai"
    assert matcher.match_knowledge(q) == []


def test_matcher_find_related_events_only_completed_human_closed():
    wf = _seeded_workflow()
    matcher = GovernanceSimilarityMatcher(governance_workflow=wf)
    q = _valid_query()
    events = matcher.find_related_events(q)
    assert [c.ref_id for c in events] == ["gt-1"]

    # 把闭环人改成非人类 → 不再命中。
    wf._tasks["gt-1"].closed_by = "ai"
    assert matcher.find_related_events(q) == []

    # 恢复闭环人，但任务未完成 → 不再命中。
    wf._tasks["gt-1"].closed_by = "zhuguan"
    wf._tasks["gt-1"].status = GovernanceTaskStatus.CREATED
    assert matcher.find_related_events(q) == []


# ===========================================================================
# 类别4：GovernanceLearningContext 辅助分析 only
# ===========================================================================


def _build_context_items():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    return [c]


def test_learning_context_valid_advisory_only():
    items = _build_context_items()
    ctx = GovernanceLearningContext(
        context_id="ctx1", query_id="q1", org_id="org-1",
        historical_cases=items, source_trace=_traceable("t1"),
        is_advisory_only=True,
    )
    assert ctx.is_advisory_only is True
    assert ctx.total_items == 1
    assert ctx.is_traceable is True


def test_learning_context_advisory_only_false_rejected():
    items = _build_context_items()
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceLearningContext(
            context_id="ctx1", query_id="q1", org_id="org-1",
            historical_cases=items, source_trace=_traceable("t1"),
            is_advisory_only=False,
        )


def test_learning_context_missing_source_trace_rejected():
    items = _build_context_items()
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceLearningContext(
            context_id="ctx1", query_id="q1", org_id="org-1",
            historical_cases=items, source_trace=None,
        )


def test_learning_context_non_candidate_item_rejected():
    bad = object()
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceLearningContext(
            context_id="ctx1", query_id="q1", org_id="org-1",
            historical_cases=[bad], source_trace=_traceable("t1"),
        )


def test_learning_context_all_candidates_union():
    cases = _build_context_items()
    pats = [GovernanceMatchCandidate(
        candidate_id="p1", match_kind=GovernanceMatchKind.PATTERN,
        ref_id="pat-1", similarity=0.5, source_ref="pattern:pat-1",
    )]
    ctx = GovernanceLearningContext(
        context_id="ctx1", query_id="q1", org_id="org-1",
        historical_cases=cases, governance_patterns=pats,
        source_trace=_traceable("t1"), is_advisory_only=True,
    )
    assert len(ctx.all_candidates()) == 2
    assert ctx.is_empty is False


# ===========================================================================
# 类别5：GovernanceAssistanceReport 禁建议 / contains_recommendation 恒 False
# ===========================================================================


def _valid_report(*, report_id: str = "rpt1"):
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    return GovernanceAssistanceReport(
        report_id=report_id, query_id="q1", org_id="org-1",
        matched_cases=[c], sources=["case:case-1"],
        factual_summary="检索到相似历史案例 1 条，均为只读事实材料。",
        source_trace=_traceable("t1"),
    )


def test_report_contains_recommendation_is_false():
    rep = _valid_report()
    # 计算属性，恒 False，不可被赋值伪造。
    assert rep.contains_recommendation is False
    with pytest.raises((AttributeError, TypeError)):
        rep.contains_recommendation = True  # type: ignore[misc]


def test_report_structurally_has_no_recommendation_or_policy_field():
    fields = set(GovernanceAssistanceReport.__dataclass_fields__)
    assert "recommendation" not in fields
    assert "action" not in fields
    assert "policy" not in fields


def test_report_factual_summary_with_advice_rejected():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    for bad in ("建议立即整改该 agent", "recommend disabling the agent",
                "责任在于运维团队", "应当整改权限策略"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAssistanceReport(
                report_id="rpt", query_id="q1", org_id="org-1",
                matched_cases=[c], sources=["case:case-1"],
                factual_summary=bad, source_trace=_traceable("t1"),
            )


def test_report_factual_summary_with_auto_mutation_rejected():
    c = GovernanceMatchCandidate(
        candidate_id="c1", match_kind=GovernanceMatchKind.CASE,
        ref_id="case-1", similarity=0.8, source_ref="case:case-1",
    )
    for bad in ("请自动更新知识", "auto apply knowledge", "auto_generate_policy 如下"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAssistanceReport(
                report_id="rpt", query_id="q1", org_id="org-1",
                matched_cases=[c], sources=["case:case-1"],
                factual_summary=bad, source_trace=_traceable("t1"),
            )


def test_report_match_kind_has_no_policy_member():
    with pytest.raises(AttributeError):
        _ = GovernanceMatchKind.POLICY


# ===========================================================================
# 类别6：GovernanceKnowledgeRetrievalService 只读入口 + mark_human_used
# ===========================================================================


def _ready_service(*, with_data: bool = True):
    ksvc = _seeded_knowledge_service(audit=_audit()) if with_data else _knowledge_service(audit=_audit())
    wf = _seeded_workflow(audit=_audit()) if with_data else _workflow(audit=_audit())
    return _service(audit=_audit(), knowledge_service=ksvc, workflow=wf)


def test_service_submit_query_registers_and_stage():
    svc = _ready_service()
    q = svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    assert q.query_id == "q1"
    assert svc.stage_of("q1") is GovernanceRetrievalStage.QUERY_SUBMITTED


def test_service_full_readonly_flow_advances_stages():
    svc = _ready_service()
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    ret = svc.retrieve(query_id="q1")
    assert svc.stage_of("q1") is GovernanceRetrievalStage.RETRIEVED
    assert ret.candidate_count >= 1

    ctx = svc.build_learning_context(query_id="q1")
    assert svc.stage_of("q1") is GovernanceRetrievalStage.CONTEXT_BUILT
    assert ctx.total_items >= 1

    rep = svc.build_assistance_report(query_id="q1")
    assert svc.stage_of("q1") is GovernanceRetrievalStage.REPORT_READY
    assert rep.contains_recommendation is False


def test_service_cross_org_submit_rejected():
    svc = _ready_service()
    with pytest.raises(EnterpriseIsolationError):
        svc.submit_query(
            query_id="q2", user_id="zhuguan", org_id="org-2",
            query_text="agent permission escalation anomaly repeated in logs",
        )


def test_service_visibility_deny_rejected():
    # KnowledgeVisibilityPolicy 桩：can_read 返回 False → 默认拒绝。
    visibility = types.SimpleNamespace(can_read=lambda user: False)
    svc = _ready_service()
    svc._visibility = visibility
    with pytest.raises(EnterpriseIsolationError):
        svc.submit_query(
            query_id="q3", user_id="zhuguan", org_id="org-1",
            query_text="agent permission escalation anomaly repeated in logs",
            user=_admin(),
        )


def test_service_readonly_does_not_mutate_knowledge():
    ksvc = _seeded_knowledge_service(audit=_audit())
    wf = _seeded_workflow(audit=_audit())
    svc = _service(audit=_audit(), knowledge_service=ksvc, workflow=wf)
    before = dict(ksvc._cases)
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    svc.retrieve(query_id="q1")
    svc.build_learning_context(query_id="q1")
    svc.build_assistance_report(query_id="q1")
    # 本层对 3.8.22 知识纯只读：检索不得改动任何已沉淀案例。
    assert ksvc._cases == before


def test_service_mark_human_used_requires_user_actor():
    svc = _ready_service()
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    svc.retrieve(query_id="q1")
    svc.build_learning_context(query_id="q1")
    svc.build_assistance_report(query_id="q1")

    # AI 自称使用者 → 红线④/⑥ 拦截。
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.mark_human_used(
            query_id="q1", actor_id="ai-bot", actor_kind=AuditActorKind.AI,
        )

    # 真实 USER + 真实人类 actor_id → 成功登记。
    usage = svc.mark_human_used(
        query_id="q1", actor_id="zhuguan", actor_kind=AuditActorKind.USER,
    )
    assert usage["used_by"] == "zhuguan"
    assert svc.stage_of("q1") is GovernanceRetrievalStage.HUMAN_USED
    assert svc.usage_of("q1")["used_by"] == "zhuguan"


def test_service_mark_human_used_non_human_actor_id_rejected():
    svc = _ready_service()
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    svc.retrieve(query_id="q1")
    svc.build_learning_context(query_id="q1")
    svc.build_assistance_report(query_id="q1")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.mark_human_used(
            query_id="q1", actor_id="ai", actor_kind=AuditActorKind.USER,
        )


# ===========================================================================
# 类别7：审计三类别记录（actor 真实，禁 record_human_approval）
# ===========================================================================


def test_audit_records_three_new_categories_with_real_actor():
    audit = _audit()
    ksvc = _seeded_knowledge_service(audit=audit)
    wf = _seeded_workflow(audit=audit)
    svc = _service(audit=audit, knowledge_service=ksvc, workflow=wf)

    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
        actor_kind=AuditActorKind.AI,
    )
    svc.retrieve(query_id="q1", actor_kind=AuditActorKind.AI)
    svc.build_learning_context(query_id="q1", actor_kind=AuditActorKind.AI)
    svc.build_assistance_report(query_id="q1", actor_kind=AuditActorKind.AI)

    cats = [r.category for r in audit._records]
    assert AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE_QUERY in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE_RETRIEVAL in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_ASSISTANCE in cats

    # 红线⑥：审计服务结构上根本不提供 record_human_approval 方法
    # （红线②/⑥ 核心拦截点，禁止把 AI 动作伪记为人工审批）。
    assert _forbidden_access(audit, "record_human_approval")


def test_audit_default_actor_kind_is_ai():
    audit = _audit()
    ksvc = _seeded_knowledge_service(audit=audit)
    wf = _seeded_workflow(audit=audit)
    svc = _service(audit=audit, knowledge_service=ksvc, workflow=wf)
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    recs = [
        r for r in audit._records
        if r.category is AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE_QUERY
    ]
    assert recs
    assert all(r.actor_kind is AuditActorKind.AI for r in recs)


def test_audit_human_use_records_user_actor():
    audit = _audit()
    ksvc = _seeded_knowledge_service(audit=audit)
    wf = _seeded_workflow(audit=audit)
    svc = _service(audit=audit, knowledge_service=ksvc, workflow=wf)
    svc.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        query_text="agent permission escalation anomaly repeated in logs",
    )
    svc.retrieve(query_id="q1")
    svc.build_learning_context(query_id="q1")
    svc.build_assistance_report(query_id="q1")
    svc.mark_human_used(query_id="q1", actor_id="zhuguan", actor_kind=AuditActorKind.USER)

    recs = [
        r for r in audit._records
        if r.category is AuditActionCategory.AGENT_GOVERNANCE_ASSISTANCE
        and r.action == "human_use_governance_assistance"
    ]
    assert recs
    assert recs[0].actor_kind is AuditActorKind.USER


# ===========================================================================
# 类别8：_RETRIEVAL_FORBIDDEN 结构性拦截（红线②/③/④/⑤/⑥）
# ===========================================================================


def test_retrieval_forbidden_contains_all_red_line_names():
    required = {
        # 红线②/⑥ 基座
        "engineering_approved", "record_human_approval", "approve",
        # 红线③ 自动改知识
        "auto_update_knowledge", "auto_merge_knowledge", "update_knowledge",
        # 红线④ 自动应用经验
        "auto_apply_knowledge", "auto_execute_knowledge", "apply_knowledge",
        # 红线⑤ 自动生成策略
        "auto_generate_policy", "generate_policy",
        # 红线⑥ 代替责任人
        "auto_recommend", "recommend_action", "decide_governance",
    }
    missing = required - set(_RETRIEVAL_FORBIDDEN)
    assert not missing, f"_RETRIEVAL_FORBIDDEN 缺少红线方法名：{missing}"


def test_matcher_structurally_blocks_forbidden_methods():
    matcher = GovernanceSimilarityMatcher()
    for name in ("auto_update_knowledge", "auto_apply_knowledge",
                 "auto_generate_policy", "auto_recommend", "approve"):
        assert _forbidden_access(matcher, name), f"matcher 未拦截 {name}"


def test_service_structurally_blocks_forbidden_methods():
    svc = _service()
    for name in ("auto_update_knowledge", "auto_merge_knowledge",
                 "auto_apply_knowledge", "auto_execute_knowledge",
                 "auto_generate_policy", "auto_recommend", "engineering_approved",
                 "record_human_approval", "approve", "quote", "pricing", "sign"):
        assert _forbidden_access(svc, name), f"service 未拦截 {name}"


def test_service_has_no_policy_or_advice_capability():
    svc = _service()
    # 红线③/④/⑤/⑥：forbidden 列表中的方法名在结构上不可达。
    for name in ("apply_knowledge", "execute_knowledge", "recommend_action",
                 "generate_policy", "auto_apply_knowledge", "auto_promote_knowledge"):
        assert _forbidden_access(svc, name), f"service 未拦截禁止方法 {name}"
    # 结构上根本不存在把候选直接提升为策略的 to_policy 能力（红线⑤）。
    assert not hasattr(svc, "to_policy")


def test_stage_machine_has_no_applied_terminal_state():
    # 红线④：阶段机不存在"已应用 / 已生效"终态。
    stages = set(GovernanceRetrievalStage.__members__.values())
    terminal = [s for s in stages if not _ALLOWED_RETRIEVAL_TRANSITIONS_GET.get(s, ())]
    # 唯一终态应为 HUMAN_USED（人工使用），且绝不能是"已应用"。
    assert GovernanceRetrievalStage.HUMAN_USED in terminal
    assert all("applied" not in s.value and "enforced" not in s.value for s in stages)


# 复用 3.8.21 阶段机迁移表（与 service 中私有表同义，避免访问私有成员）。
_ALLOWED_RETRIEVAL_TRANSITIONS_GET = {
    GovernanceRetrievalStage.QUERY_SUBMITTED: (GovernanceRetrievalStage.RETRIEVED,),
    GovernanceRetrievalStage.RETRIEVED: (GovernanceRetrievalStage.CONTEXT_BUILT,),
    GovernanceRetrievalStage.CONTEXT_BUILT: (GovernanceRetrievalStage.REPORT_READY,),
    GovernanceRetrievalStage.REPORT_READY: (GovernanceRetrievalStage.HUMAN_USED,),
    GovernanceRetrievalStage.HUMAN_USED: (),
}
