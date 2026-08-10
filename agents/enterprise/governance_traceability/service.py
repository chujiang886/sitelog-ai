"""Phase 3.8.30 企业智能体治理全链路追踪与统一审计智能层 —— 服务层。

定位：在既有治理层之上提供**只读的事实串联与重建**能力，回答审计责任人的三个问题：

1. 「这件事牵扯到哪些对象？」 → ``GovernanceTrace`` + ``GovernanceTraceLink``（任务1/2）
2. 「按时间顺序到底发生了什么？」 → ``GovernanceAuditTimeline``（任务3）
3. 「能不能原样重看一遍？」 → ``GovernanceReplayView`` / ``GovernanceTraceReport``（任务4/5）

本服务**不持有任何治理状态**，不修改任何被关联对象；它只读取事实、串联事实、
呈现事实。所有出口一律 fail-closed：

红线（结构级 + 类型级 + 语义级三重）：
① 构造/读写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _TRACEABILITY_FORBIDDEN`` 结构拦截改审计 / 出结论 / 关事件 /
   重放即执行 / 代替审计责任人。
③ **不改治理记录**：本服务对审计、编排器、知识层**纯只读**；不提供任何
   update / delete / rewrite 入口；输出视图 ``frozen=True`` 不可变。
④ **不出治理结论**：报告 ``conclusion_included`` 恒 False；无任何摘要生成、
   根因推断、定性定责逻辑——只做「按时间排序 + 原样引用」。
⑤ **不关事件**：无任何 close / resolve / dismiss 能力；重放
   ``re_execution_performed`` 恒 False。
⑥ **不代替审计责任人**：所有入口强制 ``require_human_actor(USER)``；权限经
   ``IdentityService`` + ``AgentPermissionPolicy`` 双闸门（默认拒绝）；
   每次访问留痕真实 actor。

权限口径（任务7，**刻意保守，不擅自扩权**）：
- 资源类别沿用 3.8.13 既有约定 ``"data"``（治理与审计数据归 data 类）；
- 身份层附加要求 ``Permission.VIEW_AUDIT``（审计数据隔离的主闸门）。
- 二者取**交集**。在当前内置角色表下，仅 ``ADMIN`` 同时满足两条；``REVIEWER``
  虽持 ``VIEW_AUDIT``，但其 Agent 资源作用域为 ``{knowledge}``，不含 ``data``，
  因此**默认被拒绝**。本阶段**不擅自修改** 3.8.13 的 ``_AGENT_RESOURCE_SCOPE``
  为 REVIEWER 扩权——扩权属治理决策，须主理人显式裁定（红线⑥）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import AuditActorKind, require_human_actor
from agents.enterprise.governance_traceability.forbidden import _TRACEABILITY_FORBIDDEN
from agents.enterprise.governance_traceability.models import (
    GovernanceAuditTimeline,
    GovernanceAuditTimelineEntry,
    GovernanceReplayStep,
    GovernanceReplayView,
    GovernanceTrace,
    GovernanceTraceLink,
    GovernanceTraceLinkKind,
    GovernanceTraceReport,
    GovernanceTraceSourceType,
    SourceTrace,
)
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class GovernanceTraceabilityError(EnterpriseRedLineViolationError):
    """追踪层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


