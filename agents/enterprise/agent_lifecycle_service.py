"""Enterprise Agent Capability Registry & Governance Layer —— 智能体生命周期治理（任务5，Phase 3.8.13）。

新增：``AgentLifecycleService``，提供 register() / submit_review() / activate() / deprecate()
及 invocation 审计（AGENT_EXECUTION）。

红线（fail-closed，复用 3.8.0 基座 + 3.8.13 语义）：
- 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- **activate() / deprecate() 必须由真实 USER 执行**（``require_human_actor``，红线⑥）：
  AI 不得把智能体激活为 active / 弃用（对应任务1「active必须人工确认」）。
- 不持有 ``approve`` / ``engineering_approved`` / ``quote`` / ``pricing`` / ``sign`` /
  ``authorize`` / ``record_human_approval`` / ``auto_activate`` / ``publish`` / ``apply`` 等
  方法（红线②/③/④/⑥）。
- 注册/激活仅维护智能体元数据与状态流转，**绝不**写入任何运行态/知识资产（red line ③）；
  智能体 active 后的实际调用与落地须由真实人工在运行侧发起。
- 调用审计（``record_invocation``）如实标注 actor；Agent 访问资源受 ``AgentPermissionPolicy``
  约束（默认拒绝，红线③/⑥）。
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.enterprise.agent_capability import AgentCapability
from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.agent_registry import AgentRegistry, AgentStatus
from agents.enterprise.agent_version import AgentVersionManager, AgentVersionStatus
from agents.enterprise.audit import (
    AuditActorKind,
    AuditService,
    require_human_actor,
)
from agents.enterprise.identity import IdentityService, Permission, RoleKind
from agents.enterprise.knowledge_visibility import KnowledgeVisibilityPolicy
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class AgentLifecycleService(_RedLineForbiddenMixin):
    """智能体生命周期治理服务（任务5）。

    提供 register / submit_review / activate / deprecate；跨域访问抛 ``EnterpriseIsolationError``；
    写路径断言 ``safety_invariants_ok()``（红线①/⑤）。activate / deprecate 必须由真实 USER 执行
    （红线⑥）。Agent 调用审计经 ``AuditService``（AGENT_EXECUTION）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_activate",
        "apply",
        "publish",
        "write",
        "decide",
        "recommend",
        "auto_execute",
    )

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
                "AgentLifecycleService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._identity = identity
        self._visibility = visibility
        self._permission_policy = permission_policy or AgentPermissionPolicy(
            org_id=org_id, identity=identity
        )
        self._version_manager = AgentVersionManager(
            org_id=org_id, audit=audit, identity=identity
        )
        self._agents: Dict[str, AgentRegistry] = {}
        self._capabilities: Dict[str, AgentCapability] = {}  # capability_id -> AgentCapability
        self._agent_capabilities: Dict[str, List[str]] = {}  # agent_id -> [capability_id]

    def register(
        self,
        *,
        agent_id: str,
        name: str,
        agent_type: str,
        capabilities: List[AgentCapability],
        owner: str,
        version: str = "0.1.0",
        created_at: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
    ) -> AgentRegistry:
        """注册一个智能体（默认 AI 注册，状态恒为 DRAFT，待人工复核与激活）。

        登记 AgentRegistry(status=DRAFT) + 各 AgentCapability + 首条 AgentVersion(DRAFT)。
        如实记录 AGENT_REGISTER 审计（actor 默认 AI，红线⑥）。本方法**只**登记元数据，
        不写入任何运行态/知识资产（red line ③）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下注册智能体（红线①/⑤）"
            )
        if agent_id in self._agents:
            raise ValueError(f"智能体 {agent_id!r} 已注册")
        reg = AgentRegistry(
            agent_id=agent_id,
            name=name,
            type=agent_type,
            version=version,
            capabilities=[c.capability_id for c in capabilities],
            status=AgentStatus.DRAFT,
            owner=owner,
            org_id=self._org_id,
            created_at=created_at,
        )
        self._agents[agent_id] = reg
        # 登记能力声明
        for cap in capabilities:
            self._capabilities[cap.capability_id] = cap
            self._agent_capabilities.setdefault(agent_id, []).append(cap.capability_id)
        # 首条版本
        self._version_manager.create_version(
            version_id=f"{agent_id}@v1",
            agent_id=agent_id,
            change_log=f"initial registration of {name!r} (type={agent_type})",
            created_by=actor_id,
            created_at=created_at,
            actor_id=actor_id,
            actor_kind=actor_kind,
        )
        if self._audit is not None:
            self._audit.record_agent_register_action(
                record_id=f"agent-register-{agent_id}",
                actor_id=actor_id,
                action="register_agent",
                target=agent_id,
                detail=(
                    f"name={name};type={agent_type};version={version};"
                    f"owner={owner};capabilities={len(capabilities)}"
                ),
                ts=created_at,
                actor_kind=actor_kind,
            )
        return reg

    def submit_review(
        self,
        *,
        agent_id: str,
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
        ts: str = "",
    ) -> AgentRegistry:
        """将智能体从 DRAFT 转入 REVIEWING（提交人工复核）。

        非权威状态流转：仅「标记待审」，仍须人工 ``activate`` 才能 active（红线⑥）。
        AI 可提交以供复核，但不得代行激活。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交智能体复核（红线①/⑤）"
            )
        reg = self._get_scoped(agent_id)
        if reg.status != AgentStatus.DRAFT:
            raise ValueError(
                f"智能体 {agent_id!r} 当前状态为 {reg.status.value!r}，"
                f"仅 DRAFT 可提交复核"
            )
        reg.status = AgentStatus.REVIEWING
        # 同步提交最新版本复核
        v = self._version_manager.latest_version(agent_id=agent_id)
        if v is not None and v.status == AgentVersionStatus.DRAFT:
            self._version_manager.submit_review(
                version_id=v.version_id, actor_id=actor_id, actor_kind=actor_kind, ts=ts
            )
        if self._audit is not None:
            self._audit.record_agent_register_action(
                record_id=f"agent-review-{agent_id}",
                actor_id=actor_id,
                action="submit_agent_review",
                target=agent_id,
                detail="status=reviewing",
                ts=ts,
                actor_kind=actor_kind,
            )
        return reg

    def activate(
        self,
        *,
        agent_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
    ) -> AgentRegistry:
        """激活智能体为 ACTIVE —— **必须由真实 USER 执行**（红线⑥）。

        AI 不得激活（``require_human_actor`` 守卫）。仅 REVIEWING 状态可激活；激活后如实记录
        AGENT_REGISTER 审计（actor_kind 强制 USER），并同步激活对应版本。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下激活智能体（红线①/⑤）"
            )
        # 红线⑥：激活是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        reg = self._get_scoped(agent_id)
        if reg.status != AgentStatus.REVIEWING:
            raise ValueError(
                f"智能体 {agent_id!r} 当前状态为 {reg.status.value!r}，"
                f"仅 REVIEWING 可被人工激活"
            )
        reg.status = AgentStatus.ACTIVE
        # 同步激活对应版本（版本自身也须真实 USER，actor_kind 已为 USER）
        v = self._version_manager.latest_version(agent_id=agent_id)
        if v is not None and v.status == AgentVersionStatus.REVIEWING:
            self._version_manager.activate_version(
                version_id=v.version_id,
                actor_id=actor_id,
                actor_kind=actor_kind,
                ts=ts,
            )
        if self._audit is not None:
            self._audit.record_agent_register_action(
                record_id=f"agent-activate-{agent_id}",
                actor_id=actor_id,
                action="activate_agent",
                target=agent_id,
                detail="status=active",
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )
        return reg

    def deprecate(
        self,
        *,
        agent_id: str,
        actor_id: str,
        actor_kind: Any,
        ts: str = "",
    ) -> AgentRegistry:
        """弃用智能体为 DEPRECATED —— **必须由真实 USER 执行**（红线⑥）。

        弃用是权威性状态变更（让智能体退出可用集），AI 不得代行。仅 ACTIVE / REVIEWING
        可被人工弃用；弃用后如实记录 AGENT_REGISTER 审计（actor_kind 强制 USER）。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下弃用智能体（红线①/⑤）"
            )
        # 红线⑥：弃用是权威状态变更，必须由真实人工发起。
        require_human_actor(actor_kind)
        reg = self._get_scoped(agent_id)
        if reg.status in (AgentStatus.DRAFT, AgentStatus.DEPRECATED):
            raise ValueError(
                f"智能体 {agent_id!r} 当前状态为 {reg.status.value!r}，"
                f"仅 ACTIVE/REVIEWING 可被人工弃用"
            )
        reg.status = AgentStatus.DEPRECATED
        if self._audit is not None:
            self._audit.record_agent_register_action(
                record_id=f"agent-deprecate-{agent_id}",
                actor_id=actor_id,
                action="deprecate_agent",
                target=agent_id,
                detail="status=deprecated",
                ts=ts,
                actor_kind=AuditActorKind.USER,
            )
        return reg

    def record_invocation(
        self,
        *,
        agent_id: str,
        capability_id: str,
        user: object,
        resource_category: str = "",
        actor_id: str = "ai",
        actor_kind: "str | None" = None,
        detail: str = "",
        ts: str = "",
    ) -> None:
        """记录一次 Agent 调用（AGENT_EXECUTION）。

        调用前检查 ``AgentPermissionPolicy``（默认拒绝）：若 Agent 试图访问超出其角色/权限范围的
        资源类别，则抛 ``EnterpriseRedLineViolationError`` 并（若提供了 audit）记录一次被拒调用
        （红线③/⑥）。调用事实如实记录（actor 真实）；本方法**不**执行任何 Agent 动作、不写知识资产。

        约束：仅 ACTIVE 智能体可被调用；``capability_id`` 必须属于该智能体。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下记录智能体调用（红线①/⑤）"
            )
        reg = self._get_scoped(agent_id)
        if reg.status != AgentStatus.ACTIVE:
            raise ValueError(
                f"智能体 {agent_id!r} 未激活（当前 {reg.status.value!r}），不得调用"
            )
        if capability_id not in self._agent_capabilities.get(agent_id, []):
            raise ValueError(f"能力 {capability_id!r} 不属于智能体 {agent_id!r}")
        # 默认拒绝：资源类别访问须过权限策略
        if resource_category:
            if not self._permission_policy.check_agent_access(
                user=user, resource_category=resource_category
            ):
                if self._audit is not None:
                    self._audit.record_agent_execution_action(
                        record_id=f"agent-exec-denied-{agent_id}-{capability_id}",
                        actor_id=actor_id,
                        action="invoke_agent_denied",
                        target=agent_id,
                        detail=(
                            f"capability_id={capability_id};"
                            f"resource_category={resource_category};denied=true"
                        ),
                        ts=ts,
                        actor_kind=actor_kind,
                    )
                raise EnterpriseRedLineViolationError(
                    f"Agent {agent_id!r} 访问资源类别 {resource_category!r} "
                    f"被权限策略拒绝（默认拒绝，红线③/⑥）"
                )
        if self._audit is not None:
            self._audit.record_agent_execution_action(
                record_id=f"agent-exec-{agent_id}-{capability_id}",
                actor_id=actor_id,
                action="invoke_agent",
                target=agent_id,
                detail=(
                    f"capability_id={capability_id};"
                    f"resource_category={resource_category};{detail}"
                ),
                ts=ts,
                actor_kind=actor_kind,
            )

    # ---- 只读查询 / 辅助 ----

    def get(self, *, agent_id: str) -> AgentRegistry:
        """按组织作用域读取智能体（跨域访问抛隔离错误）。"""
        return self._get_scoped(agent_id)

    def list_agents(
        self,
        *,
        status: "AgentStatus | None" = None,
    ) -> List[AgentRegistry]:
        """列出当前组织下智能体（可按 status 过滤）。"""
        out = [a for a in self._agents.values() if a.org_id == self._org_id]
        if status is not None:
            out = [a for a in out if a.status == status]
        return out

    def get_capability(self, *, capability_id: str) -> AgentCapability:
        """按组织作用域读取能力声明（跨域访问抛隔离错误）。"""
        cap = self._capabilities.get(capability_id)
        if cap is None:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(f"能力 {capability_id!r} 不存在")
        if cap.agent_id not in self._agents or self._agents[cap.agent_id].org_id != self._org_id:
            from agents.enterprise.organization import EnterpriseIsolationError

            raise EnterpriseIsolationError(
                f"能力 {capability_id!r} 归属组织与当前组织 {self._org_id!r} 不一致，"
                f"禁止跨域访问"
            )
        return cap

    def list_capabilities(self, *, agent_id: str) -> List[AgentCapability]:
        """列出某智能体全部能力声明。"""
        ids = self._agent_capabilities.get(agent_id, [])
        return [self._capabilities[cid] for cid in ids if cid in self._capabilities]

    @property
    def version_manager(self) -> AgentVersionManager:
        """暴露版本管理器（供测试/审计追溯）。"""
        return self._version_manager

    def _get_scoped(self, agent_id: str) -> AgentRegistry:
        from agents.enterprise.organization import EnterpriseIsolationError

        reg = self._agents.get(agent_id)
        if reg is None:
            raise EnterpriseIsolationError(f"智能体 {agent_id!r} 不存在")
        if reg.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"智能体 {agent_id!r} 归属组织 {reg.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return reg


__all__ = ["AgentLifecycleService"]
