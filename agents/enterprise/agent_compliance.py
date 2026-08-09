"""Enterprise Agent Compliance & Audit Intelligence Layer（Phase 3.8.19）。

链路：**Agent 行为 → 审计数据 → 规则检查 → 合规候选 → 人工审核**。

新增（任务1–6）：
- ``ComplianceRuleScope`` / ``ComplianceRuleStatus``：合规规则作用域与状态枚举。
- ``ComplianceRule``：合规规则（rule_id / name / description / scope / source /
  status）。**规则来源可追溯**：``source`` 为空即拒绝落库；``ACTIVE`` 禁止在构造期
  直接落地，只能由真实人工经 ``confirm_rule_active(actor_kind=USER)`` 推进（红线⑤）。
- ``ComplianceCheckResult`` / ``ComplianceCheck``：检查事实（check_id / agent_id /
  rule_id / result / evidence / timestamp）。**只记录检查事实**：结果枚举刻意
  **不含** ``VIOLATION`` / ``ILLEGAL`` / ``FAIL`` 等判罚语义，只有
  ``pass`` / ``attention`` / ``not_applicable``（红线③：AI 不得判定违法违规）。
- ``ComplianceRiskCandidate``：合规风险候选（risk_id / agent_id / pattern /
  evidence / requires_human_review）。**强制 requires_human_review=True**：
  模型层禁止置 False，也不提供任何 resolve / penalty / suspend 方法（红线③/④）。
- ``AgentComplianceDetector``：合规检测器（check_audit_pattern /
  check_permission_pattern / check_runtime_pattern）。**只发现候选，不判罚**：
  只产出 ``ComplianceRiskCandidate``，绝不判定违规、绝不处罚 Agent、
  绝不修改权限或策略（红线③/④/⑤）。
- ``AgentComplianceReport``：合规报告（检查事实 + 风险候选 + 来源链 ``SourceTrace``）。
  无来源链即拒绝构造；报告不含违规结论、处罚建议与批准语义。
- ``ComplianceReviewStatus`` / ``ComplianceReview``：合规人工整改记录。
  **必须真实 USER**：由 ``AgentComplianceService.human_review_compliance_risk`` 在
  ``require_human_actor(USER)`` 守卫下写入，AI 无论如何无法自行处罚（红线④/⑥）。
- ``AgentComplianceService``：聚合治理服务，承载规则登记 / 人工确认规则生效 /
  检查事实登记 / 风险候选登记 / 三类模式检测 / 报告生成 / 人工整改 / 只读查询；
  接入身份层 + ``AgentPermissionPolicy``（合规数据隔离，默认拒绝）+
  ``AgentRuntimeGovernanceService``（只读消费运行时判定事实）；联动审计
  （AGENT_COMPLIANCE_RULE / AGENT_COMPLIANCE_CHECK / AGENT_COMPLIANCE_RISK，任务7）。

红线（fail-closed，复用 3.8.0~3.8.18 基座 + 3.8.19 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved。
③ 不 AI 自动判定违法/违规（auto_violate / auto_penalty / auto_judge_compliance 等
   被 mixin 拦截；检查结果枚举无判罚态，检测器只产出「待人工复核」的候选）。
④ 不 AI 自动处罚 Agent（auto_suspend_agent / auto_ban_agent 等被拦截；
   候选 ``requires_human_review`` 恒为 True，整改强制 USER）。
⑤ 不 AI 自动修改权限或策略（auto_change_permission / auto_modify_policy /
   auto_activate_rule 等被拦截；规则生效/废止只能由真实人工确认）。
⑥ 不 AI 代替合规责任人（审计禁止 ``record_human_approval``；整改节点强制
   ``require_human_actor(USER)``；规则/检查/候选/报告只陈述事实，不含处罚建议）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_runtime_policy import (
    AgentRuntimeGovernanceService,
    RuntimeDecisionRecord,
)
from agents.enterprise.agent_security_risk import SourceTrace
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

_COMPLIANCE_FORBIDDEN = (
    # 基座（红线②/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动判定违法/违规（主理人明列三项 + 同族收敛）
    "auto_violate",
    "violate",
    "auto_penalty",
    "penalty",
    "auto_judge_compliance",
    "judge_compliance",
    "auto_judge",
    "judge_violation",
    "auto_determine_violation",
    "determine_violation",
    "declare_violation",
    "auto_declare_violation",
    "auto_declare_illegal",
    "declare_illegal",
    "judge_illegal",
    "auto_rule_violation",
    "auto_fine",
    "fine_agent",
    "auto_sanction",
    "sanction_agent",
    "auto_convict",
    "convict",
    # 红线④：禁止 AI 自动处罚 Agent（主理人明列两项 + 同族收敛）
    "auto_suspend_agent",
    "suspend_agent",
    "auto_ban_agent",
    "ban_agent",
    "auto_punish_agent",
    "punish_agent",
    "auto_disable_agent",
    "disable_agent",
    "auto_block_agent",
    "block_agent",
    "auto_terminate_agent",
    "terminate_agent",
    "auto_quarantine_agent",
    "quarantine_agent",
    "auto_revoke_agent",
    "revoke_agent",
    "auto_kill_agent",
    "kill_agent",
    # 红线⑤：禁止 AI 自动修改权限或策略
    "auto_change_permission",
    "change_permission",
    "auto_grant_permission",
    "grant_permission",
    "auto_revoke_permission",
    "revoke_permission",
    "auto_modify_permission",
    "modify_permission",
    "auto_escalate_permission",
    "escalate_permission",
    "auto_modify_policy",
    "modify_policy",
    "auto_update_policy",
    "update_policy",
    "auto_apply_policy",
    "apply_policy",
    "auto_activate_rule",
    "activate_rule",
    "auto_change_rule",
    "change_rule",
    "auto_update_rule",
    "update_rule",
    # 红线⑥：禁止 AI 代替合规责任人
    "auto_certify_compliance",
    "certify_compliance",
    "auto_attest",
    "attest_compliance",
    "auto_clear_compliance",
    "clear_compliance",
    "act_as_compliance_officer",
    "take_compliance_ownership",
    "assume_compliance_responsibility",
    "auto_govern_compliance",
    "auto_sign_compliance",
)


class ComplianceRuleScope(str, Enum):
    """合规规则作用域（任务1，只描述规则适用面，不含判罚语义）。"""

    AUDIT = "audit"              # 审计行为面（审计事实模式）
    PERMISSION = "permission"    # 权限面（权限相关事实模式）
    RUNTIME = "runtime"          # 运行时面（运行时判定事实模式）
    DATA = "data"                # 数据面（数据访问/流转事实）
    GENERAL = "general"          # 通用面


class ComplianceRuleStatus(str, Enum):
    """合规规则状态（任务1）。

    ``draft → active → deprecated``。**ACTIVE / DEPRECATED 仅真实 USER 可推进**
    （红线⑤：AI 不得自动修改策略）：AI 既不能构造 ACTIVE，也没有任何
    activate / update_rule 方法可调。
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class ComplianceCheckResult(str, Enum):
    """合规检查结果（任务2，**刻意无判罚态**）。

    红线③：AI 不得判定违法/违规。因此本枚举**不提供** ``violation`` /
    ``illegal`` / ``fail`` 等定性判罚值，只有三种**中性事实标注**：

    - ``pass``：本次检查未发现与规则不符的事实（≠ 合规认定，≠ 免责）；
    - ``attention``：发现需要**人工关注**的不符迹象（≠ 违规结论，≠ 处罚依据）；
    - ``not_applicable``：规则不适用于该事实集合。

    任何「是否违规」的定性，只能由真实合规责任人线下依职权作出（红线⑥）。
    """

    PASS = "pass"
    ATTENTION = "attention"
    NOT_APPLICABLE = "not_applicable"


