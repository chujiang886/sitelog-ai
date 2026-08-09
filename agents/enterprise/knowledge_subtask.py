"""Enterprise Knowledge Task Planning & Multi-Agent Workflow Layer —— 子任务模型（任务3，Phase 3.8.12）。

新增：
- ``KnowledgeSubTaskType``：子任务 Agent 类型枚举（retrieval / validation / analysis / draft）。
- ``KnowledgeSubTaskStatus``：子任务状态枚举（pending / running / done）。
- ``KnowledgeSubTask``：一次子任务实体（subtask_id / task_id / agent_type / input / output /
  status），**组织隔离**（org_id 绑定）。
- ``KnowledgeSubTaskService``：组织作用域内的子任务服务（拆解创建 / 读取 / 列举 / 标记完成）。

红线（fail-closed，复用 3.8.0~3.8.11 基座 + 3.8.12 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 子任务只承载各 Agent 的中间执行态（检索/校验/分析/起草），**绝不自动应用知识或生成工程结论**
  （红线③/④：不持有 auto_apply_knowledge / generate_engineering_conclusion 等方法）。
- 跨域访问抛 ``EnterpriseIsolationError``；子任务随所属任务执行，不直接做越权访问判断。
- 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
  record_human_approval（红线②/④/⑥）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditActorKind, AuditService
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy


class KnowledgeSubTaskType(str, Enum):
    """子任务 Agent 类型（任务3）。"""

    RETRIEVAL = "retrieval"
    VALIDATION = "validation"
    ANALYSIS = "analysis"
    DRAFT = "draft"


class KnowledgeSubTaskStatus(str, Enum):
    """子任务状态（任务3）。"""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"


@dataclass
class KnowledgeSubTask:
    """子任务实体（任务3）。

    绑定 ``org_id``（组织隔离）；``task_id`` 指向所属知识任务。``agent_type`` 决定由哪类 Agent
    承接；``input`` 为交办给 Agent 的输入；``output`` 为 Agent 产出的中间结果（仅候选，
    不自动落地，红线③/④）。``requires_human_review`` 由编排器在收尾时强制为 True（任务5）。
    """

    subtask_id: str
    task_id: str
    agent_type: "KnowledgeSubTaskType | str"
    org_id: str = ""
    input: dict = field(default_factory=dict)
    output: dict = field(default_factory=dict)
    status: KnowledgeSubTaskStatus = KnowledgeSubTaskStatus.PENDING
    requires_human_review: bool = False
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.agent_type, KnowledgeSubTaskType):
            self.agent_type = KnowledgeSubTaskType(self.agent_type)
        if not isinstance(self.status, KnowledgeSubTaskStatus):
            self.status = KnowledgeSubTaskStatus(self.status)


class KnowledgeSubTaskService(_RedLineForbiddenMixin):
    """子任务服务（任务3）。

    提供 ``create`` / ``get`` / ``list_for_task`` / ``complete``。写路径断言
    ``safety_invariants_ok()``（红线①/⑤）；跨域访问抛错。

    本服务**不**持有 approve / engineering_approved / quote / pricing / sign / authorize /
    record_human_approval / auto_apply_knowledge / generate_engineering_conclusion 等方法
    （红线②/③/④/⑥）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 红线③/④：禁止 AI 自动修改/发布/合并/应用/学习知识
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
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "KnowledgeSubTaskService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._subtasks: dict[str, KnowledgeSubTask] = {}

    def create(
        self,
        *,
        subtask_id: str,
        task_id: str,
        agent_type: "KnowledgeSubTaskType | str",
        input: "dict | None" = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeSubTask:
        """拆解创建一个子任务（由编排器/规划器发起，默认 AI 审计；绝不落地，红线③/④）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下拆解子任务（红线①/⑤）"
            )
        subtype = (
            agent_type if isinstance(agent_type, KnowledgeSubTaskType)
            else KnowledgeSubTaskType(agent_type)
        )
        sub = KnowledgeSubTask(
            subtask_id=subtask_id,
            task_id=task_id,
            agent_type=subtype,
            org_id=self._org_id,
            input=dict(input or {}),
            status=KnowledgeSubTaskStatus.PENDING,
            created_at=created_at,
            updated_at=created_at,
        )
        self._subtasks[subtask_id] = sub
        if self._audit is not None:
            self._audit.record_knowledge_subtask_action(
                record_id=f"sub-{subtask_id}",
                actor_id=actor_id,
                action="create_knowledge_subtask",
                target=subtask_id,
                detail=f"task_id={task_id};agent_type={subtype.value}",
                ts=created_at,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return sub

    def _get_scoped(self, subtask_id: str) -> KnowledgeSubTask:
        from agents.enterprise.organization import EnterpriseIsolationError

        s = self._subtasks.get(subtask_id)
        if s is None:
            raise EnterpriseIsolationError(f"子任务 {subtask_id!r} 不存在")
        if s.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"子任务 {subtask_id!r} 归属组织 {s.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return s

    def get(self, *, subtask_id: str) -> KnowledgeSubTask:
        """按组织作用域读取子任务（跨域抛错）。"""
        return self._get_scoped(subtask_id)

    def list_for_task(self, *, task_id: str) -> list[KnowledgeSubTask]:
        """列举某任务下的全部子任务（组织作用域过滤）。"""
        out: list[KnowledgeSubTask] = []
        for s in self._subtasks.values():
            if s.org_id != self._org_id:
                continue
            if s.task_id == task_id:
                out.append(s)
        return out

    def complete(
        self,
        *,
        subtask_id: str,
        output: "dict | None" = None,
        updated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> KnowledgeSubTask:
        """标记子任务完成并写入中间产出（默认 AI 审计；产出仅候选，不自动落地，红线③/④）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下完成子任务（红线①/⑤）"
            )
        sub = self._get_scoped(subtask_id)
        sub.output = dict(output or {})
        sub.status = KnowledgeSubTaskStatus.DONE
        sub.updated_at = updated_at
        if self._audit is not None:
            self._audit.record_knowledge_subtask_action(
                record_id=f"sub-done-{subtask_id}",
                actor_id=actor_id,
                action="complete_knowledge_subtask",
                target=subtask_id,
                detail=f"task_id={sub.task_id};agent_type={sub.agent_type.value};status=done",
                ts=updated_at,
                actor_kind=actor_kind or AuditActorKind.AI,
            )
        return sub


__all__ = [
    "KnowledgeSubTaskType",
    "KnowledgeSubTaskStatus",
    "KnowledgeSubTask",
    "KnowledgeSubTaskService",
]
