"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 任务规划器（任务2，Phase 3.8.12）。

新增：``KnowledgeTaskPlanner``（规划器 Agent）。

职责（红线严格限定）：
- 把用户目标拆解为可执行的子任务规划：``analyze_goal``（理解目标）→ ``create_plan``（生成计划）
  → ``split_subtasks``（拆分子任务）。
- 规划器**只拆任务、不执行决策、不批准、不生成工程结论**（红线④/⑥：不持有
  generate_engineering_conclusion / decide / approve / auto_apply_knowledge 等方法）。
- 复杂任务（多 Agent 协作）在计划中显式标注 ``requires_human_review=True``，交由下游
  TaskReviewCheckpoint 强制人工复核（任务5/红线⑥）。
- 任务7：规划器可结合 ``KnowledgeVisibilityPolicy`` 与 ``role`` 计算「允许检索的知识类型」，
  作为 retrieval 子任务的过滤提示（约束传播）；真实权限仍由检索 Agent 在检索时强制。
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.knowledge_subtask import KnowledgeSubTaskType
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


@dataclass
class GoalAnalysis:
    """目标理解结果（任务2）。"""

    goal: str
    complexity: str                 # simple / complex
    intent_tags: list[str] = field(default_factory=list)
    needs_multi_agent: bool = False


@dataclass
class SubTaskSpec:
    """一条子任务规划规格（任务2）。

    仅描述「由哪类 Agent 承接、做什么、输入是什么」，不执行、不落地（红线③/④）。
    """

    subtask_id: str
    agent_type: KnowledgeSubTaskType
    description: str
    input: dict = field(default_factory=dict)


@dataclass
class TaskPlan:
    """一次任务规划（任务2）。

    ``requires_human_review`` 由复杂度推导：复杂任务恒为 True（任务5 强制人工复核）。
    """

    goal: str
    complexity: str
    steps: list[str] = field(default_factory=list)
    subtasks: list[SubTaskSpec] = field(default_factory=list)
    requires_human_review: bool = False