class ComplianceReviewStatus(str, Enum):
    """合规人工整改状态（任务6）。

    ``pending → reviewed``。**仅真实 USER 可推进**（红线④/⑥）：
    AI 既不能构造 REVIEWED，也没有任何自动处罚方法可调。
    """

    PENDING = "pending"
    REVIEWED = "reviewed"


@dataclass
class ComplianceRule:
    """合规规则（任务1，**规则来源可追溯**）。

    字段严格对应：rule_id / name / description / scope / source / status；
    额外增加 org_id / created_at / keywords / confirmed_by / confirmed_at
    便于隔离、事实匹配与人工确认留痕。

    红线（⑤/⑥）：
    - ``source`` 为空即拒绝落库：规则必须能追溯到真实出处（法规条款 / 企业制度 /
      主理人决议等），AI 不得凭空编造合规规则；
    - ``status`` 构造期若显式传 ``ACTIVE``，直接抛
      ``EnterpriseRedLineViolationError``：规则生效必须由真实人工确认
      （``confirm_rule_active(actor_kind=USER)``）；
    - 模型层**不提供**任何 activate / update_rule / apply_policy 方法，
      AI 结构上无法自动修改策略。
    """

    rule_id: str
    name: str = ""
    description: str = ""
    scope: ComplianceRuleScope = ComplianceRuleScope.GENERAL
    source: str = ""
    status: ComplianceRuleStatus = ComplianceRuleStatus.DRAFT
    keywords: List[str] = field(default_factory=list)  # 事实匹配关键词（不推断、不扩写）
    created_at: str = ""
    org_id: str = ""
    confirmed_by: str = ""   # 人工确认生效者（仅事实记录，由服务层写入）
    confirmed_at: str = ""   # 人工确认时间（仅事实记录）

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ComplianceRuleScope):
            self.scope = ComplianceRuleScope(self.scope)
        if not isinstance(self.status, ComplianceRuleStatus):
            self.status = ComplianceRuleStatus(self.status)
        if not str(self.name).strip():
            raise EnterpriseRedLineViolationError(
                f"ComplianceRule {self.rule_id!r} 缺少 name："
                f"禁止落库无名合规规则（红线⑥）"
            )
        if not str(self.source).strip():
            raise EnterpriseRedLineViolationError(
                f"ComplianceRule {self.rule_id!r} 缺少 source："
                f"合规规则必须来源可追溯，禁止 AI 凭空编造规则（红线⑥）"
            )
        if self.status is ComplianceRuleStatus.ACTIVE:
            raise EnterpriseRedLineViolationError(
                f"ComplianceRule {self.rule_id!r} 禁止在构造期直接落 active："
                f"合规规则生效必须由真实人工确认（红线⑤/⑥），"
                f"请以 draft 登记后经 confirm_rule_active(actor_kind=USER) 推进"
            )
        # 仅做事实清洗，不新增、不推断任何关键词（红线③）。
        self.keywords = [k.strip() for k in self.keywords if str(k).strip()]

    @property
    def is_effective(self) -> bool:
        """规则是否处于生效态（只读事实，非批准语义）。"""
        return self.status is ComplianceRuleStatus.ACTIVE

    def matches_keyword(self, text: str) -> bool:
        """文本是否命中本规则显式声明的关键词（未声明即 False，不做模糊推断）。"""
        if not text or not self.keywords:
            return False
        value = str(text).strip()
        return any(k in value for k in self.keywords)

    def summary(self) -> str:
        """只读汇总规则事实（不含判罚语义）。"""
        return (
            f"rule={self.rule_id};name={self.name};scope={self.scope.value};"
            f"status={self.status.value};source={self.source}"
        )