# 链路来源类型 → 来源链目标类别（用于任务5 的来源链归类）。
_SOURCE_TYPE_TO_LINK_KIND: Dict[GovernanceTraceSourceType, GovernanceTraceLinkKind] = {
    GovernanceTraceSourceType.GOVERNANCE_EVENT: GovernanceTraceLinkKind.EVENT,
    GovernanceTraceSourceType.GOVERNANCE_WORKFLOW: GovernanceTraceLinkKind.WORKFLOW,
    GovernanceTraceSourceType.GOVERNANCE_TASK: GovernanceTraceLinkKind.TASK,
    GovernanceTraceSourceType.AUDIT_RECORD: GovernanceTraceLinkKind.AUDIT,
    GovernanceTraceSourceType.GOVERNANCE_KNOWLEDGE: GovernanceTraceLinkKind.KNOWLEDGE,
    GovernanceTraceSourceType.SECURITY_RISK: GovernanceTraceLinkKind.EVENT,
    GovernanceTraceSourceType.COMPLIANCE_RISK: GovernanceTraceLinkKind.EVENT,
    GovernanceTraceSourceType.QUALITY_ISSUE: GovernanceTraceLinkKind.EVENT,
    GovernanceTraceSourceType.OBSERVABILITY_ANOMALY: GovernanceTraceLinkKind.EVENT,
    GovernanceTraceSourceType.HUMAN_REPORTED: GovernanceTraceLinkKind.EVENT,
}


