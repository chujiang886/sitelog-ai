"""Enterprise Agent Governance Workflow & Accountability Layer —— 测试（任务8，Phase 3.8.21）。

八类测试：task / assignment / action / workflow / closure / permission /
audit / red_line。

最高红线（fail-closed，6 条，与主理人 Phase 3.8.21 指令一致）：
① 保持 engineering_enabled=false（构造/写路径断言 safety_invariants_ok）；
② 不输出 engineering_approved（forbidden 方法名被结构性拦截）；
③ 禁止 AI 自动整改风险（auto_remediate / auto_fix / auto_resolve 等被拦截；
   动作记录命中自动整改语义即拒绝；AI 无法自动关闭任务）；
④ 禁止 AI 自动分配责任（auto_assign / auto_delegate 等被拦截；
   GovernanceTask 构造期禁填 owner_id；assign_owner 强制 USER；
   assignee 必须是真实人类标识）；
⑤ 禁止 AI 自动修改权限策略（auto_change_permission / auto_modify_policy 等被
   拦截；本层对权限策略纯只读）；
⑥ AI 不代替治理责任人（audit 禁止 record_human_approval；任务须有 source_id；
   闭环报告须有来源链与人工结论；completed 只能人工确认）。

注：启用态通过 monkeypatch agents.enterprise.red_line.load_engineering_enabled 注入，
**不修改** verified.json / config.yaml / engineering_enabled 文件。
"""

from __future__ import annotations

import pytest

from agents.enterprise.agent_governance_workflow import (
    GovernanceActionRecord,
    GovernanceAssignment,
    GovernanceClosureReport,
    GovernanceTask,
    GovernanceTaskSourceType,
    GovernanceTaskStatus,
    GovernanceWorkflowService,
    _GOVERNANCE_FORBIDDEN,
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


def _traceable() -> "SourceTrace":
    """构造一条可溯源来源链（避免误入「无来源链」拦截）。"""
    tr = SourceTrace(trace_id="tr-1")
    tr.add_entry("security_risk:risk-1")
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
    """REVIEWER 只在 knowledge 作用域内，对 data 类治理数据默认拒绝。"""
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


def _service(*, audit=None, policy=None, org_id: str = "org-1"):
    return GovernanceWorkflowService(
        org_id=org_id,
        audit=audit,
        identity=_identity(org_id),
        permission_policy=policy,
    )


def _task(svc, task_id: str = "gt-1", **kw):
    kw.setdefault("source_type", GovernanceTaskSourceType.SECURITY_RISK)
    kw.setdefault("source_id", "risk-1")
    return svc.create_task(task_id=task_id, **kw)


def _assign(svc, task_id: str = "gt-1", assignee: str = "eng-li", role: str = "安全负责人"):
    return svc.assign_owner(
        task_id=task_id,
        assignee=assignee,
        role=role,
        actor_kind=AuditActorKind.USER,
        actor_id="owner-zhang",
        timestamp="2026-08-07T10:00:00",
    )


def _to_waiting(svc, task_id: str = "gt-1"):
    """推进到 waiting_review：assign → start_processing → submit_result。"""
    _assign(svc, task_id=task_id)
    svc.start_processing(
        task_id=task_id, actor_kind=AuditActorKind.USER, actor_id="eng-li",
        source=f"task:{task_id}", timestamp="2026-08-07T10:10:00",
    )
    svc.submit_result(
        task_id=task_id, actor_kind=AuditActorKind.USER, actor_id="eng-li",
        result="已按线下流程核查并留存记录", timestamp="2026-08-07T11:00:00",
    )


# ---------------------------------------------------------------------------
# 一、task：治理任务（任务1）
# ---------------------------------------------------------------------------

def test_task_status_enum_has_exactly_five_states() -> None:
    """状态机严格五态，且**不存在**任何 AI 自动终态（红线③/⑥）。"""
    values = {s.value for s in GovernanceTaskStatus}
    assert values == {
        "created", "assigned", "processing", "waiting_review", "completed"
    }
    for name in GovernanceTaskStatus.__members__:
        assert hasattr(GovernanceTaskStatus, name)
    for banned in ("auto_completed", "closed_by_ai", "auto_resolved", "ai_closed"):
        assert banned not in values


def test_task_source_type_enum_is_fact_only() -> None:
    """来源类型只描述事实发现，不含任何 AI 处置意图（红线③）。"""
    values = {s.value for s in GovernanceTaskSourceType}
    assert "security_risk" in values and "compliance_risk" in values
    assert "human_reported" in values
    for banned in ("ai_decision", "auto_detected_fix", "ai_remediation"):
        assert banned not in values


def test_task_created_state_and_fields() -> None:
    task = GovernanceTask(
        task_id="gt-1", source_type="security_risk", source_id="risk-1",
        created_at="2026-08-07T09:00:00", title="安全风险候选待人工核查",
    )
    assert task.status is GovernanceTaskStatus.CREATED
    assert task.owner_id == "" and task.completed_at == ""
    assert task.requires_human_completion is True
    assert task.has_owner is False and task.is_completed is False
    assert "gt-1" in task.summary()


def test_task_rejects_missing_source_id() -> None:
    """无来源即拒绝（红线⑥：治理发现必须可溯源）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="source_id"):
        GovernanceTask(task_id="gt-x", source_id="")


def test_task_rejects_missing_task_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="task_id"):
        GovernanceTask(task_id="", source_id="risk-1")


def test_task_rejects_prefilled_owner_id() -> None:
    """构造期预填 owner_id = AI 自动分配责任，直接拒绝（红线④）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="owner_id"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", owner_id="eng-li")


def test_task_rejects_prefilled_completed_at() -> None:
    """构造期预填 completed_at = 伪造完成事实，直接拒绝（红线③/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="completed_at"):
        GovernanceTask(
            task_id="gt-1", source_id="risk-1", completed_at="2026-08-07T12:00:00"
        )


def test_task_rejects_prefilled_closed_by() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="closed_by"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", closed_by="someone")


@pytest.mark.parametrize(
    "status", ["assigned", "processing", "waiting_review", "completed"]
)
def test_task_rejects_non_created_construction(status: str) -> None:
    """构造期落非 created 态一律拒绝（红线③/④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="构造期"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", status=status)


def test_task_rejects_requires_human_completion_false() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="requires_human_completion"):
        GovernanceTask(
            task_id="gt-1", source_id="risk-1", requires_human_completion=False
        )