@dataclass
class ComplianceCheck:
    """合规检查事实（任务2，**只记录检查事实**）。

    字段严格对应：check_id / agent_id / rule_id / result / evidence / timestamp；
    额外增加 org_id / checked_by / note 便于隔离与溯源。

    只记录事实（红线③/⑥）：
    - ``result`` 取值来自 ``ComplianceCheckResult``，**无任何判罚态**：
      ``attention`` 只表示「需人工关注」，**不是**违规认定；
    - ``evidence`` 为空即拒绝落库（禁止无证据的合规检查记录）；
    - ``rule_id`` 为空即拒绝落库（检查必须绑定到可追溯的规则）；
    - 模型层不提供任何 violate / penalty / suspend 方法。
    """

    check_id: str
    agent_id: str
    rule_id: str = ""
    result: ComplianceCheckResult = ComplianceCheckResult.NOT_APPLICABLE
    evidence: List[str] = field(default_factory=list)
    timestamp: str = ""
    org_id: str = ""
    checked_by: str = "ai"   # 检查发起方 id（事实，通常为 ai）
    note: str = ""           # 中性事实说明（不得含判罚/处罚/批准语义）

    def __post_init__(self) -> None:
        if not isinstance(self.result, ComplianceCheckResult):
            self.result = ComplianceCheckResult(self.result)
        if not str(self.rule_id).strip():
            raise EnterpriseRedLineViolationError(
                f"ComplianceCheck {self.check_id!r} 缺少 rule_id："
                f"检查事实必须绑定可追溯的合规规则（红线⑥）"
            )
        self.evidence = [str(e).strip() for e in self.evidence if str(e).strip()]
        if not self.evidence:
            raise EnterpriseRedLineViolationError(
                f"ComplianceCheck {self.check_id!r} 缺少 evidence："
                f"禁止落库无证据的合规检查（红线⑥：事实必须可溯源）"
            )

    @property
    def needs_attention(self) -> bool:
        """是否需要人工关注（**≠ 违规结论**，红线③）。"""
        return self.result is ComplianceCheckResult.ATTENTION

    def summary(self) -> str:
        """只读汇总检查事实（不构成任何违规判定）。"""
        return (
            f"agent={self.agent_id};rule={self.rule_id};"
            f"result={self.result.value};"
            f"evidence={'|'.join(self.evidence)}"
        )


@dataclass
class ComplianceRiskCandidate:
    """合规风险候选（任务4，**强制人工复核**）。

    字段严格对应：risk_id / agent_id / pattern / evidence / requires_human_review；
    额外增加 rule_id / org_id / detected_at / source 便于隔离与溯源。

    强制人工复核（红线③/④/⑥）：
    - ``requires_human_review`` **恒为 True**：构造期若显式传 False，直接抛
      ``EnterpriseRedLineViolationError``；
    - 候选只是「发现的疑点」，**不是**违规认定、不是处罚决定、不是停用依据；
    - ``pattern`` / ``evidence`` 为空即拒绝构造（禁止无据合规指控）；
    - 模型层不提供任何 penalty / suspend / ban / resolve 方法，AI 结构上无法处罚。
    """

    risk_id: str
    agent_id: str
    pattern: str = ""
    evidence: List[str] = field(default_factory=list)
    requires_human_review: bool = True
    rule_id: str = ""
    detected_at: str = ""
    source: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if self.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"ComplianceRiskCandidate {self.risk_id!r} 禁止把 "
                f"requires_human_review 置为 {self.requires_human_review!r}："
                f"合规风险必须由真实合规责任人复核（红线④/⑥），"
                f"AI 不得自行免除人工复核"
            )
        if not str(self.pattern).strip():
            raise EnterpriseRedLineViolationError(
                f"ComplianceRiskCandidate {self.risk_id!r} 缺少 pattern："
                f"禁止落库无模式描述的合规风险候选（红线⑥）"
            )
        self.evidence = [str(e).strip() for e in self.evidence if str(e).strip()]
        if not self.evidence:
            raise EnterpriseRedLineViolationError(
                f"ComplianceRiskCandidate {self.risk_id!r} 缺少 evidence："
                f"禁止无证据的合规风险指控（红线③/⑥：事实必须可溯源）"
            )

    def summary(self) -> str:
        """只读汇总候选事实（**不构成违规认定**，红线③）。"""
        return (
            f"agent={self.agent_id};rule={self.rule_id};pattern={self.pattern};"
            f"evidence={'|'.join(self.evidence)};"
            f"requires_human_review={self.requires_human_review}"
        )


@dataclass
class ComplianceReview:
    """合规人工整改记录（任务6，**必须真实 USER**）。

    字段：review_id / risk_id / reviewer_id / status / decision / note /
    reviewed_at / org_id。

    红线④/⑥：
    - 构造期禁止直接落 ``REVIEWED``：整改态只能由
      ``AgentComplianceService.human_review_compliance_risk`` 在
      ``require_human_actor(USER)`` 守卫下推进，AI 无论如何无法伪造「已整改」；
    - ``reviewer_id`` 必须为真实合规责任人标识，空值拒绝（责任可追溯）；
    - ``decision`` 由人工填写，AI 不得代填（禁 AI 代替合规责任人）；
    - 模型层不提供任何 auto_penalty / auto_suspend_agent / auto_clear_compliance 方法。
    """

    review_id: str
    risk_id: str
    reviewer_id: str = ""
    status: ComplianceReviewStatus = ComplianceReviewStatus.PENDING
    decision: str = ""      # 人工填写的整改结论事实（AI 不得代填）
    note: str = ""
    reviewed_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, ComplianceReviewStatus):
            self.status = ComplianceReviewStatus(self.status)
        if self.status is ComplianceReviewStatus.REVIEWED:
            raise EnterpriseRedLineViolationError(
                f"ComplianceReview {self.review_id!r} 禁止在构造期直接落 reviewed："
                f"合规整改必须由真实合规责任人执行（红线④/⑥），"
                f"请以 pending 登记后经 human_review_compliance_risk"
                f"(actor_kind=USER) 推进"
            )

    @property
    def is_reviewed(self) -> bool:
        """是否已由人工整改处置（只读事实）。"""
        return self.status is ComplianceReviewStatus.REVIEWED


