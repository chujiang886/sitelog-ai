"""Enterprise Agent Governance Knowledge & Continuous Improvement Layer —— 测试（任务8，Phase 3.8.22）。

八类测试：case / candidate / pattern / workflow / report / permission /
audit / red_line。

最高红线（fail-closed，6 条，与主理人 Phase 3.8.22 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动修改 Agent（auto_modify_agent / auto_update_agent 等被结构性拦截；
   案例 / 模式 / 知识文本命中自动改 Agent 语义即拒绝）；
④ 禁止 AI 自动修改治理策略（auto_update_policy / auto_apply_policy 等被拦截；
   知识候选 requires_human_review 恒 True、构造期只能 candidate 态；
   GovernancePattern.is_policy 恒 False，枚举无 policy 类）；
⑤ 禁止 AI 自动关闭治理任务（auto_close_task / close_task 等被拦截；
   本层对 3.8.21 治理任务纯只读，未闭环任务不得沉淀为案例）；
⑥ AI 不代替治理责任人（audit 禁止 record_human_approval；
   start_human_review / accept_candidate / reject_candidate 强制 USER；
   人工结论 actor 必须是真实人类标识；报告经验段只收人工采纳的知识）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_governance_knowledge import (
    GovernanceCase,
    GovernanceImprovementStage,
    GovernanceImprovementWorkflowService,
    GovernanceKnowledgeCandidate,
    GovernanceKnowledgeReport,
    GovernanceKnowledgeStatus,
    GovernanceKnowledgeType,
    GovernancePattern,
    GovernancePatternKind,
    _KNOWLEDGE_FORBIDDEN,
)
from agents.enterprise.agent_governance_workflow import (
    GovernanceTaskSourceType,
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


def _reviewer(org_id: str = "org-1"):
    """REVIEWER 只在 knowledge 作用域内，对 data 类治理知识默认拒绝。"""
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


def _expert(org_id: str = "org-1"):
    """EXPERT 只在 knowledge 作用域内（无 tool / data）。"""
    return _identity(org_id).make_user(
        user_id="exp", name="E", role_kind=RoleKind.EXPERT
    )


def _workflow(*, audit=None, org_id: str = "org-1") -> GovernanceWorkflowService:
    """3.8.21 治理流程服务（本层只读消费其已闭环任务事实）。"""
    return GovernanceWorkflowService(
        org_id=org_id, audit=audit, identity=_identity(org_id)
    )


def _service(*, audit=None, policy=None, workflow=None, org_id: str = "org-1"):
    return GovernanceImprovementWorkflowService(
        org_id=org_id,
        audit=audit,
        identity=_identity(org_id),
        permission_policy=policy,
        governance_workflow=workflow,
    )


def _closed_task(wf: GovernanceWorkflowService, task_id: str = "gt-1"):
    """在 3.8.21 中造一条**已由真实人工闭环**的治理任务（只读来源）。"""
    wf.create_task(
        task_id=task_id,
        source_type=GovernanceTaskSourceType.SECURITY_RISK,
        source_id="risk-1",
        title="安全风险候选待人工核查",
        agent_id="agent-a",
    )
    wf.assign_owner(
        task_id=task_id, assignee="eng-li", role="安全负责人",
        actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        timestamp="2026-08-07T10:00:00",
    )
    wf.start_processing(
        task_id=task_id, actor_kind=AuditActorKind.USER, actor_id="eng-li",
        source=f"task:{task_id}", timestamp="2026-08-07T10:10:00",
    )
    wf.submit_result(
        task_id=task_id, actor_kind=AuditActorKind.USER, actor_id="eng-li",
        result="已按线下流程核查并留存记录", timestamp="2026-08-07T11:00:00",
    )
    return wf.human_close(
        task_id=task_id, actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        human_result="人工确认已按线下规程处置完毕", completed_at="2026-08-07T12:00:00",
    )


def _case(svc, case_id: str = "gc-1", **kw):
    kw.setdefault("source_task_id", "gt-1")
    kw.setdefault("problem_pattern", "同一 Agent 连续三次触发同类越权读取告警")
    kw.setdefault("human_resolution", "责任人线下核对权限清单后收回多余读权限")
    kw.setdefault("resolved_by", "owner-zhang")
    kw.setdefault("agent_id", "agent-a")
    kw.setdefault("created_at", "2026-08-07T13:00:00")
    return svc.create_case(case_id=case_id, **kw)


def _candidate(svc, candidate_id: str = "gk-1", source_case: str = "gc-1", **kw):
    kw.setdefault("knowledge_type", GovernanceKnowledgeType.HANDLING_EXPERIENCE)
    kw.setdefault("content", "越权读取告警连续出现时，责任人线下核对权限清单可定位到多余授权")
    kw.setdefault("created_at", "2026-08-07T14:00:00")
    return svc.generate_candidate(
        candidate_id=candidate_id, source_case=source_case, **kw
    )


def _accept(svc, candidate_id: str = "gk-1", comment: str = "经线下复核，该经验属实，予以采纳"):
    svc.start_human_review(
        candidate_id=candidate_id, actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang", timestamp="2026-08-07T15:00:00",
    )
    return svc.accept_candidate(
        candidate_id=candidate_id, actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang", review_comment=comment,
        timestamp="2026-08-07T15:30:00",
    )


# ---------------------------------------------------------------------------
# 一、case：治理案例（任务1，要求人工结果来源）
# ---------------------------------------------------------------------------

def test_case_fields_and_human_resolution_fact() -> None:
    """案例字段严格对应主理人指令，且必须带真实人工处理结论（红线⑥）。"""
    case = GovernanceCase(
        case_id="gc-1",
        source_task_id="gt-1",
        agent_id="agent-a",
        problem_pattern="同类越权读取告警连续出现",
        human_resolution="责任人线下收回多余读权限",
        source_trace=_traceable(),
        created_at="2026-08-07T13:00:00",
        resolved_by="owner-zhang",
        recorded_by="ai",
    )
    assert case.is_human_resolved is True
    assert case.is_traceable is True
    assert "gc-1" in case.summary()
    # 登记者如实记为 ai，绝不伪装成人工（红线⑥）。
    assert case.recorded_by == "ai" and case.resolved_by == "owner-zhang"


def test_case_rejects_missing_source_task_id() -> None:
    """无来源治理任务即拒绝：禁止凭空造案例（红线⑤/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="source_task_id"):
        GovernanceCase(
            case_id="gc-x", source_task_id="", problem_pattern="p",
            human_resolution="r", resolved_by="owner-zhang",
            source_trace=_traceable(),
        )