@pytest.mark.parametrize(
    "text", ["auto_remediate 该风险", "已自动修复", "自动整改完成", "auto fix applied"]
)
def test_task_rejects_remediation_semantics(text: str) -> None:
    """标题/说明命中自动整改语义即拒绝（红线③）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", title=text)


@pytest.mark.parametrize("text", ["auto_assign 给张三", "自动分配责任人", "自动指派处理"])
def test_task_rejects_assignment_semantics(text: str) -> None:
    """标题/说明命中自动分配语义即拒绝（红线④）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", detail=text)


@pytest.mark.parametrize("text", ["grant permission to agent", "修改权限以规避", "变更策略"])
def test_task_rejects_permission_semantics(text: str) -> None:
    """标题/说明命中改权限语义即拒绝（红线⑤）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceTask(task_id="gt-1", source_id="risk-1", detail=text)


def test_task_can_transition_only_forward() -> None:
    """状态迁移只前进不回退，且 created 不可直达 completed（红线③/⑥）。"""
    task = GovernanceTask(task_id="gt-1", source_id="risk-1")
    assert task.can_transition_to(GovernanceTaskStatus.ASSIGNED) is True
    assert task.can_transition_to(GovernanceTaskStatus.COMPLETED) is False
    assert task.can_transition_to(GovernanceTaskStatus.PROCESSING) is False


def test_task_model_has_no_close_or_assign_methods() -> None:
    """模型层结构上不提供任何 close / complete / resolve / assign 能力。"""
    task = GovernanceTask(task_id="gt-1", source_id="risk-1")
    for banned in (
        "close", "complete", "resolve", "assign", "remediate", "auto_fix",
    ):
        assert not hasattr(task, banned)


# ---------------------------------------------------------------------------
# 二、assignment：责任分配记录（任务2）
# ---------------------------------------------------------------------------

def test_assignment_basic_fields() -> None:
    a = GovernanceAssignment(
        assignment_id="as-1", task_id="gt-1", assignee="eng-li",
        role="安全负责人", timestamp="2026-08-07T10:00:00", assigned_by="owner-zhang",
    )
    assert a.assignee == "eng-li" and a.role == "安全负责人"
    assert "as-1" in a.summary() and "eng-li" in a.summary()


def test_assignment_rejects_missing_assignment_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="assignment_id"):
        GovernanceAssignment(assignment_id="", task_id="gt-1", assignee="eng-li", role="r")


def test_assignment_rejects_missing_task_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="task_id"):
        GovernanceAssignment(assignment_id="as-1", task_id="", assignee="eng-li", role="r")


def test_assignment_rejects_empty_assignee() -> None:
    """无责任人的分配记录一律拒绝（红线④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="assignee"):
        GovernanceAssignment(assignment_id="as-1", task_id="gt-1", assignee="", role="r")