@dataclass
class AgentComplianceReport:
    """Agent 合规报告（任务5：检查事实 + 风险候选 + 来源链）。

    字段：report_id / org_id / generated_at / checks / risks / source_trace /
    generated_by。

    红线（③/④/⑥）：
    - 报告**只汇总事实**：合规检查事实 + 风险候选（均待人工复核），
      **不含**违规认定、处罚建议、停用建议、权限/策略修改建议、批准语义；
    - 无来源链（``source_trace`` 缺失或为空）即拒绝构造（强可溯源）；
    - 不提供任何 penalty / suspend / certify_compliance 方法。
    """

    report_id: str
    org_id: str = ""
    generated_at: str = ""
    checks: List[ComplianceCheck] = field(default_factory=list)
    risks: List[ComplianceRiskCandidate] = field(default_factory=list)
    source_trace: "SourceTrace | None" = None
    generated_by: str = "ai"

    def __post_init__(self) -> None:
        if self.source_trace is None or not self.source_trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"AgentComplianceReport {self.report_id!r} 缺少可溯源 source_trace："
                f"禁止生成无来源链的合规报告（红线⑥：事实必须可溯源）"
            )

    @property
    def pending_human_review_count(self) -> int:
        """待人工复核的合规风险候选数量（恒等于候选总数，红线④）。"""
        return sum(1 for r in self.risks if r.requires_human_review)

    @property
    def attention_count(self) -> int:
        """需人工关注的检查条目数（**≠ 违规数**，红线③）。"""
        return sum(1 for c in self.checks if c.needs_attention)

    def result_breakdown(self) -> Dict[str, int]:
        """按检查结果统计条目数量（只读事实，不含违规认定）。"""
        out: Dict[str, int] = {}
        for c in self.checks:
            out[c.result.value] = out.get(c.result.value, 0) + 1
        return out

    def summary(self) -> str:
        """只读汇总报告事实（**不构成任何违规判定或处罚结论**，红线③/④）。"""
        return (
            f"report={self.report_id};checks={len(self.checks)};"
            f"attention={self.attention_count};risks={len(self.risks)};"
            f"pending_human_review={self.pending_human_review_count};"
            f"source={self.source_trace.render() if self.source_trace else 'no_source'}"
        )