def test_case_rejects_missing_human_resolution() -> None:
    """无人工结论即拒绝：AI 不得代填治理结果（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="human_resolution"):
        GovernanceCase(
            case_id="gc-x", source_task_id="gt-1", problem_pattern="p",
            human_resolution="", resolved_by="owner-zhang",
            source_trace=_traceable(),
        )


def test_case_rejects_missing_problem_pattern() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="problem_pattern"):
        GovernanceCase(
            case_id="gc-x", source_task_id="gt-1", problem_pattern="",
            human_resolution="r", resolved_by="owner-zhang",
            source_trace=_traceable(),
        )


@pytest.mark.parametrize("bad", ["ai", "system", "ai-bot", "auto_agent", "自动-01"])
def test_case_rejects_non_human_resolved_by(bad: str) -> None:
    """处理人是非人类标识即拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类标识"):
        GovernanceCase(
            case_id="gc-x", source_task_id="gt-1", problem_pattern="p",
            human_resolution="r", resolved_by=bad, source_trace=_traceable(),
        )


def test_case_accepts_human_name_starting_with_ai_letters() -> None:
    """``aileen`` 等正常人名不得被误伤（只做整体等值 / 前缀分段判断）。"""
    case = GovernanceCase(
        case_id="gc-2", source_task_id="gt-1", problem_pattern="p",
        human_resolution="r", resolved_by="aileen", source_trace=_traceable(),
    )
    assert case.resolved_by == "aileen"


def test_case_rejects_untraceable() -> None:
    """无来源链即拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="无来源链"):
        GovernanceCase(
            case_id="gc-x", source_task_id="gt-1", problem_pattern="p",
            human_resolution="r", resolved_by="owner-zhang",
            source_trace=SourceTrace(trace_id="empty"),
        )


@pytest.mark.parametrize(
    "text,rule",
    [
        ("已 auto_modify_agent 处理完毕", "红线③"),
        ("系统自动修改策略后关闭", "红线"),
        ("已 auto_close 该任务", "红线⑤"),
    ],
)
def test_case_rejects_forbidden_semantics_in_text(text: str, rule: str) -> None:
    """案例自由文本命中自动改 Agent / 改策略 / 自动关闭语义即拒绝（红线③/④/⑤）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceCase(
            case_id="gc-x", source_task_id="gt-1",
            problem_pattern="p", human_resolution=text,
            resolved_by="owner-zhang", source_trace=_traceable(),
        )


def test_case_model_has_no_mutation_methods() -> None:
    """案例模型层不提供任何 modify_agent / update_policy / close_task 能力。"""
    case = GovernanceCase(
        case_id="gc-3", source_task_id="gt-1", problem_pattern="p",
        human_resolution="r", resolved_by="owner-zhang", source_trace=_traceable(),
    )
    for banned in (
        "modify_agent", "update_policy", "close_task", "approve", "auto_close_task"
    ):
        assert not hasattr(case, banned)


# ---------------------------------------------------------------------------
# 二、candidate：治理知识候选（任务2，只能候选）
# ---------------------------------------------------------------------------