def test_assignment_rejects_empty_role() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="role"):
        GovernanceAssignment(
            assignment_id="as-1", task_id="gt-1", assignee="eng-li", role=""
        )


@pytest.mark.parametrize(
    "assignee",
    ["ai", "system", "bot", "agent", "auto", "llm", "机器人", "ai-agent", "system_bot"],
)
def test_assignment_rejects_non_human_assignee(assignee: str) -> None:
    """责任人必须是真实 USER，非人类标识一律拒绝（红线④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类责任人"):
        GovernanceAssignment(
            assignment_id="as-1", task_id="gt-1", assignee=assignee, role="负责人"
        )


def test_assignment_rejects_non_human_assigned_by() -> None:
    """分配动作本身也必须由真实人工发起（红线④/⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类责任人"):
        GovernanceAssignment(
            assignment_id="as-1", task_id="gt-1", assignee="eng-li",
            role="负责人", assigned_by="ai",
        )


@pytest.mark.parametrize("note", ["auto_assign 完成", "自动分配给他", "自动整改后转派"])
def test_assignment_rejects_forbidden_note_semantics(note: str) -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceAssignment(
            assignment_id="as-1", task_id="gt-1", assignee="eng-li",
            role="负责人", note=note,
        )


def test_assignment_accepts_real_human_identifier() -> None:
    """真实人名标识正常放行（不误伤）。"""
    for who in ("eng-li", "zhang.san", "wang_wu", "owner-zhang"):
        a = GovernanceAssignment(
            assignment_id=f"as-{who}", task_id="gt-1", assignee=who, role="负责人"
        )
        assert a.assignee == who


# ---------------------------------------------------------------------------
# 三、action：处理动作事实记录（任务3）
# ---------------------------------------------------------------------------

def test_action_record_basic_fields() -> None:
    r = GovernanceActionRecord(
        record_id="ga-1", task_id="gt-1", action="人工核查访问日志",
        actor="eng-li", timestamp="2026-08-07T10:30:00",
        result="已完成核查并留存记录", source="task:gt-1", actor_kind="user",
    )
    assert r.is_human_action is True
    assert "ga-1" in r.summary() and "task:gt-1" in r.summary()


def test_action_record_rejects_missing_record_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="record_id"):
        GovernanceActionRecord(record_id="", action="a", actor="u", source="s")


def test_action_record_rejects_missing_action() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="action"):
        GovernanceActionRecord(record_id="ga-1", action="", actor="u", source="s")


def test_action_record_rejects_missing_actor() -> None:
    """处理事实必须可追溯到执行者（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="actor"):
        GovernanceActionRecord(record_id="ga-1", action="a", actor="", source="s")


def test_action_record_rejects_missing_source() -> None:
    """无源事实一律拒绝（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="source"):
        GovernanceActionRecord(record_id="ga-1", action="a", actor="u", source="")


@pytest.mark.parametrize(
    "result",
    ["auto_remediate done", "已自动修复", "automatically resolved", "自动关闭该风险"],
)
def test_action_record_rejects_auto_remediation_result(result: str) -> None:
    """结果命中自动整改语义即拒绝（红线③）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceActionRecord(
            record_id="ga-1", action="处理", actor="eng-li",
            source="task:gt-1", result=result,
        )


@pytest.mark.parametrize("action", ["auto_fix risk", "auto resolve issue", "自动处置"])
def test_action_record_rejects_auto_remediation_action(action: str) -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceActionRecord(
            record_id="ga-1", action=action, actor="eng-li", source="task:gt-1"
        )


@pytest.mark.parametrize("result", ["grant permission to agent", "撤销权限", "modify policy"])
def test_action_record_rejects_permission_semantics(result: str) -> None:
    """结果命中改权限语义即拒绝（红线⑤）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceActionRecord(
            record_id="ga-1", action="处理", actor="eng-li",
            source="task:gt-1", result=result,
        )