class AgentComplianceDetector(_RedLineForbiddenMixin):
    """Agent 合规检测器（任务3，**只发现候选，不判罚**）。

    三类模式检查：``check_audit_pattern`` / ``check_permission_pattern`` /
    ``check_runtime_pattern``，统一产出 ``ComplianceRiskCandidate``
    （``requires_human_review=True``）。

    红线（fail-closed）：
    - **只发现不判罚**（红线③）：不判定违法/违规，不给出定性结论，
      也不返回任何「已违规/可处罚/已合规」语义；
    - **不处罚 Agent**（红线④）：不停用、不封禁、不中止任何 Agent；
    - **不改权限或策略**（红线⑤）：只读事实，绝不写权限、绝不改规则状态；
    - 不持有 auto_violate / auto_penalty / auto_judge_compliance /
      auto_suspend_agent / auto_ban_agent / auto_modify_policy 等方法。
    """

    _FORBIDDEN = _COMPLIANCE_FORBIDDEN

    def __init__(
        self,
        org_id: str = "",
        identity: "IdentityService | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentComplianceDetector（红线①）"
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
        rule_id: str,
        detected_at: str,
        source: str,
        org_id: str,
    ) -> ComplianceRiskCandidate:
        return ComplianceRiskCandidate(
            risk_id=risk_id,
            agent_id=agent_id,
            pattern=pattern,
            evidence=evidence,
            requires_human_review=True,   # 恒为 True，结构上不可关闭（红线④）
            rule_id=rule_id,
            detected_at=detected_at,
            source=source,
            org_id=org_id,
        )

    @staticmethod
    def _scoped_audit_records(
        *, agent_id: str, records: "List[Any]"
    ) -> "List[Any]":
        """筛出与该 agent 相关的审计事实（只按 target / actor_id 精确匹配）。"""
        out: "List[Any]" = []
        for r in records:
            target = str(getattr(r, "target", "") or "")
            actor_id = str(getattr(r, "actor_id", "") or "")
            if target == agent_id or actor_id == agent_id:
                out.append(r)
        return out

    # ---- 审计模式检查（只发现）----

    def check_audit_pattern(
        self,
        *,
        agent_id: str,
        rule: ComplianceRule,
        audit_records: "List[Any]",
        threshold: int = 3,
        detected_at: str = "",
    ) -> "List[ComplianceRiskCandidate]":
        """按规则检查审计事实模式（**只发现候选，不判罚**，红线③/④）。

        事实判据（均为中性统计，不含定性）：
        - 与该 agent 相关的审计记录数达到 ``threshold`` → 产出「审计活动密度」候选；
        - 审计记录的 ``action`` 命中规则**显式声明**的 ``keywords`` →
          产出「关键词命中」候选（关键词由人工在规则中登记，AI 不推断、不扩写）。

        无 agent_id / 无记录 / 规则未生效 → 返回空列表（不臆造合规风险）。
        本方法**绝不**判定违规、**绝不**处罚 Agent、**绝不**修改权限或策略。
        """
        if not agent_id or not audit_records or rule is None:
            return []
        scoped = self._scoped_audit_records(
            agent_id=agent_id, records=audit_records
        )
        if not scoped:
            return []
        out: "List[ComplianceRiskCandidate]" = []
        if len(scoped) >= max(1, int(threshold)):
            out.append(
                self._build_candidate(
                    risk_id=f"crisk-audit-freq-{agent_id}-{rule.rule_id}",
                    agent_id=agent_id,
                    pattern="audit_activity_over_threshold",
                    evidence=[
                        f"audit:{getattr(r, 'record_id', '')}" for r in scoped
                    ],
                    rule_id=rule.rule_id,
                    detected_at=detected_at,
                    source=(
                        f"detector:audit_pattern;rule={rule.rule_id};"
                        f"records={len(scoped)}"
                    ),
                    org_id=self._org_id,
                )
            )
        hits = [
            r
            for r in scoped
            if rule.matches_keyword(str(getattr(r, "action", "") or ""))
        ]
        if hits:
            out.append(
                self._build_candidate(
                    risk_id=f"crisk-audit-keyword-{agent_id}-{rule.rule_id}",
                    agent_id=agent_id,
                    pattern="audit_action_keyword_hit",
                    evidence=[
                        f"audit:{getattr(r, 'record_id', '')}"
                        f";action={getattr(r, 'action', '')}"
                        for r in hits
                    ],
                    rule_id=rule.rule_id,
                    detected_at=detected_at,
                    source=(
                        f"detector:audit_pattern;rule={rule.rule_id};"
                        f"keyword_hits={len(hits)}"
                    ),
                    org_id=self._org_id,
                )
            )
        return out

    # ---- 权限模式检查（只发现，绝不改权限）----

    def check_permission_pattern(
        self,
        *,
        agent_id: str,
        rule: ComplianceRule,
        audit_records: "List[Any]",
        threshold: int = 2,
        detected_at: str = "",
    ) -> "List[ComplianceRiskCandidate]":
        """按规则检查权限相关事实模式（**只发现，绝不修改权限**，红线④/⑤）。

        事实判据：与该 agent 相关、且审计类别名含 ``permission`` 的记录数达到
        ``threshold`` → 产出候选（待人工复核）。

        本方法只读权限相关审计事实，**不调用**任何授予/撤销/变更权限接口
        （相关方法名已在 ``_COMPLIANCE_FORBIDDEN`` 中结构性拦截）。
        """
        if not agent_id or not audit_records or rule is None:
            return []
        scoped = [
            r
            for r in self._scoped_audit_records(
                agent_id=agent_id, records=audit_records
            )
            if "permission"
            in str(
                getattr(getattr(r, "category", ""), "value", None)
                or getattr(r, "category", "")
            ).lower()
        ]
        if len(scoped) < max(1, int(threshold)):
            return []
        return [
            self._build_candidate(
                risk_id=f"crisk-permission-{agent_id}-{rule.rule_id}",
                agent_id=agent_id,
                pattern="repeated_permission_audit_pattern",
                evidence=[
                    f"audit:{getattr(r, 'record_id', '')}" for r in scoped
                ],
                rule_id=rule.rule_id,
                detected_at=detected_at,
                source=(
                    f"detector:permission_pattern;rule={rule.rule_id};"
                    f"records={len(scoped)}"
                ),
                org_id=self._org_id,
            )
        ]

    # ---- 运行时模式检查（只发现，绝不停用/处罚）----

    def check_runtime_pattern(
        self,
        *,
        agent_id: str,
        rule: ComplianceRule,
        decision_records: "List[RuntimeDecisionRecord]",
        threshold: int = 2,
        detected_at: str = "",
    ) -> "List[ComplianceRiskCandidate]":
        """按规则检查运行时判定事实模式（**只发现，绝不处罚 Agent**，红线③/④）。

        消费 Phase 3.8.17 ``RuntimeDecisionRecord`` 的**既有事实**：
        未全部通过前置核查（``all_checks_passed is False``）的记录数达到
        ``threshold`` → 产出候选（待人工复核）。

        注意：``all_checks_passed is False`` 只是核查事实，**不等于违规**
        （红线③），更不触发任何停用/封禁动作（红线④）。
        """
        if not agent_id or not decision_records or rule is None:
            return []
        scoped = [
            r
            for r in decision_records
            if getattr(r, "agent_id", "") == agent_id
            and getattr(r, "all_checks_passed", True) is False
        ]
        if len(scoped) < max(1, int(threshold)):
            return []
        return [
            self._build_candidate(
                risk_id=f"crisk-runtime-{agent_id}-{rule.rule_id}",
                agent_id=agent_id,
                pattern="runtime_check_not_passed_pattern",
                evidence=[
                    f"runtime:{getattr(r, 'record_id', '')}" for r in scoped
                ],
                rule_id=rule.rule_id,
                detected_at=detected_at,
                source=(
                    f"detector:runtime_pattern;rule={rule.rule_id};"
                    f"records={len(scoped)}"
                ),
                org_id=self._org_id,
            )
        ]