def test_knowledge_type_enum_is_fact_only_without_policy() -> None:
    """知识类型只描述事实，**不存在** policy / rule 类（红线④）。"""
    values = {t.value for t in GovernanceKnowledgeType}
    assert values == {
        "problem_pattern", "handling_experience",
        "prevention_fact", "governance_lesson",
    }
    for banned in ("policy", "rule", "mandatory_standard", "enforcement"):
        assert banned not in values


def test_knowledge_status_enum_has_no_ai_terminal_state() -> None:
    """状态机四态且**无 AI 终态**（红线⑥）。"""
    values = {s.value for s in GovernanceKnowledgeStatus}
    assert values == {"candidate", "in_human_review", "accepted", "rejected"}
    for banned in ("auto_accepted", "published_by_ai", "ai_approved", "auto_adopted"):
        assert banned not in values


def test_candidate_is_candidate_only_by_construction() -> None:
    """构造出来只能是 candidate 候选态，且 requires_human_review 恒 True（红线④/⑥）。"""
    cand = GovernanceKnowledgeCandidate(
        candidate_id="gk-1", source_case="gc-1",
        knowledge_type=GovernanceKnowledgeType.HANDLING_EXPERIENCE,
        content="线下核对权限清单可定位到多余授权",
        evidence=["case:gc-1", "governance_task:gt-1"],
        generated_by="ai",
    )
    assert cand.status is GovernanceKnowledgeStatus.CANDIDATE
    assert cand.requires_human_review is True
    assert cand.is_candidate_only is True and cand.is_accepted is False
    assert cand.evidence_count == 2
    assert cand.reviewed_by == "" and cand.reviewed_at == ""
    assert "requires_human_review=True" in cand.summary()


def test_candidate_rejects_requires_human_review_false() -> None:
    """置 requires_human_review=False 即拒绝：候选永远需要人工审核（红线④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="requires_human_review"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1", content="c",
            evidence=["case:gc-1"], requires_human_review=False,
        )


@pytest.mark.parametrize(
    "status", [GovernanceKnowledgeStatus.ACCEPTED, GovernanceKnowledgeStatus.REJECTED]
)
def test_candidate_rejects_prefilled_terminal_status(status) -> None:
    """构造期直接落终态 = AI 自我审核，拒绝（红线④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="构造期落"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1", content="c",
            evidence=["case:gc-1"], status=status,
        )


def test_candidate_rejects_prefilled_review_facts() -> None:
    """构造期预填 reviewed_by / reviewed_at = 伪造人工审核事实，拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="reviewed_by"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1", content="c",
            evidence=["case:gc-1"], reviewed_by="owner-zhang",
        )


def test_candidate_rejects_missing_evidence_and_source_case() -> None:
    """无证据 / 无来源案例即拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="evidence"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1", content="c", evidence=["  "],
        )
    with pytest.raises(EnterpriseRedLineViolationError, match="source_case"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="", content="c", evidence=["case:gc-1"],
        )


def test_candidate_rejects_ai_generated_advice_content() -> None:
    """AI 生成的候选不得挟带处置建议 / 责任判定（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1",
            content="建议立即禁用该 Agent", evidence=["case:gc-1"],
            generated_by="ai",
        )


def test_candidate_allows_human_authored_experience_text() -> None:
    """人工撰写的经验文本不受 AI 建议语义拦截（拦截只针对 AI 产出）。"""
    cand = GovernanceKnowledgeCandidate(
        candidate_id="gk-2", source_case="gc-1",
        content="复盘建议：责任人应保留线下核对记录",
        evidence=["case:gc-1"], generated_by="owner-zhang",
    )
    assert cand.is_candidate_only is True


def test_candidate_rejects_policy_semantics_even_from_human() -> None:
    """任何来源的候选文本都不得挟带自动改策略语义（红线④）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceKnowledgeCandidate(
            candidate_id="gk-x", source_case="gc-1",
            content="此后由系统自动下发策略", evidence=["case:gc-1"],
            generated_by="owner-zhang",
        )


def test_candidate_model_has_no_accept_or_publish_methods() -> None:
    """候选模型层不提供 accept / reject / publish / promote 能力（红线④/⑥）。"""
    cand = GovernanceKnowledgeCandidate(
        candidate_id="gk-3", source_case="gc-1", content="c", evidence=["case:gc-1"],
    )
    for banned in (
        "accept", "reject", "publish", "promote", "promote_to_policy", "approve"
    ):
        assert not hasattr(cand, banned)


# ---------------------------------------------------------------------------
# 三、pattern：治理模式（任务3，事实归纳，禁止自动策略）
# ---------------------------------------------------------------------------

def test_pattern_kind_enum_is_three_fact_kinds_without_policy() -> None:
    """模式类型严格三类（风险 / 异常 / 处理），**不存在** policy 类（红线④）。"""
    values = {k.value for k in GovernancePatternKind}
    assert values == {"risk", "anomaly", "handling"}
    for banned in ("policy", "rule", "enforcement", "standard"):
        assert banned not in values