def test_action_record_ai_kind_is_not_human_action() -> None:
    """AI 观察记录如实标注，绝不冒充人工（红线⑥）。"""
    r = GovernanceActionRecord(
        record_id="ga-2", action="观察到人工提交了工单", actor="eng-li",
        source="ticket:1001", actor_kind="ai",
    )
    assert r.is_human_action is False


def test_action_record_model_has_no_remediation_methods() -> None:
    r = GovernanceActionRecord(
        record_id="ga-3", action="核查", actor="eng-li", source="task:gt-1"
    )
    for banned in ("remediate", "fix", "resolve", "close", "auto_fix"):
        assert not hasattr(r, banned)


# ---------------------------------------------------------------------------
# 四、workflow：治理流程编排（任务4）—— AI 只建候选，人工逐步推进，AI 无法代责
# ---------------------------------------------------------------------------

def test_create_task_only_produces_candidate() -> None:
    """create_task 产出物只能是 created 候选态：无责任人、无完成时间。"""
    t = _service()
    task = _task(t)
    assert task.status is GovernanceTaskStatus.CREATED
    assert task.owner_id == "" and task.completed_at == ""
    assert task.requires_human_completion is True


def test_create_task_requires_source_id() -> None:
    """无来源发现即拒绝（红线⑥）。"""
    t = _service()
    with pytest.raises(EnterpriseRedLineViolationError, match="source_id"):
        t.create_task(task_id="gt-x", source_type="security_risk", source_id="")


def test_create_task_rejects_duplicate() -> None:
    """禁止覆盖既有治理事实（红线⑥）。"""
    t = _service()
    _task(t, task_id="gt-1")
    with pytest.raises(EnterpriseRedLineViolationError, match="重复"):
        _task(t, task_id="gt-1")


def test_assign_owner_requires_human_actor() -> None:
    """AI 调用 assign_owner 必抛违例（红线④：禁止 AI 自动分配责任）。"""
    t = _service()
    _task(t)
    with pytest.raises(EnterpriseRedLineViolationError):
        t.assign_owner(
            task_id="gt-1", assignee="eng-li", role="安全负责人",
            actor_kind=AuditActorKind.AI, actor_id="ai-bot",
        )


def test_assign_owner_rejects_non_human_assignee() -> None:
    """责任人非人类标识一律拒绝（红线④/⑥）。"""
    t = _service()
    _task(t)
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类责任人"):
        t.assign_owner(
            task_id="gt-1", assignee="ai", role="安全负责人",
            actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        )


def test_assign_owner_moves_to_assigned() -> None:
    """真实 USER 分配成功：created → assigned，且 owner_id 写入真实人工。"""
    t = _service()
    _task(t)
    a = _assign(t)
    assert a.assignee == "eng-li"
    stored = t._tasks["gt-1"]
    assert stored.status is GovernanceTaskStatus.ASSIGNED
    assert stored.owner_id == "eng-li"


def test_start_processing_requires_human_actor() -> None:
    """AI 无法把任务推进到 processing（红线③/⑥）。"""
    t = _service()
    _task(t)
    _assign(t)
    with pytest.raises(EnterpriseRedLineViolationError):
        t.start_processing(
            task_id="gt-1", actor_kind=AuditActorKind.AI, actor_id="ai-bot",
            source="task:gt-1",
        )