class AgentComplianceService(_RedLineForbiddenMixin):
    """Agent 合规与审计智能聚合服务（任务1–8 统一入口）。

    承载：合规规则登记 / 规则人工确认（生效·废止）/ 检查事实登记 /
    风险候选登记 / 三类模式检测 / 合规报告生成 / 人工整改 / 只读查询（权限隔离）。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - 检测只产出候选事实，**不判定违法/违规**（红线③）。
    - **不处罚 Agent**：无停用/封禁/中止能力（红线④）。
    - **不写权限、不改策略**：规则生效/废止强制 ``require_human_actor(USER)``（红线⑤）。
    - 整改处置强制 ``require_human_actor(USER)``，AI 无法自行整改（红线④/⑥）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_violate / auto_penalty / auto_judge_compliance /
      auto_suspend_agent / auto_ban_agent / auto_change_permission /
      auto_modify_policy 等方法。
    """

    _FORBIDDEN = _COMPLIANCE_FORBIDDEN

    def __init__(
        self,
        org_id: str,
        audit: "AuditService | None" = None,
        identity: "IdentityService | None" = None,
        visibility: "KnowledgeVisibilityPolicy | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
        runtime_policy: "AgentRuntimeGovernanceService | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentComplianceService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        # 只读消费 Phase 3.8.17 运行时判定事实；本层绝不修改任何运行策略（红线⑤）。
        self._runtime_policy = runtime_policy
        self._detector = AgentComplianceDetector(
            org_id=org_id, identity=identity, permission_policy=permission_policy
        )
        self._rules: Dict[str, ComplianceRule] = {}
        self._checks: Dict[str, ComplianceCheck] = {}
        self._risks: Dict[str, ComplianceRiskCandidate] = {}
        self._reviews: Dict[str, ComplianceReview] = {}
        self._reports: Dict[str, AgentComplianceReport] = {}

    @property
    def detector(self) -> AgentComplianceDetector:
        """只读暴露合规检测器（只发现候选，不判罚）。"""
        return self._detector

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """合规数据读取权限校验（**默认拒绝**，任务8）。

        结合 ``AgentPermissionPolicy``：角色须在该资源类别作用域内，且若声明了读权限
        须经 ``IdentityService`` 校验。任一不过即抛隔离错误（红线⑥：合规数据受控访问）。

        注意：本方法**只读校验**，绝不修改任何权限或策略（红线⑤）。
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
                    f"用户角色无权限访问 Agent 合规与审计数据"
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
    # 合规规则（登记 draft；生效/废止必须真实 USER）
    # ------------------------------------------------------------------

    def register_compliance_rule(
        self,
        *,
        rule: ComplianceRule,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> ComplianceRule:
        """登记一条合规规则（**只能 draft/deprecated 落地**，红线⑤）。

        规则来源必须可追溯（模型层强制 ``source`` 非空）；生效态只能由真实人工经
        ``confirm_rule_active`` 推进，本方法不赋予任何规则以效力。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记合规规则（红线①）"
            )
        if rule.status is ComplianceRuleStatus.ACTIVE:
            raise EnterpriseRedLineViolationError(
                f"register_compliance_rule 拒绝直接登记 active 规则 "
                f"{rule.rule_id!r}：规则生效必须由真实人工确认（红线⑤）"
            )
        rule.org_id = self._org_id
        self._rules[rule.rule_id] = rule
        if self._audit is not None:
            self._audit.record_agent_compliance_rule_action(
                record_id=f"agent-compliance-rule-{rule.rule_id}",
                actor_id=actor_id,
                action="register_compliance_rule",
                target=rule.rule_id,
                detail=rule.summary(),
                ts=rule.created_at,
                actor_kind=actor_kind,
            )
        return rule

    def confirm_rule_active(
        self,
        *,
        rule_id: str,
        actor_kind: Any,
        actor_id: str,
        confirmed_at: str = "",
        note: str = "",
    ) -> ComplianceRule:
        """人工确认某合规规则生效（**必须真实 USER**，红线⑤/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError``。本方法只登记「人工确认」事实，
        不代替合规责任人作出任何合规性判断。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下确认规则生效（红线①）"
            )
        rule = self._rules.get(rule_id)
        if rule is None:
            raise EnterpriseRedLineViolationError(
                f"confirm_rule_active 找不到合规规则 {rule_id!r}："
                f"禁止凭空生效规则（红线⑤）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "confirm_rule_active 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        if rule.status is ComplianceRuleStatus.DEPRECATED:
            raise EnterpriseRedLineViolationError(
                f"规则 {rule_id!r} 已废止，不可再生效（红线⑤）"
            )
        rule.status = ComplianceRuleStatus.ACTIVE
        rule.confirmed_by = actor_id
        rule.confirmed_at = confirmed_at
        if self._audit is not None:
            self._audit.record_agent_compliance_rule_action(
                record_id=f"agent-compliance-rule-active-{rule_id}",
                actor_id=actor_id,
                action="confirm_compliance_rule_active",
                target=rule_id,
                detail=(
                    f"rule_id={rule_id};status=active;"
                    f"confirmed_by={actor_id};note={note}"
                ),
                ts=confirmed_at,
                actor_kind=AuditActorKind.USER,
            )
        return rule

    def confirm_rule_deprecated(
        self,
        *,
        rule_id: str,
        actor_kind: Any,
        actor_id: str,
        confirmed_at: str = "",
        note: str = "",
    ) -> ComplianceRule:
        """人工废止某合规规则（**必须真实 USER**，红线⑤/⑥）。

        与生效同源：AI 结构上无法自动改变任何规则状态。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下废止规则（红线①）"
            )
        rule = self._rules.get(rule_id)
        if rule is None:
            raise EnterpriseRedLineViolationError(
                f"confirm_rule_deprecated 找不到合规规则 {rule_id!r}（红线⑤）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "confirm_rule_deprecated 必须提供真实 actor_id（红线⑥）"
            )
        rule.status = ComplianceRuleStatus.DEPRECATED
        rule.confirmed_by = actor_id
        rule.confirmed_at = confirmed_at
        if self._audit is not None:
            self._audit.record_agent_compliance_rule_action(
                record_id=f"agent-compliance-rule-deprecated-{rule_id}",
                actor_id=actor_id,
                action="confirm_compliance_rule_deprecated",
                target=rule_id,
                detail=(
                    f"rule_id={rule_id};status=deprecated;"
                    f"confirmed_by={actor_id};note={note}"
                ),
                ts=confirmed_at,
                actor_kind=AuditActorKind.USER,
            )
        return rule

    # ------------------------------------------------------------------
    # 检查事实（只登记事实）
    # ------------------------------------------------------------------

    def record_compliance_check(
        self,
        *,
        check: ComplianceCheck,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> ComplianceCheck:
        """登记一条合规检查事实（**只记录事实**，红线③/④/⑥）。

        登记动作不判定违规、不处罚 Agent、不修改权限或策略，
        并如实写入 ``AGENT_COMPLIANCE_CHECK`` 审计。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记合规检查（红线①）"
            )
        if check.rule_id not in self._rules:
            raise EnterpriseRedLineViolationError(
                f"record_compliance_check 拒绝登记 {check.check_id!r}："
                f"引用了未登记的规则 {check.rule_id!r}（红线⑥：规则来源可追溯）"
            )
        check.org_id = self._org_id
        self._checks[check.check_id] = check
        if self._audit is not None:
            self._audit.record_agent_compliance_check_action(
                record_id=f"agent-compliance-check-{check.check_id}",
                actor_id=actor_id,
                action="record_compliance_check",
                target=check.agent_id,
                detail=check.summary(),
                ts=check.timestamp,
                actor_kind=actor_kind,
            )
        return check

    # ------------------------------------------------------------------
    # 风险候选（只登记，强制人工复核）
    # ------------------------------------------------------------------

    def register_risk_candidate(
        self,
        *,
        risk: ComplianceRiskCandidate,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> ComplianceRiskCandidate:
        """登记一条合规风险候选（**必待人工复核**，红线④/⑥）。

        候选 ``requires_human_review`` 恒为 True（模型层强制）；登记同时自动生成
        一条 ``ComplianceReview``（``pending``），等待真实合规责任人整改处置。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记合规风险候选（红线①）"
            )
        if risk.requires_human_review is not True:
            raise EnterpriseRedLineViolationError(
                f"register_risk_candidate 拒绝 requires_human_review != True 的候选 "
                f"{risk.risk_id!r}：合规风险必须人工复核（红线④）"
            )
        risk.org_id = self._org_id
        self._risks[risk.risk_id] = risk
        review_id = f"creview-{risk.risk_id}"
        if review_id not in self._reviews:
            self._reviews[review_id] = ComplianceReview(
                review_id=review_id,
                risk_id=risk.risk_id,
                status=ComplianceReviewStatus.PENDING,
                org_id=self._org_id,
            )
        if self._audit is not None:
            self._audit.record_agent_compliance_risk_action(
                record_id=f"agent-compliance-risk-{risk.risk_id}",
                actor_id=actor_id,
                action="register_compliance_risk_candidate",
                target=risk.agent_id,
                detail=risk.summary(),
                ts=risk.detected_at,
                actor_kind=actor_kind,
            )
        return risk

    # ------------------------------------------------------------------
    # 模式检测（只发现，不判罚）
    # ------------------------------------------------------------------

    def run_compliance_detection(
        self,
        *,
        agent_id: str,
        rule_id: str,
        audit_records: "List[Any] | None" = None,
        runtime_records: "List[RuntimeDecisionRecord] | None" = None,
        user: object = None,
        detected_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
        audit_threshold: int = 3,
        permission_threshold: int = 2,
        runtime_threshold: int = 2,
    ) -> "List[ComplianceRiskCandidate]":
        """对某 Agent 按某规则跑三类模式检查并登记候选（**只发现，不判罚**）。

        数据来源（全部为**既有事实**，本层不生成、不推断）：
        - ``audit_records``：审计事实；未显式传入时，若已注入 ``AuditService``
          则读取其组织内既有记录（只读）。
        - ``runtime_records``：Phase 3.8.17 运行时判定事实；未显式传入时，
          若已注入 ``AgentRuntimeGovernanceService`` 且提供了 ``user``，
          则经其**自带权限隔离**只读拉取（本层绝不修改运行策略，红线⑤）。

        规则须为生效态（``ACTIVE``）才执行检查：未经人工确认的规则不产生任何效力
        （红线⑤）。检测结果一律为「待人工复核」的合规风险候选：本方法不判定违规、
        不处罚 Agent、不修改权限或策略（红线③/④/⑤）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行合规检测（红线①）"
            )
        rule = self._rules.get(rule_id)
        if rule is None:
            raise EnterpriseRedLineViolationError(
                f"run_compliance_detection 找不到合规规则 {rule_id!r}："
                f"禁止凭空检查（红线⑥：规则来源可追溯）"
            )
        if not rule.is_effective:
            raise EnterpriseRedLineViolationError(
                f"合规规则 {rule_id!r} 尚未由真实人工确认生效（当前 "
                f"{rule.status.value}），禁止据此产生合规风险候选（红线⑤）"
            )
        records: "List[Any]" = list(audit_records or [])
        if not records and self._audit is not None:
            records = list(self._audit.query())
        runtime_facts: "List[RuntimeDecisionRecord]" = list(runtime_records or [])
        if (
            not runtime_facts
            and self._runtime_policy is not None
            and user is not None
        ):
            runtime_facts = list(
                self._runtime_policy.list_decision_records(
                    user=user, agent_id=agent_id
                )
            )
        found: "List[ComplianceRiskCandidate]" = []
        found.extend(
            self._detector.check_audit_pattern(
                agent_id=agent_id,
                rule=rule,
                audit_records=records,
                threshold=audit_threshold,
                detected_at=detected_at,
            )
        )
        found.extend(
            self._detector.check_permission_pattern(
                agent_id=agent_id,
                rule=rule,
                audit_records=records,
                threshold=permission_threshold,
                detected_at=detected_at,
            )
        )
        found.extend(
            self._detector.check_runtime_pattern(
                agent_id=agent_id,
                rule=rule,
                decision_records=runtime_facts,
                threshold=runtime_threshold,
                detected_at=detected_at,
            )
        )
        for candidate in found:
            self.register_risk_candidate(
                risk=candidate, actor_id=actor_id, actor_kind=actor_kind
            )
        return found

    # ------------------------------------------------------------------
    # 合规报告（检查事实 + 候选 + 来源链）
    # ------------------------------------------------------------------

    def generate_compliance_report(
        self,
        *,
        report_id: str,
        agent_id: str = "",
        generated_at: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentComplianceReport:
        """生成合规报告（**只汇总事实 + 候选，强可溯源**，红线③/④/⑥）。

        报告只包含：已登记的合规检查事实、待人工复核的风险候选、来源链。
        **不含**违规认定、处罚建议、停用建议、权限/策略修改建议；
        来源链为空即拒绝生成。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下生成合规报告（红线①）"
            )
        checks = [c for c in self._checks.values() if c.org_id == self._org_id]
        risks = [r for r in self._risks.values() if r.org_id == self._org_id]
        if agent_id:
            checks = [c for c in checks if c.agent_id == agent_id]
            risks = [r for r in risks if r.agent_id == agent_id]
        trace = SourceTrace(trace_id=f"trace-{report_id}")
        for c in checks:
            trace.add_entry(f"check:{c.check_id}")
        for r in risks:
            trace.add_entry(f"crisk:{r.risk_id}")
        if not trace.is_traceable:
            raise EnterpriseRedLineViolationError(
                f"generate_compliance_report 拒绝生成 {report_id!r}：无任何事实来源，"
                f"禁止输出无来源链的合规报告（红线⑥）"
            )
        report = AgentComplianceReport(
            report_id=report_id,
            org_id=self._org_id,
            generated_at=generated_at,
            checks=checks,
            risks=risks,
            source_trace=trace,
            generated_by=actor_id,
        )
        self._reports[report_id] = report
        if self._audit is not None:
            self._audit.record_agent_compliance_risk_action(
                record_id=f"agent-compliance-report-{report_id}",
                actor_id=actor_id,
                action="generate_agent_compliance_report",
                target=agent_id or self._org_id,
                detail=report.summary(),
                ts=generated_at,
                actor_kind=actor_kind,
            )
        return report

    # ------------------------------------------------------------------
    # 人工整改（必须真实 USER）
    # ------------------------------------------------------------------

    def human_review_compliance_risk(
        self,
        *,
        risk_id: str,
        actor_kind: Any,
        actor_id: str,
        decision: str,
        reviewed_at: str = "",
        note: str = "",
    ) -> ComplianceReview:
        """人工整改某合规风险候选（**必须真实 USER**，红线④/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError``。``decision`` 由合规责任人填写，
        AI 不得代填空值；已整改的风险不可重复处置（终态）。

        本方法**只登记人工整改事实**，不自动处罚 Agent、不自动修改权限或策略。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下处置合规风险（红线①）"
            )
        risk = self._risks.get(risk_id)
        if risk is None:
            raise EnterpriseRedLineViolationError(
                f"human_review_compliance_risk 找不到合规风险候选 {risk_id!r}："
                f"禁止凭空处置（红线④）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "human_review_compliance_risk 必须提供真实 actor_id"
                "（红线⑥：人工责任可追溯）"
            )
        if not str(decision).strip():
            raise EnterpriseRedLineViolationError(
                "human_review_compliance_risk 必须由人工填写 decision："
                "AI 不得代替合规责任人给出整改结论（红线⑥）"
            )
        review_id = f"creview-{risk_id}"
        review = self._reviews.get(review_id)
        if review is None:
            review = ComplianceReview(
                review_id=review_id, risk_id=risk_id, org_id=self._org_id
            )
            self._reviews[review_id] = review
        if review.is_reviewed:
            raise EnterpriseRedLineViolationError(
                f"合规风险 {risk_id!r} 已由 {review.reviewer_id!r} 人工整改，"
                f"不可重复处置（红线④）"
            )
        review.status = ComplianceReviewStatus.REVIEWED
        review.reviewer_id = actor_id
        review.decision = decision
        review.note = note
        review.reviewed_at = reviewed_at
        if self._audit is not None:
            self._audit.record_agent_compliance_risk_action(
                record_id=f"agent-compliance-review-{risk_id}",
                actor_id=actor_id,
                action="human_review_compliance_risk",
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

    def list_compliance_rules(
        self,
        *,
        user: object,
        scope: "ComplianceRuleScope | None" = None,
        status: "ComplianceRuleStatus | None" = None,
        resource_category: str = "data",
    ) -> "List[ComplianceRule]":
        """列出当前组织下合规规则（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._rules.values() if r.org_id == self._org_id]
        if scope is not None:
            out = [r for r in out if r.scope is scope]
        if status is not None:
            out = [r for r in out if r.status is status]
        return out

    def list_compliance_checks(
        self,
        *,
        user: object,
        agent_id: str = "",
        result: "ComplianceCheckResult | None" = None,
        resource_category: str = "data",
    ) -> "List[ComplianceCheck]":
        """列出当前组织下合规检查事实（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [c for c in self._checks.values() if c.org_id == self._org_id]
        if agent_id:
            out = [c for c in out if c.agent_id == agent_id]
        if result is not None:
            out = [c for c in out if c.result is result]
        return out

    def list_risk_candidates(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[ComplianceRiskCandidate]":
        """列出当前组织下合规风险候选（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._risks.values() if r.org_id == self._org_id]
        if agent_id:
            out = [r for r in out if r.agent_id == agent_id]
        return out

    def list_compliance_reviews(
        self,
        *,
        user: object,
        status: "ComplianceReviewStatus | None" = None,
        resource_category: str = "data",
    ) -> "List[ComplianceReview]":
        """列出当前组织下合规整改记录（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._reviews.values() if r.org_id == self._org_id]
        if status is not None:
            out = [r for r in out if r.status is status]
        return out

    def list_compliance_reports(
        self,
        *,
        user: object,
        resource_category: str = "data",
    ) -> "List[AgentComplianceReport]":
        """列出当前组织下合规报告（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        return [r for r in self._reports.values() if r.org_id == self._org_id]


__all__ = [
    "ComplianceRuleScope",
    "ComplianceRuleStatus",
    "ComplianceCheckResult",
    "ComplianceReviewStatus",
    "ComplianceRule",
    "ComplianceCheck",
    "ComplianceRiskCandidate",
    "ComplianceReview",
    "AgentComplianceReport",
    "AgentComplianceDetector",
    "AgentComplianceService",
    "_COMPLIANCE_FORBIDDEN",
]
