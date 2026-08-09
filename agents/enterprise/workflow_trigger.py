"""Enterprise Operation Layer —— 自动触发规则（任务3，Phase 3.8.3）。

新增：``WorkflowTriggerRule``，支持事件触发 project_created / file_uploaded / task_completed。

最高红线加固（红线③，fail-closed）：**只触发流程，不触发审批**。
- 事件匹配命中后，``fire`` 仅登记一条「工作流触发事件」并如实写入审计（WORKFLOW_EVENT），
  标记该模板流程进入「待人工执行 / pending」状态；**绝不**代人工审批、代签、代确认。
- 服务继承 ``_RedLineForbiddenMixin``，forbidden 集合在红线②/④/⑥基础上**额外**拦截
  ``auto_approve`` / ``auto_sign_off`` / ``confirm`` / ``trigger_approval`` 等，从结构上
  杜绝「自动触发审批」能力（红线③）。系统**不提供**任何 approve / confirm 入口。

隔离与红线约束（复用 3.8.0~3.8.2 基座）：
- 所有规则按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- ``WorkflowTriggerService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 可选联动 ``AuditService.record_workflow_event`` 如实标注动作发起方（actor 真实）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class WorkflowTriggerEventType(str, Enum):
    """可触发工作流的事件类型（红线③：仅触发，不审批）。"""

    PROJECT_CREATED = "project_created"
    FILE_UPLOADED = "file_uploaded"
    TASK_COMPLETED = "task_completed"


@dataclass
class WorkflowTriggerRule:
    """工作流自动触发规则（任务3）。

    仅描述「当某事件发生时，启动某个模板流程」；**不**包含任何审批动作。
    """

    rule_id: str
    org_id: str
    template_id: str
    event_type: WorkflowTriggerEventType
    enabled: bool = True
    created_by: str = ""
    created_at: str = ""


@dataclass
class WorkflowTriggerEvent:
    """一次触发产生的事件记录（只触发流程，不触发审批）。

    ``status`` 恒为 PENDING（待真实人工执行），系统**不**自动推进到 approved。
    """

    event_id: str
    org_id: str
    rule_id: str
    template_id: str
    event_type: WorkflowTriggerEventType
    status: str = "pending"  # 常量，不因任何自动逻辑改变为 approved
    context: dict = field(default_factory=dict)
    fired_by: str = "system"
    fired_at: str = ""


class WorkflowTriggerService(_RedLineForbiddenMixin):
    """工作流触发服务（任务3）。

    事件驱动地匹配规则并「触发」流程（登记 pending 事件），**绝不**代人工审批/确认/签署
    （红线③）。构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        "auto_approve",       # 红线③：禁止自动通过
        "auto_sign_off",      # 红线③：禁止自动签核
        "confirm",            # 红线③：禁止自动确认（含确认审批）
        "trigger_approval",   # 红线③：禁止触发审批
        "request_approval",   # 红线③：禁止发起自动审批请求
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "WorkflowTriggerService（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._rules: dict[str, WorkflowTriggerRule] = {}
        self._events: dict[str, WorkflowTriggerEvent] = {}

    def register_rule(
        self,
        *,
        rule_id: str,
        template_id: str,
        event_type: "WorkflowTriggerEventType | str",
        enabled: bool = True,
        created_by: str = "",
        created_at: str = "",
    ) -> WorkflowTriggerRule:
        """登记一条触发规则（仅描述 event -> template 的启动关系，不含审批）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下登记触发规则（红线①/⑤）"
            )
        evt = (
            event_type
            if isinstance(event_type, WorkflowTriggerEventType)
            else WorkflowTriggerEventType(event_type)
        )
        rule = WorkflowTriggerRule(
            rule_id=rule_id,
            org_id=self._org_id,
            template_id=template_id,
            event_type=evt,
            enabled=enabled,
            created_by=created_by,
            created_at=created_at,
        )
        self._rules[rule_id] = rule
        if self._audit is not None:
            self._audit.record_workflow_event(
                record_id=f"trigger-rule-{rule_id}",
                actor_id=created_by or "system",
                action="register_workflow_trigger_rule",
                target=template_id,
                detail=f"event={evt.value};enabled={enabled}",
                ts=created_at,
            )
        return rule

    def evaluate(
        self,
        *,
        event_type: "WorkflowTriggerEventType | str",
        context: dict | None = None,
    ) -> list[WorkflowTriggerRule]:
        """评估某事件应触发哪些规则（只读匹配，不执行任何写动作/不审批）。

        返回当前组织下、匹配该事件且 ``enabled=True`` 的规则列表。
        """
        evt = (
            event_type
            if isinstance(event_type, WorkflowTriggerEventType)
            else WorkflowTriggerEventType(event_type)
        )
        matched = [
            r
            for r in self._rules.values()
            if r.org_id == self._org_id and r.enabled and r.event_type == evt
        ]
        return matched

    def fire(
        self,
        *,
        event_type: "WorkflowTriggerEventType | str",
        event_id: str,
        context: dict | None = None,
        fired_at: str = "",
    ) -> list[WorkflowTriggerEvent]:
        """触发匹配规则对应的工作流（红线③：只触发流程，不触发审批）。

        对每条命中的启用规则，登记一条 ``WorkflowTriggerEvent``（status=pending），
        并如实写入审计（WORKFLOW_EVENT，actor_kind=SYSTEM 标注为自动化触发，但**绝不**
        标注为人工审批）。返回本次产生的触发事件列表。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下触发工作流（红线①/⑤）"
            )
        rules = self.evaluate(event_type=event_type, context=context)
        events: list[WorkflowTriggerEvent] = []
        ctx = dict(context or {})
        for rule in rules:
            ev = WorkflowTriggerEvent(
                event_id=f"{event_id}:{rule.rule_id}",
                org_id=self._org_id,
                rule_id=rule.rule_id,
                template_id=rule.template_id,
                event_type=rule.event_type,
                status="pending",  # 永远 pending；审批须由真实人工线下完成
                context=ctx,
                fired_by="system",
                fired_at=fired_at,
            )
            self._events[ev.event_id] = ev
            events.append(ev)
            if self._audit is not None:
                # 注意：如实标注为 workflow event（自动化触发），**不**是 human approval。
                self._audit.record_workflow_event(
                    record_id=f"trigger-fire-{ev.event_id}",
                    actor_id="system",
                    action="workflow_triggered_pending",
                    target=rule.template_id,
                    detail=(
                        f"event={rule.event_type.value};rule={rule.rule_id};"
                        f"status=pending"
                    ),
                    ts=fired_at,
                )
        return events

    def get_rule(self, *, rule_id: str) -> WorkflowTriggerRule:
        """按组织作用域读取规则（跨域访问抛隔离错误）。"""
        return self._get_scoped_rule(rule_id)

    def list_rules(self, *, event_type: "WorkflowTriggerEventType | str | None" = None) -> list[
        WorkflowTriggerRule
    ]:
        """列出当前组织下规则（可按 event_type 过滤）。"""
        out = [r for r in self._rules.values() if r.org_id == self._org_id]
        if event_type is not None:
            want = (
                event_type
                if isinstance(event_type, WorkflowTriggerEventType)
                else WorkflowTriggerEventType(event_type)
            )
            out = [r for r in out if r.event_type == want]
        return out

    def list_events(self, *, template_id: str = "") -> list[WorkflowTriggerEvent]:
        """列出当前组织下已产生的触发事件（status 恒为 pending，等待真实人工执行）。"""
        out = [e for e in self._events.values() if e.org_id == self._org_id]
        if template_id:
            out = [e for e in out if e.template_id == template_id]
        return out

    def _get_scoped_rule(self, rule_id: str) -> WorkflowTriggerRule:
        from agents.enterprise.organization import EnterpriseIsolationError

        rule = self._rules.get(rule_id)
        if rule is None:
            raise EnterpriseIsolationError(f"触发规则 {rule_id!r} 不存在")
        if rule.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"触发规则 {rule_id!r} 归属组织 {rule.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return rule


__all__ = [
    "WorkflowTriggerEventType",
    "WorkflowTriggerRule",
    "WorkflowTriggerEvent",
    "WorkflowTriggerService",
]