def test_pattern_is_never_policy() -> None:
    """``is_policy`` 恒为 False：模式永远只是事实归纳（红线④）。"""
    pat = GovernancePattern(
        pattern_id="gp-1", pattern_kind=GovernancePatternKind.RISK,
        description="同类越权读取告警在三个案例中反复出现",
        case_ids=["gc-1", "gc-2", "gc-3"], agent_id="agent-a",
    )
    assert pat.is_policy is False
    assert pat.occurrence_count == 3
    assert pat.is_traceable is True
    assert "is_policy=False" in pat.summary()


def test_pattern_rejects_empty_case_evidence() -> None:
    """无案例支撑即拒绝：禁止凭空造模式（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="case_ids"):
        GovernancePattern(pattern_id="gp-x", description="d", case_ids=[])
    with pytest.raises(EnterpriseRedLineViolationError, match="case_ids"):
        GovernancePattern(pattern_id="gp-x", description="d", case_ids=["  ", ""])


def test_pattern_rejects_missing_description() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="description"):
        GovernancePattern(pattern_id="gp-x", description="", case_ids=["gc-1"])


@pytest.mark.parametrize(
    "bad",
    ["建议禁用该 Agent", "recommend disabling this agent", "应当整改该配置", "判定责任在运维"],
)
def test_pattern_rejects_advice_or_accountability_text(bad: str) -> None:
    """模式只做事实归纳，禁止处置建议 / 责任判定（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernancePattern(pattern_id="gp-x", description=bad, case_ids=["gc-1"])


def test_pattern_rejects_policy_semantics_text() -> None:
    """模式描述不得挟带自动改策略语义（红线④）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernancePattern(
            pattern_id="gp-x", description="后续 auto_apply_policy 生效",
            case_ids=["gc-1"],
        )


def test_pattern_model_has_no_policy_conversion_methods() -> None:
    """模式模型层不提供 to_policy / apply / enforce / activate 能力（红线④）。"""
    pat = GovernancePattern(
        pattern_id="gp-2", description="同类异常反复出现", case_ids=["gc-1"],
    )
    for banned in ("to_policy", "apply", "enforce", "activate", "publish_policy"):
        assert not hasattr(pat, banned)


# ---------------------------------------------------------------------------
# 四、workflow：持续改进流程（任务4，人工审核）
# ---------------------------------------------------------------------------

def test_stage_enum_has_five_states_without_ai_terminal() -> None:
    """改进流程严格五态，且**不存在** AI 终态（红线⑥）。"""
    values = {s.value for s in GovernanceImprovementStage}
    assert values == {
        "case_created", "candidate_generated", "human_review", "accepted", "rejected"
    }
    for banned in ("auto_accepted", "auto_published", "ai_reviewed", "auto_adopted"):
        assert banned not in values


def test_full_chain_case_to_accepted_knowledge() -> None:
    """完整链路：治理事件 → 人工处理 → 案例 → 候选 → 人工审核 → 沉淀。"""
    wf = _workflow()
    _closed_task(wf)
    svc = _service(audit=_audit(), workflow=wf)
    case = _case(svc)
    assert svc.stage_of("gc-1") is GovernanceImprovementStage.CASE_CREATED
    assert case.source_task_id == "gt-1"

    cand = _candidate(svc)
    assert cand.is_candidate_only is True
    assert svc.stage_of("gc-1") is GovernanceImprovementStage.CANDIDATE_GENERATED

    svc.start_human_review(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang", timestamp="2026-08-07T15:00:00",
    )
    assert svc.stage_of("gc-1") is GovernanceImprovementStage.HUMAN_REVIEW

    accepted = svc.accept_candidate(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang", review_comment="经线下复核属实，予以采纳",
        timestamp="2026-08-07T15:30:00",
    )
    assert accepted.is_accepted is True
    assert accepted.reviewed_by == "owner-zhang"
    assert svc.stage_of("gc-1") is GovernanceImprovementStage.ACCEPTED


def test_reject_candidate_by_human() -> None:
    """人工驳回同样是终态入口，且必须由真实 USER 执行（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    svc.start_human_review(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
    )
    cand = svc.reject_candidate(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang", review_comment="证据不足，不予采纳",
    )
    assert cand.status is GovernanceKnowledgeStatus.REJECTED
    assert svc.stage_of("gc-1") is GovernanceImprovementStage.REJECTED


def test_create_case_rejects_unclosed_governance_task() -> None:
    """来源治理任务未由人工闭环即拒绝沉淀（红线⑤/⑥）。"""
    wf = _workflow()
    wf.create_task(
        task_id="gt-open", source_type=GovernanceTaskSourceType.SECURITY_RISK,
        source_id="risk-2", title="待处理",
    )
    svc = _service(audit=_audit(), workflow=wf)
    with pytest.raises(EnterpriseRedLineViolationError, match="未闭环"):
        _case(svc, case_id="gc-open", source_task_id="gt-open")