class KnowledgeTaskPlanner(_RedLineForbiddenMixin):
    """任务规划器（任务2）。

    提供 ``analyze_goal`` / ``create_plan`` / ``split_subtasks``。规划器**只拆任务、不执行决策**，
    最终采用必须经真实人工复核（红线②/③/④/⑥）。

    为统一红线姿态，规划器继承 ``_RedLineForbiddenMixin``：任何批准/报价/审批/自动应用知识/
    生成工程结论入口都会结构上被拦截（防御性 fail-closed）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/发布/合并/应用知识
        "auto_update_knowledge",
        "auto_publish_knowledge",
        "auto_merge_knowledge",
        "auto_apply_knowledge",
        "auto_activate",
        "publish",
        "merge",
        "apply",
        "commit",
        "write",
        # 红线④/⑤：禁止自动生成工程结论 / 经营决策 / 审批 / 管理建议
        "generate_engineering_conclusion",
        "auto_business_decision",
        "make_management_decision",
        "recommend_management_action",
        "optimize_business_strategy",
        "execute_strategy",
        "decide_operation",
        "auto_decision",
        "decide",
    )

    def __init__(
        self,
        org_id: str,
        audit: "Any | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeTaskPlanner（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility or KnowledgeVisibilityPolicy(org_id=org_id)

    def analyze_goal(
        self,
        goal: str,
        role: "RoleKind | None" = None,
    ) -> GoalAnalysis:
        """理解用户目标：推断复杂度与意图标签，判断是否需多 Agent 协作（不执行决策）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下分析目标（红线①/⑤）"
            )
        tags: list[str] = []
        goal_lower = goal.lower()
        if any(k in goal for k in ("规范", "regulation", "标准", "条文")):
            tags.append("regulation_lookup")
        if any(k in goal for k in ("案例", "case", "相似", "既往")):
            tags.append("case_lookup")
        if any(k in goal for k in ("分析", "对比", "评估", "analysis")):
            tags.append("analysis")
        if any(k in goal for k in ("起草", "回答", "生成", "summary", "回答用户")):
            tags.append("draft")
        # 多 Agent 协作判定：含检索+（校验或分析或起草）即视为复杂任务
        multi = ("regulation_lookup" in tags or "case_lookup" in tags) and (
            "analysis" in tags or "draft" in tags or "case_lookup" in tags
        )
        complexity = "complex" if (multi or len(tags) >= 2) else "simple"
        return GoalAnalysis(
            goal=goal,
            complexity=complexity,
            intent_tags=tags,
            needs_multi_agent=multi,
        )

    def split_subtasks(
        self,
        goal: str,
        task_id: str | None = None,
        role: "RoleKind | None" = None,
        analysis: "GoalAnalysis | None" = None,
    ) -> list[SubTaskSpec]:
        """把目标拆成子任务规格（retrieval → validation → [analysis] → draft）。

        不执行、不落地；复杂任务在 spec 之外由 ``create_plan`` 显式标注 requires_human_review。
        任务7：retrieval 子任务的 input 携带 ``allowed_knowledge_types``（由 visibility 按角色
        计算），作为约束传播；真实过滤仍由检索 Agent 强制。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下拆解子任务（红线①/⑤）"
            )
        ana = analysis or self.analyze_goal(goal, role=role)
        allowed_types = self._allowed_knowledge_types(role)

        specs: list[SubTaskSpec] = []

        # ① retrieval：召回可追溯候选知识（约束按角色可见性）
        specs.append(
            SubTaskSpec(
                subtask_id=f"{task_id or 'st'}-s1",
                agent_type=KnowledgeSubTaskType.RETRIEVAL,
                description="检索与用户目标相关的可追溯候选知识",
                input={"goal": goal, "allowed_knowledge_types": allowed_types},
            )
        )

        # ② validation：四维校验（来源/版本/权限/溯源）
        specs.append(
            SubTaskSpec(
                subtask_id=f"{task_id or 'st'}-s2",
                agent_type=KnowledgeSubTaskType.VALIDATION,
                description="对召回知识做来源/版本/权限/溯源校验",
                input={"goal": goal},
            )
        )

        # ③ analysis（仅当目标含分析意图）：结构化比对/评估
        if "analysis" in ana.intent_tags:
            specs.append(
                SubTaskSpec(
                    subtask_id=f"{task_id or 'st'}-s3",
                    agent_type=KnowledgeSubTaskType.ANALYSIS,
                    description="对校验后的知识做结构化分析与评估",
                    input={"goal": goal},
                )
            )

        # ④ draft：起草待复核草稿（requires_human_review 由下游强制）
        draft_idx = len(specs) + 1
        specs.append(
            SubTaskSpec(
                subtask_id=f"{task_id or 'st'}-s{draft_idx}",
                agent_type=KnowledgeSubTaskType.DRAFT,
                description="基于校验/分析后的知识起草待人工复核的回答草稿",
                input={"goal": goal},
            )
        )
        return specs

    def create_plan(
        self,
        goal: str,
        task_id: str | None = None,
        role: "RoleKind | None" = None,
    ) -> TaskPlan:
        """生成完整任务计划（analyze_goal + split_subtasks + 步骤描述）。

        复杂任务 ``requires_human_review`` 强制为 True（任务5/红线⑥）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成计划（红线①/⑤）"
            )
        ana = self.analyze_goal(goal, role=role)
        specs = self.split_subtasks(goal, task_id=task_id, role=role, analysis=ana)
        steps = [f"[{s.agent_type.value}] {s.description}" for s in specs]
        return TaskPlan(
            goal=goal,
            complexity=ana.complexity,
            steps=steps,
            subtasks=specs,
            requires_human_review=(ana.complexity == "complex"),
        )

    def _allowed_knowledge_types(self, role: "RoleKind | None") -> list[str]:
        """任务7：按角色计算允许检索的知识类型（默认拒绝；无角色则空）。"""
        if role is None or self._visibility is None:
            return []
        from agents.enterprise.knowledge_visibility import _ROLE_VISIBLE_KNOWLEDGE

        allowed = _ROLE_VISIBLE_KNOWLEDGE.get(role, set())
        return [t for t in allowed if t != "all"]


__all__ = [
    "GoalAnalysis",
    "SubTaskSpec",
    "TaskPlan",
    "KnowledgeTaskPlanner",
]
