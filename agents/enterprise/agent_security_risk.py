"""Enterprise Agent Security & Risk Governance Layer（Phase 3.8.18）。

新增（任务1–5）：
- ``AgentSecurityEventType`` / ``AgentSecuritySeverity``：安全事件类型与严重度枚举。
- ``AgentSecurityEvent``：安全事实事件（event_id / agent_id / event_type / severity /
  source / timestamp）。**只记录事实**：不含处置、不含结论、不含封禁建议；
  ``source`` 为空即拒绝落库（红线⑥：事实必须可溯源）。
- ``SourceTrace``：来源链（trace_id + 事实来源条目），供安全报告强制可溯源。
- ``AgentRiskCandidate``：风险候选（risk_id / agent_id / pattern / evidence /
  requires_human_review）。**强制 requires_human_review=True**：模型层禁止置 False，
  也不提供任何 resolve / fix / dismiss 方法（红线⑤）。
- ``AgentSecurityDetector``：安全检测器（detect_access_anomaly /
  detect_permission_anomaly / detect_execution_anomaly）。**只发现，不处理**：
  只产出 ``AgentRiskCandidate``，绝不封禁 Agent、绝不修改权限、绝不处置风险
  （红线③/④/⑤）。
- ``AgentSecurityReport``：安全报告（安全事实 + 风险候选 + 来源链）。
  无来源链即拒绝构造；报告不含处置结论与批准语义。
- ``AgentRiskReviewStatus`` / ``AgentRiskReview``：风险人工处置记录。
  **必须真实 USER**：由 ``AgentSecurityRiskService.human_review_risk`` 在
  ``require_human_actor(USER)`` 守卫下写入，AI 无论如何无法自行处置（红线⑤/⑥）。
- ``AgentSecurityRiskService``：聚合治理服务，承载安全事件登记 / 风险候选登记 /
  异常检测 / 报告生成 / 人工风险处置 / 只读查询；接入身份层 +
  ``AgentPermissionPolicy`` 做安全数据权限隔离（默认拒绝）；联动审计
  （AGENT_SECURITY_EVENT / AGENT_RISK / AGENT_RISK_REVIEW，任务6）。

红线（fail-closed，复用 3.8.0~3.8.17 基座 + 3.8.18 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved。
③ 不 AI 自动封禁 Agent（auto_disable_agent / block_agent / kill_agent 等被 mixin
   拦截；检测器只产出候选，绝不改变任何 Agent 的可用状态）。
④ 不 AI 自动修改权限（auto_change_permission / auto_grant_permission /
   auto_revoke_permission 等被拦截；本层只读权限，绝不写权限）。
⑤ 不 AI 自动处置安全风险（auto_resolve_risk / auto_fix_risk 等被拦截；
   风险候选 ``requires_human_review`` 恒为 True，处置强制 USER）。
⑥ 不 AI 代替安全责任（审计禁止 ``record_human_approval``；风险处置节点强制
   ``require_human_actor(USER)``；事件/候选/报告只陈述事实，不含处置建议）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, Permission
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# forbidden 方法名（红线②/③/④/⑤/⑥，结构上不可达）
# ---------------------------------------------------------------------------

_SECURITY_FORBIDDEN = (
    # 基座（红线②/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动封禁 Agent（主理人明列三项 + 同族收敛）
    "auto_disable_agent",
    "disable_agent",
    "block_agent",
    "auto_block_agent",
    "kill_agent",
    "auto_kill_agent",
    "ban_agent",
    "auto_ban_agent",
    "suspend_agent",
    "auto_suspend_agent",
    "terminate_agent",
    "auto_terminate_agent",
    "shutdown_agent",
    "auto_shutdown_agent",
    "quarantine_agent",
    "auto_quarantine_agent",
    # 红线④：禁止 AI 自动修改权限（主理人明列三项 + 同族收敛）
    "auto_change_permission",
    "change_permission",
    "auto_grant_permission",
    "grant_permission",
    "auto_revoke_permission",
    "revoke_permission",
    "modify_permission",
    "auto_modify_permission",
    "update_permission",
    "auto_update_permission",
    "escalate_permission",
    "auto_escalate_permission",
    "elevate_permission",
    "auto_elevate_permission",
    "reset_permission",
    "auto_reset_permission",
    # 红线⑤：禁止 AI 自动处置安全风险（主理人明列两项 + 同族收敛）
    "auto_resolve_risk",
    "resolve_risk",
    "auto_fix_risk",
    "fix_risk",
    "auto_mitigate_risk",
    "mitigate_risk",
    "auto_close_risk",
    "close_risk",
    "auto_dismiss_risk",
    "dismiss_risk",
    "auto_remediate",
    "remediate_risk",
    "auto_handle_incident",
    "handle_incident",
    "auto_respond_incident",
    # 红线⑥：禁止 AI 代替安全责任
    "auto_secure",
    "take_security_ownership",
    "act_as_security_officer",
    "assume_security_responsibility",
    "auto_govern_security",
)


class AgentSecurityEventType(str, Enum):
    """安全事件类型（任务1，只描述事实类别，不含处置语义）。"""

    ACCESS = "access"                  # 访问类事实（资源/知识/数据访问）
    PERMISSION = "permission"          # 权限类事实（权限校验被拒/越权尝试）
    EXECUTION = "execution"            # 执行类事实（工具调用/执行行为）
    AUTHENTICATION = "authentication"  # 认证类事实（登录/身份校验）
    DATA_FLOW = "data_flow"            # 数据流转事实（导出/外发）


class AgentSecuritySeverity(str, Enum):
    """安全事件严重度（任务1）。

    严重度只是**事实标注**，不代表任何处置结论，更不触发任何自动动作（红线③/⑤）。
    """

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentRiskReviewStatus(str, Enum):
    """风险人工处置状态（任务5）。

    ``pending → reviewed``。**仅真实 USER 可推进**（红线⑤/⑥）：
    AI 既不能构造 REVIEWED，也没有任何自动处置方法可调。
    """

    PENDING = "pending"
    REVIEWED = "reviewed"


@dataclass
class SourceTrace:
    """来源链（任务4：报告强可溯源）。

    ``entries`` 为事实来源条目（如 ``event:evt-1`` / ``risk:risk-1`` /
    ``detector:access_anomaly``）。空来源链视为不可溯源，报告层直接拒绝。
    本类不提供任何推断、补全、编造来源的方法（红线⑥）。
    """

    trace_id: str
    entries: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.entries = [str(e).strip() for e in self.entries if str(e).strip()]

    @property
    def is_traceable(self) -> bool:
        """是否具备可溯源来源（空链即不可溯源）。"""
        return bool(self.entries)

    def add_entry(self, entry: str) -> None:
        """追加一条**真实存在**的来源条目（空值忽略，不编造）。"""
        value = str(entry).strip()
        if value:
            self.entries.append(value)

    def render(self) -> str:
        """只读渲染来源链（不改动任何状态）。"""
        return ",".join(self.entries) if self.entries else "no_source"


@dataclass
class AgentSecurityEvent:
    """Agent 安全事件（任务1，**只记录事实**）。

    字段严格对应：event_id / agent_id / event_type / severity / source / timestamp；
    额外增加 org_id / detail 便于隔离与事实描述。

    只记录事实（红线③/⑤/⑥）：
    - 事件只陈述「发生了什么」，**不含**处置结论、封禁建议、权限修改建议；
    - ``source`` 为空即拒绝落库（禁止无源安全事实）；
    - 模型层不提供任何 disable / block / resolve / grant 方法。
    """

    event_id: str
    agent_id: str
    event_type: AgentSecurityEventType = AgentSecurityEventType.ACCESS
    severity: AgentSecuritySeverity = AgentSecuritySeverity.INFO
    source: str = ""
    timestamp: str = ""
    org_id: str = ""
    detail: str = ""   # 中性事实说明（不得含处置/批准语义）

    def __post_init__(self) -> None:
        if not isinstance(self.event_type, AgentSecurityEventType):
            self.event_type = AgentSecurityEventType(self.event_type)
        if not isinstance(self.severity, AgentSecuritySeverity):
            self.severity = AgentSecuritySeverity(self.severity)
        if not str(self.source).strip():
            raise EnterpriseRedLineViolationError(
                f"AgentSecurityEvent {self.event_id!r} 缺少 source："
                f"禁止落库无源的安全事实（红线⑥：事实必须可溯源）"
            )

    def summary(self) -> str:
        """只读汇总事件事实（不改动任何状态，不含处置语义）。"""
        return (
            f"agent={self.agent_id};type={self.event_type.value};"
            f"severity={self.severity.value};source={self.source}"
        )


@dataclass
class AgentRiskCandidate:
    """Agent 风险候选（任务2，**强制人工复核**）。

    字段严格对应：risk_id / agent_id / pattern / evidence / requires_human_review；
    额外增加 org_id / detected_at / severity / source 便于隔离与溯源。

    强制人工复核（红线⑤/⑥）：
    - ``requires_human_review`` **恒为 True**：构造期若显式传 False，直接抛
      ``EnterpriseRedLineViolationError``；
    - 候选只是「发现的疑点」，**不是**结论、不是处置、不是封禁依据；
    - ``evidence`` 为空即拒绝构造（禁止无证据风险指控）；
    - 模型层不提供任何 resolve / fix / dismiss / close 方法，AI 结构上无法处置。
    """

    risk_id: str
    agent_id: str
    pattern: str = ""
    evidence: List[str] = field(default_factory=list)
    requires_human_review: bool = True
    severity: AgentSecuritySeverity = AgentSecuritySeverity.MEDIUM
    detected_at: str = ""
    source: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.severity, AgentSecuritySeverity):
            self.severity = AgentSecuritySeverity(self.severity)
        if self.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"AgentRiskCandidate {self.risk_id!r} 禁止把 requires_human_review "
                f"置为 {self.requires_human_review!r}：安全风险处置必须由真实人工复核"
                f"（红线⑤/⑥），AI 不得自行免除人工复核"
            )
        if not str(self.pattern).strip():
            raise EnterpriseRedLineViolationError(
                f"AgentRiskCandidate {self.risk_id!r} 缺少 pattern："
                f"禁止落库无模式描述的风险候选（红线⑥）"
            )
        self.evidence = [str(e).strip() for e in self.evidence if str(e).strip()]
        if not self.evidence:
            raise EnterpriseRedLineViolationError(
                f"AgentRiskCandidate {self.risk_id!r} 缺少 evidence："
                f"禁止无证据的风险指控（红线⑥：事实必须可溯源）"
            )

    def summary(self) -> str:
        """只读汇总候选事实（不含处置结论）。"""
        return (
            f"agent={self.agent_id};pattern={self.pattern};"
            f"severity={self.severity.value};"
            f"evidence={'|'.join(self.evidence)};"
            f"requires_human_review={self.requires_human_review}"
        )


@dataclass
class AgentRiskReview:
    """风险人工处置记录（任务5，**必须真实 USER**）。

    字段：review_id / risk_id / reviewer_id / status / decision / note /
    reviewed_at / org_id。

    红线⑤/⑥：
    - 构造期禁止直接落 ``REVIEWED``：处置态只能由
      ``AgentSecurityRiskService.human_review_risk`` 在 ``require_human_actor(USER)``
      守卫下推进，AI 无论如何无法伪造「已处置」；
    - ``reviewer_id`` 必须为真实人工标识，空值拒绝（人工责任可追溯）；
    - 模型层不提供任何 auto_resolve / auto_fix / auto_close 方法。
    """

    review_id: str
    risk_id: str
    reviewer_id: str = ""
    status: AgentRiskReviewStatus = AgentRiskReviewStatus.PENDING
    decision: str = ""      # 人工填写的处置结论事实（AI 不得代填）
    note: str = ""
    reviewed_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentRiskReviewStatus):
            self.status = AgentRiskReviewStatus(self.status)
        if self.status is AgentRiskReviewStatus.REVIEWED:
            raise EnterpriseRedLineViolationError(
                f"AgentRiskReview {self.review_id!r} 禁止在构造期直接落 reviewed："
                f"安全风险处置必须由真实人工执行（红线⑤/⑥），"
                f"请以 pending 登记后经 human_review_risk(actor_kind=USER) 推进"
            )

    @property
    def is_reviewed(self) -> bool:
        """是否已由人工处置（只读事实）。"""
        return self.status is AgentRiskReviewStatus.REVIEWED


@dataclass
class AgentSecurityReport:
    """Agent 安全报告（任务4：安全事实 + 风险候选 + 来源链）。

    字段：report_id / org_id / generated_at / events / risks / source_trace /
    generated_by。

    红线（③/⑤/⑥）：
    - 报告**只汇总事实**：安全事件事实 + 风险候选（均待人工复核），
      **不含**处置结论、封禁建议、权限修改建议、批准语义；
    - 无来源链（``source_trace`` 缺失或为空）即拒绝构造（强可溯源）；
    - 不提供任何 resolve / disable / grant 方法。
    """

    report_id: str
    org_id: str = ""
    generated_at: str = ""
    events: List[AgentSecurityEvent] = field(default_factory=list)
    risks: List[AgentRiskCandidate] = field(default_factory=list)
    source_trace: "SourceTrace | None" = None
    generated_by: str = "ai"

    def __post_init__(self) -> None:
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentSecurityReport {self.report_id!r} 缺少可溯源 source_trace："
                f"禁止生成无来源链的安全报告（红线⑥：事实必须可溯源）"
            )

    @property
    def pending_human_review_count(self) -> int:
        """待人工复核的风险候选数量（恒等于风险候选总数，红线⑤）。"""
        return sum(1 for r in self.risks if r.requires_human_review)

    def severity_breakdown(self) -> Dict[str, int]:
        """按严重度统计安全事件数量（只读事实，不含处置建议）。"""
        out: Dict[str, int] = {}
        for e in self.events:
            out[e.severity.value] = out.get(e.severity.value, 0) + 1
        return out

    def summary(self) -> str:
        """只读汇总报告事实（**不构成任何处置结论**，红线③/⑤）。"""
        return (
            f"report={self.report_id};events={len(self.events)};"
            f"risks={len(self.risks)};"
            f"pending_human_review={self.pending_human_review_count};"
            f"source={self.source_trace.render() if self.source_trace else 'no_source'}"
        )


class AgentSecurityDetector(_RedLineForbiddenMixin):
    """Agent 安全检测器（任务3，**只发现，不处理**）。

    三类检测：``detect_access_anomaly`` / ``detect_permission_anomaly`` /
    ``detect_execution_anomaly``，统一产出 ``AgentRiskCandidate``
    （``requires_human_review=True``）。

    红线（fail-closed）：
    - **只发现不处理**（红线③/⑤）：不封禁 Agent、不中止执行、不处置风险，
      也不返回任何「已处置/已封禁/可放行」语义；
    - **不修改权限**（红线④）：只读权限事实，绝不写权限；
    - 不持有 auto_disable_agent / block_agent / kill_agent /
      auto_change_permission / auto_resolve_risk / auto_fix_risk 等方法。
    """

    _FORBIDDEN = _SECURITY_FORBIDDEN

    def __init__(
        self,
        org_id: str = "",
        identity: "IdentityService | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentSecurityDetector（红线①）"
            )
        self._org_id = org_id
        self._identity = identity
        self._permission_policy = permission_policy

    # ---- 内部：统一候选构造（强制人工复核 + 强制证据）----

    @staticmethod
    def _build_candidate(
        *,
        risk_id: str,
        agent_id: str,
        pattern: str,
        evidence: "List[str]",
        severity: AgentSecuritySeverity,
        detected_at: str,
        source: str,
        org_id: str,
    ) -> AgentRiskCandidate:
        return AgentRiskCandidate(
            risk_id=risk_id,
            agent_id=agent_id,
            pattern=pattern,
            evidence=evidence,
            requires_human_review=True,   # 恒为 True，结构上不可关闭（红线⑤）
            severity=severity,
            detected_at=detected_at,
            source=source,
            org_id=org_id,
        )

    # ---- 访问异常检测（只发现）----

    def detect_access_anomaly(
        self,
        *,
        agent_id: str,
        events: "List[AgentSecurityEvent]",
        threshold: int = 3,
        detected_at: str = "",
    ) -> "List[AgentRiskCandidate]":
        """检测访问类异常（**只发现，不处理**，红线③/⑤）。

        事实判据：同一 agent 的 ACCESS 类事件数量达到 ``threshold``，或存在
        HIGH/CRITICAL 严重度访问事件 → 产出风险候选（待人工复核）。

        无 agent_id / 无事件 → 返回空列表（不臆造风险）。
        本方法**绝不**封禁 Agent、**绝不**修改权限、**绝不**处置风险。
        """
        if not agent_id or not events:
            return []
        scoped = [
            e
            for e in events
            if e.agent_id == agent_id
            and e.event_type is AgentSecurityEventType.ACCESS
        ]
        if not scoped:
            return []
        out: "List[AgentRiskCandidate]" = []
        if len(scoped) >= max(1, int(threshold)):
            out.append(
                self._build_candidate(
                    risk_id=f"risk-access-freq-{agent_id}",
                    agent_id=agent_id,
                    pattern="access_frequency_over_threshold",
                    evidence=[f"event:{e.event_id}" for e in scoped],
                    severity=AgentSecuritySeverity.MEDIUM,
                    detected_at=detected_at,
                    source=f"detector:access_anomaly;events={len(scoped)}",
                    org_id=self._org_id,
                )
            )
        severe = [
            e
            for e in scoped
            if e.severity
            in (AgentSecuritySeverity.HIGH, AgentSecuritySeverity.CRITICAL)
        ]
        if severe:
            out.append(
                self._build_candidate(
                    risk_id=f"risk-access-severe-{agent_id}",
                    agent_id=agent_id,
                    pattern="high_severity_access_event",
                    evidence=[f"event:{e.event_id}" for e in severe],
                    severity=AgentSecuritySeverity.HIGH,
                    detected_at=detected_at,
                    source=f"detector:access_anomaly;severe={len(severe)}",
                    org_id=self._org_id,
                )
            )
        return out

    # ---- 权限异常检测（只发现，绝不改权限）----

    def detect_permission_anomaly(
        self,
        *,
        agent_id: str,
        events: "List[AgentSecurityEvent]",
        threshold: int = 2,
        detected_at: str = "",
    ) -> "List[AgentRiskCandidate]":
        """检测权限类异常（**只发现，绝不修改权限**，红线④/⑤）。

        事实判据：同一 agent 的 PERMISSION 类事件数量达到 ``threshold`` → 产出候选。

        本方法只读权限相关事件事实，**不调用**任何授予/撤销/变更权限接口
        （相关方法名已在 ``_SECURITY_FORBIDDEN`` 中结构性拦截）。
        """
        if not agent_id or not events:
            return []
        scoped = [
            e
            for e in events
            if e.agent_id == agent_id
            and e.event_type is AgentSecurityEventType.PERMISSION
        ]
        if len(scoped) < max(1, int(threshold)):
            return []
        return [
            self._build_candidate(
                risk_id=f"risk-permission-{agent_id}",
                agent_id=agent_id,
                pattern="repeated_permission_anomaly",
                evidence=[f"event:{e.event_id}" for e in scoped],
                severity=AgentSecuritySeverity.HIGH,
                detected_at=detected_at,
                source=f"detector:permission_anomaly;events={len(scoped)}",
                org_id=self._org_id,
            )
        ]

    # ---- 执行异常检测（只发现，绝不中止/封禁）----

    def detect_execution_anomaly(
        self,
        *,
        agent_id: str,
        events: "List[AgentSecurityEvent]",
        threshold: int = 2,
        detected_at: str = "",
    ) -> "List[AgentRiskCandidate]":
        """检测执行类异常（**只发现，绝不封禁/中止 Agent**，红线③/⑤）。

        事实判据：同一 agent 的 EXECUTION 类事件数量达到 ``threshold``，
        或存在 CRITICAL 执行事件 → 产出候选（待人工复核）。
        """
        if not agent_id or not events:
            return []
        scoped = [
            e
            for e in events
            if e.agent_id == agent_id
            and e.event_type is AgentSecurityEventType.EXECUTION
        ]
        if not scoped:
            return []
        out: "List[AgentRiskCandidate]" = []
        if len(scoped) >= max(1, int(threshold)):
            out.append(
                self._build_candidate(
                    risk_id=f"risk-execution-{agent_id}",
                    agent_id=agent_id,
                    pattern="repeated_execution_anomaly",
                    evidence=[f"event:{e.event_id}" for e in scoped],
                    severity=AgentSecuritySeverity.MEDIUM,
                    detected_at=detected_at,
                    source=f"detector:execution_anomaly;events={len(scoped)}",
                    org_id=self._org_id,
                )
            )
        critical = [
            e for e in scoped if e.severity is AgentSecuritySeverity.CRITICAL
        ]
        if critical:
            out.append(
                self._build_candidate(
                    risk_id=f"risk-execution-critical-{agent_id}",
                    agent_id=agent_id,
                    pattern="critical_execution_event",
                    evidence=[f"event:{e.event_id}" for e in critical],
                    severity=AgentSecuritySeverity.CRITICAL,
                    detected_at=detected_at,
                    source=f"detector:execution_anomaly;critical={len(critical)}",
                    org_id=self._org_id,
                )
            )
        return out


class AgentSecurityRiskService(_RedLineForbiddenMixin):
    """Agent 安全与风险治理聚合服务（任务1–7 统一入口）。

    承载：安全事件登记 / 风险候选登记 / 三类异常检测 / 安全报告生成 /
    人工风险处置 / 只读查询（权限隔离）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - 检测只产出候选事实，**不封禁 Agent**（红线③）。
    - 本层只读权限，**不写权限**（红线④）。
    - 风险处置强制 ``require_human_actor(USER)``，AI 无法自行处置（红线⑤/⑥）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_disable_agent / block_agent / kill_agent /
      auto_change_permission / auto_grant_permission / auto_revoke_permission /
      auto_resolve_risk / auto_fix_risk 等方法。
    """

    _FORBIDDEN = _SECURITY_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentSecurityRiskService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._detector = AgentSecurityDetector(
            org_id=org_id, identity=identity, permission_policy=permission_policy
        )
        self._events: Dict[str, AgentSecurityEvent] = {}
        self._risks: Dict[str, AgentRiskCandidate] = {}
        self._reviews: Dict[str, AgentRiskReview] = {}
        self._reports: Dict[str, AgentSecurityReport] = {}

    @property
    def detector(self) -> AgentSecurityDetector:
        """只读暴露安全检测器（只发现，不处理）。"""
        return self._detector

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """安全数据读取权限校验（**默认拒绝**，任务7）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误（红线⑥：安全数据受控访问）。

        注意：本方法**只读校验**，绝不修改任何权限（红线④）。
        """
        from agents.enterprise.organization import EnterpriseIsolationError

        if self._permission_policy is not None:
            allowed = self._permission_policy.check_agent_access(
                user=user,
                resource_category=resource_category,
                required_permission=Permission.READ_RESOURCE,
            )
            if not allowed:
                raise EnterpriseIsolationError(
                    f"用户角色无权限访问 Agent 安全与风险数据"
                    f"（resource={resource_category}），默认拒绝"
                )
        elif self._identity is not None:
            if not (
                hasattr(user, "role")
                and self._identity.check(user, Permission.READ_RESOURCE)
            ):
                raise EnterpriseIsolationError(
                    "无 AgentPermissionPolicy 时，需经身份层 READ_RESOURCE 校验，默认拒绝"
                )

    # ------------------------------------------------------------------
    # 安全事件（只登记事实）
    # ------------------------------------------------------------------

    def record_security_event(
        self,
        *,
        event: AgentSecurityEvent,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentSecurityEvent:
        """登记一条安全事实事件（**只记录事实**，红线③/⑤/⑥）。

        登记动作不改变任何 Agent 状态、不修改权限、不处置风险，
        并如实写入 ``AGENT_SECURITY_EVENT`` 审计。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记安全事件（红线①）"
            )
        event.org_id = self._org_id
        self._events[event.event_id] = event
        if self._audit is not None:
            self._audit.record_agent_security_event_action(
                record_id=f"agent-security-event-{event.event_id}",
                actor_id=actor_id,
                action="record_agent_security_event",
                target=event.agent_id,
                detail=event.summary(),
                ts=event.timestamp,
                actor_kind=actor_kind,
            )
        return event

    # ------------------------------------------------------------------
    # 风险候选（只登记，强制人工复核）
    # ------------------------------------------------------------------

    def register_risk_candidate(
        self,
        *,
        risk: AgentRiskCandidate,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentRiskCandidate:
        """登记一条风险候选（**必待人工复核**，红线⑤/⑥）。

        候选 ``requires_human_review`` 恒为 True（模型层强制）；登记同时自动生成
        一条 ``AgentRiskReview``（``pending``），等待真实人工处置。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记风险候选（红线①）"
            )
        if risk.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"register_risk_candidate 拒绝 requires_human_review != True 的候选 "
                f"{risk.risk_id!r}：安全风险必须人工复核（红线⑤）"
            )
        risk.org_id = self._org_id
        self._risks[risk.risk_id] = risk
        review_id = f"review-{risk.risk_id}"
        if review_id not in self._reviews:
            self._reviews[review_id] = AgentRiskReview(
                review_id=review_id,
                risk_id=risk.risk_id,
                status=AgentRiskReviewStatus.PENDING,
                org_id=self._org_id,
            )
        if self._audit is not None:
            self._audit.record_agent_risk_action(
                record_id=f"agent-risk-{risk.risk_id}",
                actor_id=actor_id,
                action="register_agent_risk_candidate",
                target=risk.agent_id,
                detail=risk.summary(),
                ts=risk.detected_at,
                actor_kind=actor_kind,
            )
        return risk

    # ------------------------------------------------------------------
    # 异常检测（只发现，不处理）
    # ------------------------------------------------------------------

    def run_detection(
        self,
        *,
        agent_id: str,
        detected_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
        access_threshold: int = 3,
        permission_threshold: int = 2,
        execution_threshold: int = 2,
    ) -> "List[AgentRiskCandidate]":
        """对某 Agent 跑三类异常检测并登记候选（**只发现，不处理**，红线③/④/⑤）。

        检测结果一律为「待人工复核」的风险候选：本方法不封禁 Agent、不修改权限、
        不处置风险，也不产生任何放行/批准语义。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行安全检测（红线①）"
            )
        scoped_events = [
            e for e in self._events.values() if e.org_id == self._org_id
        ]
        found: "List[AgentRiskCandidate]" = []
        found.extend(
            self._detector.detect_access_anomaly(
                agent_id=agent_id,
                events=scoped_events,
                threshold=access_threshold,
                detected_at=detected_at,
            )
        )
        found.extend(
            self._detector.detect_permission_anomaly(
                agent_id=agent_id,
                events=scoped_events,
                threshold=permission_threshold,
                detected_at=detected_at,
            )
        )
        found.extend(
            self._detector.detect_execution_anomaly(
                agent_id=agent_id,
                events=scoped_events,
                threshold=execution_threshold,
                detected_at=detected_at,
            )
        )
        for candidate in found:
            self.register_risk_candidate(
                risk=candidate, actor_id=actor_id, actor_kind=actor_kind
            )
        return found

    # ------------------------------------------------------------------
    # 安全报告（事实 + 候选 + 来源链）
    # ------------------------------------------------------------------

    def generate_security_report(
        self,
        *,
        report_id: str,
        agent_id: str = "",
        generated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentSecurityReport:
        """生成安全报告（**只汇总事实 + 候选，强可溯源**，红线③/⑤/⑥）。

        报告只包含：已登记的安全事件事实、待人工复核的风险候选、来源链。
        **不含**处置结论、封禁建议、权限修改建议；来源链为空即拒绝生成。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成安全报告（红线①）"
            )
        events = [e for e in self._events.values() if e.org_id == self._org_id]
        risks = [r for r in self._risks.values() if r.org_id == self._org_id]
        if agent_id:
            events = [e for e in events if e.agent_id == agent_id]
            risks = [r for r in risks if r.agent_id == agent_id]
        trace = SourceTrace(trace_id=f"trace-{report_id}")
        for e in events:
            trace.add_entry(f"event:{e.event_id}")
        for r in risks:
            trace.add_entry(f"risk:{r.risk_id}")
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"generate_security_report 拒绝生成 {report_id!r}：无任何事实来源，"
                f"禁止输出无来源链的安全报告（红线⑥）"
            )
        report = AgentSecurityReport(
            report_id=report_id,
            org_id=self._org_id,
            generated_at=generated_at,
            events=events,
            risks=risks,
            source_trace=trace,
            generated_by=actor_id,
        )
        self._reports[report_id] = report
        if self._audit is not None:
            self._audit.record_agent_risk_action(
                record_id=f"agent-security-report-{report_id}",
                actor_id=actor_id,
                action="generate_agent_security_report",
                target=agent_id or self._org_id,
                detail=report.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return report

    # ------------------------------------------------------------------
    # 风险人工处置（必须真实 USER）
    # ------------------------------------------------------------------

    def human_review_risk(
        self,
        *,
        risk_id: str,
        actor_kind: Any,
        actor_id: str,
        decision: str,
        reviewed_at: str = "",
        note: str = "",
    ) -> AgentRiskReview:
        """人工处置某风险候选（**必须真实 USER**，红线⑤/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError``。``decision`` 由人工填写，
        AI 不得代填空值；已处置的风险不可重复处置（终态）。

        本方法**只登记人工处置事实**，不自动封禁 Agent、不自动修改权限。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下处置安全风险（红线①）"
            )
        risk = self._risks.get(risk_id)
        if risk is None:
            raise EnterpriseRedLineViolationError(
                f"human_review_risk 找不到风险候选 {risk_id!r}：禁止凭空处置（红线⑤）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "human_review_risk 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        if not str(decision).strip():
            raise EnterpriseRedLineViolationError(
                "human_review_risk 必须由人工填写 decision："
                "AI 不得代替安全责任人给出处置结论（红线⑥）"
            )
        review_id = f"review-{risk_id}"
        review = self._reviews.get(review_id)
        if review is None:
            review = AgentRiskReview(
                review_id=review_id, risk_id=risk_id, org_id=self._org_id
            )
            self._reviews[review_id] = review
        if review.is_reviewed:
            raise EnterpriseRedLineViolationError(
                f"风险 {risk_id!r} 已由 {review.reviewer_id!r} 人工处置，"
                f"不可重复处置（红线⑤）"
            )
        review.status = AgentRiskReviewStatus.REVIEWED
        review.reviewer_id = actor_id
        review.decision = decision
        review.note = note
        review.reviewed_at = reviewed_at
        if self._audit is not None:
            self._audit.record_agent_risk_review_action(
                record_id=f"agent-risk-review-{risk_id}",
                actor_id=actor_id,
                action="human_review_agent_risk",
                target=risk.agent_id,
                detail=(
                    f"risk_id={risk_id};status=reviewed;"
                    f"reviewer={actor_id};decision={decision}"
                ),
                ts=reviewed_at,
                actor_kind=AuditActorKind.USER,
            )
        return review

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def list_security_events(
        self,
        *,
        user: object,
        agent_id: str = "",
        event_type: "AgentSecurityEventType | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentSecurityEvent]":
        """列出当前组织下安全事件（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [e for e in self._events.values() if e.org_id == self._org_id]
        if agent_id:
            out = [e for e in out if e.agent_id == agent_id]
        if event_type is not None:
            out = [e for e in out if e.event_type is event_type]
        return out

    def list_risk_candidates(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[AgentRiskCandidate]":
        """列出当前组织下风险候选（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._risks.values() if r.org_id == self._org_id]
        if agent_id:
            out = [r for r in out if r.agent_id == agent_id]
        return out

    def list_risk_reviews(
        self,
        *,
        user: object,
        status: "AgentRiskReviewStatus | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentRiskReview]":
        """列出当前组织下风险处置记录（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._reviews.values() if r.org_id == self._org_id]
        if status is not None:
            out = [r for r in out if r.status is status]
        return out

    def list_security_reports(
        self,
        *,
        user: object,
        resource_category: str = "data",
    ) -> "List[AgentSecurityReport]":
        """列出当前组织下安全报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return [r for r in self._reports.values() if r.org_id == self._org_id]


__all__ = [
    "AgentSecurityEventType",
    "AgentSecuritySeverity",
    "AgentRiskReviewStatus",
    "SourceTrace",
    "AgentSecurityEvent",
    "AgentRiskCandidate",
    "AgentRiskReview",
    "AgentSecurityReport",
    "AgentSecurityDetector",
    "AgentSecurityRiskService",
    "_SECURITY_FORBIDDEN",
]
