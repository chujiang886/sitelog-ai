"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 测试（任务8，Phase 3.8.12）。

覆盖 8 类：
1. task 模型（创建/读取/列举本人/规划写入/状态推进，组织隔离）
2. planner（analyze_goal 复杂度判定；create_plan 子任务拆解与 requires_human_review；split_subtasks 顺序）
3. subtask 模型（拆解创建/完成/列举/读取；组织隔离）
4. orchestrator（闭环 run_task：返回待复核草稿、任务进入 waiting_review、子任务完成、事件日志）
5. checkpoint（复杂任务 requires_human_review 强制 True；AI 不得自动收口；仅真实 USER 可 finalize）
6. 审计（KNOWLEDGE_TASK / KNOWLEDGE_SUBTASK / KNOWLEDGE_AGENT_WORKFLOW 如实记录 actor）
7. 权限接入（不同用户只能访问自己的任务；ADMIN 可跨用户；规划器按角色约束可见知识类型）
8. 红线（forbidden 方法被拦截；safety_invariants_ok；无 engineering_approved；AI 不得自动完成最终任务）
"""

from __future__ import annotations

import pytest

from agents.enterprise import (
    EnterpriseOperationLayer,
    KnowledgeTaskOrchestrator,
    KnowledgeTaskPlanner,
    KnowledgeTaskService,
    KnowledgeTaskStatus,
    KnowledgeSubTaskService,
    KnowledgeSubTaskType,
    TaskReviewCheckpoint,
)
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_retrieval import KnowledgeItem
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def _layer(org_id: str = "org-1") -> EnterpriseOperationLayer:
    return EnterpriseOperationLayer(org_id=org_id)


def _seed_retrieval(layer: EnterpriseOperationLayer) -> None:
    """向编排器的检索引擎灌入知识（带 source，供 draft 引用）。

    各条 title/content 与测试目标共享分词，确保检索能命中并返回非空 sources：
    - regulation 项（EXPERT/ADMIN 可见）对应复杂目标的 ask_regulation 意图过滤；
    - design_spec 项（DESIGNER 可见）对应简单目标的通用检索。
    """
    engine = layer.knowledge_task_orchestrator._retrieval_agent._engine
    engine.index(
        item=KnowledgeItem(
            knowledge_id="k-reg1", title="风压设计规范对比", content="风压计算与不同版本对比",
            knowledge_type="regulation", source="import-reg", org_id=layer.org_id,
            version="v1", tags=["风压"],
        )
    )
    engine.index(
        item=KnowledgeItem(
            knowledge_id="k-ds1", title="开窗面积计算规则", content="开窗面积怎么算",
            knowledge_type="design_spec", source="import-ds", org_id=layer.org_id,
            version="v1", tags=["开窗"],
        )
    )


# ---- 1. task 模型 ----

def test_task_create_get_list_update_plan() -> None:
    layer = _layer()
    layer.knowledge_tasks.create(
        task_id="t1", conversation_id="c1", user_id="u1",
        goal="整理风压设计规范", created_at="t0",
    )
    task = layer.knowledge_tasks.get(
        task_id="t1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert task.task_id == "t1"
    assert task.user_id == "u1"
    assert task.status is KnowledgeTaskStatus.CREATED
    assert task.goal == "整理风压设计规范"

    mine = layer.knowledge_tasks.list_for_user(user_id="u1")
    assert len(mine) == 1

    planned = layer.knowledge_tasks.update_plan(
        task_id="t1", steps=["检索规范", "校验来源", "起草"],
        requesting_user_id="u1", updated_at="t1",
    )
    assert planned.status is KnowledgeTaskStatus.PLANNING
    assert planned.steps == ["检索规范", "校验来源", "起草"]


def test_task_org_isolation() -> None:
    l1 = _layer("org-A")
    l2 = _layer("org-B")
    l1.knowledge_tasks.create(task_id="ta", conversation_id="c1", user_id="u1", goal="g")
    assert l2.knowledge_tasks.list_for_user(user_id="u1") == []


# ---- 2. planner ----

def test_planner_analyze_goal_complex() -> None:
    planner = KnowledgeTaskPlanner(org_id="org-1")
    ana = planner.analyze_goal("检索风压规范并分析对比不同版本", role=RoleKind.DESIGNER)
    assert ana.complexity == "complex"
    assert ana.needs_multi_agent is True
    assert "regulation_lookup" in ana.intent_tags
    assert "analysis" in ana.intent_tags


def test_planner_analyze_goal_simple() -> None:
    planner = KnowledgeTaskPlanner(org_id="org-1")
    ana = planner.analyze_goal("开窗面积怎么算", role=RoleKind.DESIGNER)
    assert ana.complexity == "simple"
    assert ana.needs_multi_agent is False


def test_planner_create_plan_subtask_order_and_review_flag() -> None:
    planner = KnowledgeTaskPlanner(org_id="org-1")
    plan = planner.create_plan(
        "检索风压规范并分析对比不同版本", task_id="t1", role=RoleKind.DESIGNER,
    )
    types = [s.agent_type for s in plan.subtasks]
    # 顺序：retrieval → validation → analysis → draft
    assert types[0] is KnowledgeSubTaskType.RETRIEVAL
    assert types[1] is KnowledgeSubTaskType.VALIDATION
    assert KnowledgeSubTaskType.ANALYSIS in types
    assert types[-1] is KnowledgeSubTaskType.DRAFT
    # 复杂任务 requires_human_review 强制 True（任务5/红线⑥）
    assert plan.requires_human_review is True
    assert len(plan.steps) == len(plan.subtasks)


def test_planner_simple_plan_no_review_required() -> None:
    planner = KnowledgeTaskPlanner(org_id="org-1")
    plan = planner.create_plan("开窗面积怎么算", task_id="t2", role=RoleKind.DESIGNER)
    types = [s.agent_type for s in plan.subtasks]
    assert KnowledgeSubTaskType.ANALYSIS not in types
    assert plan.requires_human_review is False


# ---- 3. subtask 模型 ----

def test_subtask_create_complete_list() -> None:
    layer = _layer()
    layer.knowledge_subtasks.create(
        subtask_id="s1", task_id="t1", agent_type="retrieval",
        input={"goal": "g"}, created_at="t0",
    )
    done = layer.knowledge_subtasks.complete(
        subtask_id="s1", output={"context_items": 3}, updated_at="t1",
    )
    assert done.status.value == "done"
    assert done.output == {"context_items": 3}
    listed = layer.knowledge_subtasks.list_for_task(task_id="t1")
    assert len(listed) == 1


# ---- 4. orchestrator ----

def test_orchestrator_run_task_complex() -> None:
    layer = _layer()
    _seed_retrieval(layer)
    layer.knowledge_tasks.create(
        task_id="t1", conversation_id="c1", user_id="u1",
        goal="检索风压规范并分析对比不同版本", created_at="t0",
    )
    draft = layer.knowledge_task_orchestrator.run_task(
        task_id="t1", goal="检索风压规范并分析对比不同版本", user_id="u1",
        conversation_id="c1", role=RoleKind.EXPERT, created_at="t1",
        content="基于规范 A 与规范 B 的对比草稿", confidence=0.6,
    )
    # 回答草稿恒待人工复核（红线⑥）
    assert draft.requires_human_review is True
    # 任务进入 waiting_review，绝不自动 completed（任务5/红线⑥）
    task = layer.knowledge_tasks.get(
        task_id="t1", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert task.status is KnowledgeTaskStatus.WAITING_REVIEW
    assert task.requires_human_review is True
    # 子任务被拆解并完成（retrieval/validation/analysis/draft ≥ 4）
    subs = layer.knowledge_subtasks.list_for_task(task_id="t1")
    assert len(subs) >= 4
    # 事件日志完整
    events = layer.knowledge_task_orchestrator.task_workflow_event_log()
    assert len(events) >= 6
    steps = {e.step for e in events}
    assert {"plan", "query", "retrieve", "validate", "draft", "review"} <= steps


def test_orchestrator_run_task_simple() -> None:
    layer = _layer()
    _seed_retrieval(layer)
    layer.knowledge_tasks.create(
        task_id="t2", conversation_id="c1", user_id="u1",
        goal="开窗面积怎么算", created_at="t0",
    )
    draft = layer.knowledge_task_orchestrator.run_task(
        task_id="t2", goal="开窗面积怎么算", user_id="u1",
        conversation_id="c1", role=RoleKind.DESIGNER, created_at="t1",
        content="按 GB50009 计算", confidence=0.5,
    )
    assert draft.requires_human_review is True
    task = layer.knowledge_tasks.get(
        task_id="t2", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
    )
    assert task.status is KnowledgeTaskStatus.WAITING_REVIEW
    # 简单任务无 analysis 子任务
    subs = layer.knowledge_subtasks.list_for_task(task_id="t2")
    assert all(s.agent_type is not KnowledgeSubTaskType.ANALYSIS for s in subs)


# ---- 5. checkpoint ----

def test_checkpoint_complex_requires_review() -> None:
    layer = _layer()
    task = layer.knowledge_tasks.create(
        task_id="t3", conversation_id="c1", user_id="u1", goal="g", created_at="t0",
    )
    cp = TaskReviewCheckpoint(org_id="org-1", task_service=layer.knowledge_tasks)
    # 复杂任务但未置 requires_human_review → 拒绝 AI 自动收口
    with pytest.raises(EnterpriseRedLineViolationError):
        cp.checkpoint(task=task, is_complex=True)
    # 置位后可过闸
    task.requires_human_review = True
    cp.checkpoint(task=task, is_complex=True)


def test_checkpoint_finalize_requires_human() -> None:
    layer = _layer()
    _seed_retrieval(layer)
    layer.knowledge_tasks.create(
        task_id="t4", conversation_id="c1", user_id="u1", goal="g", created_at="t0",
    )
    layer.knowledge_task_orchestrator.run_task(
        task_id="t4", goal="检索风压规范并分析对比不同版本", user_id="u1",
        conversation_id="c1", role=RoleKind.EXPERT, created_at="t1", content="草稿",
    )
    cp = TaskReviewCheckpoint(org_id="org-1", task_service=layer.knowledge_tasks)
    finalized = cp.finalize_by_human(
        task_id="t4", requesting_user_id="u1", requesting_role=RoleKind.DESIGNER,
        updated_at="t2",
    )
    assert finalized.status is KnowledgeTaskStatus.COMPLETED


# ---- 6. 审计 ----

def test_audit_records_for_task_workflow() -> None:
    layer = _layer()
    _seed_retrieval(layer)
    layer.knowledge_tasks.create(
        task_id="t1", conversation_id="c1", user_id="u1", goal="g", created_at="t0",
    )
    layer.knowledge_task_orchestrator.run_task(
        task_id="t1", goal="检索风压规范并分析对比不同版本", user_id="u1",
        conversation_id="c1", role=RoleKind.EXPERT, created_at="t1", content="草稿",
    )
    task_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_TASK)
    assert len(task_recs) >= 1
    # 任务由用户创建 → 首条 actor 为 USER
    assert task_recs[0].actor_kind == AuditActorKind.USER

    wf_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_AGENT_WORKFLOW)
    assert len(wf_recs) == 1
    assert wf_recs[0].actor_kind == AuditActorKind.AI

    sub_recs = layer.audit.query(category=AuditActionCategory.KNOWLEDGE_SUBTASK)
    assert len(sub_recs) >= 3


# ---- 7. 权限接入 ----

def test_task_access_isolation() -> None:
    layer = _layer()
    layer.knowledge_tasks.create(
        task_id="t1", conversation_id="c1", user_id="u1", goal="g", created_at="t0",
    )
    # 他人越权访问 → 拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_tasks.get(
            task_id="t1", requesting_user_id="u2", requesting_role=RoleKind.DESIGNER,
        )
    # ADMIN 可跨用户访问
    admin_task = layer.knowledge_tasks.get(
        task_id="t1", requesting_user_id="admin", requesting_role=RoleKind.ADMIN,
    )
    assert admin_task.task_id == "t1"


def test_planner_role_visibility_constraint() -> None:
    planner = KnowledgeTaskPlanner(org_id="org-1")
    # DESIGNER 不可见 regulation（角色可见性策略，任务7）
    allowed = planner._allowed_knowledge_types(RoleKind.DESIGNER)
    assert "regulation" not in allowed
    # ADMIN 全可见
    allowed_admin = planner._allowed_knowledge_types(RoleKind.ADMIN)
    assert "regulation" in allowed_admin
    # 规划中 retrieval 子任务携带 allowed_knowledge_types 约束
    plan = planner.create_plan(
        "检索风压规范并分析对比不同版本", task_id="t1", role=RoleKind.DESIGNER,
    )
    retrieval = next(s for s in plan.subtasks
                     if s.agent_type is KnowledgeSubTaskType.RETRIEVAL)
    assert "regulation" not in retrieval.input["allowed_knowledge_types"]


# ---- 8. 红线 ----

def test_red_line_forbidden_methods_intercepted() -> None:
    layer = _layer()
    # 任务服务 forbidden 方法被拦截
    for name in ("approve", "engineering_approved", "quote", "pricing",
                 "sign", "authorize", "record_human_approval",
                 "auto_update_knowledge", "auto_apply_knowledge",
                 "generate_engineering_conclusion", "decide"):
        with pytest.raises(EnterpriseRedLineViolationError):
            _ = getattr(layer.knowledge_tasks, name)
    # 编排器 forbidden 方法被拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(layer.knowledge_task_orchestrator, "approve")
    # 检查点 forbidden 方法被拦截
    with pytest.raises(EnterpriseRedLineViolationError):
        _ = getattr(layer.task_review_checkpoint, "approve")


def test_red_line_safety_invariants_ok() -> None:
    # 当前为禁用态（红线①/⑤）
    assert safety_invariants_ok() is True


def test_red_line_ai_cannot_auto_complete_task() -> None:
    layer = _layer()
    layer.knowledge_tasks.create(
        task_id="t1", conversation_id="c1", user_id="u1", goal="g", created_at="t0",
    )
    # AI 尝试把任务标为 completed → 红线⑥ 拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        layer.knowledge_tasks.advance_status(
            task_id="t1", status=KnowledgeTaskStatus.COMPLETED,
            requesting_user_id="u1", actor_kind=AuditActorKind.AI,
        )
    # USER 可完成（human-gating）
    done = layer.knowledge_tasks.advance_status(
        task_id="t1", status=KnowledgeTaskStatus.COMPLETED,
        requesting_user_id="u1", actor_kind=AuditActorKind.USER,
    )
    assert done.status is KnowledgeTaskStatus.COMPLETED


def test_no_engineering_approved_attribute() -> None:
    # 新服务不输出 engineering_approved（红线②）：forbidden 方法名不出现在类字典中
    # （访问即被 _RedLineForbiddenMixin 拦截，故不可用 hasattr 判定，须查 __dict__）。
    assert "engineering_approved" not in KnowledgeTaskService.__dict__
    assert "engineering_approved" not in KnowledgeTaskOrchestrator.__dict__
