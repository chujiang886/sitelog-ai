"""Enterprise Agent Governance Knowledge Assistant Layer —— 测试（任务8，Phase 3.8.24）。

八类测试对应主理人六条最高红线（fail-closed）：

① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动修改知识（auto_update_knowledge / auto_merge_knowledge 等被结构性
   拦截；问题 / 上下文 / 答案文本命中自动改知识语义即拒绝）；
④ 禁止 AI 自动应用治理经验（auto_apply_knowledge / auto_execute_knowledge 等被拦截；
   答案草稿 requires_human_review 恒 True，不存在任何"应用/执行/落地"路径）；
⑤ 禁止 AI 自动生成治理策略（generate_policy / recommend_policy 等被拦截；
   GovernanceAnswerDraft 结构上无法承载策略）；
⑥ 禁止 AI 代替治理责任人（审计禁止 record_human_approval；
   confirm_answer 强制 require_human_actor(USER)；答案草稿禁止建议 / 责任判定语义）。

启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

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
from agents.enterprise.agent_governance_knowledge_assistant import (
    AssistantReviewDecision,
    GovernanceAnswerDraft,
    GovernanceAssistantAgent,
    GovernanceAssistantContext,
    GovernanceAssistantQuery,
    GovernanceAssistantReview,
    GovernanceAssistantStage,
    _ASSISTANT_FORBIDDEN,
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
        user_id="zhuguan", name="Z", role_kind=RoleKind.ADMIN
    )


def _reviewer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
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


def _agent(
    *,
    audit=None,
    policy=None,
    visibility=None,
    knowledge_service=None,
    workflow=None,
    org_id: str = "org-1",
):
    """治理知识助手编排服务（统一入口）。"""
    return GovernanceAssistantAgent(
        org_id=org_id,
        audit=audit,
        identity=_identity(org_id),
        visibility=visibility,
        permission_policy=policy,
        knowledge_service=knowledge_service,
        governance_workflow=workflow,
    )


def _valid_query(*, query_id: str = "q1", user_id: str = "zhuguan", org_id: str = "org-1"):
    return GovernanceAssistantQuery(
        query_id=query_id,
        user_id=user_id,
        org_id=org_id,
        question="agent permission escalation anomaly repeated in logs",
    )


def _seeded_agent(*, org_id: str = "org-1"):
    audit = _audit(org_id)
    return _agent(
        audit=audit,
        policy=_policy(org_id),
        knowledge_service=_seeded_knowledge_service(audit=audit, org_id=org_id),
        workflow=_seeded_workflow(audit=audit, org_id=org_id),
        org_id=org_id,
    )


# ===========================================================================
# 类别1：GovernanceAssistantQuery 构造校验 / 权限隔离 / 语义拦截（任务1）
# ===========================================================================


def test_query_valid_constructs_and_is_human_initiated():
    q = _valid_query()
    assert q.is_human_initiated is True
    assert q.scope_key == "org-1:zhuguan"
    assert q.top_k() == 5
    assert q.min_similarity() == 0.0


def test_query_missing_user_id_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantQuery(
            query_id="q", user_id="", org_id="org-1",
            question="agent permission escalation anomaly",
        )


def test_query_non_human_user_id_rejected():
    for bad in ("ai", "system", "agent", "auto", "bot"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAssistantQuery(
                query_id="q", user_id=bad, org_id="org-1",
                question="agent permission escalation anomaly",
            )


def test_query_missing_org_id_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantQuery(
            query_id="q", user_id="zhuguan", org_id="",
            question="agent permission escalation anomaly",
        )


def test_query_empty_question_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantQuery(
            query_id="q", user_id="zhuguan", org_id="org-1", question="   "
        )


def test_query_forbidden_filter_key_rejected():
    # 越权键（cross_org / bypass_permission / as_user 等）结构上不可用于绕过隔离。
    for bad in ("cross_org", "bypass_permission", "as_user", "org_id"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAssistantQuery(
                query_id="q", user_id="zhuguan", org_id="org-1",
                question="agent permission escalation anomaly",
                filters={bad: "x"},
            )


def test_query_unknown_filter_key_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantQuery(
            query_id="q", user_id="zhuguan", org_id="org-1",
            question="agent permission escalation anomaly",
            filters={"unknown_key": "x"},
        )


def test_query_mutation_marker_in_question_rejected():
    # 红线③：问题不得要求 AI 自动改知识。
    for marker in ("auto_update_knowledge", "自动修改知识", "auto merge knowledge"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAssistantQuery(
                query_id="q", user_id="zhuguan", org_id="org-1",
                question=f"please {marker} for me",
            )


def test_query_advice_word_allowed_in_question():
    # 红线⑥ 约束的是 AI 输出，而非人提问；人可以说"有没有类似案例、大家一般怎么处理"。
    q = GovernanceAssistantQuery(
        query_id="q", user_id="zhuguan", org_id="org-1",
        question="有没有类似案例，大家一般建议怎么处理这种权限升级异常？",
    )
    assert q.question


# ===========================================================================
# 类别2：GovernanceAssistantContext 构造校验 / 只辅助分析（任务2）
# ===========================================================================


def test_context_valid_and_advisory_only():
    trace = _traceable("tr-ctx1")
    ctx = GovernanceAssistantContext(
        context_id="actx-1", query_id="q1", org_id="org-1",
        source_chain=trace, is_advisory_only=True,
    )
    assert ctx.is_advisory_only is True
    assert ctx.is_traceable is True
    assert ctx.is_empty is True


def test_context_advisory_only_false_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantContext(
            context_id="actx-1", query_id="q1", org_id="org-1",
            source_chain=_traceable("tr-ctx1"), is_advisory_only=False,
        )


def test_context_missing_source_chain_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantContext(
            context_id="actx-1", query_id="q1", org_id="org-1",
            source_chain=None, is_advisory_only=True,
        )


def test_context_non_candidate_entry_rejected():
    # 上下文只接受 GovernanceMatchCandidate，禁止塞入未经红线校验的对象。
    trace = _traceable("tr-ctx1")
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantContext(
            context_id="actx-1", query_id="q1", org_id="org-1",
            cases=[{"not": "a candidate"}], source_chain=trace,
            is_advisory_only=True,
        )


# ===========================================================================
# 类别3：GovernanceAssistantAgent 编排 / 只生成事实摘要（任务3）
# ===========================================================================


def test_understand_query_returns_retrieval_query():
    agent = _agent()
    q = _valid_query()
    kq = agent.understand_query(q)
    from agents.enterprise.agent_governance_knowledge_retrieval import GovernanceKnowledgeQuery
    assert isinstance(kq, GovernanceKnowledgeQuery)
    assert kq.query_text == q.question
    assert kq.user_id == q.user_id
    assert kq.org_id == q.org_id


def test_retrieve_context_builds_context_with_candidates():
    agent = _seeded_agent()
    q = _valid_query()
    ctx = agent.retrieve_context(q)
    assert isinstance(ctx, GovernanceAssistantContext)
    assert ctx.is_advisory_only is True
    # 命中 3.8.22 seeded 案例 / 模式 / 知识 / 3.8.21 已闭环事件。
    assert ctx.total_items >= 1
    assert ctx.source_chain is not None and ctx.is_traceable


def test_retrieve_context_empty_when_no_data():
    agent = _agent(audit=_audit())
    q = _valid_query()
    ctx = agent.retrieve_context(q)
    assert ctx.is_empty is True
    assert ctx.is_traceable is True  # 空也如实带来源链（query 自身）


def test_build_summary_returns_factual_draft():
    agent = _seeded_agent()
    q = _valid_query()
    ctx = agent.retrieve_context(q)
    draft = agent.build_summary(ctx)
    assert isinstance(draft, GovernanceAnswerDraft)
    assert draft.requires_human_review is True
    assert draft.contains_recommendation is False
    assert draft.references  # 引用来源非空
    assert 0.0 <= draft.confidence <= 1.0


def test_agent_stage_progression():
    agent = _seeded_agent()
    q = _valid_query()
    assert agent.stage_of(q.query_id) is None
    agent.submit_query(
        query_id=q.query_id, user_id=q.user_id, org_id=q.org_id,
        question=q.question, user=_admin(),
    )
    assert agent.stage_of(q.query_id) == GovernanceAssistantStage.QUERY_UNDERSTOOD
    ctx = agent.retrieve_context(q)
    assert agent.stage_of(q.query_id) == GovernanceAssistantStage.CONTEXT_RETRIEVED
    draft = agent.build_summary(ctx)
    assert agent.stage_of(q.query_id) == GovernanceAssistantStage.SUMMARY_BUILT


def test_agent_forbidden_methods_raise():
    agent = _agent()
    for name in (
        "auto_update_knowledge", "auto_merge_knowledge", "auto_apply_knowledge",
        "auto_execute_knowledge", "generate_policy", "recommend_policy",
        "auto_confirm", "auto_answer", "record_human_approval",
        "engineering_approved", "approve",
    ):
        assert _forbidden_access(agent, name), f"期望 {name} 被结构拦截"


# ===========================================================================
# 类别4：GovernanceAnswerDraft 引用来源 / 禁止建议（任务4）
# ===========================================================================


def _valid_draft(*, answer_id: str = "ans-1", query_id: str = "q1"):
    return GovernanceAnswerDraft(
        answer_id=answer_id, query_id=query_id,
        facts=["检索到相似历史案例 1 条（最高重合度 0.6）"],
        references=["case:case-1"], confidence=0.6,
        requires_human_review=True,
        summary="检索到相似历史案例 1 条，以上为只读事实材料。",
    )


def test_draft_valid_and_requires_human_review():
    d = _valid_draft()
    assert d.requires_human_review is True
    assert d.is_advisory_only is True
    assert d.is_traceable is True


def test_draft_requires_human_review_false_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAnswerDraft(
            answer_id="ans-1", query_id="q1",
            facts=["x"], references=["case:1"], confidence=0.5,
            requires_human_review=False,
        )


def test_draft_contains_recommendation_false():
    d = _valid_draft()
    assert d.contains_recommendation is False
    # 结构上不存在 recommendation / action / policy 字段。
    for forbidden_attr in ("recommendation", "action", "policy"):
        assert not hasattr(d, forbidden_attr), f"草稿不应含 {forbidden_attr} 字段"


def test_draft_confidence_bounds():
    for bad in (-0.1, 1.5, "x"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAnswerDraft(
                answer_id="ans-1", query_id="q1", facts=["x"],
                references=["case:1"], confidence=bad,
                requires_human_review=True,
            )


def test_draft_facts_advice_marker_rejected():
    # 红线⑥：答案文本不得含建议 / 责任判定语义。
    for marker in ("建议立即禁用", "应当整改", "判定责任", "must be disabled"):
        with pytest.raises(EnterpriseRedLineViolationError):
            GovernanceAnswerDraft(
                answer_id="ans-1", query_id="q1", facts=[marker],
                references=["case:1"], confidence=0.5,
                requires_human_review=True,
            )


# ===========================================================================
# 类别5：GovernanceAssistantReview 人工确认节点（任务5，红线②/⑥）
# ===========================================================================


def test_review_valid_user_constructs():
    r = GovernanceAssistantReview(
        review_id="rev-1", answer_id="ans-1", query_id="q1",
        reviewer_id="zhuguan", reviewer_kind=AuditActorKind.USER.value,
        decision=AssistantReviewDecision.ACKNOWLEDGED,
    )
    assert r.is_human_confirmed is True
    assert r.decision == AssistantReviewDecision.ACKNOWLEDGED


def test_review_non_user_kind_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantReview(
            review_id="rev-1", answer_id="ans-1", query_id="q1",
            reviewer_id="zhuguan", reviewer_kind=AuditActorKind.AI.value,
            decision=AssistantReviewDecision.ACKNOWLEDGED,
        )


def test_review_non_human_reviewer_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantReview(
            review_id="rev-1", answer_id="ans-1", query_id="q1",
            reviewer_id="ai", reviewer_kind=AuditActorKind.USER.value,
            decision=AssistantReviewDecision.ACKNOWLEDGED,
        )


def test_review_note_marker_rejected():
    with pytest.raises(EnterpriseRedLineViolationError):
        GovernanceAssistantReview(
            review_id="rev-1", answer_id="ans-1", query_id="q1",
            reviewer_id="zhuguan", reviewer_kind=AuditActorKind.USER.value,
            decision=AssistantReviewDecision.ACKNOWLEDGED,
            note="建议立即禁用该 agent",
        )


def test_confirm_answer_requires_human():
    # 红线⑥：AI 调用 confirm_answer 直接抛错。
    agent = _seeded_agent()
    q = _valid_query()
    agent.submit_query(
        query_id=q.query_id, user_id=q.user_id, org_id=q.org_id,
        question=q.question, user=_admin(),
    )
    ctx = agent.retrieve_context(q)
    draft = agent.build_summary(ctx)
    with pytest.raises(EnterpriseRedLineViolationError):
        agent.confirm_answer(
            answer_id=draft.answer_id, reviewer_id="ai",
            reviewer_kind=AuditActorKind.AI,
            decision=AssistantReviewDecision.ACKNOWLEDGED,
        )


def test_confirm_answer_creates_review_for_user():
    agent = _seeded_agent()
    q = _valid_query()
    agent.submit_query(
        query_id=q.query_id, user_id=q.user_id, org_id=q.org_id,
        question=q.question, user=_admin(),
    )
    ctx = agent.retrieve_context(q)
    draft = agent.build_summary(ctx)
    review = agent.confirm_answer(
        answer_id=draft.answer_id, reviewer_id="zhuguan",
        reviewer_kind=AuditActorKind.USER,
        decision=AssistantReviewDecision.ACKNOWLEDGED,
    )
    assert isinstance(review, GovernanceAssistantReview)
    assert review.is_human_confirmed is True
    assert agent.stage_of(q.query_id) == GovernanceAssistantStage.REVIEWED
    assert agent.review_of(draft.answer_id) is not None


# ===========================================================================
# 类别6：权限接入 —— 默认拒绝 / 跨组织隔离 / 可见性（任务7）
# ===========================================================================


def test_access_default_deny_without_policy_and_identity():
    # 既无权限策略也无身份层时，读路径默认拒绝（fail-closed）。
    agent = _agent()
    fake_user = object()
    with pytest.raises(EnterpriseIsolationError):
        agent.get_query("any", user=fake_user)


def test_cross_org_access_denied():
    # 跨组织提交问题被拒（红线⑥：治理知识默认按组织隔离）。
    agent = _agent(policy=_policy("org-1"), org_id="org-1")
    with pytest.raises(EnterpriseIsolationError):
        agent.submit_query(
            query_id="q", user_id="zhuguan", org_id="org-2",
            question="agent permission escalation anomaly", user=_admin(),
        )


def test_visibility_deny_blocks_access():
    # 知识可见性策略未授予时默认拒绝。
    class _DenyVisibility:
        def can_read(self, user) -> bool:
            return False

    agent = _agent(visibility=_DenyVisibility(), org_id="org-1")
    fake_user = object()
    with pytest.raises(EnterpriseIsolationError):
        agent.get_query("any", user=fake_user)


def test_access_granted_for_admin():
    agent = _agent(policy=_policy("org-1"), org_id="org-1")
    # admin 有 READ_RESOURCE 权限，访问不被隔离错误拒绝。
    q = agent.submit_query(
        query_id="q1", user_id="zhuguan", org_id="org-1",
        question="agent permission escalation anomaly", user=_admin(),
    )
    assert q.query_id == "q1"


# ===========================================================================
# 类别7：审计增强 —— 3 个新类别 + 记录方法（任务6）
# ===========================================================================


def test_audit_assistant_categories_present():
    vals = {x.value for x in AuditActionCategory}
    assert "agent_governance_assistant_query" in vals
    assert "agent_governance_assistant_context" in vals
    assert "agent_governance_assistant_draft" in vals


def test_audit_assistant_record_methods():
    svc = _audit()
    r1 = svc.record_agent_governance_assistant_query_action(
        record_id="gaq-1", actor_id="ai", target="q1", detail="submit")
    r2 = svc.record_agent_governance_assistant_context_action(
        record_id="gac-1", actor_id="ai", target="actx-1", detail="ctx")
    r3 = svc.record_agent_governance_assistant_draft_action(
        record_id="gad-1", actor_id="ai", target="ans-1", detail="draft")
    assert r1.category == AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_QUERY
    assert r2.category == AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_CONTEXT
    assert r3.category == AuditActionCategory.AGENT_GOVERNANCE_ASSISTANT_DRAFT
    # actor 真实：AI 登记默认 AI，不得伪造成人工审批。
    assert r1.actor_kind == AuditActorKind.AI


def test_audit_record_human_approval_forbidden():
    svc = _audit()
    assert _forbidden_access(svc, "record_human_approval")


def test_assistant_flow_emits_expected_audit_categories():
    agent = _seeded_agent()
    q = _valid_query()
    agent.submit_query(
        query_id=q.query_id, user_id=q.user_id, org_id=q.org_id,
        question=q.question, user=_admin(),
    )
    ctx = agent.retrieve_context(q)
    draft = agent.build_summary(ctx)
    agent.confirm_answer(
        answer_id=draft.answer_id, reviewer_id="zhuguan",
        reviewer_kind=AuditActorKind.USER,
        decision=AssistantReviewDecision.ACKNOWLEDGED,
    )
    cats = {r.category.value for r in agent._audit._records}
    assert "agent_governance_assistant_query" in cats
    assert "agent_governance_assistant_context" in cats
    assert "agent_governance_assistant_draft" in cats
    # 确认动作登记为真实 USER，而非 AI。
    confirm = [r for r in agent._audit._records
               if r.action == "human_confirm_assistant_answer"]
    assert confirm and confirm[0].actor_kind == AuditActorKind.USER


# ===========================================================================
# 类别8：六大红线整体验证（fail-closed）
# ===========================================================================


def test_safety_invariants_ok_true_when_disabled():
    # 红线①：禁用态下 safety_invariants_ok 为 True，构造路径放行。
    assert safety_invariants_ok() is True
    # 构造一个合法对象验证不抛错。
    q = _valid_query()
    assert q.query_id == "q1"


def test_forbidden_method_names_blocked_on_agent():
    # 红线②/③/④/⑤/⑥：所有 forbidden 方法名在结构上不可达。
    agent = _agent()
    for name in _ASSISTANT_FORBIDDEN:
        assert _forbidden_access(agent, name), f"期望 {name} 被结构拦截"


def test_no_engineering_approved_in_module_namespace():
    # 红线②：模块命名空间不应暴露 engineering_approved 作为可调用方法。
    assert not hasattr(GovernanceAssistantAgent, "engineering_approved")
    assert "engineering_approved" in _ASSISTANT_FORBIDDEN


def test_draft_is_advisory_only_and_no_recommendation():
    # 红线⑥：答案草稿永远只是辅助材料，不含建议 / 处置。
    d = _valid_draft()
    assert d.is_advisory_only is True
    assert d.contains_recommendation is False


def test_ai_cannot_self_confirm_answer_red_line():
    # 红线⑥：AI 无论如何无法代替治理责任人确认答案。
    agent = _seeded_agent()
    q = _valid_query()
    agent.submit_query(
        query_id=q.query_id, user_id=q.user_id, org_id=q.org_id,
        question=q.question, user=_admin(),
    )
    ctx = agent.retrieve_context(q)
    draft = agent.build_summary(ctx)
    for kind in (AuditActorKind.AI, AuditActorKind.SYSTEM):
        with pytest.raises(EnterpriseRedLineViolationError):
            agent.confirm_answer(
                answer_id=draft.answer_id, reviewer_id="bot",
                reviewer_kind=kind,
                decision=AssistantReviewDecision.ACKNOWLEDGED,
            )