def test_submit_result_requires_human_actor() -> None:
    """AI 不得提交处理结果（红线⑥）。"""
    t = _service()
    _task(t)
    _assign(t)
    t.start_processing(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="eng-li",
        source="task:gt-1",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        t.submit_result(
            task_id="gt-1", result="AI 自动提交的结论",
            actor_kind=AuditActorKind.AI, actor_id="ai-bot",
        )


def test_submit_result_rejects_empty_result() -> None:
    """结果必须由人工填写，空结果拒绝（红线⑥）。"""
    t = _service()
    _task(t)
    _assign(t)
    t.start_processing(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="eng-li",
        source="task:gt-1",
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="result"):
        t.submit_result(
            task_id="gt-1", result="",
            actor_kind=AuditActorKind.USER, actor_id="eng-li",
        )


def test_full_human_workflow_to_waiting_review() -> None:
    """完整人工链路：created → assigned → processing → waiting_review。"""
    t = _service(audit=_audit())
    _task(t)
    _to_waiting(t)
    assert t._tasks["gt-1"].status is GovernanceTaskStatus.WAITING_REVIEW
    # 处理动作事实已登记
    recs = t.list_action_records_of("gt-1")
    assert len(recs) == 2
    assert all(r.is_human_action for r in recs)


def test_human_close_is_only_completion_entry() -> None:
    """human_close 是唯一闭环入口，生成 GovernanceClosureReport。"""
    t = _service(audit=_audit())
    _task(t)
    _to_waiting(t)
    report = t.human_close(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        human_result="已按线下流程完成核查并归档，风险可控",
        completed_at="2026-08-07T12:00:00",
    )
    assert isinstance(report, GovernanceClosureReport)
    assert t._tasks["gt-1"].status is GovernanceTaskStatus.COMPLETED
    assert t._tasks["gt-1"].closed_by == "owner-zhang"


def test_human_close_requires_human_actor() -> None:
    """AI 无论如何无法自动关闭任务（红线③/⑥）。"""
    t = _service()
    _task(t)
    _to_waiting(t)
    with pytest.raises(EnterpriseRedLineViolationError):
        t.human_close(
            task_id="gt-1", actor_kind=AuditActorKind.AI, actor_id="ai-bot",
            human_result="AI 自动闭环",
        )


def test_record_observed_action_does_not_change_status() -> None:
    """record_observed_action 只记录事实，绝不改状态（红线③）。"""
    t = _service(audit=_audit())
    _task(t)
    _assign(t)
    rec = t.record_observed_action(
        record_id="obs-1", task_id="gt-1", action="观察到人工提交了工单",
        actor="eng-li", source="ticket:1001",
    )
    assert rec.actor_kind == "ai"
    assert t._tasks["gt-1"].status is GovernanceTaskStatus.ASSIGNED
    # 已登记到审计（如实 actor_kind=ai）
    assert any(
        e.category == AuditActionCategory.AGENT_GOVERNANCE_ACTION
        for e in t._audit._records
    )


def test_workflow_rejects_illegal_backward_transition() -> None:
    """禁止非法/回退状态迁移（红线③/⑥）。"""
    t = _service()
    _task(t)
    _to_waiting(t)
    # waiting_review 不能直接退回 processing
    with pytest.raises(EnterpriseRedLineViolationError, match="非法状态迁移"):
        t.start_processing(
            task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="eng-li",
            source="task:gt-1",
        )


# ---------------------------------------------------------------------------
# 五、closure：治理闭环报告（任务5）—— 必须可溯源、人工结论、真实责任人
# ---------------------------------------------------------------------------

def test_closure_report_basic_fields() -> None:
    report = GovernanceClosureReport(
        report_id="cl-1", task_id="gt-1", org_id="org-1",
        source_type="security_risk", source_id="risk-1",
        action_records=[], human_result="已核查并归档",
        closed_by="owner-zhang", source_trace=_traceable(),
    )
    assert report.action_count == 0
    assert report.is_traceable is True
    assert "cl-1" in report.summary()


def test_closure_report_rejects_missing_source_id() -> None:
    with pytest.raises(EnterpriseRedLineViolationError, match="source_id"):
        GovernanceClosureReport(
            report_id="cl-1", task_id="gt-1", org_id="org-1",
            source_type="security_risk", source_id="",
            action_records=[], human_result="已核查", closed_by="owner-zhang",
            source_trace=SourceTrace(trace_id="tr-1"),
        )


def test_closure_report_rejects_missing_human_result() -> None:
    """无人工结论即拒绝（红线⑥：闭环结论须人工给出）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="human_result"):
        GovernanceClosureReport(
            report_id="cl-1", task_id="gt-1", org_id="org-1",
            source_type="security_risk", source_id="risk-1",
            action_records=[], human_result="",
            closed_by="owner-zhang", source_trace=_traceable(),
        )


def test_closure_report_rejects_non_human_closed_by() -> None:
    """闭环责任人必须真实 USER（红线⑥）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="非人类责任人"):
        GovernanceClosureReport(
            report_id="cl-1", task_id="gt-1", org_id="org-1",
            source_type="security_risk", source_id="risk-1",
            action_records=[], human_result="已核查",
            closed_by="ai", source_trace=_traceable(),
        )