def test_create_case_reads_workflow_without_mutating_it() -> None:
    """本层对 3.8.21 治理任务**纯只读**：沉淀案例不改变任务任何状态（红线⑤）。"""
    wf = _workflow()
    _closed_task(wf)
    before = wf._tasks["gt-1"]
    before_status, before_closed_by = before.status, before.closed_by
    svc = _service(audit=_audit(), workflow=wf)
    _case(svc)
    after = wf._tasks["gt-1"]
    assert after.status is before_status and after.closed_by == before_closed_by
    assert len(wf._tasks) == 1


@pytest.mark.parametrize(
    "actor_kind", [AuditActorKind.AI, AuditActorKind.SYSTEM, None]
)
def test_ai_cannot_start_review_or_conclude(actor_kind) -> None:
    """AI 无论如何无法自我审核 / 自我采纳 / 自我驳回（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.start_human_review(
            candidate_id="gk-1", actor_kind=actor_kind, actor_id="ai"
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.accept_candidate(
            candidate_id="gk-1", actor_kind=actor_kind, actor_id="ai",
            review_comment="ok",
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.reject_candidate(
            candidate_id="gk-1", actor_kind=actor_kind, actor_id="ai",
            review_comment="ok",
        )


def test_human_review_rejects_non_human_actor_id() -> None:
    """actor_kind=USER 但 actor_id 是非人类标识，同样拒绝（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类标识"):
        svc.start_human_review(
            candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="ai-bot"
        )


def test_accept_requires_human_review_comment() -> None:
    """人工审核结论必须附人工意见，AI 不得代替下结论（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    svc.start_human_review(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang"
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="review_comment"):
        svc.accept_candidate(
            candidate_id="gk-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-zhang", review_comment="   ",
        )


def test_review_comment_rejects_auto_policy_semantics() -> None:
    """人工审核意见也不得挟带自动改策略 / 自动关任务语义（红线④/⑤）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    svc.start_human_review(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang"
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        svc.accept_candidate(
            candidate_id="gk-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-zhang", review_comment="采纳后 auto_apply_policy",
        )


def test_conclude_requires_prior_human_review() -> None:
    """未经人工 start_human_review 不得直接下结论（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="start_human_review"):
        svc.accept_candidate(
            candidate_id="gk-1", actor_kind=AuditActorKind.USER,
            actor_id="owner-zhang", review_comment="直接采纳",
        )


def test_stage_transitions_are_forward_only() -> None:
    """阶段只前进不回退：已终态后不得再推进（红线④/⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    _accept(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="非法阶段迁移"):
        svc.generate_candidate(
            candidate_id="gk-9", source_case="gc-1",
            knowledge_type=GovernanceKnowledgeType.GOVERNANCE_LESSON,
            content="另一条经验事实", evidence=["case:gc-1"],
        )


def test_repeat_human_review_is_rejected() -> None:
    """审核只前进不回退，重复审核直接拒绝（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    svc.start_human_review(
        candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang"
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="重复审核"):
        svc.start_human_review(
            candidate_id="gk-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang"
        )


def test_service_rejects_unknown_case_or_candidate() -> None:
    """禁止凭空推进流程：案例 / 候选不存在即拒绝（红线⑥）。"""
    svc = _service(audit=_audit())
    with pytest.raises(EnterpriseRedLineViolationError, match="找不到治理案例"):
        _candidate(svc, source_case="gc-none")
    with pytest.raises(EnterpriseRedLineViolationError, match="找不到知识候选"):
        svc.start_human_review(
            candidate_id="gk-none", actor_kind=AuditActorKind.USER,
            actor_id="owner-zhang",
        )


def test_service_rejects_duplicate_ids() -> None:
    """禁止覆盖既有治理事实（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="重复创建治理案例"):
        _case(svc)
    _candidate(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="重复创建知识候选"):
        _candidate(svc)


def test_record_pattern_requires_existing_cases() -> None:
    """模式归纳的案例证据必须真实存在（红线⑥）。"""
    svc = _service(audit=_audit())
    _case(svc)
    with pytest.raises(EnterpriseRedLineViolationError, match="不存在"):
        svc.record_pattern(
            pattern_id="gp-x", pattern_kind=GovernancePatternKind.RISK,
            description="同类风险反复出现", case_ids=["gc-1", "gc-missing"],
        )
    pat = svc.record_pattern(
        pattern_id="gp-1", pattern_kind=GovernancePatternKind.RISK,
        description="同类风险反复出现", case_ids=["gc-1"],
        observed_at="2026-08-07T16:00:00",
    )
    assert pat.is_policy is False and pat.occurrence_count == 1


