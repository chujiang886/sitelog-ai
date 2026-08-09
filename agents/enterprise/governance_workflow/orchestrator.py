"""Phase 3.8.25 企业智能体治理工作流编排器 —— **唯一真实实现**。

.. note:: Phase 3.8.27 治理基础设施收敛层

   本文件是 ``GovernanceWorkflowOrchestrator`` 的**唯一**实现。Phase 3.8.25 曾同时
   存在 ``orchestrator.py`` 与 ``service.py`` 两份同名实现（前者被生产装配层与驾驶舱
   使用，后者被包 ``__init__`` 再导出与另一套测试使用），构成严重架构债：同一个类名
   在不同 import 路径上解析为两个不同的类对象，红线守卫、状态机语义、审计口径、存储
   模型全部各写一遍，任何一侧修补都无法保证另一侧同步。

   3.8.27 将两份实现合并至此，``service.py`` 降级为**向后兼容再导出垫片**（不含任何
   实现）。合并原则：**取严不取宽** —— 任一侧更严格的守卫全部保留，任一侧更宽松的
   默认值全部收紧（例如 ``submit_execution_result`` 不再默认 ``actor_kind="user"``，
   必须由调用方显式声明责任人类型）。

定位：**复用而非重建**。本编排器把「用户问题 → 事实辅助分析（3.8.24 助手）→
人工研判 → 治理任务创建（3.8.21 问责层）→ 执行跟踪 → 结果归档 → 审计闭环」串成
一条可追踪流水线，自己**不重写** 3.8.21 问责层、3.8.24 知识助手、既有权限/身份/
可见性策略，只**组合调用**它们。

方法边界（谁能调用，一眼看清）：

============================  ==========  ==================================
方法                          发起者      语义
============================  ==========  ==================================
``create_workflow``           AI / 人工   登记候选工作流（created）
``register_candidate``        AI / 人工   同上（3.8.25 编排器历史别名）
``create_from_answer_draft``  AI / 人工   由 3.8.24 助手草稿登记候选（只落 created）
``create_from_draft``         **仅 USER** 由 3.8.24 事实草稿人工立案
``submit_for_review``         AI / 人工   推送进人工研判队列（under_review）
``human_confirm``             **仅 USER** 人工研判（→ human_confirmed）
``start_execution``           **仅 USER** 人工开始执行（→ in_progress）
``record_execution``          **仅 USER** 登记人工执行事实（不改状态）
``submit_execution_result``   **仅 USER** 人工提交结果（→ waiting_result）
``human_complete``            **仅 USER** 人工确认完成（→ completed）
``append_note`` /
``append_human_note``         **仅 USER** 追加人工备注
``archive`` / ``human_archive`` **仅 USER** 人工归档
``list_* / get_*``            只读        事实查询（经权限校验）
============================  ==========  ==================================

与本仓库既有企业层服务一致，本类继承 ``_RedLineForbiddenMixin``，并通过
``_FORBIDDEN = _WORKFLOW_FORBIDDEN``（结构级禁名）拦截自动审批 / 自动执行 / 自动
关闭 / 自动生成策略 / 代替责任人等禁名方法。

红线（fail-closed，六条，与主理人 Phase 3.8.25 指令一致）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② 不输出 ``engineering_approved``（继承自 3.8.21，已在 ``_FORBIDDEN`` 内）。
③ 禁 AI 自动治理 / 自动审批 / 自动关闭问题：所有前进状态转移的人工节点均
   ``require_human_actor(USER)``；AI 仅能 ``create_workflow`` / ``register_candidate``
   （落 CREATED 候选）与 ``submit_for_review``（推入人工研判队列，不构成治理决定）。
④ 禁 AI 自动执行治理动作：执行跟踪入口强制 ``require_human_actor(USER)`` 且
   ``GovernanceExecutionRecord.actor_kind`` 必须为 ``user``。
⑤ 禁 AI 自动生成治理策略 / 改知识：所有人工文本经六组语义扫描
   （``_reject_all_markers``）；对权限/可见性策略纯只读。
⑥ 禁 AI 代替治理责任人：人工确认 / 执行 / 完成 / 归档 / 备注全部
   ``require_human_actor(USER)``，审计留痕 actor / time / decision / reason。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.agent_governance_workflow import (
    GovernanceTaskSourceType,
)
from agents.enterprise.audit import AuditActorKind, require_human_actor
from agents.enterprise.governance_workflow.forbidden import _WORKFLOW_FORBIDDEN
from agents.enterprise.governance_workflow.models import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
    _reject_all_markers,
)
from agents.enterprise.governance_workflow.repository import (
    InMemoryWorkflowRepository,
    WorkflowHistoryEntry,
    WorkflowHistoryEvent,
    WorkflowRepository,
)
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class GovernanceWorkflowAccessDenied(
    EnterpriseIsolationError, EnterpriseRedLineViolationError
):
    """治理工作流访问被拒（默认拒绝闸门统一异常，Phase 3.8.27）。

    合并前两份实现对「权限拒绝」抛出的异常类型不同：``orchestrator.py`` 抛
    ``EnterpriseRedLineViolationError``（红线语义），``service.py`` 抛
    ``EnterpriseIsolationError``（隔离语义）。二者都是 ``Exception`` 的直接子类，
    因此本异常**同时继承二者**：任何一方的既有捕获契约（``pytest.raises`` /
    上层 ``except``）都继续成立，不需要修改任何调用方或测试。

    语义上二者本就是同一件事：**权限默认拒绝既是隔离失败，也是红线⑤守卫生效**。
    """


class GovernanceWorkflowOrchestrator(_RedLineForbiddenMixin):
    """治理工作流编排器（任务1/2/3/4/5 主体，唯一真实实现）。

    说明：3.8.25 的六态机 ``CREATED → UNDER_REVIEW → HUMAN_CONFIRMED →
    IN_PROGRESS → WAITING_RESULT → COMPLETED`` 由本类驱动；3.8.21 的
    ``GovernanceWorkflowService``（五态问责机）作为**可选**依赖在
    ``human_confirm`` 通过时派生「治理任务」，二者并存、互不覆盖 —— 本类
    **绝不代 3.8.21 推进任务状态**（各自守卫各自的状态机，避免绕过人工节点）。
    """

    # 结构级红线拦截：编排层禁名（继承 3.8.21 + 编排专属增量）。
    _FORBIDDEN = _WORKFLOW_FORBIDDEN

    #: 默认资源类别。沿用合并前 ``service.py`` 的 ``"data"``：治理工作流数据在
    #: ``_AGENT_RESOURCE_SCOPE`` 中归属 data 类别；``"governance_workflow"`` 未在
    #: 作用域表内登记，若作为默认值会让 ENGINEER 角色被误拒（默认拒绝的副作用）。
    _DEFAULT_RESOURCE_CATEGORY = "data"

    def __init__(
        self,
        org_id: str,
        *,
        audit: Any = None,
        identity: "Optional[IdentityService]" = None,
        visibility: "Optional[KnowledgeVisibilityPolicy]" = None,
        permission_policy: "Optional[AgentPermissionPolicy]" = None,
        governance_workflow: Any = None,  # 3.8.21 问责层服务（可选）
        assistant: Any = None,            # 3.8.24 知识助手（可选）
        repository: "Optional[WorkflowRepository]" = None,  # 3.8.27 持久化端口
    ) -> None:
        """``org_id`` 兼容位置参数与关键字参数（合并前两份实现签名不同）。

        ``repository``（Phase 3.8.27 新增，可选）：治理事实的存储端口。不传时使用
        :class:`InMemoryWorkflowRepository`，行为与 3.8.25 的裸 dict 完全等价 ——
        因此**所有既有调用方无需任何改动**。需要跨进程留存治理责任事实时，传入
        :class:`JsonFileWorkflowRepository`（或未来的数据库适配器）即可，编排器
        本身不感知具体存储介质。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceWorkflowOrchestrator（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        # 只读使用：仅用于访问校验，绝不写任何权限或策略（红线⑤）。
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._governance_workflow = governance_workflow
        # 只读消费 3.8.24 助手层事实草稿（可为空）；本层绝不回写助手层状态。
        self._assistant = assistant

        # Phase 3.8.27：存储从「编排器内联的五个裸 dict」下沉到持久化端口。
        # 默认适配器是内存实现，语义与 3.8.25 逐字节等价；下面五个属性作为
        # 向后兼容视图代理到端口，既有代码与测试对 ``self._workflows`` 等的
        # 读写继续成立。
        self._repo: WorkflowRepository = repository or InMemoryWorkflowRepository()

    # ------------------------------------------------------------------
    # 存储视图（Phase 3.8.27：代理到持久化端口，保持既有属性契约）
    # ------------------------------------------------------------------

    @property
    def repository(self) -> WorkflowRepository:
        """当前持久化端口（只读暴露，供装配层与运维取证使用）。"""
        return self._repo

    @property
    def _workflows(self) -> Dict[str, GovernanceWorkflow]:
        """工作流字典视图（代理端口，历史属性契约不变）。"""
        return self._repo.workflows

    @property
    def _reviews(self) -> Dict[str, GovernanceWorkflowReview]:
        """人工研判字典视图（代理端口）。"""
        return self._repo.reviews

    @property
    def _executions(self) -> Dict[str, List[GovernanceExecutionRecord]]:
        """执行记录按 workflow_id 聚合的视图（驾驶舱依赖顺序化列表）。"""
        return self._repo.executions

    @property
    def _execution_index(self) -> Dict[str, GovernanceExecutionRecord]:
        """执行记录按 record_id 建立的唯一索引视图（重复登记检测依赖）。"""
        return self._repo.execution_index

    @property
    def _archived(self) -> Dict[str, GovernanceWorkflow]:
        """归档索引视图（代理端口）。"""
        return self._repo.archived

    def history(
        self, *, workflow_id: str = "", user: Any = None
    ) -> List[WorkflowHistoryEntry]:
        """只读回放一条（或全部）治理工作流的变更历史（Phase 3.8.27）。

        与审计互补：审计按动作类别全局归档，本接口按工作流回放生命周期轨迹
        —— 「这条工作流经过哪些状态、每步是谁在何时推动的」。**只读**，
        端口层不提供任何改写历史的入口（append-only，红线⑥）。
        """
        if user is not None:
            self._ensure_access(user=user)
        return self._repo.list_history(workflow_id=workflow_id)

    # ------------------------------------------------------------------
    # 隔离与访问控制（红线⑤/⑥：默认拒绝 + 组织隔离）
    # ------------------------------------------------------------------

    def _ensure_same_org(self, org_id: str, *, op: str) -> None:
        """跨组织隔离校验（**禁止跨组织操作治理工作流**，默认拒绝）。"""
        target = str(org_id or "").strip()
        if target and self._org_id and target != self._org_id:
            raise EnterpriseIsolationError(
                f"{op} 拒绝跨组织访问：本服务归属 {self._org_id!r}，"
                f"目标数据归属 {target!r}（红线⑤/⑥：禁止跨组织读取/处置治理工作流）"
            )

    def _ensure_org_scope(self, target_org: str, op: str) -> None:
        """``_ensure_same_org`` 的历史别名（3.8.25 orchestrator 侧调用方兼容）。"""
        self._ensure_same_org(target_org, op=op)

    def _policy_allows(self, *, user: Any, resource_category: str) -> bool:
        """询问权限策略是否放行（**任何异常一律视为拒绝**，fail-closed）。

        兼容两种策略形态：完整 ``AgentPermissionPolicy``（接受
        ``required_permission``）与仅实现 ``check_agent_access(user,
        resource_category)`` 的最小鸭子类型策略。
        """
        policy = self._permission_policy
        if policy is None:
            return True
        try:
            return bool(
                policy.check_agent_access(
                    user=user,
                    resource_category=resource_category,
                    required_permission=Permission.READ_RESOURCE,
                )
            )
        except TypeError:
            # 最小鸭子类型策略：不接受 required_permission。
            try:
                return bool(
                    policy.check_agent_access(
                        user=user, resource_category=resource_category
                    )
                )
            except Exception:
                return False
        except Exception:
            return False

    def _ensure_access(
        self, *, user: Any = None, resource_category: str = ""
    ) -> None:
        """治理工作流数据访问权限校验（**默认拒绝**）。

        - ``user is None``：不做用户级校验（仅组织隔离生效），与合并前两份实现一致；
        - 有 ``AgentPermissionPolicy``：角色须在资源类别作用域内且通过身份层读权限；
        - 无策略但有 ``IdentityService``：退化为身份层 ``READ_RESOURCE`` 校验；
        - 任一不过即抛 ``GovernanceWorkflowAccessDenied``（同时是隔离错误与红线错误）。

        本方法**只读校验**，绝不修改任何权限或策略（红线⑤）。
        """
        if user is None:
            return
        category = resource_category or self._DEFAULT_RESOURCE_CATEGORY
        if self._permission_policy is not None:
            if not self._policy_allows(user=user, resource_category=category):
                raise GovernanceWorkflowAccessDenied(
                    f"用户角色无权限访问治理工作流编排数据"
                    f"（resource={category}），默认拒绝（红线⑤）"
                )
            return
        if self._identity is not None:
            allowed = False
            try:
                allowed = bool(
                    hasattr(user, "role")
                    and self._identity.check(user, Permission.READ_RESOURCE)
                )
            except Exception:
                allowed = False
            if not allowed:
                raise GovernanceWorkflowAccessDenied(
                    "无 AgentPermissionPolicy 时，需经身份层 READ_RESOURCE 校验，默认拒绝"
                )

    # ------------------------------------------------------------------
    # 内部：取工作流 / 状态机 / 责任人守卫
    # ------------------------------------------------------------------

    def _get_workflow_or_raise(
        self, workflow_id: str, *, op: str = "get_workflow"
    ) -> GovernanceWorkflow:
        """只读取出治理工作流，不存在即拒绝（禁止凭空推进编排）。"""
        wf = self._repo.get_workflow(workflow_id)
        if wf is None:
            raise EnterpriseRedLineViolationError(
                f"{op} 找不到治理工作流 {workflow_id!r}："
                f"禁止凭空推进治理编排 / 处置治理工作流（红线⑥：可溯源）"
            )
        self._ensure_same_org(wf.org_id, op=op)
        return wf

    def _get_workflow(self, workflow_id: str) -> GovernanceWorkflow:
        """``_get_workflow_or_raise`` 的历史别名（3.8.25 orchestrator 侧兼容）。"""
        return self._get_workflow_or_raise(workflow_id, op="get_workflow")

    @staticmethod
    def _ensure_transition(
        wf: GovernanceWorkflow, target: GovernanceWorkflowStatus, *, op: str
    ) -> None:
        """校验状态迁移合法性（非法迁移直接拒绝，只前进不回退）。"""
        if not wf.can_transition_to(target):
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝把工作流 {wf.workflow_id!r} 从 {wf.status.value} 迁移到 "
                f"{target.value}：非法状态迁移（编排只能按 created → under_review → "
                f"human_confirmed → in_progress → waiting_result → completed 由真实"
                f"人工逐步推进，红线③/④/⑥）"
            )

    @staticmethod
    def _ensure_not_archived(wf: GovernanceWorkflow, *, op: str) -> None:
        """已归档的工作流为只读事实，禁止再改（红线⑥：归档即封存）。"""
        if wf.archived:
            raise EnterpriseRedLineViolationError(
                f"{op} 拒绝修改已归档工作流 {wf.workflow_id!r}："
                f"归档后的治理事实只读封存（红线⑥）"
            )

    @staticmethod
    def _require_actor_id(actor_id: Any, *, op: str) -> str:
        """人工节点必须提供真实 actor_id（红线⑥：人工责任可追溯）。"""
        aid = str(actor_id or "").strip()
        if not aid:
            raise EnterpriseRedLineViolationError(
                f"{op} 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        return aid

    @staticmethod
    def _pick_actor(primary: Any, fallback: Any) -> Any:
        """在两套历史参数名之间取值（``reviewer_id``/``actor_id``、``actor``/``actor_id``）。"""
        if primary is not None and str(primary).strip():
            return primary
        return fallback

    # ------------------------------------------------------------------
    # 任务1：候选登记（AI 只能落 CREATED 候选态）
    # ------------------------------------------------------------------

    def create_workflow(
        self,
        *,
        workflow_id: str,
        source_type: "GovernanceWorkflowSourceType | str",
        source_id: str,
        title: str = "",
        description: str = "",
        source_facts: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: Any = None,
        task_id: str = "",
        draft_id: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """把一条治理线索登记为**候选工作流**（红线③/④）。

        AI 可以发起本方法，但产出物在结构上只能是 ``created`` 候选态：
        无人工研判人、无完成时间、``requires_human_confirmation`` 恒为 True。
        AI 既不能借此审批（红线③），也不能借此执行或关闭（红线④）。

        ``source_id`` 为空即拒绝（由 ``GovernanceWorkflow`` 构造期守卫）：工作流必须
        源自一条真实的上游治理发现（红线⑥）。重复 ``workflow_id`` 直接拒绝，禁止
        覆盖既有治理事实。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下创建治理工作流（红线①）"
            )
        if user is not None:
            self._ensure_access(user=user)
        self._ensure_same_org(self._org_id, op="create_workflow")
        if self._repo.has_workflow(workflow_id):
            raise EnterpriseRedLineViolationError(
                f"create_workflow 拒绝重复创建治理工作流 {workflow_id!r}："
                f"禁止覆盖既有治理事实（红线⑥）"
            )
        wf = GovernanceWorkflow(
            workflow_id=workflow_id,
            source_type=source_type,
            source_id=source_id,
            org_id=self._org_id,
            title=title,
            description=description,
            source_facts=list(source_facts or []),
            references=list(references or []),
            created_at=created_at,
            created_by=actor_id,
            task_id=task_id,
            draft_id=draft_id,
        )
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.CREATED,
            actor_id=actor_id,
            actor_kind=actor_kind,
            at=created_at,
            detail=f"source={wf.source_type.value}:{wf.source_id}",
        )
        self._audit_create(
            record_id=f"agent-governance-workflow-{wf.workflow_id}",
            actor_id=actor_id,
            action="create_governance_workflow_candidate",
            target=wf.workflow_id,
            detail=wf.summary(),
            ts=created_at,
            actor_kind=actor_kind,
        )
        return wf

    def register_candidate(
        self,
        *,
        workflow_id: str,
        source_type: "GovernanceWorkflowSourceType | str",
        source_id: str,
        title: str = "",
        description: str = "",
        source_facts: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
        created_at: str = "",
        actor_id: str = "ai",
        draft_id: str = "",
        task_id: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """登记一条治理工作流**候选**（3.8.25 编排器历史入口，红线③）。

        Phase 3.8.27 起本方法是 :meth:`create_workflow` 的**语义别名**（``actor_kind``
        固定为 AI —— 编排器侧历史调用方全部是 AI 侧线索登记），不再各自维护一套建模
        与审计口径。保留方法名以免破坏 3.8.25 装配层与驾驶舱调用契约。
        """
        return self.create_workflow(
            workflow_id=workflow_id,
            source_type=source_type,
            source_id=source_id,
            title=title,
            description=description,
            source_facts=source_facts,
            references=references,
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=AuditActorKind.AI,
            task_id=task_id,
            draft_id=draft_id,
            user=user,
        )

    # ------------------------------------------------------------------
    # 任务2：桥接 3.8.24 知识助手草稿
    # ------------------------------------------------------------------

    def create_from_draft(
        self,
        *,
        draft: Any,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        title: str = "",
        description: str = "",
        created_at: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """从 3.8.24 ``GovernanceAnswerDraft`` 播种**人工待审核工作流**（仅 USER）。

        桥接语义（红线③/④/⑥）：

        - 助手草稿只是**事实材料**，不是治理结论。本方法只把草稿里的 ``facts`` /
          ``references`` 原样播种为工作流来源事实，**绝不自动创建任何治理动作、
          绝不自动推进状态**；
        - ``require_human_actor(actor_kind)`` 强制：**AI 无法用草稿凭空开工作流**，
          必须由真实人工看过草稿后决定是否立案（红线③/⑥）；
        - 草稿 ``requires_human_review`` 必须为 True，且 ``contains_recommendation``
          必须为 False，否则拒绝（防止上游被改造成「已采纳结论」后绕过人工）；
        - 产出工作流恒为 ``created`` 态，``requires_human_confirmation`` 恒为 True。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下从草稿创建治理工作流（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="create_from_draft")
        if user is not None:
            self._ensure_access(user=user)
        if draft is None:
            raise EnterpriseRedLineViolationError(
                "create_from_draft 缺少 draft：禁止凭空立案治理工作流（红线⑥）"
            )
        if getattr(draft, "requires_human_review", None) is not True:
            raise EnterpriseRedLineViolationError(
                "create_from_draft 拒绝 requires_human_review 非 True 的草稿："
                "助手答案永远是待人工审阅的材料，不得作为已采纳结论直接立案（红线④/⑥）"
            )
        if getattr(draft, "contains_recommendation", False):
            raise EnterpriseRedLineViolationError(
                "create_from_draft 拒绝含治理建议的草稿："
                "工作流只能由事实播种，不得由 AI 建议驱动（红线⑤/⑥）"
            )
        self._ensure_same_org(
            str(getattr(draft, "org_id", "") or "").strip(), op="create_from_draft"
        )
        answer_id = str(getattr(draft, "answer_id", "") or "").strip()
        if not answer_id:
            raise EnterpriseRedLineViolationError(
                "create_from_draft 拒绝无 answer_id 的草稿：来源必须可溯源（红线⑥）"
            )
        facts = [str(f) for f in list(getattr(draft, "facts", []) or [])]
        references = [str(r) for r in list(getattr(draft, "references", []) or [])]
        summary = str(getattr(draft, "summary", "") or "")
        return self.create_workflow(
            workflow_id=workflow_id,
            source_type=GovernanceWorkflowSourceType.ASSISTANT_DRAFT,
            source_id=answer_id,
            title=title or f"governance-workflow-from-draft:{answer_id}",
            description=description or summary,
            source_facts=facts,
            references=references or [f"draft:{answer_id}"],
            created_at=created_at,
            actor_id=aid,
            actor_kind=actor_kind,
            draft_id=answer_id,
        )

    def create_from_answer_draft(
        self,
        *,
        draft: Any,
        workflow_id: Optional[str] = None,
        title: str = "",
        description: str = "",
        created_at: str = "",
        actor_id: str = "ai",
    ) -> GovernanceWorkflow:
        """由 3.8.24 助手答案草稿登记**候选**工作流（AI 可发起，只落 CREATED）。

        与 :meth:`create_from_draft` 的区别（**刻意保留两个入口**）：本方法是 AI 侧
        「把一条助手答案挂成候选线索」，产出物仍需人工经 ``submit_for_review`` +
        ``human_confirm`` 才能推进；``create_from_draft`` 则是**人工亲自立案**
        （强制 USER）。二者都只落 ``created`` 态，都不构成任何治理决定（红线③/⑥）。
        """
        if getattr(draft, "requires_human_review", None) is not True:
            raise EnterpriseRedLineViolationError(
                "GovernanceAnswerDraft.requires_human_review 必须为 True："
                "禁止把未经验证的助手答案转为治理工作流（红线③/⑥）"
            )
        answer_id = str(getattr(draft, "answer_id", "") or "").strip()
        if not answer_id:
            raise EnterpriseRedLineViolationError(
                "草稿缺少 answer_id：治理工作流必须可溯源到一条真实助手答案（红线⑥）"
            )
        return self.register_candidate(
            workflow_id=workflow_id or f"gw-{answer_id}",
            source_type=GovernanceWorkflowSourceType.ASSISTANT_DRAFT,
            source_id=answer_id,
            title=title or f"治理线索（源自助手答案 {answer_id}）",
            description=description or str(getattr(draft, "summary", "") or ""),
            source_facts=list(getattr(draft, "facts", []) or []),
            references=list(getattr(draft, "references", []) or []),
            created_at=created_at,
            actor_id=actor_id,
            draft_id=answer_id,
        )

    # ------------------------------------------------------------------
    # 状态机驱动（复用 models.py 的合法迁移表；非法迁移直接拒绝）
    # ------------------------------------------------------------------

    def submit_for_review(
        self,
        *,
        workflow_id: str,
        actor_id: str = "ai",
        actor_kind: Any = None,
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """把候选工作流推入**人工研判队列**（``created → under_review``）。

        本迁移**不构成任何治理决定**：它只表示「这条线索需要人来看」，因此允许 AI
        发起。真正的研判结论只能由 :meth:`human_confirm` 在 USER 守卫下给出
        （红线③/⑥）。审计写入 ``AGENT_GOVERNANCE_WORKFLOW_CREATE`` 类别 —— 送入
        队列属于「线索登记」语义，不是「研判」语义，故**刻意不落 REVIEW 类别**，
        避免审计口径把 AI 推送伪装成人工研判事实。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推进治理编排（红线①）"
            )
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="submit_for_review")
        self._ensure_not_archived(wf, op="submit_for_review")
        self._ensure_transition(
            wf, GovernanceWorkflowStatus.UNDER_REVIEW, op="submit_for_review"
        )
        prev = wf.status.value
        wf.status = GovernanceWorkflowStatus.UNDER_REVIEW
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.SUBMITTED_FOR_REVIEW,
            actor_id=actor_id,
            actor_kind=actor_kind,
            at=timestamp,
            status_from=prev,
        )
        self._audit_create(
            record_id=f"agent-governance-workflow-review-queue-{workflow_id}",
            actor_id=actor_id,
            action="submit_governance_workflow_for_human_review",
            target=workflow_id,
            detail=wf.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return wf

    # ------------------------------------------------------------------
    # 人工研判（仅 USER；REJECTED / NEED_MORE_INFO 不迁移状态）
    # ------------------------------------------------------------------

    def human_confirm(
        self,
        *,
        workflow_id: str,
        reason: str,
        reviewer_id: str = "",
        reviewer_kind: Any = None,
        actor_id: str = "",
        actor_kind: Any = None,
        decision: "WorkflowReviewDecision | str" = WorkflowReviewDecision.CONFIRMED,
        review_id: str = "",
        reviewed_at: str = "",
        org_id: Optional[str] = None,
        derive_task: bool = False,
        task_id: Optional[str] = None,
        user: Any = None,
    ) -> GovernanceWorkflowReview:
        """**真实人工研判**治理工作流（``under_review → human_confirmed``，红线③/⑥）。

        参数兼容：合并前两份实现分别用 ``reviewer_id`` / ``reviewer_kind``（编排器侧）
        与 ``actor_id`` / ``actor_kind``（服务侧）表达同一个「研判人」。Phase 3.8.27
        起两套都接受，由 :meth:`_pick_actor` 归一 —— **语义完全一致，不是两种权限**。

        ``require_human_actor(...)`` 强制：AI（``ai`` / ``system`` / ``None``）调用
        必抛 ``EnterpriseRedLineViolationError`` —— AI 永远无法自动审批。
        ``GovernanceWorkflowReview`` 构造期会**二次强制**同一守卫，形成双保险。

        决策语义：

        - ``CONFIRMED``：工作流迁移 ``under_review → human_confirmed``；
        - ``REJECTED`` / ``NEED_MORE_INFO``：**不迁移状态**，只登记人工研判事实
          （状态机只前进不回退，被否决的线索停在 under_review 等待补充）。

        无论何种决策 ``reason`` 必填，且全程写入审计（红线⑥）。确认通过时可选派生
        一条 3.8.21 治理任务（仍以真实人工为 actor，本层绝不代 3.8.21 推进状态）。
        """
        kind = self._pick_actor(reviewer_kind, actor_kind)
        require_human_actor(kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下进行人工研判（红线①）"
            )
        aid = self._require_actor_id(
            self._pick_actor(reviewer_id, actor_id), op="human_confirm"
        )
        if user is not None:
            self._ensure_access(user=user)
        scope_org = str(org_id or self._org_id or "").strip()
        self._ensure_same_org(scope_org, op="human_confirm")

        wf = self._get_workflow_or_raise(workflow_id, op="human_confirm")
        self._ensure_not_archived(wf, op="human_confirm")
        if wf.status is not GovernanceWorkflowStatus.UNDER_REVIEW:
            raise EnterpriseRedLineViolationError(
                f"human_confirm 拒绝在 {wf.status.value} 态研判工作流 "
                f"{workflow_id!r}：人工研判只能发生在 under_review 态"
                f"（须先经 submit_for_review 送入研判队列，红线③/⑥）"
            )

        rid = (
            str(review_id or "").strip()
            or f"gwr-{workflow_id}-{reviewed_at or 'now'}"
        )
        if self._repo.has_review(rid):
            raise EnterpriseRedLineViolationError(
                f"human_confirm 拒绝重复登记人工研判 {rid!r}："
                f"禁止覆盖既有人工研判事实（红线⑥）"
            )
        review = GovernanceWorkflowReview(
            review_id=rid,
            workflow_id=workflow_id,
            reviewer_id=aid,
            reviewer_kind=kind,
            decision=decision,
            reason=reason,
            reviewed_at=reviewed_at,
            org_id=self._org_id,
        )
        self._repo.put_review(review, status_from=wf.status.value)

        if self._audit is not None:
            # 审计记录 id 恒以 "gwr-" 前缀标识「人工研判」动作，便于按前缀区分
            # AI 推送（review-queue）与人工研判决定（红线⑥：责任可识别）。
            self._audit.record_agent_governance_workflow_review_action(
                record_id=rid if rid.startswith("gwr-") else f"gwr-{rid}",
                actor_id=aid,
                action="human_confirm_governance_workflow",
                target=workflow_id,
                detail=review.summary(),
                ts=reviewed_at,
                actor_kind=AuditActorKind.USER,
            )

        if review.is_confirmed:
            self._ensure_transition(
                wf, GovernanceWorkflowStatus.HUMAN_CONFIRMED, op="human_confirm"
            )
            prev = wf.status.value
            wf.status = GovernanceWorkflowStatus.HUMAN_CONFIRMED
            wf.confirmed_by = aid
            wf.confirmed_at = reviewed_at
            if derive_task and self._governance_workflow is not None:
                tid = task_id or f"gt-{workflow_id}"
                self._governance_workflow.create_task(
                    task_id=tid,
                    source_type=GovernanceTaskSourceType.GOVERNANCE_INSIGHT,
                    source_id=workflow_id,
                    title=wf.title,
                    detail=wf.description,
                    created_at=reviewed_at,
                    actor_id=aid,
                    actor_kind=AuditActorKind.USER,
                )
                wf.task_id = tid
            # 落库放在派生 3.8.21 治理任务**之后**：``task_id`` 属于本次人工研判
            # 产生的事实，必须与状态推进在同一份快照里，避免持久化适配器存下
            # 「已确认但无关联任务」的半截事实。
            self._repo.put_workflow(
                wf,
                event=WorkflowHistoryEvent.HUMAN_CONFIRMED,
                actor_id=aid,
                actor_kind=AuditActorKind.USER,
                at=reviewed_at,
                status_from=prev,
                detail=f"review={rid}",
            )
        return review

    # ------------------------------------------------------------------
    # 执行跟踪 + 闭环归档（全部人工节点，仅 USER）
    # ------------------------------------------------------------------

    def start_execution(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        action: str = "human_start_governance_execution",
        source: str = "",
        result: str = "",
        note: str = "",
        timestamp: str = "",
        record_id: str = "",
        user: Any = None,
    ) -> GovernanceExecutionRecord:
        """登记「**真实人工**开始执行治理动作」（``human_confirmed → in_progress``）。

        ``require_human_actor(actor_kind)`` 强制：AI 无法把工作流推进到执行态。
        本方法只**登记事实**，本层不持有任何执行能力（红线④）。

        返回值为落库的 ``GovernanceExecutionRecord``（合并前编排器侧返回工作流对象；
        3.8.27 统一返回执行记录 —— 记录里已含 ``workflow_id``，信息量严格更大，且
        与 :meth:`record_execution` / :meth:`submit_execution_result` 口径一致）。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下推进治理执行（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="start_execution")
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="start_execution")
        self._ensure_not_archived(wf, op="start_execution")
        self._ensure_transition(
            wf, GovernanceWorkflowStatus.IN_PROGRESS, op="start_execution"
        )
        record = self._append_execution(
            record_id=str(record_id or "").strip() or f"exec-start-{workflow_id}",
            workflow_id=workflow_id,
            action=action,
            actor=aid,
            timestamp=timestamp,
            result=result,
            source=source or f"workflow:{workflow_id}",
            note=note,
        )
        prev = wf.status.value
        wf.status = GovernanceWorkflowStatus.IN_PROGRESS
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.EXECUTION_STARTED,
            actor_id=aid,
            actor_kind=actor_kind,
            at=timestamp,
            status_from=prev,
            detail=f"record={record.record_id}",
        )
        self._audit_execution(
            record_id=f"agent-governance-workflow-exec-{record.record_id}",
            actor_id=aid,
            action="human_start_governance_execution",
            target=workflow_id,
            detail=record.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return record

    def record_execution(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        action: str,
        source: str,
        record_id: str,
        result: str = "",
        note: str = "",
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceExecutionRecord:
        """追加一条「**真实人工**执行事实」（**不改变状态**）。

        用于执行过程中的多次跟踪记录。强制 USER，且执行记录 ``actor_kind`` 恒为
        ``user`` —— AI 无法登记「自己执行了治理动作」（红线④/⑥）。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记治理执行事实（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="record_execution")
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="record_execution")
        self._ensure_not_archived(wf, op="record_execution")
        if wf.status not in (
            GovernanceWorkflowStatus.IN_PROGRESS,
            GovernanceWorkflowStatus.WAITING_RESULT,
        ):
            raise EnterpriseRedLineViolationError(
                f"record_execution 拒绝在 {wf.status.value} 态登记执行事实："
                f"执行跟踪只能发生在 in_progress / waiting_result 态"
                f"（须先经 human_confirm + start_execution，红线③/④）"
            )
        record = self._append_execution(
            record_id=record_id,
            workflow_id=workflow_id,
            action=action,
            actor=aid,
            timestamp=timestamp,
            result=result,
            source=source,
            note=note,
        )
        self._audit_execution(
            record_id=f"agent-governance-workflow-exec-{record.record_id}",
            actor_id=aid,
            action="human_track_governance_execution",
            target=workflow_id,
            detail=record.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return record

    def submit_execution_result(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str = "",
        actor: str = "",
        result: Optional[str] = None,
        source: str = "",
        action: str = "human_submit_governance_result",
        record_id: str = "",
        note: str = "",
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceExecutionRecord:
        """**真实人工**提交执行结果（``in_progress → waiting_result``，红线④/⑥）。

        参数兼容：责任人可用 ``actor_id``（服务侧历史名）或 ``actor``（编排器侧历史
        名）声明，语义一致。``actor_kind`` **不再有默认值**（合并前编排器侧默认
        ``"user"``）—— 责任人类型必须由调用方显式声明，避免默认值把 AI 调用悄悄
        当成人工（取严不取宽，红线④/⑥）。

        ``result`` 若**显式传入**则必须非空并经六组语义扫描（命中自动整改 / 自动执行 /
        自动审批 / 生成策略 / 改权限即拒绝，红线③/④/⑤）；省略时按空结果登记，
        由后续 :meth:`human_complete` 补齐闭环结论。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交治理结果（红线①）"
            )
        aid = self._require_actor_id(
            self._pick_actor(actor_id, actor), op="submit_execution_result"
        )
        if result is not None:
            if not str(result).strip():
                raise EnterpriseRedLineViolationError(
                    "submit_execution_result 缺少 result："
                    "人工执行结果必须由真实人工填写，AI 不代填（红线⑥）"
                )
            _reject_all_markers(
                result,
                ctx=f"submit_execution_result 的 result（工作流 {workflow_id!r}）",
            )
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="submit_execution_result")
        self._ensure_not_archived(wf, op="submit_execution_result")
        self._ensure_transition(
            wf, GovernanceWorkflowStatus.WAITING_RESULT, op="submit_execution_result"
        )
        record = self._append_execution(
            record_id=str(record_id or "").strip() or f"exec-result-{workflow_id}",
            workflow_id=workflow_id,
            action=action,
            actor=aid,
            timestamp=timestamp,
            result=str(result or ""),
            source=source or f"workflow:{workflow_id}",
            note=note,
        )
        prev = wf.status.value
        wf.status = GovernanceWorkflowStatus.WAITING_RESULT
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.RESULT_SUBMITTED,
            actor_id=aid,
            actor_kind=actor_kind,
            at=timestamp,
            status_from=prev,
            detail=f"record={record.record_id}",
        )
        self._audit_execution(
            record_id=f"agent-governance-workflow-exec-{record.record_id}",
            actor_id=aid,
            action="human_submit_governance_result",
            target=workflow_id,
            detail=record.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return record

    def human_complete(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        human_result: Optional[str] = None,
        note: str = "",
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """**真实人工**确认治理闭环（``waiting_result → completed``，红线③/⑥）。

        这是**唯一**能把工作流推进到 ``completed`` 的入口，且强制
        ``require_human_actor(USER)``：AI 无论如何无法自动关闭治理问题。

        闭环结论文本可用 ``human_result``（服务侧历史名）或 ``note``（编排器侧历史
        名）给出。``human_result`` 若**显式传入**则必须非空（AI 不得代替治理责任人
        下结论）；两者皆经六组语义扫描后追加到 ``human_notes``（红线⑤/⑥）。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下确认治理闭环（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="human_complete")
        if human_result is not None and not str(human_result).strip():
            raise EnterpriseRedLineViolationError(
                "human_complete 缺少 human_result："
                "闭环结论必须由真实人工填写，AI 不得代替治理责任人下结论（红线⑥）"
            )
        conclusion = str(
            human_result if human_result is not None else (note or "")
        ).strip()
        if conclusion:
            _reject_all_markers(
                conclusion,
                ctx=f"human_complete 的闭环结论（工作流 {workflow_id!r}）",
            )
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="human_complete")
        self._ensure_not_archived(wf, op="human_complete")
        self._ensure_transition(
            wf, GovernanceWorkflowStatus.COMPLETED, op="human_complete"
        )
        prev = wf.status.value
        wf.status = GovernanceWorkflowStatus.COMPLETED
        wf.completed_by = aid
        wf.completed_at = timestamp
        if conclusion:
            wf.human_notes.append(conclusion)
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.COMPLETED,
            actor_id=aid,
            actor_kind=actor_kind,
            at=timestamp,
            status_from=prev,
            detail=f"notes={len(wf.human_notes)}",
        )
        self._audit_execution(
            record_id=f"agent-governance-workflow-complete-{workflow_id}",
            actor_id=aid,
            action="human_complete_governance_workflow",
            target=workflow_id,
            detail=wf.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return wf

    def append_human_note(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        note: str,
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """**真实人工**追加备注（任意非归档态可用，红线③/④/⑤/⑥）。

        备注经六组语义扫描；AI 无法追加备注（强制 USER），避免 AI 借备注夹带建议。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下追加治理备注（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="append_human_note")
        if not str(note or "").strip():
            raise EnterpriseRedLineViolationError(
                "append_human_note 缺少 note：禁止落库空白人工备注（红线⑥）"
            )
        _reject_all_markers(
            note, ctx=f"append_human_note 的 note（工作流 {workflow_id!r}）"
        )
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="append_human_note")
        self._ensure_not_archived(wf, op="append_human_note")
        wf.human_notes.append(str(note).strip())
        self._repo.put_workflow(
            wf,
            event=WorkflowHistoryEvent.NOTE_APPENDED,
            actor_id=aid,
            actor_kind=actor_kind,
            at=timestamp,
            status_from=wf.status.value,
            detail=f"note_count={len(wf.human_notes)}",
        )
        self._audit_execution(
            record_id=(
                f"agent-governance-workflow-note-{workflow_id}-{len(wf.human_notes)}"
            ),
            actor_id=aid,
            action="human_append_governance_note",
            target=workflow_id,
            detail=f"workflow={workflow_id} note_count={len(wf.human_notes)}",
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return wf

    def append_note(
        self,
        *,
        workflow_id: str,
        note: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """:meth:`append_human_note` 的历史别名（3.8.25 编排器侧调用方兼容）。"""
        return self.append_human_note(
            workflow_id=workflow_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            note=note,
            timestamp=timestamp,
            user=user,
        )

    def human_archive(
        self,
        *,
        workflow_id: str,
        actor_kind: Any,
        actor_id: str,
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """**真实人工**归档已完成的治理工作流（结果归档，红线③/⑥）。

        只有 ``completed`` 态可归档；归档后工作流转为只读封存事实。强制 USER：
        AI 无法自动归档。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下归档治理工作流（红线①）"
            )
        aid = self._require_actor_id(actor_id, op="human_archive")
        if user is not None:
            self._ensure_access(user=user)
        wf = self._get_workflow_or_raise(workflow_id, op="human_archive")
        self._ensure_not_archived(wf, op="human_archive")
        if wf.status is not GovernanceWorkflowStatus.COMPLETED:
            raise EnterpriseRedLineViolationError(
                f"human_archive 拒绝归档 {wf.status.value} 态工作流 {workflow_id!r}："
                f"只有经真实人工确认完成（completed）的治理事实才能归档（红线③/⑥）"
            )
        wf.archived = True
        wf.archived_by = aid
        wf.archived_at = timestamp
        self._repo.put_archived(
            wf, actor_id=aid, actor_kind=actor_kind, at=timestamp
        )
        self._audit_execution(
            record_id=f"agent-governance-workflow-archive-{workflow_id}",
            actor_id=aid,
            action="human_archive_governance_workflow",
            target=workflow_id,
            detail=wf.summary(),
            ts=timestamp,
            actor_kind=actor_kind,
        )
        return wf

    def archive(
        self,
        *,
        workflow_id: str,
        actor_id: str,
        actor_kind: Any,
        timestamp: str = "",
        user: Any = None,
    ) -> GovernanceWorkflow:
        """:meth:`human_archive` 的历史别名（3.8.25 编排器侧调用方兼容）。"""
        return self.human_archive(
            workflow_id=workflow_id,
            actor_kind=actor_kind,
            actor_id=actor_id,
            timestamp=timestamp,
            user=user,
        )

    # ------------------------------------------------------------------
    # 内部：执行记录落库 + 审计代理
    # ------------------------------------------------------------------

    def _append_execution(
        self,
        *,
        record_id: str,
        workflow_id: str,
        action: str,
        actor: str,
        timestamp: str,
        result: str,
        source: str,
        note: str = "",
    ) -> GovernanceExecutionRecord:
        """落库一条执行事实（重复 ``record_id`` 直接拒绝，禁止覆盖既有事实）。

        双索引：``_executions`` 按 ``workflow_id`` 聚合成列表（驾驶舱
        ``get_execution_records`` 依赖顺序化视图）；``_execution_index`` 按
        ``record_id`` 建唯一索引（重复登记检测依赖）。二者指向同一批对象。
        """
        rid = str(record_id or "").strip()
        if self._repo.has_execution(rid):
            raise EnterpriseRedLineViolationError(
                f"拒绝重复登记执行事实 {rid!r}：禁止覆盖既有治理事实（红线⑥）"
            )
        record = GovernanceExecutionRecord(
            record_id=rid,
            workflow_id=workflow_id,
            action=action,
            actor=actor,
            # 红线④：执行记录的责任人类型恒为字面量 "user"（构造期二次强制）。
            # 上游 require_human_actor(actor_kind) 已校验为真实 USER。
            actor_kind="user",
            timestamp=timestamp,
            result=result,
            source=source,
            note=note,
            org_id=self._org_id,
        )
        self._repo.put_execution(record)
        return record

    def _audit_create(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str,
        detail: str,
        ts: str,
        actor_kind: Any,
    ) -> None:
        if self._audit is None:
            return
        self._audit.record_agent_governance_workflow_create_action(
            record_id=record_id,
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
            actor_kind=actor_kind,
        )

    def _audit_execution(
        self,
        *,
        record_id: str,
        actor_id: str,
        action: str,
        target: str,
        detail: str,
        ts: str,
        actor_kind: Any,
    ) -> None:
        if self._audit is None:
            return
        self._audit.record_agent_governance_workflow_execution_action(
            record_id=record_id,
            actor_id=actor_id,
            action=action,
            target=target,
            detail=detail,
            ts=ts,
            actor_kind=actor_kind,
        )

    def _record_execution_audit(
        self, *, workflow_id: str, actor_id: str, action: str, detail: str, ts: str
    ) -> None:
        """:meth:`_audit_execution` 的历史别名（3.8.25 编排器侧内部调用兼容）。"""
        self._audit_execution(
            record_id=f"agent-governance-workflow-exec-{workflow_id}-{action}",
            actor_id=actor_id,
            action=action,
            target=workflow_id,
            detail=detail,
            ts=ts,
            actor_kind=AuditActorKind.USER,
        )

    # ------------------------------------------------------------------
    # 只读查询（默认拒绝 + 组织隔离）
    # ------------------------------------------------------------------

    def get_workflow(self, workflow_id: str, *, user: Any = None) -> GovernanceWorkflow:
        """只读取出单条治理工作流（经权限与跨组织校验）。"""
        if user is not None:
            self._ensure_access(user=user)
        return self._get_workflow_or_raise(workflow_id, op="get_workflow")

    def list_workflows(
        self,
        *,
        org_id: Optional[str] = None,
        status: "Optional[GovernanceWorkflowStatus | str]" = None,
        user: Any = None,
        resource_category: str = "",
    ) -> List[GovernanceWorkflow]:
        """只读列出治理工作流（组织隔离 + 可选权限闸门 + 可选状态过滤）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        scope = str(org_id or self._org_id or "").strip()
        if org_id:
            self._ensure_same_org(scope, op="list_workflows")
        target = (
            None
            if status is None
            else (
                status
                if isinstance(status, GovernanceWorkflowStatus)
                else GovernanceWorkflowStatus(status)
            )
        )
        out: List[GovernanceWorkflow] = []
        for wf in self._workflows.values():
            if scope and wf.org_id and wf.org_id != scope:
                continue
            if target is not None and wf.status is not target:
                continue
            out.append(wf)
        return out

    def get_reviews(
        self, workflow_id: Optional[str] = None, *, user: Any = None
    ) -> List[GovernanceWorkflowReview]:
        """只读列出人工研判记录（位置参数形态，驾驶舱依赖）。"""
        if user is not None:
            self._ensure_access(user=user)
        return [
            r
            for r in self._reviews.values()
            if (workflow_id is None or r.workflow_id == workflow_id)
        ]

    def list_reviews(
        self, *, workflow_id: str = "", user: Any = None
    ) -> List[GovernanceWorkflowReview]:
        """只读列出本组织人工研判记录（关键字形态，可按工作流过滤）。"""
        if user is not None:
            self._ensure_access(user=user)
        return [
            r
            for r in self._reviews.values()
            if r.org_id == self._org_id
            and (not workflow_id or r.workflow_id == workflow_id)
        ]

    def get_execution_records(
        self, workflow_id: str, *, user: Any = None
    ) -> List[GovernanceExecutionRecord]:
        """只读列出某工作流的执行跟踪记录（位置参数形态，驾驶舱依赖）。"""
        if user is not None:
            self._ensure_access(user=user)
        return list(self._executions.get(str(workflow_id).strip(), []))

    def list_execution_records(
        self, *, workflow_id: str = "", user: Any = None
    ) -> List[GovernanceExecutionRecord]:
        """只读列出本组织执行跟踪记录（关键字形态，可按工作流过滤）。"""
        if user is not None:
            self._ensure_access(user=user)
        return [
            e
            for e in self._execution_index.values()
            if e.org_id == self._org_id
            and (not workflow_id or e.workflow_id == workflow_id)
        ]


__all__ = [
    "GovernanceWorkflowOrchestrator",
    "GovernanceWorkflowAccessDenied",
]