def test_closure_report_rejects_untraceable() -> None:
    """无来源链即拒绝闭环（红线⑥）。"""
    empty = SourceTrace(trace_id="tr-empty")
    assert empty.is_traceable is False
    with pytest.raises(EnterpriseRedLineViolationError, match="来源链"):
        GovernanceClosureReport(
            report_id="cl-1", task_id="gt-1", org_id="org-1",
            source_type="security_risk", source_id="risk-1",
            action_records=[], human_result="已核查",
            closed_by="owner-zhang", source_trace=empty,
        )


def test_closure_report_rejects_remediation_semantics() -> None:
    """人工结论命中自动整改语义即拒绝（红线③）。"""
    with pytest.raises(EnterpriseRedLineViolationError, match="禁止语义"):
        GovernanceClosureReport(
            report_id="cl-1", task_id="gt-1", org_id="org-1",
            source_type="security_risk", source_id="risk-1",
            action_records=[], human_result="已 auto_remediate 完成",
            closed_by="owner-zhang", source_trace=_traceable(),
        )


def test_closure_report_render_source_includes_trace() -> None:
    """render_source 必须呈现来源链（事实可溯源）。"""
    trace = SourceTrace(trace_id="tr-1")
    trace.add_entry("security_risk:risk-1")
    report = GovernanceClosureReport(
        report_id="cl-1", task_id="gt-1", org_id="org-1",
        source_type="security_risk", source_id="risk-1",
        action_records=[], human_result="已核查", closed_by="owner-zhang",
        source_trace=trace,
    )
    rendered = report.render_source()
    assert "risk-1" in rendered
    assert report.source_trace is not None and report.source_trace.trace_id == "tr-1"


# ---------------------------------------------------------------------------
# 六、permission：权限隔离（任务7）—— 治理数据默认拒绝，ADMIN 放行
# ---------------------------------------------------------------------------

def test_reviewer_denied_governance_data_by_default() -> None:
    """REVIEWER 只在 knowledge 作用域，对 data 类治理数据默认拒绝。"""
    policy = _policy()
    svc = _service(audit=_audit(), policy=policy)
    _task(svc)
    reviewer = _reviewer()
    with pytest.raises(EnterpriseIsolationError):
        svc.list_tasks(user=reviewer)


def test_admin_allowed_governance_data() -> None:
    """ADMIN 在 data 作用域内，可读取治理任务数据。"""
    policy = _policy()
    svc = _service(audit=_audit(), policy=policy)
    _task(svc)
    admin = _admin()
    items = svc.list_tasks(user=admin)
    assert len(items) == 1
    assert items[0].task_id == "gt-1"


def test_reviewer_denied_closure_reports() -> None:
    """闭环报告同样受 data 作用域隔离（默认拒绝）。"""
    policy = _policy()
    svc = _service(audit=_audit(), policy=policy)
    _task(svc)
    _to_waiting(svc)
    svc.human_close(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        human_result="已核查归档",
    )
    reviewer = _reviewer()
    with pytest.raises(EnterpriseIsolationError):
        svc.list_closure_reports(user=reviewer)


def test_workflow_service_is_read_only_on_permission() -> None:
    """本层对权限策略纯只读：不存在任何写/改权限的方法（红线⑤）。"""
    svc = _service(policy=_policy())
    for banned in (
        "change_permission", "modify_policy", "grant_permission",
        "revoke_permission", "auto_change_permission",
    ):
        # 结构级拦截：禁止方法名访问即抛红线违例（红线⑤）
        assert _forbidden_access(svc, banned)
    # 只读引用，无 set 器
    assert "permission_policy" not in [
        a for a in dir(svc) if a.startswith("set_")
    ]


# ---------------------------------------------------------------------------
# 七、audit：审计增强（+3 类，禁 record_human_approval，红线⑥）
# ---------------------------------------------------------------------------

def test_audit_has_three_new_governance_categories() -> None:
    """审计枚举含 task / action / closure 三类（本层关心的语义契约）。

    Phase 3.8.31 Task 9：此处原有 ``assert len(members) == 72`` 的总数断言。
    枚举总数是**全局事实**，不是本层的契约；总数权威唯一保留在
    ``tests/agents/test_enterprise_knowledge_governance_audit.py``。
    此处只断言本层真正依赖的三类存在，避免"新增一类就要连改十几处旧测试"。
    """
    values = {m.value for m in AuditActionCategory.__members__.values()}
    assert "agent_governance_task" in values
    assert "agent_governance_action" in values
    assert "agent_governance_closure" in values


