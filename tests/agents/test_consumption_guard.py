"""Tests for Engineering AI Consumption Enforcement（Phase 3.4 Sprint 3.4.3）。

覆盖：Approved 允许（权威） / Pending 拒绝 / Captured 拒绝 / Deprecated 拒绝 /
Gate 失败拒绝 / 辅助引用须 pending_verification / 审计记录（consumed/blocked）/
严禁 approved 事件 / engineering_enabled 保持 False。

夹具全部使用纯标识符 / 占位签名（KI-1 / SRC-1 / domain-A），不引入任何业务数值，
不写入 verified.json，不创建 ReleaseApproval。
"""

from __future__ import annotations

from agents.config_loader import load_engineering_enabled
from agents.engineering.gate.unified_activation_gate import (
    UnifiedActivationDecision,
    UnifiedActivationGate,
)
from agents.engineering.knowledge.activation.consumer_guard import (
    BLOCKED_EVENT,
    CONSUMED_EVENT,
    EngineeringKnowledgeGuard,
)
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.repository import FORBIDDEN_EVENT_TYPE

_APPROVED = "Engineering_Approved"
_TS = "2026-08-01T00:00:00+00:00"


def make_item(
    *,
    knowledge_id: str = "KI-1",
    validation_status: str = "Pending_Verification",
    content: str = "sample content text",
    domain: str = "domain-A",
    source: str = "SRC-1",
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        knowledge_type="spec",
        parent_knowledge_id=PENDING_PLACEHOLDER,
        title=f"title for {knowledge_id}",
        content=content,
        source=source,
        author="AUTH-1",
        domain=domain,
        content_hash="",
        validation_status=validation_status,
        linked_entities=[],
        created_at=_TS,
        updated_at=_TS,
    )


def _unified(allowed: bool) -> UnifiedActivationDecision:
    return UnifiedActivationDecision(
        allowed=allowed, blocking_reasons=[], domain_results={}, detail=""
    )


class TestConsumptionApprovedAllowed:
    def test_approved_is_permitted_as_authoritative(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status=_APPROVED)
        res = guard.consume_knowledge(item, _unified(allowed=True))
        assert res.permitted is True
        assert res.as_authoritative is True
        assert res.requires_pending_verification is False
        assert res.reason == "consumed"
        # 审计记录为 consumed。
        assert res.event is not None
        assert res.event.event_type == CONSUMED_EVENT

    def test_approved_audit_event_recorded(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status=_APPROVED)
        guard.consume_knowledge(item, _unified(allowed=True))
        events = guard.audit_log.events_for(item.knowledge_id)
        assert len(events) == 1
        assert events[0].event_type == CONSUMED_EVENT


class TestConsumptionPendingRejected:
    def test_pending_is_rejected(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status="Pending_Verification")
        res = guard.consume_knowledge(item, _unified(allowed=True))
        assert res.permitted is False
        assert res.as_authoritative is False
        assert res.reason == "not_citable_forbidden"
        assert res.event.event_type == BLOCKED_EVENT

    def test_pending_blocked_audit_recorded(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status="Pending_Verification")
        guard.consume_knowledge(item, _unified(allowed=True))
        events = guard.audit_log.events_for(item.knowledge_id)
        assert len(events) == 1
        assert events[0].event_type == BLOCKED_EVENT


class TestConsumptionDeprecatedRejected:
    def test_deprecated_is_rejected(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status="Deprecated")
        res = guard.consume_knowledge(item, _unified(allowed=True))
        assert res.permitted is False
        assert res.reason == "not_citable_forbidden"
        assert res.event.event_type == BLOCKED_EVENT

    def test_captured_is_rejected(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status="Captured")
        res = guard.consume_knowledge(item, _unified(allowed=True))
        assert res.permitted is False
        assert res.event.event_type == BLOCKED_EVENT


class TestConsumptionAuxiliaryRequiresPending:
    def test_expert_verified_is_auxiliary_only(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status="Expert_Verified")
        res = guard.consume_knowledge(item, _unified(allowed=True))
        assert res.permitted is True
        assert res.as_authoritative is False
        assert res.requires_pending_verification is True
        assert res.event.event_type == CONSUMED_EVENT


class TestConsumptionGateFailure:
    def test_unified_gate_blocked_rejects_any_knowledge(self) -> None:
        guard = EngineeringKnowledgeGuard()
        # 即便知识是 Approved，统一闸门不允许也整体拒绝。
        item = make_item(validation_status=_APPROVED)
        res = guard.consume_knowledge(item, _unified(allowed=False))
        assert res.permitted is False
        assert res.reason == "unified_gate_blocked"
        assert res.event.event_type == BLOCKED_EVENT

    def test_gate_blocked_does_not_record_consumed(self) -> None:
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status=_APPROVED)
        guard.consume_knowledge(item, _unified(allowed=False))
        events = guard.audit_log.events_for(item.knowledge_id)
        assert events and events[0].event_type == BLOCKED_EVENT


class TestConsumptionNoApprovedEvent:
    def test_no_approved_event_recorded_ever(self) -> None:
        guard = EngineeringKnowledgeGuard()
        for status in (_APPROVED, "Expert_Verified", "Pending_Verification", "Deprecated", "Captured"):
            item = make_item(knowledge_id=f"KI-{status}", validation_status=status)
            guard.consume_knowledge(item, _unified(allowed=True))
            for ev in guard.audit_log.all_events():
                assert ev.event_type != FORBIDDEN_EVENT_TYPE
                assert ev.event_type != "approved"


class TestConsumptionEngineeringEnabledInvariant:
    def test_engineering_enabled_unchanged_after_consume(self) -> None:
        before = load_engineering_enabled()
        guard = EngineeringKnowledgeGuard()
        item = make_item(validation_status=_APPROVED)
        guard.consume_knowledge(item, _unified(allowed=True))
        assert load_engineering_enabled() is before is False

    def test_safety_invariants_ok(self) -> None:
        assert EngineeringKnowledgeGuard.safety_invariants_ok() is True


class TestConsumptionIntegrationPoint:
    def test_engineering_computation_input_hook(self) -> None:
        # 任务3：工程计算入口只读接入点（不修改计算逻辑）。
        gate = UnifiedActivationGate()
        repo = __import__(
            "agents.engineering.knowledge.repository", fromlist=["KnowledgeRepository"]
        ).KnowledgeRepository(store_path=None)
        # 空仓库 → 统一闸门不允许 → 计算入口拒绝。
        dec = gate.evaluate(repo)
        item = make_item(validation_status=_APPROVED)
        res = EngineeringKnowledgeGuard().guard_engineering_computation_input(item, dec)
        assert res.permitted is False
        assert res.reason == "unified_gate_blocked"