def test_service_forbids_disabled_state(monkeypatch) -> None:
    """engineering_enabled=true 时服务构造与写路径全部 fail-closed（红线①）。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    assert safety_invariants_ok() is False
    with pytest.raises(EnterpriseRedLineViolationError, match="safety_invariants_ok"):
        GovernanceImprovementWorkflowService(org_id="org-1")


# ---------------------------------------------------------------------------
# 五、report：治理知识报告（任务5，案例/模式/经验/来源链）
# ---------------------------------------------------------------------------

def test_report_contains_four_sections_with_source_trace() -> None:
    """报告含案例 + 模式 + 经验 + 来源链四段（任务5）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    svc.record_pattern(
        pattern_id="gp-1", pattern_kind=GovernancePatternKind.HANDLING,
        description="人工反复采用线下核对权限清单的处理方式", case_ids=["gc-1"],
    )
    _candidate(svc)
    _accept(svc)
    report = svc.build_knowledge_report(
        user=_admin(), report_id="gr-1", generated_at="2026-08-07T16:30:00",
    )
    assert report.case_count == 1
    assert report.pattern_count == 1
    assert report.experience_count == 1
    assert report.is_traceable is True
    assert "case:gc-1" in report.render_source()
    assert "accepted_knowledge:gk-1" in report.render_source()
    assert "gr-1" in report.summary()


def test_report_excludes_unreviewed_candidates() -> None:
    """未经人工采纳的候选不得进入沉淀报告（红线④/⑥）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    _candidate(svc)  # 仅候选，未审核
    report = svc.build_knowledge_report(user=_admin(), report_id="gr-2")
    assert report.experience_count == 0
    assert report.case_count == 1


def test_report_model_rejects_unaccepted_experience() -> None:
    """直接构造报告时混入未采纳候选即拒绝（红线④/⑥）。"""
    cand = GovernanceKnowledgeCandidate(
        candidate_id="gk-5", source_case="gc-1", content="c", evidence=["case:gc-1"],
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="人工审核采纳"):
        GovernanceKnowledgeReport(
            report_id="gr-x", experiences=[cand], source_trace=_traceable("tr-r"),
        )


def test_report_rejects_untraceable_and_empty() -> None:
    """无来源链 / 无任何事实内容即拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="无来源链"):
        GovernanceKnowledgeReport(
            report_id="gr-x", source_trace=SourceTrace(trace_id="empty"),
        )
    with pytest.raises(EnterpriseRedLineViolationError, match="无任何事实内容"):
        GovernanceKnowledgeReport(report_id="gr-x", source_trace=_traceable("tr-r2"))


def test_build_report_rejects_when_no_facts() -> None:
    """服务层无任何案例 / 模式 / 经验时拒绝出报告（红线⑥）。"""
    svc = _service(audit=_audit(), policy=_policy())
    with pytest.raises(EnterpriseRedLineViolationError, match="无任何事实来源"):
        svc.build_knowledge_report(user=_admin(), report_id="gr-empty")


def test_report_can_be_fetched_read_only() -> None:
    """报告可只读取回，且不含任何策略生效语义。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    svc.build_knowledge_report(user=_admin(), report_id="gr-3")
    got = svc.get_knowledge_report(user=_admin(), report_id="gr-3")
    assert got is not None and got.report_id == "gr-3"
    text = got.summary()
    for banned in ("approved", "policy_applied", "engineering_approved"):
        assert banned not in text


# ---------------------------------------------------------------------------
# 六、permission：权限接入（任务7，治理知识隔离，默认拒绝）
# ---------------------------------------------------------------------------

def test_admin_allowed_knowledge_scope() -> None:
    """ADMIN 在 knowledge 作用域内，可读取治理知识数据。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    items = svc.list_cases(user=_admin())
    assert len(items) == 1 and items[0].case_id == "gc-1"


def test_reviewer_denied_data_scope_knowledge() -> None:
    """REVIEWER 只在 knowledge 作用域，对 data 类治理知识默认拒绝（红线⑥）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    with pytest.raises(EnterpriseIsolationError):
        svc.list_cases(user=_reviewer(), resource_category="data")


def test_expert_denied_tool_scope_knowledge() -> None:
    """EXPERT 只在 knowledge 作用域，对 tool 类默认拒绝（默认拒绝原则）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    with pytest.raises(EnterpriseIsolationError):
        svc.list_candidates(user=_expert(), resource_category="tool")