def test_audit_records_governance_task_action() -> None:
    """create_task 触发审计（AI 如实标注 actor_kind=ai）。"""
    svc = _service(audit=_audit())
    _task(svc)
    assert any(
        e.category == AuditActionCategory.AGENT_GOVERNANCE_TASK
        for e in svc._audit._records
    )


def test_audit_records_governance_closure_action() -> None:
    """human_close 触发审计 closure 类（actor_kind 如实为 user）。"""
    svc = _service(audit=_audit())
    _task(svc)
    _to_waiting(svc)
    svc.human_close(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        human_result="已核查归档",
    )
    assert any(
        e.category == AuditActionCategory.AGENT_GOVERNANCE_CLOSURE
        for e in svc._audit._records
    )


def test_audit_forbids_record_human_approval() -> None:
    """审计层不存在 record_human_approval（红线⑥：AI 不冒充人工确认）。"""
    audit = _audit()
    # 结构上不可达：访问即抛红线违例
    assert _forbidden_access(audit, "record_human_approval")
    # 该禁止项同样在治理工作流 forbidden 元组内
    assert "record_human_approval" in _GOVERNANCE_FORBIDDEN


def test_forbidden_tuple_covers_remediation_and_assignment() -> None:
    """_GOVERNANCE_FORBIDDEN 含 auto_remediate/auto_fix/auto_resolve/auto_assign 等。"""
    for banned in (
        "auto_remediate", "auto_fix", "auto_resolve", "auto_assign",
        "auto_delegate", "auto_close", "close_task", "complete_task",
        "auto_change_permission", "grant_permission", "revoke_permission",
        "engineering_approved", "approve", "record_human_approval",
    ):
        assert banned in _GOVERNANCE_FORBIDDEN


# ---------------------------------------------------------------------------
# 八、red_line：最高红线结构性验证（任务1–7 全程 fail-closed）
# ---------------------------------------------------------------------------

def test_service_rejects_engineering_enabled(monkeypatch) -> None:
    """在启用态（engineering_enabled=True）下构造服务必抛红线违例（红线①）。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: True
    )
    with pytest.raises(EnterpriseRedLineViolationError, match="safety_invariants_ok"):
        GovernanceWorkflowService(org_id="org-1")


def test_safety_invariants_ok_true_under_disabled() -> None:
    """默认被禁态（engineering_enabled=False）下 safety_invariants_ok() 为 True（红线①护栏通过）。"""
    assert safety_invariants_ok() is True


def test_service_has_no_engineering_approved_attribute() -> None:
    """本层不持有 engineering_approved（红线②：禁输出）。"""
    svc = _service()
    assert "engineering_approved" in _GOVERNANCE_FORBIDDEN
    # 结构拦截：访问即抛违例
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = svc.engineering_approved


def test_service_forbids_auto_remediation_methods() -> None:
    """结构级拦截：auto_remediate / auto_fix / auto_resolve 等不可达（红线③）。"""
    svc = _service()
    for banned in ("auto_remediate", "auto_fix", "auto_resolve", "auto_close"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, banned)


def test_service_forbids_auto_assign_and_permission_methods() -> None:
    """结构级拦截：auto_assign / grant_permission 等不可达（红线④/⑤）。"""
    svc = _service()
    for banned in ("auto_assign", "auto_delegate", "grant_permission", "revoke_permission"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(svc, banned)


def test_full_flow_still_never_sets_engineering_approved() -> None:
    """完整人工闭环后，任务/报告均无 engineering_approved 字段或输出（红线②）。"""
    svc = _service(audit=_audit())
    _task(svc)
    _to_waiting(svc)
    report = svc.human_close(
        task_id="gt-1", actor_kind=AuditActorKind.USER, actor_id="owner-zhang",
        human_result="已核查归档",
    )
    for obj in (svc._tasks["gt-1"], report):
        assert not hasattr(obj, "engineering_approved")
    # 审计记录中没有 approve / engineering_approved 动作
    for e in svc._audit._records:
        assert "approve" not in (e.action or "").lower()