class GovernanceTraceabilityService(_RedLineForbiddenMixin):
    """治理全链路追踪与统一审计智能服务（任务1~5、7 主体）。

    与 3.8.26 驾驶舱同构：继承 ``_RedLineForbiddenMixin``，三道闸门
    （组织隔离 / 权限默认拒绝 / 人工强制）+ 审计留痕；**但比驾驶舱更严格**——
    驾驶舱尚有唯一写入口 ``confirm_review``，本层**没有任何治理状态写入口**。
    """

    # 结构级红线拦截：追踪层禁名（3.8.26 驾驶舱禁名 ∪ 本层增量）。
    _FORBIDDEN = _TRACEABILITY_FORBIDDEN

    #: 资源类别沿用 3.8.13 既有约定（治理/审计数据归 data 类）。
    _DEFAULT_RESOURCE_CATEGORY = "data"

    #: 身份层附加权限：查看审计（审计数据隔离主闸门）。
    _REQUIRED_PERMISSION = Permission.VIEW_AUDIT

    def __init__(
        self,
        *,
        org_id: str,
        audit: Any = None,                                    # AuditService
        identity: "Optional[IdentityService]" = None,
        permission_policy: "Optional[AgentPermissionPolicy]" = None,
        orchestrator: Any = None,   # 3.8.25 编排器（只读，可选）
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "GovernanceTraceabilityService（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._permission_policy = permission_policy
        # 只读消费编排器事实（可为空）；本层绝不回写编排器状态（红线③/⑤）。
        self._orchestrator = orchestrator

        self._traces: Dict[str, GovernanceTrace] = {}
        self._links: Dict[str, GovernanceTraceLink] = {}
        self._links_by_trace: Dict[str, List[str]] = {}
        self._audit_seq = 0

    # ------------------------------------------------------------------
    # 三道闸门（红线⑤/⑥：组织隔离 + 默认拒绝 + 人工强制）
    # ------------------------------------------------------------------

    def _ensure_org_scope(self, target_org: str, op: str) -> None:
        """跨组织访问拦截（审计数据隔离的第一道，任务7）。"""
        tgt = str(target_org or "").strip()
        if self._org_id and tgt and tgt != self._org_id:
            raise EnterpriseIsolationError(
                f"{op} 拒绝跨组织访问：服务 org={self._org_id!r} 但请求 org={tgt!r}"
                f"（红线⑥：禁止跨组织读取治理链路与审计事实）"
            )

    def _policy_allows(self, *, user: Any, resource_category: str) -> bool:
        """询问权限策略是否放行（**任何异常一律视为拒绝**，fail-closed）。

        兼容完整 ``AgentPermissionPolicy``（接受 ``required_permission``）与仅实现
        ``check_agent_access(user, resource_category)`` 的最小鸭子类型策略。
        """
        policy = self._permission_policy
        if policy is None:
            return True
        try:
            return bool(
                policy.check_agent_access(
                    user=user,
                    resource_category=resource_category,
                    required_permission=self._REQUIRED_PERMISSION,
                )
            )
        except TypeError:
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
        self, *, user: Any, resource_category: str = ""
    ) -> None:
        """审计数据访问闸门（**默认拒绝**，任务7）。

        - 无操作者 → 拒绝（匿名不可读审计）；
        - 有 ``AgentPermissionPolicy`` → 角色须在资源作用域内且过身份层 VIEW_AUDIT；
        - 无策略但有 ``IdentityService`` → 退化为身份层 ``VIEW_AUDIT`` 校验；
        - 两者皆无 → 仅组织隔离 + 人工强制生效（供最小装配与测试）。
        """
        if user is None:
            raise EnterpriseRedLineViolationError(
                "缺少操作者：治理追踪层默认拒绝匿名访问审计事实（红线⑥）"
            )
        category = resource_category or self._DEFAULT_RESOURCE_CATEGORY
        if self._permission_policy is not None:
            if not self._policy_allows(user=user, resource_category=category):
                raise EnterpriseRedLineViolationError(
                    f"权限策略拒绝访问 resource_category={category!r}"
                    f"（默认拒绝，红线⑥：审计数据隔离）"
                )
            return
        if self._identity is not None:
            allowed = False
            try:
                allowed = bool(
                    self._identity.check(user, self._REQUIRED_PERMISSION)
                )
            except Exception:
                allowed = False
            if not allowed:
                raise EnterpriseRedLineViolationError(
                    f"身份层拒绝访问：缺少 {self._REQUIRED_PERMISSION.value} 权限"
                    f"（默认拒绝，红线⑥：审计数据隔离）"
                )

    def _require_user(self, user: Any) -> Any:
        """追踪层仅对真实审计责任人（USER）开放（读写均强制，红线⑥）。"""
        if user is None:
            raise EnterpriseRedLineViolationError(
                "治理追踪层仅对真实审计责任人（USER）开放（红线⑥）"
            )
        actor_kind = getattr(user, "actor_kind", None)
        if actor_kind is None:
            raise EnterpriseRedLineViolationError(
                "操作者缺少 actor_kind：无法证明其为真实人工，默认拒绝（红线⑥）"
            )
        # 兼容字面 "user"：统一归一到枚举后再交给 require_human_actor 硬校验。
        if not isinstance(actor_kind, AuditActorKind):
            try:
                actor_kind = AuditActorKind(str(actor_kind).lower())
            except Exception:
                actor_kind = None
        require_human_actor(actor_kind)
        return user

    def _gate(self, *, user: Any, org_id: str, op: str) -> Any:
        """三道闸门统一入口：人工强制 → 组织隔离 → 权限默认拒绝。

        组织隔离同时校验**请求目标组织**与**操作者自身归属组织**：外组织的人
        即便持有 VIEW_AUDIT，也不得读取本组织的审计事实（任务7：审计数据隔离）。
        """
        self._require_user(user)
        self._ensure_org_scope(org_id, op)
        self._ensure_org_scope(str(getattr(user, "org_id", "") or ""), f"{op}(actor)")
        self._ensure_access(user=user)
        return user

    @staticmethod
    def _actor_id_of(user: Any) -> str:
        return str(
            getattr(user, "actor_id", None) or getattr(user, "user_id", "") or ""
        ).strip()

    # ------------------------------------------------------------------
    # 审计留痕（任务6 接入：actor 真实，绝无 record_human_approval）
    # ------------------------------------------------------------------

    def _next_audit_id(self, prefix: str) -> str:
        self._audit_seq += 1
        return f"{prefix}-{self._org_id}-{self._audit_seq}"

    def _audit_trace(self, *, user: Any, action: str, target: str, detail: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record_governance_trace(
            record_id=self._next_audit_id("gtrace"),
            actor_id=self._actor_id_of(user),
            action=action,
            target=target,
            detail=detail,
            ts="",
        )

    def _audit_timeline(self, *, user: Any, action: str, target: str, detail: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record_governance_timeline(
            record_id=self._next_audit_id("gtl"),
            actor_id=self._actor_id_of(user),
            action=action,
            target=target,
            detail=detail,
            ts="",
        )

    def _audit_replay(self, *, user: Any, action: str, target: str, detail: str = "") -> None:
        if self._audit is None:
            return
        self._audit.record_governance_replay(
            record_id=self._next_audit_id("grp"),
            actor_id=self._actor_id_of(user),
            action=action,
            target=target,
            detail=detail,
            ts="",
        )

    # ------------------------------------------------------------------
    # 任务1：治理链路登记（全链路唯一）
    # ------------------------------------------------------------------

    def register_trace(
        self,
        *,
        trace_id: str,
        source_id: str,
        created_at: str,
        user: Any,
        org_id: str = "",
        source_type: "GovernanceTraceSourceType | str" = (
            GovernanceTraceSourceType.HUMAN_REPORTED
        ),
        workflow_id: str = "",
        task_id: str = "",
        title: str = "",
        description: str = "",
        source_facts: Sequence[str] = (),
        references: Sequence[str] = (),
    ) -> GovernanceTrace:
        """登记一条治理链路（**唯一性强校验**：重复 trace_id 直接拒绝）。

        登记只是把既有事实串起来，**不改变任何被串联对象的状态**（红线③/⑤）。
        """
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="register_trace")

        tid = str(trace_id).strip()
        if tid in self._traces:
            raise GovernanceTraceabilityError(
                f"trace_id {tid!r} 已存在：治理链路标识必须全链路唯一，"
                f"禁止覆盖既有链路事实（红线③：治理记录不可被改写）"
            )

        trace = GovernanceTrace(
            trace_id=tid,
            source_type=source_type,
            source_id=source_id,
            workflow_id=workflow_id,
            task_id=task_id,
            created_at=created_at,
            org_id=target_org,
            created_by=self._actor_id_of(user),
            title=title,
            description=description,
            source_facts=list(source_facts),
            references=list(references),
        )
        self._traces[tid] = trace
        self._links_by_trace.setdefault(tid, [])
        self._audit_trace(
            user=user,
            action="register_trace",
            target=tid,
            detail=f"source_type={trace.source_type.value};source_id={trace.source_id}",
        )
        return trace

    def get_trace(self, *, trace_id: str, user: Any, org_id: str = "") -> GovernanceTrace:
        """按 id 读取链路（只读）。"""
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="get_trace")
        trace = self._traces.get(str(trace_id).strip())
        if trace is None:
            raise GovernanceTraceabilityError(
                f"治理链路 {trace_id!r} 不存在：禁止凭空返回不存在的事实（红线④）"
            )
        self._ensure_org_scope(trace.org_id, "get_trace")
        self._audit_trace(user=user, action="get_trace", target=trace.trace_id)
        return trace

    def list_traces(
        self,
        *,
        user: Any,
        org_id: str = "",
        source_type: "Optional[GovernanceTraceSourceType | str]" = None,
    ) -> List[GovernanceTrace]:
        """列出本组织的治理链路（只读）。"""
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="list_traces")
        want = None
        if source_type is not None:
            want = (
                source_type
                if isinstance(source_type, GovernanceTraceSourceType)
                else GovernanceTraceSourceType(source_type)
            )
        out = [
            t
            for t in self._traces.values()
            if (not target_org or t.org_id == target_org)
            and (want is None or t.source_type is want)
        ]
        out.sort(key=lambda t: (t.created_at, t.trace_id))
        self._audit_trace(user=user, action="list_traces", target=target_org)
        return out

    # ------------------------------------------------------------------
    # 任务2：链路关联（只建立关联）
    # ------------------------------------------------------------------

    def link(
        self,
        *,
        link_id: str,
        trace_id: str,
        link_kind: "GovernanceTraceLinkKind | str",
        target_id: str,
        user: Any,
        org_id: str = "",
        created_at: str = "",
        note: str = "",
    ) -> GovernanceTraceLink:
        """建立一条链路关联（**只建立关联，不触碰目标对象状态**）。

        目标对象可以是治理事件 / 工作流 / 任务 / 审计记录 / 知识条目。本方法
        **不会**修改目标对象的任何字段，也不会推动任何状态机（红线③/⑤）。
        """
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="link")

        tid = str(trace_id).strip()
        trace = self._traces.get(tid)
        if trace is None:
            raise GovernanceTraceabilityError(
                f"治理链路 {trace_id!r} 不存在：禁止把关联挂到不存在的链路上（红线⑥）"
            )
        self._ensure_org_scope(trace.org_id, "link")

        lid = str(link_id).strip()
        if lid in self._links:
            raise GovernanceTraceabilityError(
                f"link_id {lid!r} 已存在：禁止覆盖既有关联事实（红线③）"
            )

        record = GovernanceTraceLink(
            link_id=lid,
            trace_id=tid,
            link_kind=link_kind,
            target_id=target_id,
            org_id=target_org,
            created_at=created_at,
            created_by=self._actor_id_of(user),
            note=note,
        )
        self._links[lid] = record
        self._links_by_trace.setdefault(tid, []).append(lid)
        self._audit_trace(
            user=user,
            action="link_trace",
            target=tid,
            detail=f"kind={record.link_kind.value};target_id={record.target_id}",
        )
        return record

    def list_links(
        self,
        *,
        trace_id: str,
        user: Any,
        org_id: str = "",
        link_kind: "Optional[GovernanceTraceLinkKind | str]" = None,
    ) -> List[GovernanceTraceLink]:
        """列出某链路下的关联（只读）。"""
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="list_links")
        tid = str(trace_id).strip()
        want = None
        if link_kind is not None:
            want = (
                link_kind
                if isinstance(link_kind, GovernanceTraceLinkKind)
                else GovernanceTraceLinkKind(link_kind)
            )
        out = [
            self._links[lid]
            for lid in self._links_by_trace.get(tid, [])
            if want is None or self._links[lid].link_kind is want
        ]
        out.sort(key=lambda l: (l.created_at, l.link_id))
        self._audit_trace(user=user, action="list_links", target=tid)
        return out

    # ------------------------------------------------------------------
    # 任务3：统一审计时间线（只读）
    # ------------------------------------------------------------------

    def _related_targets(self, trace: GovernanceTrace) -> List[str]:
        """该链路涉及的全部对象标识（用于统一审计查询）。"""
        ids: List[str] = [trace.trace_id]
        for extra in (trace.source_id, trace.workflow_id, trace.task_id):
            if extra and extra not in ids:
                ids.append(extra)
        for lid in self._links_by_trace.get(trace.trace_id, []):
            tgt = self._links[lid].target_id
            if tgt and tgt not in ids:
                ids.append(tgt)
        return ids

    def _collect_entries(
        self, trace: GovernanceTrace
    ) -> List[GovernanceAuditTimelineEntry]:
        """把「链路事实 + 关联事实 + 审计事实」汇成时间线条目。

        **纯搬运**：条目内容一律原样引用既有记录，不做任何摘要、推断或改写
        （红线③/④）。
        """
        entries: List[GovernanceAuditTimelineEntry] = []

        # ① 链路自身的登记事实。
        entries.append(
            GovernanceAuditTimelineEntry(
                entry_id=f"trace:{trace.trace_id}",
                ts=trace.created_at,
                actor_kind=AuditActorKind.USER,
                actor_id=trace.created_by,
                action="register_trace",
                source=trace.trace_id,
                source_kind="trace",
                target=trace.source_id,
                detail=trace.title,
            )
        )

        # ② 关联事实。
        for lid in self._links_by_trace.get(trace.trace_id, []):
            ln = self._links[lid]
            entries.append(
                GovernanceAuditTimelineEntry(
                    entry_id=f"link:{ln.link_id}",
                    ts=ln.created_at,
                    actor_kind=AuditActorKind.USER,
                    actor_id=ln.created_by,
                    action=f"link_{ln.link_kind.value}",
                    source=ln.link_id,
                    source_kind="link",
                    target=ln.target_id,
                    detail=ln.note,
                )
            )

        # ③ 统一审计查询：把散落在各治理层的审计记录按对象标识聚合。
        if self._audit is not None:
            seen: set = set()
            for tgt in self._related_targets(trace):
                try:
                    records = self._audit.query(target=tgt)
                except Exception:
                    records = []
                for r in records:
                    rid = getattr(r, "record_id", "")
                    if not rid or rid in seen:
                        continue
                    seen.add(rid)
                    entries.append(
                        GovernanceAuditTimelineEntry(
                            entry_id=f"audit:{rid}",
                            ts=getattr(r, "ts", "") or "",
                            actor_kind=getattr(r, "actor_kind", AuditActorKind.AI),
                            actor_id=getattr(r, "actor_id", "") or "",
                            action=getattr(r, "action", "") or "",
                            source=rid,
                            source_kind="audit",
                            target=getattr(r, "target", "") or "",
                            detail=getattr(r, "detail", "") or "",
                        )
                    )

        # 稳定排序：先时间、后来源类别、再标识（空时间戳沉底但保持确定性）。
        entries.sort(key=lambda e: (e.ts or "~", e.source_kind, e.entry_id))
        return entries

    def build_audit_timeline(
        self,
        *,
        trace_id: str,
        user: Any,
        org_id: str = "",
        generated_at: str = "",
    ) -> GovernanceAuditTimeline:
        """构建统一审计时间线（任务3，**只读**：ts / actor / action / source）。"""
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="build_audit_timeline")
        tid = str(trace_id).strip()
        trace = self._traces.get(tid)
        if trace is None:
            raise GovernanceTraceabilityError(
                f"治理链路 {trace_id!r} 不存在：无法为不存在的事实生成时间线（红线④）"
            )
        self._ensure_org_scope(trace.org_id, "build_audit_timeline")

        entries = tuple(self._collect_entries(trace))
        timeline = GovernanceAuditTimeline(
            trace_id=tid,
            org_id=trace.org_id,
            entries=entries,
            generated_at=generated_at,
            generated_by=self._actor_id_of(user),
        )
        self._audit_timeline(
            user=user,
            action="view_timeline",
            target=tid,
            detail=f"entries={len(entries)}",
        )
        return timeline

    # ------------------------------------------------------------------
    # 任务4：治理事实重放（重建事实，禁止重新执行）
    # ------------------------------------------------------------------

    def build_replay_view(
        self,
        *,
        trace_id: str,
        user: Any,
        org_id: str = "",
        generated_at: str = "",
    ) -> GovernanceReplayView:
        """重建一条链路的事实时间线（任务4）。

        **「重放」= 按时间序把既有事实重新展示一遍**，供人工复核。本方法
        绝不调用任何治理动作、绝不推动任何状态机、绝不写入除「查看审计」以外的
        任何记录（红线④/⑤）。
        """
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="build_replay_view")
        tid = str(trace_id).strip()
        trace = self._traces.get(tid)
        if trace is None:
            raise GovernanceTraceabilityError(
                f"治理链路 {trace_id!r} 不存在：无法重放不存在的事实（红线④）"
            )
        self._ensure_org_scope(trace.org_id, "build_replay_view")

        steps: List[GovernanceReplayStep] = []
        for seq, e in enumerate(self._collect_entries(trace), start=1):
            steps.append(
                GovernanceReplayStep(
                    seq=seq,
                    ts=e.ts,
                    actor_kind=e.actor_kind,
                    actor_id=e.actor_id,
                    action=e.action,
                    source=e.source,
                    fact=e.detail,
                )
            )
        view = GovernanceReplayView(
            trace_id=tid,
            org_id=trace.org_id,
            steps=tuple(steps),
            generated_at=generated_at,
            generated_by=self._actor_id_of(user),
        )
        self._audit_replay(
            user=user,
            action="view_replay",
            target=tid,
            detail=f"steps={len(steps)}",
        )
        return view

    # ------------------------------------------------------------------
    # 任务5：治理追踪报告（完整来源链）
    # ------------------------------------------------------------------

    def build_trace_report(
        self,
        *,
        report_id: str,
        trace_id: str,
        user: Any,
        org_id: str = "",
        generated_at: str = "",
    ) -> GovernanceTraceReport:
        """生成治理追踪报告（任务5，**完整来源链，零结论**）。

        报告 = 来源链（每个事实来自哪里）+ 只读时间线。它**不含**任何结论、
        定性、根因或处置建议——那些只能由真实审计责任人给出（红线④/⑥）。
        """
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="build_trace_report")
        tid = str(trace_id).strip()
        trace = self._traces.get(tid)
        if trace is None:
            raise GovernanceTraceabilityError(
                f"治理链路 {trace_id!r} 不存在：无法为不存在的事实出具报告（红线④）"
            )
        self._ensure_org_scope(trace.org_id, "build_trace_report")

        chain: List[SourceTrace] = [
            SourceTrace(
                source_kind=_SOURCE_TYPE_TO_LINK_KIND.get(
                    trace.source_type, GovernanceTraceLinkKind.EVENT
                ),
                source_id=trace.source_id,
                ts=trace.created_at,
                actor_id=trace.created_by,
                summary=trace.title,
            )
        ]
        if trace.workflow_id:
            chain.append(
                SourceTrace(
                    source_kind=GovernanceTraceLinkKind.WORKFLOW,
                    source_id=trace.workflow_id,
                    ts=trace.created_at,
                    actor_id=trace.created_by,
                )
            )
        if trace.task_id:
            chain.append(
                SourceTrace(
                    source_kind=GovernanceTraceLinkKind.TASK,
                    source_id=trace.task_id,
                    ts=trace.created_at,
                    actor_id=trace.created_by,
                )
            )
        for lid in self._links_by_trace.get(tid, []):
            ln = self._links[lid]
            chain.append(
                SourceTrace(
                    source_kind=ln.link_kind,
                    source_id=ln.target_id,
                    ts=ln.created_at,
                    actor_id=ln.created_by,
                    summary=ln.note,
                )
            )

        timeline = GovernanceAuditTimeline(
            trace_id=tid,
            org_id=trace.org_id,
            entries=tuple(self._collect_entries(trace)),
            generated_at=generated_at,
            generated_by=self._actor_id_of(user),
        )
        report = GovernanceTraceReport(
            report_id=str(report_id).strip(),
            trace_id=tid,
            org_id=trace.org_id,
            source_chain=tuple(chain),
            timeline=timeline,
            generated_at=generated_at,
            generated_by=self._actor_id_of(user),
        )
        self._audit_trace(
            user=user,
            action="build_trace_report",
            target=tid,
            detail=f"sources={len(chain)}",
        )
        return report

    # ------------------------------------------------------------------
    # 只读自检（供装配层 / 运维取证）
    # ------------------------------------------------------------------

    def is_read_only(self) -> bool:
        """本层恒为只读层：不持有任何治理状态写入口（结构性事实）。"""
        return True

    def stats(self, *, user: Any, org_id: str = "") -> Dict[str, int]:
        """链路与关联的计数（只读，纯事实）。"""
        target_org = str(org_id or self._org_id).strip()
        self._gate(user=user, org_id=target_org, op="stats")
        return {
            "traces": len(self._traces),
            "links": len(self._links),
        }


__all__ = [
    "GovernanceTraceabilityService",
    "GovernanceTraceabilityError",
]