def test_all_read_paths_are_permission_gated() -> None:
    """所有只读查询路径统一受权限隔离（默认拒绝）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    bad = _reviewer()
    for call in (
        lambda: svc.list_cases(user=bad, resource_category="data"),
        lambda: svc.list_patterns(user=bad, resource_category="data"),
        lambda: svc.list_candidates(user=bad, resource_category="data"),
        lambda: svc.get_knowledge_report(user=bad, report_id="x", resource_category="data"),
        lambda: svc.build_knowledge_report(
            user=bad, report_id="y", resource_category="data"
        ),
    ):
        with pytest.raises(EnterpriseIsolationError):
            call()


def test_list_filters_work_under_permission() -> None:
    """过滤条件正常工作（agent_id / status / source_case / pattern_kind）。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    svc.record_pattern(
        pattern_id="gp-1", pattern_kind=GovernancePatternKind.ANOMALY,
        description="同类异常反复出现", case_ids=["gc-1"],
    )
    _candidate(svc)
    admin = _admin()
    assert len(svc.list_cases(user=admin, agent_id="agent-a")) == 1
    assert len(svc.list_cases(user=admin, agent_id="agent-zzz")) == 0
    assert len(svc.list_cases(user=admin, source_task_id="gt-1")) == 1
    assert len(
        svc.list_patterns(user=admin, pattern_kind=GovernancePatternKind.ANOMALY)
    ) == 1
    assert len(
        svc.list_patterns(user=admin, pattern_kind=GovernancePatternKind.RISK)
    ) == 0
    assert len(
        svc.list_candidates(user=admin, status=GovernanceKnowledgeStatus.CANDIDATE)
    ) == 1
    assert len(svc.list_candidates(user=admin, source_case="gc-1")) == 1


def test_knowledge_service_is_read_only_on_policy_and_agent() -> None:
    """本层对治理策略 / Agent 纯只读：不存在任何写/改方法（红线③/④）。"""
    svc = _service(policy=_policy())
    for banned in (
        "update_policy", "apply_policy", "auto_update_policy", "auto_apply_policy",
        "modify_agent", "update_agent", "auto_modify_agent", "auto_update_agent",
        "grant_permission", "change_permission",
    ):
        assert _forbidden_access(svc, banned)
    assert not [a for a in dir(svc) if a.startswith("set_")]


# ---------------------------------------------------------------------------
# 七、audit：审计增强（+3 类，actor 真实，禁 record_human_approval，红线⑥）
# ---------------------------------------------------------------------------

def test_audit_has_three_new_knowledge_categories() -> None:
    """审计枚举新增 case / knowledge / improvement 三类，总数 59；3.8.23 再 +3 → 62。"""
    members = list(AuditActionCategory.__members__.values())
    values = {m.value for m in members}
    assert "agent_governance_case" in values
    assert "agent_governance_knowledge" in values
    assert "agent_governance_improvement" in values
    assert len(members) == 69


