"""Enterprise Agent Policy & Runtime Governance Layer（Phase 3.8.17）。

新增（任务1–4）：
- ``AgentRuntimePolicyStatus``：运行策略状态枚举（draft / active / deprecated）。
- ``AgentRuntimePolicy``：Agent 运行策略（policy_id / agent_id / rules / scope /
  status / created_at / org_id）。**ACTIVE 必须人工确认**：构造期禁止直接落 ACTIVE，
  模型自身不提供任何激活方法，只能由 ``AgentRuntimeGovernanceService.
  confirm_policy_active`` 在 ``require_human_actor(USER)`` 守卫下推进（红线④/⑥）。
- ``AgentToolAccessPolicy``：工具访问策略（**默认拒绝**：未显式列入 allowed_tools 的
  工具一律不可访问；denied_tools 优先级更高；空工具名视为未声明 → 拒绝）。
- ``RuntimeCheckOutcome``：运行时核查结论枚举（pass / fail），缺省一律 fail（fail-closed）。
- ``AgentExecutionGuard``：执行前置核查器（check_policy / check_permission /
  check_scope），**只检查、不批准**：返回事实型核查结论，不授予任何运行许可，
  不修改任何策略，不放行任何工具（红线③/④/⑤）。
- ``RuntimeDecisionRecord``：运行时判定事实记录（record_id / agent_id /
  policy_result / permission_result / scope_result / tool_result / timestamp /
  source / org_id）。**只记录事实**，不构成批准，来源为空即拒绝落库（红线⑥）。
- ``AgentRuntimeGovernanceService``：聚合治理服务，承载策略登记 / 人工确认生效 /
  人工弃用 / 工具访问策略登记 / 工具访问核查 / 运行时前置核查与事实记录；
  接入身份层 + ``AgentPermissionPolicy`` 做运行治理数据权限隔离（默认拒绝）；
  联动审计（AGENT_POLICY / AGENT_RUNTIME_CHECK / AGENT_TOOL_ACCESS，任务5）。

红线（fail-closed，复用 3.8.0~3.8.16 基座 + 3.8.17 新增）：
① 构造/写路径断言 ``safety_invariants_ok()``（engineering_enabled 必须为 False）。
② 不输出 engineering_approved。
③ 不 AI 自动批准 Agent 运行（approve_run / auto_approve_execution /
   allow_execution / grant_execution / bypass_policy 等被 mixin 拦截；Guard 只返回
   核查事实，绝不返回「已批准」语义）。
④ 不 AI 自动修改 Agent 策略（auto_update_policy / auto_apply_policy /
   auto_approve_policy / update_policy / modify_policy / auto_activate 等被拦截；
   状态推进必须 ``require_human_actor(USER)``）。
⑤ 不 AI 自动放行工具访问（auto_grant_tool / allow_tool_access / whitelist_tool /
   unlock_tool / elevate_tool_access 等被拦截；工具策略默认拒绝）。
⑥ 不 AI 代替管理责任（审计禁止 ``record_human_approval``；人工确认节点强制
   ``require_human_actor(USER)``；判定记录只陈述事实，不含处置/批准建议）。
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

_RUNTIME_FORBIDDEN = (
    # 基座（红线②/③/④/⑥，与 red_line._ENTERPRISE_FORBIDDEN_METHODS 对齐）
    "approve",
    "engineering_approved",
    "quote",
    "pricing",
    "sign",
    "authorize",
    "record_human_approval",
    # 红线③：禁止 AI 自动批准 Agent 运行（核查 ≠ 批准）
    "approve_run",
    "auto_approve_run",
    "approve_execution",
    "auto_approve_execution",
    "allow_execution",
    "auto_allow_execution",
    "grant_execution",
    "auto_grant_execution",
    "permit_execution",
    "auto_permit_execution",
    "authorize_execution",
    "auto_authorize_execution",
    "bypass_policy",
    "auto_bypass_policy",
    "override_policy",
    "auto_override_policy",
    "force_run",
    "auto_force_run",
    # 红线④：禁止 AI 自动修改 Agent 策略（主理人明列三项 + 同族收敛）
    "auto_update_policy",
    "auto_apply_policy",
    "auto_approve_policy",
    "update_policy",
    "apply_policy",
    "modify_policy",
    "auto_modify_policy",
    "set_policy",
    "auto_set_policy",
    "patch_policy",
    "auto_patch_policy",
    "activate_policy",
    "auto_activate_policy",
    "auto_activate",
    "auto_deprecate_policy",
    "rewrite_policy",
    "auto_rewrite_policy",
    # 红线⑤：禁止 AI 自动放行工具访问
    "grant_tool_access",
    "auto_grant_tool_access",
    "auto_grant_tool",
    "allow_tool_access",
    "auto_allow_tool_access",
    "permit_tool_access",
    "auto_permit_tool_access",
    "whitelist_tool",
    "auto_whitelist_tool",
    "unlock_tool",
    "auto_unlock_tool",
    "elevate_tool_access",
    "auto_elevate_tool_access",
    "enable_tool",
    "auto_enable_tool",
    # 红线⑥：禁止 AI 代替管理责任
    "auto_manage",
    "take_ownership",
    "act_as_admin",
    "assume_responsibility",
    "auto_govern",
)


class AgentRuntimePolicyStatus(str, Enum):
    """Agent 运行策略状态（任务1）。

    ``draft → active → deprecated``。**ACTIVE 仅能由真实人工确认**（红线④/⑥）：
    AI 既不能构造出 ACTIVE，也不能调用任何自动激活方法。
    """

    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"


class RuntimeCheckOutcome(str, Enum):
    """运行时核查结论（任务3/任务4）。

    只有两种事实结论：通过 / 未通过。**缺省一律 FAIL**（fail-closed）：
    没有生效策略、无权限、越界、无工具授权，统统记为 FAIL，绝不「默认放行」。
    结论只是核查事实，**不构成批准**（红线③）。
    """

    PASS = "pass"
    FAIL = "fail"


@dataclass
class AgentRuntimePolicy:
    """Agent 运行策略（任务1）。

    字段严格对应：policy_id / agent_id / rules / scope / status / created_at；
    额外增加 org_id 做组织隔离。

    **ACTIVE 必须人工确认**（红线④/⑥）：
    - 构造期若显式传入 ``ACTIVE``，直接抛 ``EnterpriseRedLineViolationError``；
      新策略只能以 ``DRAFT`` 落地（``DEPRECATED`` 允许作为历史事实导入）。
    - 模型层**不提供**任何 ``activate`` / ``auto_activate`` / ``update`` 方法，
      状态推进只能经服务层 ``confirm_policy_active`` 在 USER 守卫下完成。
    """

    policy_id: str
    agent_id: str
    rules: List[str] = field(default_factory=list)   # 运行规则事实（如 "max_steps<=5"）
    scope: List[str] = field(default_factory=list)   # 允许的运行作用域（如 "project:P1"）
    status: AgentRuntimePolicyStatus = AgentRuntimePolicyStatus.DRAFT
    created_at: str = ""
    org_id: str = ""
    activated_by: str = ""      # 人工确认生效者（仅事实记录，由服务层写入）
    activated_at: str = ""      # 人工确认生效时间（仅事实记录）

    def __post_init__(self) -> None:
        if not isinstance(self.status, AgentRuntimePolicyStatus):
            self.status = AgentRuntimePolicyStatus(self.status)
        if self.status is AgentRuntimePolicyStatus.ACTIVE:
            raise EnterpriseRedLineViolationError(
                f"AgentRuntimePolicy {self.policy_id!r} 禁止在构造期直接落 ACTIVE："
                f"运行策略生效必须由真实人工确认（红线④/⑥），"
                f"请以 DRAFT 登记后经 confirm_policy_active(actor_kind=USER) 推进"
            )
        # 规则/作用域去空白，仅做事实清洗，不新增、不推断任何规则（红线④）。
        self.rules = [r.strip() for r in self.rules if str(r).strip()]
        self.scope = [s.strip() for s in self.scope if str(s).strip()]

    @property
    def is_effective(self) -> bool:
        """策略是否处于生效态（只读事实，非批准语义）。"""
        return self.status is AgentRuntimePolicyStatus.ACTIVE

    def covers_rule(self, rule: str) -> bool:
        """某条运行规则是否已被本策略显式声明（默认拒绝：未声明即 False）。"""
        if not rule:
            return False
        return rule.strip() in self.rules

    def covers_scope(self, scope: str) -> bool:
        """某作用域是否落在本策略声明范围内（默认拒绝：未声明即 False）。"""
        if not scope:
            return False
        return scope.strip() in self.scope


@dataclass
class AgentToolAccessPolicy:
    """Agent 工具访问策略（任务2，**默认拒绝**）。

    字段：policy_id / agent_id / allowed_tools / denied_tools / scope / org_id /
    created_at。

    默认拒绝语义（红线⑤）：
    - 工具名为空 → 拒绝（未声明的东西不放行）。
    - 工具在 ``denied_tools`` → 拒绝（拒绝优先级最高，显式拒绝不可被覆盖）。
    - 工具不在 ``allowed_tools`` → 拒绝（白名单之外一律不可访问）。
    - ``allowed_tools`` 为空 → 全部拒绝（空白名单 ≠ 全放行）。
    - 本模型不提供任何 ``grant`` / ``allow`` / ``whitelist`` / ``unlock`` 方法，
      AI 无法在结构上放行工具；扩权只能由人工线下修订策略后重新登记。
    """

    policy_id: str
    agent_id: str
    allowed_tools: List[str] = field(default_factory=list)
    denied_tools: List[str] = field(default_factory=list)
    scope: List[str] = field(default_factory=list)
    created_at: str = ""
    org_id: str = ""

    def __post_init__(self) -> None:
        self.allowed_tools = [t.strip() for t in self.allowed_tools if str(t).strip()]
        self.denied_tools = [t.strip() for t in self.denied_tools if str(t).strip()]
        self.scope = [s.strip() for s in self.scope if str(s).strip()]

    def is_tool_allowed(self, tool_name: str) -> bool:
        """工具是否被显式允许（**默认拒绝**，红线⑤）。"""
        if not tool_name:
            return False
        name = tool_name.strip()
        if not name:
            return False
        if name in self.denied_tools:
            return False
        return name in self.allowed_tools

    def check_tool(self, tool_name: str) -> RuntimeCheckOutcome:
        """返回工具访问核查结论（事实型，不放行、不批准）。"""
        return (
            RuntimeCheckOutcome.PASS
            if self.is_tool_allowed(tool_name)
            else RuntimeCheckOutcome.FAIL
        )


@dataclass
class RuntimeDecisionRecord:
    """运行时判定事实记录（任务4）。

    字段严格对应：policy_result / permission_result / timestamp / source；
    额外增加 record_id / agent_id / scope_result / tool_result / org_id 便于溯源。

    **只记录事实**（红线③/⑥）：
    - 本记录陈述「策略核查/权限核查/作用域核查/工具核查」的结论事实，
      **不构成运行批准**，也不含任何处置建议、放行建议、策略修改建议。
    - ``source`` 为空即拒绝落库（AI 不得创造无源判定记录）。
    - 模型不提供任何 approve / allow / grant 方法。
    """

    record_id: str
    agent_id: str
    policy_result: RuntimeCheckOutcome = RuntimeCheckOutcome.FAIL
    permission_result: RuntimeCheckOutcome = RuntimeCheckOutcome.FAIL
    scope_result: RuntimeCheckOutcome = RuntimeCheckOutcome.FAIL
    tool_result: RuntimeCheckOutcome = RuntimeCheckOutcome.FAIL
    timestamp: str = ""
    source: str = ""
    org_id: str = ""
    checked_by: str = ""    # 核查发起方 id（事实，通常为 ai）
    note: str = ""          # 中性事实说明（不得含批准/处置语义）

    def __post_init__(self) -> None:
        for name in (
            "policy_result",
            "permission_result",
            "scope_result",
            "tool_result",
        ):
            value = getattr(self, name)
            if not isinstance(value, RuntimeCheckOutcome):
                setattr(self, name, RuntimeCheckOutcome(value))
        if not str(self.source).strip():
            raise EnterpriseRedLineViolationError(
                f"RuntimeDecisionRecord {self.record_id!r} 缺少 source："
                f"禁止落库无源的运行时判定记录（红线⑥：事实必须可溯源）"
            )

    @property
    def all_checks_passed(self) -> bool:
        """四项核查是否全部通过（**事实汇总，不等于批准**，红线③）。

        即便为 True，也仅表示「核查未发现不符」，运行放行仍须由真实人工/外部
        运行时依据自身职责决定；本层不授予、不代替任何运行许可。
        """
        return all(
            r is RuntimeCheckOutcome.PASS
            for r in (
                self.policy_result,
                self.permission_result,
                self.scope_result,
                self.tool_result,
            )
        )

    def summary(self) -> str:
        """只读汇总核查事实（不改动任何状态）。"""
        return (
            f"agent={self.agent_id};policy={self.policy_result.value};"
            f"permission={self.permission_result.value};"
            f"scope={self.scope_result.value};tool={self.tool_result.value};"
            f"source={self.source}"
        )


class AgentExecutionGuard(_RedLineForbiddenMixin):
    """Agent 执行前置核查器（任务3）。

    只提供三类**核查**能力：``check_policy`` / ``check_permission`` / ``check_scope``
    （外加工具访问核查 ``check_tool_access``）。

    红线（fail-closed）：
    - **只检查，不自动批准**（红线③）：所有方法返回 ``RuntimeCheckOutcome`` 事实，
      不返回「已批准/可运行」结论，也不触发任何执行。
    - **不修改策略**（红线④）：Guard 只读策略，不写、不激活、不弃用。
    - **不放行工具**（红线⑤）：工具核查依赖 ``AgentToolAccessPolicy`` 默认拒绝语义。
    - 不持有 approve / allow_execution / grant_execution / auto_update_policy 等方法。
    """

    _FORBIDDEN = _RUNTIME_FORBIDDEN

    def __init__(
        self,
        org_id: str = "",
        identity: "IdentityService | None" = None,
        permission_policy: "AgentPermissionPolicy | None" = None,
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "AgentExecutionGuard（红线①）"
            )
        self._org_id = org_id
        self._identity = identity
        self._permission_policy = permission_policy

    # ---- 策略核查（只读，默认拒绝）----

    def check_policy(
        self,
        *,
        agent_id: str,
        policies: "List[AgentRuntimePolicy]",
        requested_rules: "List[str] | None" = None,
    ) -> RuntimeCheckOutcome:
        """核查是否存在覆盖请求规则的**生效**策略（默认拒绝，红线③/④）。

        判定事实：
        - 无 agent_id → FAIL；
        - 该 agent 无 ACTIVE 策略 → FAIL（草稿/弃用策略一律不算数）；
        - 请求规则中存在任何一条未被生效策略显式声明 → FAIL；
        - 未声明请求规则时，仅要求存在生效策略即 PASS（不推断规则内容）。
        """
        if not agent_id:
            return RuntimeCheckOutcome.FAIL
        active = [
            p
            for p in (policies or [])
            if p.agent_id == agent_id and p.is_effective
        ]
        if not active:
            return RuntimeCheckOutcome.FAIL
        rules = [r for r in (requested_rules or []) if str(r).strip()]
        if not rules:
            return RuntimeCheckOutcome.PASS
        for rule in rules:
            if not any(p.covers_rule(rule) for p in active):
                return RuntimeCheckOutcome.FAIL
        return RuntimeCheckOutcome.PASS

    # ---- 权限核查（接入身份层 + AgentPermissionPolicy，默认拒绝）----

    def check_permission(
        self,
        *,
        user: object,
        resource_category: str = "tool",
        required_permission: "Permission | None" = None,
    ) -> RuntimeCheckOutcome:
        """核查发起方是否具备运行相关资源访问权限（默认拒绝，红线⑥）。

        - 优先走 ``AgentPermissionPolicy.check_agent_access``（角色作用域 + 身份层双重校验）；
        - 无策略实例时退回 ``IdentityService.check``；
        - 两者皆无 → FAIL（无从校验即拒绝，绝不默认放行）。
        """
        if user is None:
            return RuntimeCheckOutcome.FAIL
        permission = required_permission or Permission.READ_RESOURCE
        if self._permission_policy is not None:
            try:
                allowed = self._permission_policy.check_agent_access(
                    user=user,
                    resource_category=resource_category,
                    required_permission=permission,
                )
            except Exception:
                return RuntimeCheckOutcome.FAIL
            return (
                RuntimeCheckOutcome.PASS if allowed else RuntimeCheckOutcome.FAIL
            )
        if self._identity is not None:
            try:
                allowed = bool(
                    hasattr(user, "role") and self._identity.check(user, permission)
                )
            except Exception:
                return RuntimeCheckOutcome.FAIL
            return (
                RuntimeCheckOutcome.PASS if allowed else RuntimeCheckOutcome.FAIL
            )
        return RuntimeCheckOutcome.FAIL

    # ---- 作用域核查（只读，默认拒绝）----

    def check_scope(
        self,
        *,
        agent_id: str,
        policies: "List[AgentRuntimePolicy]",
        requested_scope: str = "",
    ) -> RuntimeCheckOutcome:
        """核查请求作用域是否落在生效策略声明范围内（默认拒绝，红线③）。

        - 无 agent_id / 无请求作用域 → FAIL（未声明即拒绝）；
        - 无 ACTIVE 策略 → FAIL；
        - 请求作用域未被任一生效策略显式声明 → FAIL。
        """
        if not agent_id or not str(requested_scope).strip():
            return RuntimeCheckOutcome.FAIL
        active = [
            p
            for p in (policies or [])
            if p.agent_id == agent_id and p.is_effective
        ]
        if not active:
            return RuntimeCheckOutcome.FAIL
        return (
            RuntimeCheckOutcome.PASS
            if any(p.covers_scope(requested_scope) for p in active)
            else RuntimeCheckOutcome.FAIL
        )

    # ---- 工具访问核查（只读，默认拒绝）----

    def check_tool_access(
        self,
        *,
        agent_id: str,
        tool_name: str,
        tool_policies: "List[AgentToolAccessPolicy]",
    ) -> RuntimeCheckOutcome:
        """核查工具访问是否被显式允许（**默认拒绝**，红线⑤）。

        无策略、无工具名、命中 denied、不在 allowed → 一律 FAIL。
        本方法**绝不**放行工具，只如实返回核查结论。
        """
        if not agent_id or not str(tool_name).strip():
            return RuntimeCheckOutcome.FAIL
        scoped = [p for p in (tool_policies or []) if p.agent_id == agent_id]
        if not scoped:
            return RuntimeCheckOutcome.FAIL
        # 显式拒绝优先：任一策略拒绝即整体拒绝。
        for policy in scoped:
            if tool_name.strip() in policy.denied_tools:
                return RuntimeCheckOutcome.FAIL
        return (
            RuntimeCheckOutcome.PASS
            if any(p.is_tool_allowed(tool_name) for p in scoped)
            else RuntimeCheckOutcome.FAIL
        )


class AgentRuntimeGovernanceService(_RedLineForbiddenMixin):
    """Agent 策略与运行时治理聚合服务（任务1–6 统一入口）。

    承载：运行策略登记 / 人工确认生效 / 人工弃用 / 工具访问策略登记 /
    工具访问核查 / 运行时前置核查与事实记录 / 只读查询。

    红线（fail-closed）：
    - 构造/写路径断言 ``safety_invariants_ok()``（红线①）。
    - 策略状态推进（生效/弃用）强制 ``require_human_actor(USER)``（红线④/⑥），
      AI 无论如何都无法激活策略。
    - 核查只产出事实结论与 ``RuntimeDecisionRecord``，**不批准运行**（红线③）。
    - 工具访问默认拒绝，服务层不提供任何放行入口（红线⑤）。
    - 读路径经 ``AgentPermissionPolicy.check_agent_access``（默认拒绝，红线⑥）。
    - 不持有 approve / engineering_approved / quote / pricing / sign / authorize /
      record_human_approval / auto_update_policy / auto_apply_policy /
      auto_approve_policy / allow_execution / grant_tool_access 等方法。
    """

    _FORBIDDEN = _RUNTIME_FORBIDDEN

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
                "AgentRuntimeGovernanceService（红线①）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy
        self._guard = AgentExecutionGuard(
            org_id=org_id, identity=identity, permission_policy=permission_policy
        )
        self._policies: Dict[str, AgentRuntimePolicy] = {}
        self._tool_policies: Dict[str, AgentToolAccessPolicy] = {}
        self._decisions: Dict[str, RuntimeDecisionRecord] = {}

    @property
    def guard(self) -> AgentExecutionGuard:
        """只读暴露执行前置核查器（只检查，不批准）。"""
        return self._guard

    # ------------------------------------------------------------------
    # 权限隔离（读路径，默认拒绝）
    # ------------------------------------------------------------------

    def _ensure_access(self, *, user: object, resource_category: str = "data") -> None:
        """运行治理数据读取权限校验（**默认拒绝**，任务6）。

        结合 AgentPermissionPolicy：角色须在该资源类别作用域内，且若声明了读权限须经
        IdentityService 校验。任一不过即抛隔离错误（红线⑥：治理数据受控访问）。
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
                    f"用户角色无权限访问 Agent 运行策略与治理数据"
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
    # 运行策略（登记 = AI 可做；生效/弃用 = 仅人工）
    # ------------------------------------------------------------------

    def register_runtime_policy(
        self,
        *,
        policy: AgentRuntimePolicy,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentRuntimePolicy:
        """登记一条运行策略草稿（只登记事实，**不生效**，红线④）。

        登记后策略仍为 ``DRAFT``（模型层已禁止构造期落 ACTIVE），必须由真实人工
        调用 ``confirm_policy_active`` 才会生效。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记运行策略（红线①）"
            )
        if policy.status is AgentRuntimePolicyStatus.ACTIVE:
            raise EnterpriseRedLineViolationError(
                f"register_runtime_policy 拒绝直接登记 ACTIVE 策略 {policy.policy_id!r}："
                f"策略生效必须由真实人工确认（红线④/⑥）"
            )
        policy.org_id = self._org_id
        self._policies[policy.policy_id] = policy
        if self._audit is not None:
            self._audit.record_agent_policy_action(
                record_id=f"agent-policy-{policy.policy_id}",
                actor_id=actor_id,
                action="register_agent_runtime_policy",
                target=policy.agent_id,
                detail=(
                    f"policy_id={policy.policy_id};status={policy.status.value};"
                    f"rules={'|'.join(policy.rules)};scope={'|'.join(policy.scope)}"
                ),
                ts=policy.created_at,
                actor_kind=actor_kind,
            )
        return policy

    def confirm_policy_active(
        self,
        *,
        policy_id: str,
        actor_kind: Any,
        actor_id: str,
        activated_at: str = "",
    ) -> AgentRuntimePolicy:
        """人工确认某运行策略生效（**必须真实 USER**，红线④/⑥）。

        ``require_human_actor(actor_kind)`` 强制：AI（actor_kind=ai/system/None）
        调用必抛 ``EnterpriseRedLineViolationError``。仅 ``DRAFT`` 可推进为 ``ACTIVE``；
        已弃用策略不可复活（须重新登记新策略）。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下确认策略生效（红线①）"
            )
        policy = self._policies.get(policy_id)
        if policy is None:
            raise EnterpriseRedLineViolationError(
                f"confirm_policy_active 找不到策略 {policy_id!r}：禁止凭空生效（红线④）"
            )
        if policy.status is not AgentRuntimePolicyStatus.DRAFT:
            raise EnterpriseRedLineViolationError(
                f"策略 {policy_id!r} 当前状态为 {policy.status.value}，"
                f"仅 draft 可由人工确认生效（红线④）"
            )
        if not str(actor_id).strip():
            raise EnterpriseRedLineViolationError(
                "confirm_policy_active 必须提供真实 actor_id（红线⑥：人工责任可追溯）"
            )
        policy.status = AgentRuntimePolicyStatus.ACTIVE
        policy.activated_by = actor_id
        policy.activated_at = activated_at
        if self._audit is not None:
            self._audit.record_agent_policy_action(
                record_id=f"agent-policy-active-{policy_id}",
                actor_id=actor_id,
                action="confirm_agent_runtime_policy_active",
                target=policy.agent_id,
                detail=(
                    f"policy_id={policy_id};status=active;"
                    f"activated_by={actor_id};activated_at={activated_at}"
                ),
                ts=activated_at,
                actor_kind=AuditActorKind.USER,
            )
        return policy

    def confirm_policy_deprecated(
        self,
        *,
        policy_id: str,
        actor_kind: Any,
        actor_id: str,
        deprecated_at: str = "",
        reason: str = "",
    ) -> AgentRuntimePolicy:
        """人工确认某运行策略弃用（**必须真实 USER**，红线④/⑥）。

        AI 不得自动弃用策略（等同于自动修改策略）。弃用为终态。
        """
        require_human_actor(actor_kind)
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下确认策略弃用（红线①）"
            )
        policy = self._policies.get(policy_id)
        if policy is None:
            raise EnterpriseRedLineViolationError(
                f"confirm_policy_deprecated 找不到策略 {policy_id!r}（红线④）"
            )
        if policy.status is AgentRuntimePolicyStatus.DEPRECATED:
            raise EnterpriseRedLineViolationError(
                f"策略 {policy_id!r} 已是 deprecated 终态，不可重复弃用（红线④）"
            )
        policy.status = AgentRuntimePolicyStatus.DEPRECATED
        if self._audit is not None:
            self._audit.record_agent_policy_action(
                record_id=f"agent-policy-deprecated-{policy_id}",
                actor_id=actor_id,
                action="confirm_agent_runtime_policy_deprecated",
                target=policy.agent_id,
                detail=f"policy_id={policy_id};status=deprecated;reason={reason}",
                ts=deprecated_at,
                actor_kind=AuditActorKind.USER,
            )
        return policy

    # ------------------------------------------------------------------
    # 工具访问策略（登记 + 核查，默认拒绝）
    # ------------------------------------------------------------------

    def register_tool_access_policy(
        self,
        *,
        policy: AgentToolAccessPolicy,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
    ) -> AgentToolAccessPolicy:
        """登记一条工具访问策略（白名单来自人工声明，AI 不自行扩权，红线⑤）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记工具访问策略（红线①）"
            )
        policy.org_id = self._org_id
        self._tool_policies[policy.policy_id] = policy
        if self._audit is not None:
            self._audit.record_agent_tool_access_action(
                record_id=f"agent-tool-policy-{policy.policy_id}",
                actor_id=actor_id,
                action="register_agent_tool_access_policy",
                target=policy.agent_id,
                detail=(
                    f"policy_id={policy.policy_id};"
                    f"allowed={'|'.join(policy.allowed_tools)};"
                    f"denied={'|'.join(policy.denied_tools)}"
                ),
                ts=policy.created_at,
                actor_kind=actor_kind,
            )
        return policy

    def check_tool_access(
        self,
        *,
        agent_id: str,
        tool_name: str,
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
        ts: str = "",
    ) -> RuntimeCheckOutcome:
        """核查某 Agent 是否被显式允许访问某工具（**默认拒绝**，红线⑤）。

        只返回核查事实结论，**不放行**工具；结论如实写入 ``AGENT_TOOL_ACCESS`` 审计。
        """
        scoped = [
            p for p in self._tool_policies.values() if p.org_id == self._org_id
        ]
        outcome = self._guard.check_tool_access(
            agent_id=agent_id, tool_name=tool_name, tool_policies=scoped
        )
        if self._audit is not None:
            self._audit.record_agent_tool_access_action(
                record_id=f"agent-tool-check-{agent_id}-{tool_name}-{ts or 'na'}",
                actor_id=actor_id,
                action="check_agent_tool_access",
                target=agent_id,
                detail=f"tool={tool_name};outcome={outcome.value}",
                ts=ts,
                actor_kind=actor_kind,
            )
        return outcome

    # ------------------------------------------------------------------
    # 运行时前置核查（只检查，不批准）
    # ------------------------------------------------------------------

    def run_execution_check(
        self,
        *,
        record_id: str,
        agent_id: str,
        user: object,
        requested_rules: "List[str] | None" = None,
        requested_scope: str = "",
        tool_name: str = "",
        resource_category: str = "tool",
        timestamp: str = "",
        actor_id: str = "ai",
        actor_kind: "Any | None" = None,
        note: str = "",
    ) -> RuntimeDecisionRecord:
        """执行运行前四项核查并落一条事实记录（**只检查，不批准**，红线③）。

        四项核查：策略（check_policy）/ 权限（check_permission）/ 作用域（check_scope）/
        工具（check_tool_access）。任何一项缺依据一律 FAIL（fail-closed）。

        返回的 ``RuntimeDecisionRecord`` 仅陈述核查事实，**不构成运行批准**：
        即便四项全 PASS，是否真正放行仍由外部运行时与真实管理责任人决定。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行运行时核查（红线①）"
            )
        scoped_policies = [
            p for p in self._policies.values() if p.org_id == self._org_id
        ]
        scoped_tool_policies = [
            p for p in self._tool_policies.values() if p.org_id == self._org_id
        ]
        policy_result = self._guard.check_policy(
            agent_id=agent_id,
            policies=scoped_policies,
            requested_rules=requested_rules,
        )
        permission_result = self._guard.check_permission(
            user=user, resource_category=resource_category
        )
        scope_result = self._guard.check_scope(
            agent_id=agent_id,
            policies=scoped_policies,
            requested_scope=requested_scope,
        )
        tool_result = self._guard.check_tool_access(
            agent_id=agent_id,
            tool_name=tool_name,
            tool_policies=scoped_tool_policies,
        )
        # source 只描述本次实际查阅的事实依据，不编造来源（红线⑥）。
        consulted_policies = [
            p.policy_id for p in scoped_policies if p.agent_id == agent_id
        ] or ["no_policy"]
        consulted_tools = [
            p.policy_id for p in scoped_tool_policies if p.agent_id == agent_id
        ] or ["no_tool_policy"]
        source = (
            f"runtime_policies={','.join(consulted_policies)};"
            f"tool_policies={','.join(consulted_tools)}"
        )
        record = RuntimeDecisionRecord(
            record_id=record_id,
            agent_id=agent_id,
            policy_result=policy_result,
            permission_result=permission_result,
            scope_result=scope_result,
            tool_result=tool_result,
            timestamp=timestamp,
            source=source,
            org_id=self._org_id,
            checked_by=actor_id,
            note=note,
        )
        self._decisions[record_id] = record
        if self._audit is not None:
            self._audit.record_agent_runtime_check_action(
                record_id=f"agent-runtime-check-{record_id}",
                actor_id=actor_id,
                action="run_agent_runtime_check",
                target=agent_id,
                detail=record.summary(),
                ts=timestamp,
                actor_kind=actor_kind,
            )
        return record

    # ------------------------------------------------------------------
    # 只读查询（权限隔离，默认拒绝）
    # ------------------------------------------------------------------

    def list_runtime_policies(
        self,
        *,
        user: object,
        agent_id: str = "",
        status: "AgentRuntimePolicyStatus | None" = None,
        resource_category: str = "data",
    ) -> "List[AgentRuntimePolicy]":
        """列出当前组织下运行策略（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [p for p in self._policies.values() if p.org_id == self._org_id]
        if agent_id:
            out = [p for p in out if p.agent_id == agent_id]
        if status is not None:
            out = [p for p in out if p.status is status]
        return out

    def list_tool_access_policies(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[AgentToolAccessPolicy]":
        """列出当前组织下工具访问策略（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [p for p in self._tool_policies.values() if p.org_id == self._org_id]
        if agent_id:
            out = [p for p in out if p.agent_id == agent_id]
        return out

    def list_decision_records(
        self,
        *,
        user: object,
        agent_id: str = "",
        resource_category: str = "data",
    ) -> "List[RuntimeDecisionRecord]":
        """列出当前组织下运行时判定事实记录（权限隔离，默认拒绝）。"""
        self._ensure_access(user=user, resource_category=resource_category)
        out = [r for r in self._decisions.values() if r.org_id == self._org_id]
        if agent_id:
            out = [r for r in out if r.agent_id == agent_id]
        return out


__all__ = [
    "AgentRuntimePolicyStatus",
    "RuntimeCheckOutcome",
    "AgentRuntimePolicy",
    "AgentToolAccessPolicy",
    "RuntimeDecisionRecord",
    "AgentExecutionGuard",
    "AgentRuntimeGovernanceService",
    "_RUNTIME_FORBIDDEN",
]
