"""Phase 3.8.27 治理工作流持久化端口（Task 2）。

.. note:: 为什么需要这一层

   Phase 3.8.25 的 ``GovernanceWorkflowOrchestrator`` 把全部治理事实（工作流 /
   人工研判 / 执行记录 / 归档）存在**五个裸 dict** 里：进程一退，所有「谁在何时
   做了什么决定」的责任事实全部蒸发；而 Phase 3.8.26 在 ``backend/app/db`` 侧建了
   一套 SQLAlchemy 仓储，却与 agents 层编排器**完全脱节** —— 编排器不知道它存在，
   仓储也拿不到编排器的状态机。这是典型的「两层各存一份、谁也不是事实源」架构债。

   3.8.27 的解法是**依赖倒置**：在 agents 层定义持久化**端口**（本文件的
   :class:`WorkflowRepository` 抽象基类），编排器只依赖端口；具体存储由适配器实现。
   本阶段交付两个适配器：

   ==============================  ====================================
   适配器                          定位
   ==============================  ====================================
   ``InMemoryWorkflowRepository``  默认实现，与 3.8.25 裸 dict **行为等价**
   ``JsonFileWorkflowRepository``  可持久化实现，原子写 + 完整性校验
   ==============================  ====================================

   ``backend/app/db/repositories/governance_workflow_repository.py``（3.8.26 的
   SQLAlchemy 仓储）在后续阶段可作为**第三个适配器**接入同一端口，届时 agents 层
   无需任何改动 —— 这正是端口存在的意义。本阶段**不**把 SQLAlchemy 拉进 agents 层：
   agents 包必须能在无数据库、无 backend 依赖的环境下独立运行。

红线约束（fail-closed，与编排器六条红线一一对应）：

① 所有构造与写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② 继承 ``_RedLineForbiddenMixin``，``_FORBIDDEN`` 覆盖 ``auto_approve`` /
   ``auto_close_workflow`` / ``purge_history`` / ``delete_workflow`` 等禁名 ——
   仓储层在**结构上**不提供任何「自动推进」与「抹除治理事实」的入口。
③ 历史是 **append-only**：``append_history`` 只增不改，端口**不提供**任何
   update/delete history 方法（治理留痕不可被 AI 覆盖）。
④ 反序列化（从磁盘恢复）走**受控 restore 路径**：既不能绕过语义扫描，也不能
   凭空造出「已人工确认」的工作流 —— 见 :func:`_restore_workflow` 的恢复期不变量。
⑤ 完整性校验：每条持久化记录带 SHA-256 摘要，加载时逐条比对，不一致即
   ``WorkflowStoreIntegrityError``（默认严格模式**拒绝启动**，绝不带病加载治理数据）。
⑥ 仓储自身**不做**任何人工身份判定 —— ``require_human_actor`` 的守卫在编排器与
   模型构造期，仓储不重复实现、更不放宽（取严不取宽）。
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import MISSING, dataclass, fields as dataclass_fields
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from agents.enterprise.governance_workflow.models import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
    _reject_all_markers,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# 异常
# ---------------------------------------------------------------------------

class WorkflowRepositoryError(Exception):
    """仓储层通用异常（记录不存在 / 载荷非法 / 存储不可用）。"""


class WorkflowStoreIntegrityError(
    WorkflowRepositoryError, EnterpriseRedLineViolationError
):
    """持久化存储完整性校验失败（红线⑤：绝不带病加载治理事实）。

    同时继承 ``EnterpriseRedLineViolationError``：上层既有的红线捕获契约
    （``pytest.raises(EnterpriseRedLineViolationError)`` / ``except`` 分支）
    对「存储被篡改/损坏」这一情形同样成立，无需新增捕获点。

    .. warning:: 摘要是**完整性**校验（防意外截断、编码损坏、半写入），
       不是密码学**防篡改**保证 —— 掌握文件写权限的人可以重算摘要。真正的
       防篡改依赖操作系统文件权限与 3.8.26 数据库侧的 CHECK 约束，本层不做
       超出自身能力的安全承诺。
    """


# ---------------------------------------------------------------------------
# 变更历史（append-only）
# ---------------------------------------------------------------------------

class WorkflowHistoryEvent(str, Enum):
    """治理工作流变更历史事件（**只描述已发生的事实**）。

    枚举中**刻意不存在** ``auto_approved`` / ``auto_closed`` / ``ai_confirmed``：
    AI 自动推进的历史事件在类型层面即不可表达（红线③/④）。
    """

    CREATED = "created"
    SUBMITTED_FOR_REVIEW = "submitted_for_review"
    #: 人工研判**事实**登记（无论结论是 confirmed / rejected / need_more_info）。
    REVIEWED = "reviewed"
    #: 工作流因研判通过而**推进**到 human_confirmed 态（与 REVIEWED 刻意分开：
    #: 「登记了一次研判」与「工作流被推进」是两件事，rejected 只有前者没有后者）。
    HUMAN_CONFIRMED = "human_confirmed"
    EXECUTION_STARTED = "execution_started"
    EXECUTION_RECORDED = "execution_recorded"
    RESULT_SUBMITTED = "result_submitted"
    COMPLETED = "completed"
    NOTE_APPENDED = "note_appended"
    ARCHIVED = "archived"
    RESTORED = "restored"


@dataclass(frozen=True)
class WorkflowHistoryEntry:
    """一条不可变的变更历史（append-only，禁止修改与删除）。

    与审计（``audit.py``）的关系：**互补而非重复**。审计面向合规，按动作类别
    分区、全局可检索；本历史面向单条工作流的**生命周期回放**，回答「这条工作流
    经过了哪些状态、每一步是谁在何时推动的」。二者都写，缺一不可（Task 2 要求
    「保持 Audit 事件完整」——本层不替换审计，只在其旁边增加可回放的状态轨迹）。
    """

    entry_id: str
    workflow_id: str
    event: WorkflowHistoryEvent = WorkflowHistoryEvent.CREATED
    actor_id: str = ""
    actor_kind: str = ""
    at: str = ""
    status_from: str = ""
    status_to: str = ""
    detail: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowHistoryEntry（红线①）"
            )
        # frozen dataclass：规范化只能经 object.__setattr__。
        object.__setattr__(self, "entry_id", str(self.entry_id).strip())
        object.__setattr__(self, "workflow_id", str(self.workflow_id).strip())
        object.__setattr__(self, "actor_id", str(self.actor_id).strip())
        object.__setattr__(
            self, "actor_kind", str(getattr(self.actor_kind, "value", self.actor_kind) or "").strip().lower()
        )
        object.__setattr__(self, "detail", str(self.detail).strip())
        object.__setattr__(self, "org_id", str(self.org_id).strip())
        if not isinstance(self.event, WorkflowHistoryEvent):
            object.__setattr__(self, "event", WorkflowHistoryEvent(self.event))

        if not self.entry_id:
            raise EnterpriseRedLineViolationError(
                "WorkflowHistoryEntry 缺少 entry_id：禁止落库无标识的变更历史（红线⑥）"
            )
        if not self.workflow_id:
            raise EnterpriseRedLineViolationError(
                f"WorkflowHistoryEntry {self.entry_id!r} 缺少 workflow_id："
                f"变更历史必须挂在一条真实工作流之上（红线⑥）"
            )
        _reject_all_markers(
            self.detail,
            ctx=f"WorkflowHistoryEntry {self.entry_id!r} 的 detail",
        )

    def to_payload(self) -> Dict[str, Any]:
        """序列化为可持久化的纯字典（只含事实字段）。"""
        return {
            "entry_id": self.entry_id,
            "workflow_id": self.workflow_id,
            "event": self.event.value,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "at": self.at,
            "status_from": self.status_from,
            "status_to": self.status_to,
            "detail": self.detail,
            "org_id": self.org_id,
        }


# ---------------------------------------------------------------------------
# 序列化 / 受控恢复
# ---------------------------------------------------------------------------

def _enum_value(value: Any) -> Any:
    """枚举取 ``.value``，其余原样（序列化统一入口）。"""
    return getattr(value, "value", value)


def _dataclass_payload(obj: Any) -> Dict[str, Any]:
    """把治理模型 dataclass 序列化为纯字典（枚举降级为字符串）。

    不使用 ``dataclasses.asdict``：后者会递归深拷贝并对枚举原样保留，
    这里需要的是「只取声明字段 + 枚举取值」的浅层、可 JSON 化结果。
    """
    out: Dict[str, Any] = {}
    for f in dataclass_fields(obj):
        value = getattr(obj, f.name)
        if isinstance(value, list):
            out[f.name] = [_enum_value(v) for v in value]
        else:
            out[f.name] = _enum_value(value)
    return out


def _digest(payload: Dict[str, Any]) -> str:
    """对载荷做 SHA-256 规范化摘要（完整性校验，非防篡改）。"""
    canonical = json.dumps(
        payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


#: 恢复期允许出现「人工确认事实」的状态（红线③：低于此线不得带 confirmed_by）。
_CONFIRMED_OR_BEYOND = (
    GovernanceWorkflowStatus.HUMAN_CONFIRMED,
    GovernanceWorkflowStatus.IN_PROGRESS,
    GovernanceWorkflowStatus.WAITING_RESULT,
    GovernanceWorkflowStatus.COMPLETED,
)


def _restore_workflow(payload: Dict[str, Any]) -> GovernanceWorkflow:
    """从持久化载荷**受控恢复**一条工作流。

    为什么不能直接调构造函数：``GovernanceWorkflow.__post_init__`` 是**创建期**
    守卫 —— 它规定「工作流只能以 created 候选态生成，且不得预填 confirmed_by /
    completed_by / archived」。这条守卫在**创建**语义下完全正确（禁止 AI 凭空造出
    一条「已被人工确认」的工作流），但它同时使得任何持久化恢复都不可能：一条
    昨天由真人确认过的工作流，今天从磁盘读回来时**本来就该**带着
    ``status=human_confirmed`` 与 ``confirmed_by``。

    因此恢复走独立路径，并以**恢复期不变量**替代创建期不变量 —— 不是放宽，而是
    换一组同样 fail-closed 的检查：

    1. ``safety_invariants_ok()`` 仍然断言（红线①）；
    2. 标识与溯源字段（``workflow_id`` / ``source_id``）仍然必填（红线⑥）；
    3. ``requires_human_confirmation`` 仍然恒为 True，载荷置 False 即拒（红线⑥）；
    4. **状态与人工事实必须自洽**：``confirmed_by`` 非空却停留在
       ``created`` / ``under_review``，或 ``status=completed`` 却无 ``completed_by``，
       或 ``archived=True`` 却无 ``archived_by`` —— 一律拒绝。这正是「禁止伪造人工
       确认事实」在恢复语义下的等价表述（红线③/⑥）；
    5. 文本字段仍走**六组语义扫描**（``_reject_all_markers``）：即便有人手改了
       JSON 塞进「自动审批通过」之类的措辞，也在加载期就被拦下（红线⑤）。

    任一不变量不成立即抛 :class:`WorkflowStoreIntegrityError`（fail-closed）。
    """
    if not safety_invariants_ok():
        raise EnterpriseRedLineViolationError(
            "safety_invariants_ok() 失败：禁止在启用态下恢复治理工作流（红线①）"
        )

    wf = object.__new__(GovernanceWorkflow)  # 绕过创建期守卫，改用恢复期不变量
    known = {f.name for f in dataclass_fields(GovernanceWorkflow)}
    unknown = set(payload) - known
    if unknown:
        raise WorkflowStoreIntegrityError(
            f"工作流载荷含未知字段 {sorted(unknown)!r}：拒绝加载来路不明的治理数据"
        )
    for f in dataclass_fields(GovernanceWorkflow):
        default: Any
        if f.default_factory is not MISSING:  # type: ignore[misc]
            default = f.default_factory()  # type: ignore[misc]
        elif f.default is not MISSING:
            default = f.default
        else:
            default = ""
        object.__setattr__(wf, f.name, payload.get(f.name, default))

    wf.status = GovernanceWorkflowStatus(wf.status)
    wf.source_type = GovernanceWorkflowSourceType(wf.source_type)
    wf.workflow_id = str(wf.workflow_id).strip()
    wf.source_id = str(wf.source_id).strip()
    wf.org_id = str(wf.org_id).strip()
    wf.source_facts = [str(x).strip() for x in (wf.source_facts or []) if str(x).strip()]
    wf.references = [str(x).strip() for x in (wf.references or []) if str(x).strip()]
    wf.human_notes = [str(x).strip() for x in (wf.human_notes or []) if str(x).strip()]

    # --- 恢复期不变量 ---
    if not wf.workflow_id:
        raise WorkflowStoreIntegrityError("恢复失败：工作流缺少 workflow_id（红线⑥）")
    if not wf.source_id:
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 缺少 source_id（红线⑥：必须可溯源）"
        )
    if wf.requires_human_confirmation is not True:
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 的 requires_human_confirmation 非 True："
            f"治理工作流的推进必须由真实人工确认，该标志不可被存储层改写（红线⑥）"
        )
    confirmed = bool(str(wf.confirmed_by).strip())
    if confirmed and wf.status not in _CONFIRMED_OR_BEYOND:
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 处于 {wf.status.value} 态却带有 "
            f"confirmed_by={wf.confirmed_by!r}：禁止伪造人工确认事实（红线③/⑥）"
        )
    if wf.status in _CONFIRMED_OR_BEYOND and not confirmed:
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 已推进到 {wf.status.value} 态却无 "
            f"confirmed_by：人工研判责任人缺失，治理链断裂（红线⑥）"
        )
    if wf.status is GovernanceWorkflowStatus.COMPLETED and not str(wf.completed_by).strip():
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 为 completed 态却无 completed_by："
            f"完成事实必须落到真实人工身上（红线⑥）"
        )
    if wf.archived and not str(wf.archived_by).strip():
        raise WorkflowStoreIntegrityError(
            f"恢复失败：工作流 {wf.workflow_id!r} 标记 archived 却无 archived_by："
            f"归档是真实人工动作，不得凭空存在（红线③/⑥）"
        )

    # --- 语义扫描（与创建期同一套六组标记，不放宽） ---
    _reject_all_markers(wf.title, ctx=f"恢复的工作流 {wf.workflow_id!r} 的 title")
    _reject_all_markers(
        wf.description, ctx=f"恢复的工作流 {wf.workflow_id!r} 的 description"
    )
    for idx, fact in enumerate(wf.source_facts):
        _reject_all_markers(
            fact, ctx=f"恢复的工作流 {wf.workflow_id!r} 的 source_facts[{idx}]"
        )
    for idx, note in enumerate(wf.human_notes):
        _reject_all_markers(
            note, ctx=f"恢复的工作流 {wf.workflow_id!r} 的 human_notes[{idx}]"
        )
    return wf


def _restore_review(payload: Dict[str, Any]) -> GovernanceWorkflowReview:
    """恢复一条人工研判记录。

    与工作流不同，``GovernanceWorkflowReview`` 的构造期守卫（reviewer 必须真实
    USER、reason 必填且过语义扫描）在恢复语义下**依然完全成立** —— 一条持久化的
    研判记录本来就该带着真实 reviewer 与理由。因此这里**直接走正常构造函数**，
    守卫一条不减（取严不取宽）。
    """
    try:
        return GovernanceWorkflowReview(
            review_id=payload.get("review_id", ""),
            workflow_id=payload.get("workflow_id", ""),
            reviewer_id=payload.get("reviewer_id", ""),
            reviewer_kind=payload.get("reviewer_kind"),
            decision=WorkflowReviewDecision(payload.get("decision", "need_more_info")),
            reason=payload.get("reason", ""),
            reviewed_at=payload.get("reviewed_at", ""),
            org_id=payload.get("org_id", ""),
        )
    except EnterpriseRedLineViolationError as exc:
        raise WorkflowStoreIntegrityError(
            f"恢复人工研判记录失败（存储中的研判事实不满足红线守卫）：{exc}"
        ) from exc


def _restore_execution(payload: Dict[str, Any]) -> GovernanceExecutionRecord:
    """恢复一条执行记录（同 :func:`_restore_review`，直接走构造期守卫）。"""
    try:
        return GovernanceExecutionRecord(
            record_id=payload.get("record_id", ""),
            workflow_id=payload.get("workflow_id", ""),
            action=payload.get("action", ""),
            actor=payload.get("actor", ""),
            actor_kind=payload.get("actor_kind", "user"),
            timestamp=payload.get("timestamp", ""),
            result=payload.get("result", ""),
            source=payload.get("source", ""),
            note=payload.get("note", ""),
            org_id=payload.get("org_id", ""),
        )
    except EnterpriseRedLineViolationError as exc:
        raise WorkflowStoreIntegrityError(
            f"恢复执行记录失败（存储中的执行事实不满足红线守卫）：{exc}"
        ) from exc


# ---------------------------------------------------------------------------
# 结构级红线禁名（仓储层专属增量）
# ---------------------------------------------------------------------------

#: 仓储层禁名：既不提供「自动推进」入口，也不提供「抹除治理事实」入口。
#: 前半段对应红线③/④（AI 自动审批 / 自动执行 / 自动关闭）；
#: 后半段对应红线⑥（治理留痕不可被删改 —— append-only 在结构上不可绕过）。
_REPOSITORY_FORBIDDEN = (
    # 红线③/④：仓储不得成为绕过人工节点的后门
    "auto_approve",
    "auto_confirm",
    "auto_review",
    "auto_close_workflow",
    "auto_complete_workflow",
    "auto_archive_workflow",
    "auto_execute",
    "auto_advance_status",
    "advance_status_automatically",
    "force_status",
    "set_status_without_human",
    "bypass_human_review",
    # 红线⑥：治理事实与留痕不可删改
    "delete_workflow",
    "remove_workflow",
    "drop_workflow",
    "delete_review",
    "remove_review",
    "delete_execution",
    "remove_execution",
    "delete_history",
    "remove_history",
    "purge_history",
    "purge_workflows",
    "truncate_history",
    "rewrite_history",
    "update_history",
    "overwrite_history",
    "clear_all",
    "wipe",
)


# ---------------------------------------------------------------------------
# 端口：WorkflowRepository
# ---------------------------------------------------------------------------

class WorkflowRepository(_RedLineForbiddenMixin, ABC):
    """治理工作流持久化**端口**（抽象基类，Task 2 的核心交付）。

    职责边界（**只存事实，不做判断**）：

    - 仓储**不**实现状态机：``created → under_review → ...`` 的合法转移由编排器
      的 ``_ensure_transition`` 守卫，仓储只忠实记录调用方给它的对象；
    - 仓储**不**实现人工身份判定：``require_human_actor`` 在编排器与模型构造期，
      仓储不重复、更不放宽；
    - 仓储**不**提供删除与历史改写（见 ``_FORBIDDEN``）。

    四类能力对应 Task 2 要求的 create / update / query / history：

    ==========  ====================================================
    create      ``put_workflow`` / ``put_review`` / ``put_execution``
    update      同上（upsert 语义：同 id 覆盖为最新事实快照）
    query       ``get_*`` / ``has_*`` / ``list_*``
    history     ``append_history`` / ``list_history``（append-only）
    ==========  ====================================================

    .. note:: 为什么 ``put_workflow`` 是 upsert 而不是 insert-only

       编排器对工作流是**原地改写**（``wf.status = ...``），同一个对象在生命周期中
       被多次推进。仓储若坚持 insert-only，编排器每次推进都要先 delete 再 insert，
       反而给出了删除入口（违背红线⑥）。因此这里选择 upsert：**重复创建的拒绝
       由编排器负责**（``create_workflow`` 已有 ``workflow_id in self._workflows``
       的重复拒绝守卫），仓储只保证「最新快照 + 完整历史」。
    """

    _FORBIDDEN = _REPOSITORY_FORBIDDEN

    # -------------------------- 工作流 --------------------------

    @abstractmethod
    def put_workflow(
        self,
        workflow: GovernanceWorkflow,
        *,
        event: WorkflowHistoryEvent,
        actor_id: str = "",
        actor_kind: Any = "",
        at: str = "",
        status_from: str = "",
        detail: str = "",
    ) -> None:
        """写入/更新一条工作流快照，**并强制留下一条变更历史**。

        ``event`` 为必填关键字参数：这是刻意的接口设计 —— 让「写事实却不留痕」在
        调用侧就写不出来（红线⑥）。
        """

    @abstractmethod
    def get_workflow(self, workflow_id: str) -> Optional[GovernanceWorkflow]:
        """按 id 取工作流，不存在返回 ``None``。"""

    @abstractmethod
    def has_workflow(self, workflow_id: str) -> bool:
        """工作流是否存在。"""

    @abstractmethod
    def list_workflows(
        self, *, org_id: str = "", status: Any = None
    ) -> List[GovernanceWorkflow]:
        """列出工作流（可按组织 / 状态过滤）。"""

    # -------------------------- 人工研判 --------------------------

    @abstractmethod
    def put_review(
        self,
        review: GovernanceWorkflowReview,
        *,
        status_from: str = "",
        detail: str = "",
    ) -> None:
        """写入一条人工研判记录，并自动追加 ``reviewed`` 历史。"""

    @abstractmethod
    def get_review(self, review_id: str) -> Optional[GovernanceWorkflowReview]:
        """按 id 取研判记录。"""

    @abstractmethod
    def has_review(self, review_id: str) -> bool:
        """研判记录是否存在。"""

    @abstractmethod
    def list_reviews(self, *, workflow_id: str = "") -> List[GovernanceWorkflowReview]:
        """列出研判记录（可按工作流过滤）。"""

    # -------------------------- 执行记录 --------------------------

    @abstractmethod
    def put_execution(
        self,
        record: GovernanceExecutionRecord,
        *,
        event: WorkflowHistoryEvent = WorkflowHistoryEvent.EXECUTION_RECORDED,
        detail: str = "",
    ) -> None:
        """写入一条执行事实，并自动追加对应历史。"""

    @abstractmethod
    def get_execution(self, record_id: str) -> Optional[GovernanceExecutionRecord]:
        """按 id 取执行记录。"""

    @abstractmethod
    def has_execution(self, record_id: str) -> bool:
        """执行记录是否存在。"""

    @abstractmethod
    def list_executions(
        self, *, workflow_id: str = ""
    ) -> List[GovernanceExecutionRecord]:
        """列出执行记录（可按工作流过滤，同一工作流内保持登记顺序）。"""

    # -------------------------- 归档 --------------------------

    @abstractmethod
    def put_archived(
        self,
        workflow: GovernanceWorkflow,
        *,
        actor_id: str = "",
        actor_kind: Any = "",
        at: str = "",
    ) -> None:
        """登记一条已归档工作流（归档不删除原记录，只增加封存索引）。"""

    @abstractmethod
    def list_archived(self) -> List[GovernanceWorkflow]:
        """列出已归档工作流。"""

    # -------------------------- 历史 --------------------------

    @abstractmethod
    def append_history(self, entry: WorkflowHistoryEntry) -> None:
        """追加一条变更历史（**append-only**，端口无任何改/删对应方法）。"""

    @abstractmethod
    def list_history(self, *, workflow_id: str = "") -> List[WorkflowHistoryEntry]:
        """按时间顺序列出变更历史（可按工作流过滤）。"""

    # -------------------------- 向后兼容原始视图 --------------------------

    @property
    @abstractmethod
    def workflows(self) -> Dict[str, GovernanceWorkflow]:
        """工作流原始字典视图（编排器 ``_workflows`` 属性代理，向后兼容）。"""

    @property
    @abstractmethod
    def reviews(self) -> Dict[str, GovernanceWorkflowReview]:
        """研判原始字典视图。"""

    @property
    @abstractmethod
    def executions(self) -> Dict[str, List[GovernanceExecutionRecord]]:
        """执行记录按 workflow_id 聚合的字典视图。"""

    @property
    @abstractmethod
    def execution_index(self) -> Dict[str, GovernanceExecutionRecord]:
        """执行记录按 record_id 建立的唯一索引视图。"""

    @property
    @abstractmethod
    def archived(self) -> Dict[str, GovernanceWorkflow]:
        """归档索引视图。"""


# ---------------------------------------------------------------------------
# 适配器一：内存实现（默认，与 3.8.25 裸 dict 行为等价）
# ---------------------------------------------------------------------------

class InMemoryWorkflowRepository(WorkflowRepository):
    """内存仓储（默认实现）。

    行为与 Phase 3.8.25 编排器内联的五个裸 dict **完全等价** —— 这是本阶段
    「不破坏既有接口」的关键：默认装配路径的存储语义一个字节都没变，变的只是
    这些 dict 从编排器搬到了仓储对象里，并额外获得了 append-only 变更历史。

    编排器的 ``_workflows`` / ``_reviews`` / ``_executions`` /
    ``_execution_index`` / ``_archived`` 五个属性直接代理到这里的同名视图，
    因此既有测试对私有字典的直接读写（如
    ``orch._workflows["gw-2"] = other``）继续有效。
    """

    def __init__(self) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "InMemoryWorkflowRepository（红线①）"
            )
        self._workflows: Dict[str, GovernanceWorkflow] = {}
        self._reviews: Dict[str, GovernanceWorkflowReview] = {}
        self._executions: Dict[str, List[GovernanceExecutionRecord]] = {}
        self._execution_index: Dict[str, GovernanceExecutionRecord] = {}
        self._archived: Dict[str, GovernanceWorkflow] = {}
        self._history: List[WorkflowHistoryEntry] = []
        self._seq = 0

    # -------------------------- 内部 --------------------------

    def _next_entry_id(self, workflow_id: str) -> str:
        self._seq += 1
        return f"wfh-{workflow_id}-{self._seq:06d}"

    def _persist(self) -> None:
        """持久化钩子。内存实现为空操作；文件实现覆写为原子落盘。"""

    # -------------------------- 工作流 --------------------------

    def put_workflow(
        self,
        workflow: GovernanceWorkflow,
        *,
        event: WorkflowHistoryEvent,
        actor_id: str = "",
        actor_kind: Any = "",
        at: str = "",
        status_from: str = "",
        detail: str = "",
    ) -> None:
        self._workflows[workflow.workflow_id] = workflow
        self.append_history(
            WorkflowHistoryEntry(
                entry_id=self._next_entry_id(workflow.workflow_id),
                workflow_id=workflow.workflow_id,
                event=event,
                actor_id=actor_id,
                actor_kind=actor_kind,
                at=at,
                status_from=status_from,
                status_to=workflow.status.value,
                detail=detail,
                org_id=workflow.org_id,
            )
        )

    def get_workflow(self, workflow_id: str) -> Optional[GovernanceWorkflow]:
        return self._workflows.get(str(workflow_id).strip())

    def has_workflow(self, workflow_id: str) -> bool:
        return str(workflow_id).strip() in self._workflows

    def list_workflows(
        self, *, org_id: str = "", status: Any = None
    ) -> List[GovernanceWorkflow]:
        want_org = str(org_id or "").strip()
        want_status = None
        if status is not None:
            want_status = (
                status
                if isinstance(status, GovernanceWorkflowStatus)
                else GovernanceWorkflowStatus(status)
            )
        out: List[GovernanceWorkflow] = []
        for wf in self._workflows.values():
            if want_org and wf.org_id != want_org:
                continue
            if want_status is not None and wf.status is not want_status:
                continue
            out.append(wf)
        return out

    # -------------------------- 人工研判 --------------------------

    def put_review(
        self,
        review: GovernanceWorkflowReview,
        *,
        status_from: str = "",
        detail: str = "",
    ) -> None:
        self._reviews[review.review_id] = review
        self.append_history(
            WorkflowHistoryEntry(
                entry_id=self._next_entry_id(review.workflow_id),
                workflow_id=review.workflow_id,
                event=WorkflowHistoryEvent.REVIEWED,
                actor_id=review.reviewer_id,
                actor_kind=_enum_value(review.reviewer_kind) or "user",
                at=review.reviewed_at,
                status_from=status_from,
                status_to="",
                detail=detail or f"decision={review.decision.value}",
                org_id=review.org_id,
            )
        )

    def get_review(self, review_id: str) -> Optional[GovernanceWorkflowReview]:
        return self._reviews.get(str(review_id).strip())

    def has_review(self, review_id: str) -> bool:
        return str(review_id).strip() in self._reviews

    def list_reviews(self, *, workflow_id: str = "") -> List[GovernanceWorkflowReview]:
        want = str(workflow_id or "").strip()
        return [
            r for r in self._reviews.values() if not want or r.workflow_id == want
        ]

    # -------------------------- 执行记录 --------------------------

    def put_execution(
        self,
        record: GovernanceExecutionRecord,
        *,
        event: WorkflowHistoryEvent = WorkflowHistoryEvent.EXECUTION_RECORDED,
        detail: str = "",
    ) -> None:
        bucket = self._executions.setdefault(record.workflow_id, [])
        if record.record_id not in self._execution_index:
            bucket.append(record)
        self._execution_index[record.record_id] = record
        self.append_history(
            WorkflowHistoryEntry(
                entry_id=self._next_entry_id(record.workflow_id),
                workflow_id=record.workflow_id,
                event=event,
                actor_id=record.actor,
                actor_kind=record.actor_kind,
                at=record.timestamp,
                detail=detail or f"record={record.record_id}",
                org_id=record.org_id,
            )
        )

    def get_execution(self, record_id: str) -> Optional[GovernanceExecutionRecord]:
        return self._execution_index.get(str(record_id).strip())

    def has_execution(self, record_id: str) -> bool:
        return str(record_id).strip() in self._execution_index

    def list_executions(
        self, *, workflow_id: str = ""
    ) -> List[GovernanceExecutionRecord]:
        want = str(workflow_id or "").strip()
        if want:
            return list(self._executions.get(want, []))
        return list(self._execution_index.values())

    # -------------------------- 归档 --------------------------

    def put_archived(
        self,
        workflow: GovernanceWorkflow,
        *,
        actor_id: str = "",
        actor_kind: Any = "",
        at: str = "",
    ) -> None:
        self._archived[workflow.workflow_id] = workflow
        self._workflows[workflow.workflow_id] = workflow
        self.append_history(
            WorkflowHistoryEntry(
                entry_id=self._next_entry_id(workflow.workflow_id),
                workflow_id=workflow.workflow_id,
                event=WorkflowHistoryEvent.ARCHIVED,
                actor_id=actor_id,
                actor_kind=actor_kind,
                at=at,
                status_to=workflow.status.value,
                org_id=workflow.org_id,
            )
        )

    def list_archived(self) -> List[GovernanceWorkflow]:
        return list(self._archived.values())

    # -------------------------- 历史 --------------------------

    def append_history(self, entry: WorkflowHistoryEntry) -> None:
        self._history.append(entry)
        self._persist()

    def list_history(self, *, workflow_id: str = "") -> List[WorkflowHistoryEntry]:
        want = str(workflow_id or "").strip()
        return [e for e in self._history if not want or e.workflow_id == want]

    # -------------------------- 原始视图 --------------------------

    @property
    def workflows(self) -> Dict[str, GovernanceWorkflow]:
        return self._workflows

    @property
    def reviews(self) -> Dict[str, GovernanceWorkflowReview]:
        return self._reviews

    @property
    def executions(self) -> Dict[str, List[GovernanceExecutionRecord]]:
        return self._executions

    @property
    def execution_index(self) -> Dict[str, GovernanceExecutionRecord]:
        return self._execution_index

    @property
    def archived(self) -> Dict[str, GovernanceWorkflow]:
        return self._archived


# ---------------------------------------------------------------------------
# 适配器二：JSON 文件实现（可持久化）
# ---------------------------------------------------------------------------

#: 存储格式版本。加载到更高版本即拒绝（fail-closed，绝不猜测未来格式的语义）。
_STORE_VERSION = 1


class JsonFileWorkflowRepository(InMemoryWorkflowRepository):
    """JSON 文件仓储（可持久化适配器）。

    设计取舍（为什么是「内存镜像 + 全量原子快照」而不是增量追加）：

    - 治理工作流是**低频高价值**数据：一天可能只有几十条状态推进，但每一条都
      牵涉责任认定。这个量级下，全量快照的写放大完全可以接受，而它换来的是
      「文件永远是一个自洽的完整状态」—— 不存在增量日志重放到一半崩溃后的
      半截状态（治理数据最怕的正是这个）。
    - 写入走 ``tempfile + os.replace``：POSIX 下 ``rename`` 是原子的，因此
      要么读到旧的完整快照，要么读到新的完整快照，**不存在半写入文件**。
    - 每条记录带 SHA-256 摘要，加载时逐条比对（红线⑤）。

    ``strict`` 参数：默认 ``True`` —— 任何一条记录摘要不符或不满足恢复期不变量，
    **整个仓储拒绝加载**并抛 :class:`WorkflowStoreIntegrityError`。这是刻意的
    fail-closed 选择：治理数据带病运行的代价（基于被污染的责任事实做决策）远高于
    服务拒绝启动。``strict=False`` 仅供离线取证/修复工具使用，会跳过坏记录并把
    跳过事实登记进 ``load_errors``。
    """

    def __init__(self, path: "str | Path", *, strict: bool = True) -> None:
        super().__init__()
        self._path = Path(path)
        self._strict = bool(strict)
        self._loading = False
        #: 非严格模式下被跳过的坏记录（(kind, id, reason) 三元组），供取证使用。
        self.load_errors: List[tuple] = []
        if self._path.exists():
            self._load()

    # -------------------------- 落盘 --------------------------

    @property
    def path(self) -> Path:
        """存储文件路径（只读）。"""
        return self._path

    def _persist(self) -> None:
        """原子写入全量快照（临时文件 + ``os.replace``）。"""
        if self._loading:
            return  # 加载过程中的重建不回写，避免自我覆盖
        doc = self.snapshot()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            prefix=f".{self._path.name}.", suffix=".tmp", dir=str(self._path.parent)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2, sort_keys=True)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, self._path)
        except BaseException:
            # 失败时清理临时文件，绝不留下半截产物
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def snapshot(self) -> Dict[str, Any]:
        """导出当前全量快照（带逐条摘要），供落盘与外部取证使用。"""

        def wrap(payload: Dict[str, Any]) -> Dict[str, Any]:
            return {"payload": payload, "digest": _digest(payload)}

        # 执行记录按 workflow 分桶顺序展开，保证恢复后同一工作流内顺序不变。
        exec_payloads: List[Dict[str, Any]] = []
        for bucket in self._executions.values():
            for rec in bucket:
                exec_payloads.append(wrap(_dataclass_payload(rec)))

        return {
            "version": _STORE_VERSION,
            "workflows": [
                wrap(_dataclass_payload(wf)) for wf in self._workflows.values()
            ],
            "reviews": [
                wrap(_dataclass_payload(rv)) for rv in self._reviews.values()
            ],
            "executions": exec_payloads,
            "archived": sorted(self._archived.keys()),
            "history": [wrap(e.to_payload()) for e in self._history],
        }

    # -------------------------- 加载 --------------------------

    def _unwrap(self, item: Any, *, kind: str) -> Optional[Dict[str, Any]]:
        """校验一条记录的摘要并返回载荷；不合格按 ``strict`` 抛出或跳过。"""
        if not isinstance(item, dict) or "payload" not in item:
            return self._reject(kind, "", "记录结构非法（缺少 payload）")
        payload = item.get("payload")
        if not isinstance(payload, dict):
            return self._reject(kind, "", "payload 不是对象")
        expected = item.get("digest", "")
        actual = _digest(payload)
        if expected != actual:
            return self._reject(
                kind,
                str(payload.get("workflow_id") or payload.get("entry_id") or ""),
                f"摘要不匹配（期望 {expected!r}，实际 {actual!r}）：文件可能被截断或改动",
            )
        return payload

    def _reject(self, kind: str, rid: str, reason: str) -> None:
        msg = f"加载治理存储失败 [{kind}:{rid or '?'}]：{reason}"
        if self._strict:
            raise WorkflowStoreIntegrityError(msg)
        self.load_errors.append((kind, rid, reason))
        return None

    def _load(self) -> None:
        """从磁盘恢复（fail-closed：版本、摘要、恢复期不变量任一不过即拒）。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WorkflowRepositoryError(
                f"无法读取治理存储 {self._path}：{exc}"
            ) from exc
        if not raw.strip():
            return
        try:
            doc = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise WorkflowStoreIntegrityError(
                f"治理存储 {self._path} 不是合法 JSON（文件可能被截断）：{exc}"
            ) from exc
        if not isinstance(doc, dict):
            raise WorkflowStoreIntegrityError(
                f"治理存储 {self._path} 顶层不是对象：拒绝加载"
            )
        version = doc.get("version")
        if version != _STORE_VERSION:
            raise WorkflowStoreIntegrityError(
                f"治理存储版本 {version!r} 与当前实现 {_STORE_VERSION!r} 不一致："
                f"拒绝按猜测的语义加载治理事实"
            )

        self._loading = True
        try:
            for item in doc.get("workflows", []) or []:
                payload = self._unwrap(item, kind="workflow")
                if payload is None:
                    continue
                try:
                    wf = _restore_workflow(payload)
                except EnterpriseRedLineViolationError as exc:
                    if self._strict:
                        raise
                    self.load_errors.append(
                        ("workflow", str(payload.get("workflow_id", "")), str(exc))
                    )
                    continue
                self._workflows[wf.workflow_id] = wf

            for wid in doc.get("archived", []) or []:
                wf = self._workflows.get(str(wid).strip())
                if wf is None:
                    self._reject("archived", str(wid), "归档索引指向不存在的工作流")
                    continue
                self._archived[wf.workflow_id] = wf

            for item in doc.get("reviews", []) or []:
                payload = self._unwrap(item, kind="review")
                if payload is None:
                    continue
                try:
                    rv = _restore_review(payload)
                except WorkflowStoreIntegrityError:
                    if self._strict:
                        raise
                    self.load_errors.append(
                        ("review", str(payload.get("review_id", "")), "红线守卫拒绝")
                    )
                    continue
                self._reviews[rv.review_id] = rv

            for item in doc.get("executions", []) or []:
                payload = self._unwrap(item, kind="execution")
                if payload is None:
                    continue
                try:
                    rec = _restore_execution(payload)
                except WorkflowStoreIntegrityError:
                    if self._strict:
                        raise
                    self.load_errors.append(
                        ("execution", str(payload.get("record_id", "")), "红线守卫拒绝")
                    )
                    continue
                self._executions.setdefault(rec.workflow_id, []).append(rec)
                self._execution_index[rec.record_id] = rec

            for item in doc.get("history", []) or []:
                payload = self._unwrap(item, kind="history")
                if payload is None:
                    continue
                try:
                    entry = WorkflowHistoryEntry(**payload)
                except (EnterpriseRedLineViolationError, TypeError, ValueError) as exc:
                    if self._strict:
                        raise WorkflowStoreIntegrityError(
                            f"恢复变更历史失败：{exc}"
                        ) from exc
                    self.load_errors.append(
                        ("history", str(payload.get("entry_id", "")), str(exc))
                    )
                    continue
                self._history.append(entry)
            # 序号游标推进到已有历史之后，避免恢复后 entry_id 撞号。
            self._seq = len(self._history)
        finally:
            self._loading = False


__all__ = [
    "WorkflowRepository",
    "InMemoryWorkflowRepository",
    "JsonFileWorkflowRepository",
    "WorkflowHistoryEntry",
    "WorkflowHistoryEvent",
    "WorkflowRepositoryError",
    "WorkflowStoreIntegrityError",
    "_REPOSITORY_FORBIDDEN",
    "_restore_workflow",
]