def test_audit_records_case_and_knowledge_and_improvement() -> None:
    """三类审计在对应链路节点各自落库，actor 如实。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    _accept(svc)
    cats = [r.category for r in svc._audit._records]
    assert AuditActionCategory.AGENT_GOVERNANCE_CASE in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE in cats
    assert AuditActionCategory.AGENT_GOVERNANCE_IMPROVEMENT in cats


def test_audit_actor_kind_is_truthful() -> None:
    """AI 动作如实标 ai，人工审核如实标 user（红线⑥：绝不伪装）。"""
    svc = _service(audit=_audit())
    _case(svc)
    _candidate(svc)
    _accept(svc)
    ai_records = [
        r for r in svc._audit._records
        if r.category is AuditActionCategory.AGENT_GOVERNANCE_KNOWLEDGE
    ]
    assert ai_records and all(r.actor_kind is AuditActorKind.AI for r in ai_records)
    human_records = [
        r for r in svc._audit._records
        if r.category is AuditActionCategory.AGENT_GOVERNANCE_IMPROVEMENT
    ]
    assert human_records
    assert all(r.actor_kind is AuditActorKind.USER for r in human_records)
    assert all(r.actor_id == "owner-zhang" for r in human_records)


def test_audit_records_report_generation() -> None:
    """知识报告汇编落 knowledge 类审计。"""
    svc = _service(audit=_audit(), policy=_policy())
    _case(svc)
    svc.build_knowledge_report(user=_admin(), report_id="gr-4")
    assert any(
        r.action == "build_governance_knowledge_report"
        for r in svc._audit._records
    )


def test_audit_forbids_record_human_approval() -> None:
    """审计层不存在 record_human_approval（红线⑥：AI 不冒充人工确认）。"""
    audit = _audit()
    assert _forbidden_access(audit, "record_human_approval")
    assert "record_human_approval" in _KNOWLEDGE_FORBIDDEN


def test_audit_query_filters_new_categories() -> None:
    """新增三类可经 query 过滤（只读）。"""
    svc = _service(audit=_audit())
    _case(svc)
    got = svc._audit.query(category=AuditActionCategory.AGENT_GOVERNANCE_CASE)
    assert len(got) == 1 and got[0].target == "gc-1"


# ---------------------------------------------------------------------------
# 八、red_line：六条最高红线（fail-closed）
# ---------------------------------------------------------------------------

def test_red_line_1_engineering_enabled_stays_false() -> None:
    """红线①：全程 engineering_enabled=false。"""
    assert safety_invariants_ok() is True
    layer = EnterpriseOperationLayer(org_id="org-1")
    assert layer.is_activation_safe() is True


def test_red_line_2_no_engineering_approved_symbol() -> None:
    """红线②：engineering_approved 在结构上不可达。"""
    svc = _service()
    assert _forbidden_access(svc, "engineering_approved")
    assert "engineering_approved" in _KNOWLEDGE_FORBIDDEN
    import agents.enterprise.agent_governance_knowledge as mod
    assert not hasattr(mod, "engineering_approved")


@pytest.mark.parametrize(
    "banned",
    [
        "auto_modify_agent", "auto_update_agent", "modify_agent", "update_agent",
        "auto_disable_agent", "disable_agent", "auto_retrain_agent",
        "auto_rewrite_prompt", "rewrite_prompt",
    ],
)
def test_red_line_3_forbids_auto_agent_modification(banned: str) -> None:
    """红线③：禁 AI 自动修改 Agent（结构级拦截）。"""
    svc = _service()
    assert banned in _KNOWLEDGE_FORBIDDEN
    assert _forbidden_access(svc, banned)


@pytest.mark.parametrize(
    "banned",
    [
        "auto_update_policy", "auto_apply_policy", "update_policy", "apply_policy",
        "auto_promote_knowledge", "promote_knowledge_to_policy",
        "auto_accept_candidate", "auto_publish_knowledge",
    ],
)
def test_red_line_4_forbids_auto_policy_change(banned: str) -> None:
    """红线④：禁 AI 自动修改治理策略 / 自动采纳知识（结构级拦截）。"""
    svc = _service()
    assert banned in _KNOWLEDGE_FORBIDDEN
    assert _forbidden_access(svc, banned)


@pytest.mark.parametrize(
    "banned",
    [
        "auto_close", "auto_close_task", "close_task", "close_governance_task",
        "auto_complete_task", "complete_task", "auto_resolve_task", "auto_signoff",
    ],
)
def test_red_line_5_forbids_auto_task_closure(banned: str) -> None:
    """红线⑤：禁 AI 自动关闭治理任务（结构级拦截）。"""
    svc = _service()
    assert banned in _KNOWLEDGE_FORBIDDEN
    assert _forbidden_access(svc, banned)


@pytest.mark.parametrize(
    "banned",
    [
        "act_as_governance_owner", "take_governance_ownership",
        "assume_governance_responsibility", "auto_review", "auto_review_candidate",
        "auto_confirm_knowledge", "auto_decide_governance", "auto_conclude_case",
        "auto_recommend", "recommend_action", "auto_advise", "auto_suggest",
    ],
)
def test_red_line_6_forbids_replacing_governance_owner(banned: str) -> None:
    """红线⑥：禁 AI 代替治理责任人（结构级拦截）。"""
    svc = _service()
    assert banned in _KNOWLEDGE_FORBIDDEN
    assert _forbidden_access(svc, banned)


def test_red_line_base_forbidden_items_present() -> None:
    """基座 forbidden 项（approve/quote/pricing/sign/authorize）全部覆盖（红线②）。"""
    for banned in ("approve", "quote", "pricing", "sign", "authorize"):
        assert banned in _KNOWLEDGE_FORBIDDEN


def test_red_line_all_write_paths_fail_closed(monkeypatch) -> None:
    """启用态下所有写路径 fail-closed（红线①）。"""
    svc = _service(audit=_audit())
    _case(svc)
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        _case(svc, case_id="gc-2")
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.record_pattern(
            pattern_id="gp-2", pattern_kind=GovernancePatternKind.RISK,
            description="d", case_ids=["gc-1"],
        )
    with pytest.raises(EnterpriseRedLineViolationError):
        _candidate(svc, candidate_id="gk-2")


def test_enterprise_layer_mounts_knowledge_service() -> None:
    """聚合门面挂载治理知识层，并与 3.8.21 治理流程服务同源（任务7）。"""
    layer = EnterpriseOperationLayer(org_id="org-1")
    svc = layer.agent_governance_knowledge
    assert isinstance(svc, GovernanceImprovementWorkflowService)
    assert svc._governance_workflow is layer.agent_governance_workflow
    assert svc._audit is layer.audit
    assert svc._permission_policy is layer.agent_permission_policy


def test_module_exports_nine_public_symbols() -> None:
    """模块导出面严格受控，且不含任何策略 / 修改能力符号。"""
    import agents.enterprise.agent_governance_knowledge as mod
    assert set(mod.__all__) == {
        "GovernanceCase",
        "GovernancePatternKind",
        "GovernancePattern",
        "GovernanceKnowledgeType",
        "GovernanceKnowledgeStatus",
        "GovernanceKnowledgeCandidate",
        "GovernanceKnowledgeReport",
        "GovernanceImprovementStage",
        "GovernanceImprovementWorkflowService",
        "_KNOWLEDGE_FORBIDDEN",
    }
