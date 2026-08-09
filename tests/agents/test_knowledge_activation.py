"""Tests for Knowledge Activation Layer（Phase 3.4 Sprint 3.4.1）。

覆盖：Gate fail-closed / 各 G 检查 / Consumption 分类 / ReadBoundary 限制 /
Rollback 链 / engineering_enabled 保持 False / 禁止 approved 事件。

夹具全部使用纯标识符（KI-1 / SRC-1 / domain-A），不引入任何业务数值，
避免触发防编造扫描；不写入 verified.json、不创建 ReleaseApproval。
"""

from __future__ import annotations

import pytest

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.repository import (
    FORBIDDEN_EVENT_TYPE,
    KnowledgeEventLog,
    KnowledgeRepository,
)
from agents.engineering.knowledge.activation.consumption import (
    AUXILIARY_ONLY,
    CITABLE,
    NOT_CITABLE,
    KnowledgeConsumptionPolicy,
)
from agents.engineering.knowledge.activation.gate import (
    ALL_GATES,
    ActivationContext,
    KnowledgeActivationGate,
)
from agents.engineering.knowledge.activation.read_boundary import (
    ALLOWED_KINDS,
    KnowledgeReadBoundary,
)
from agents.engineering.knowledge.activation.rollback import (
    KnowledgeRollbackPolicy,
)

_TS = "2026-08-01T00:00:00+00:00"
_APPROVED = "Engineering_Approved"


def make_item(
    *,
    knowledge_id: str = "KI-1",
    validation_status: str = "Pending_Verification",
    content: str = "sample content text",
    domain: str = "domain-A",
    source: str = "SRC-1",
    parent_knowledge_id: str = PENDING_PLACEHOLDER,
    linked_entities: list[str] | None = None,
) -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        knowledge_type="spec",
        parent_knowledge_id=parent_knowledge_id,
        title=f"title for {knowledge_id}",
        content=content,
        source=source,
        author="AUTH-1",
        domain=domain,
        content_hash="",
        validation_status=validation_status,
        linked_entities=list(linked_entities or []),
        created_at=_TS,
        updated_at=_TS,
    )


def build_approved_repo(dual_sign: bool = True) -> KnowledgeRepository:
    """构造含一个 Engineering_Approved 候选 item 的仓库（可选是否双签）。"""
    repo = KnowledgeRepository(store_path=None)
    item = make_item(
        knowledge_id="KI-APP-1",
        validation_status=_APPROVED,
        content="approved content text",
        domain="domain-A",
        source="SRC-1",
    )
    repo.save(item)  # create 事件（actor=system）
    if dual_sign:
        repo.save(item, actor="expert", event_type="verify")
        repo.save(item, actor="engineer", event_type="verify")
    return repo


# ------------------------------------------------------------------ #
# 任务1：ActivationGate
# ------------------------------------------------------------------ #
class TestActivationGateFailClosed:
    def test_default_is_fail_closed(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        gate = KnowledgeActivationGate()
        dec = gate.can_activate_knowledge(repo)
        assert dec.allowed is False
        assert dec.blocking_reasons  # 必有原因

    def test_all_six_gates_present_in_results(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        gate = KnowledgeActivationGate()
        dec = gate.can_activate_knowledge(repo)
        for g in ALL_GATES:
            assert g in dec.gate_results

    def test_default_blocks_with_g1_g3_g5_g6(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        gate = KnowledgeActivationGate()
        dec = gate.can_activate_knowledge(repo)
        # 默认无候选 -> G1 失败；G3/G5/G6 注入缺失 -> 失败。
        assert any(r.startswith("G1_") for r in dec.blocking_reasons)
        assert any(r.startswith("G3_") for r in dec.blocking_reasons)
        assert any(r.startswith("G5_") for r in dec.blocking_reasons)
        assert any(r.startswith("G6_") for r in dec.blocking_reasons)


class TestActivationGateGreen:
    def test_all_green_allowed(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is True
        assert dec.blocking_reasons == []

    def test_g3_ci_missing_blocks(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=False, rollback_ready=True, authorization_present=True
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert "G3_ci_not_green" in dec.blocking_reasons

    def test_g5_rollback_missing_blocks(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=False, authorization_present=True
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert "G5_rollback_not_ready" in dec.blocking_reasons

    def test_g6_authorization_missing_blocks(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=False
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert "G6_authorization_missing" in dec.blocking_reasons

    def test_g1_no_approved_candidate_blocks(self) -> None:
        # 仓库里只有 Pending 态，无 Engineering_Approved -> G1 失败。
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-P-1", validation_status="Pending_Verification"))
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert any(r.startswith("G1_") for r in dec.blocking_reasons)

    def test_g2_dual_sign_missing_blocks(self) -> None:
        # 有 approved 候选但无双签 verify 事件 -> G2 失败。
        repo = build_approved_repo(dual_sign=False)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert "G2_dual_sign_incomplete" in dec.blocking_reasons

    def test_g2_dual_sign_explicit_injection(self) -> None:
        # 显式注入 dual_sign_present 覆盖推导。
        repo = build_approved_repo(dual_sign=False)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True,
            rollback_ready=True,
            authorization_present=True,
            dual_sign_present=True,
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert any(g == "G2" and v for g, v in dec.gate_results.items())

    def test_g4_audit_chain_missing_verify_blocks(self) -> None:
        # approved 候选仅有 create 事件、无 verify -> G4 失败。
        repo = KnowledgeRepository(store_path=None)
        item = make_item(
            knowledge_id="KI-APP-2", validation_status=_APPROVED,
            content="approved content text two",
        )
        repo.save(item)  # 仅 create 事件
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True,
            dual_sign_present=True,
        )
        dec = gate.can_activate_knowledge(repo, context=ctx)
        assert dec.allowed is False
        assert "G4_audit_chain_incomplete" in dec.blocking_reasons


class TestActivationGateRedLines:
    def test_engineering_enabled_unchanged_after_eval(self) -> None:
        before = load_engineering_enabled()
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True
        )
        gate.can_activate_knowledge(repo, context=ctx)
        after = load_engineering_enabled()
        assert before is False
        assert after is False  # 门禁绝不翻转

    def test_no_approved_event_recorded(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = KnowledgeActivationGate()
        ctx = ActivationContext(
            ci_green=True, rollback_ready=True, authorization_present=True
        )
        gate.can_activate_knowledge(repo, context=ctx)
        for ev in repo.event_log.all_events():
            assert ev.event_type != FORBIDDEN_EVENT_TYPE

    def test_event_log_rejects_approved(self) -> None:
        log = KnowledgeEventLog()
        with pytest.raises(ValueError):
            log.record("KI-1", FORBIDDEN_EVENT_TYPE)

    def test_rejects_non_repository(self) -> None:
        gate = KnowledgeActivationGate()
        dec = gate.can_activate_knowledge(None)  # type: ignore[arg-type]
        assert dec.allowed is False
        assert "G0_repository_required" in dec.blocking_reasons


# ------------------------------------------------------------------ #
# 任务2：ConsumptionPolicy
# ------------------------------------------------------------------ #
class TestConsumptionPolicy:
    def test_approved_is_citable(self) -> None:
        pol = KnowledgeConsumptionPolicy()
        item = make_item(validation_status=_APPROVED)
        assert pol.classify(item) == CITABLE
        assert pol.is_citable(item) is True
        assert pol.requires_pending_verification(item) is False

    @pytest.mark.parametrize(
        "status",
        ["Engineering_Verified", "Expert_Verified", "Source_Verified"],
    )
    def test_verified_variants_auxiliary_only(self, status: str) -> None:
        pol = KnowledgeConsumptionPolicy()
        item = make_item(validation_status=status)
        assert pol.classify(item) == AUXILIARY_ONLY
        assert pol.is_auxiliary_only(item) is True
        assert pol.requires_pending_verification(item) is True

    @pytest.mark.parametrize(
        "status", ["Captured", "Pending_Verification", "Deprecated"]
    )
    def test_not_citable_states(self, status: str) -> None:
        pol = KnowledgeConsumptionPolicy()
        item = make_item(validation_status=status)
        assert pol.classify(item) == NOT_CITABLE
        assert pol.is_not_citable(item) is True
        assert pol.requires_pending_verification(item) is True

    def test_decision_for_shape(self) -> None:
        pol = KnowledgeConsumptionPolicy()
        item = make_item(validation_status=_APPROVED)
        d = pol.decision_for(item)
        assert d["policy"] == CITABLE
        assert d["citable"] is True
        assert d["requires_pending_verification"] is False


# ------------------------------------------------------------------ #
# 任务3：ReadBoundary
# ------------------------------------------------------------------ #
class TestReadBoundary:
    def test_allowed_kinds(self) -> None:
        rb = KnowledgeReadBoundary()
        for kind in ("metadata", "quality_report", "relationship", "conflict"):
            assert rb.can_read(kind) is True
        assert rb.can_read("verified_value") is False

    def test_forbidden_reads(self) -> None:
        rb = KnowledgeReadBoundary()
        assert rb.can_read_verified_value() is False
        assert rb.can_create_release_approval() is False
        assert rb.can_write_engineering_enabled() is False
        assert rb.can_self_produce_approved() is False

    def test_invariants_ok(self) -> None:
        rb = KnowledgeReadBoundary()
        assert rb.read_invariants_ok() is True
        assert "metadata" in ALLOWED_KINDS


# ------------------------------------------------------------------ #
# 任务4：RollbackPolicy
# ------------------------------------------------------------------ #
class TestRollbackPolicy:
    def test_deprecate_sets_deprecated_and_successor(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-OLD", content="old content text"))
        repo.save(make_item(knowledge_id="KI-NEW", content="new content text"))
        rb = KnowledgeRollbackPolicy()
        ver = rb.deprecate(repo, "KI-OLD", successor="KI-NEW", actor="rollback")
        assert ver >= 2
        assert repo.get("KI-OLD").validation_status == "Deprecated"
        assert rb.successor_of(repo, "KI-OLD") == "KI-NEW"

    def test_replacement_chain_one_hop(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-OLD", content="old content text"))
        repo.save(make_item(knowledge_id="KI-NEW", content="new content text"))
        rb = KnowledgeRollbackPolicy()
        rb.deprecate(repo, "KI-OLD", successor="KI-NEW")
        assert rb.build_replacement_chain(repo, "KI-OLD") == ["KI-OLD", "KI-NEW"]
        assert rb.is_replacement_available(repo, "KI-OLD") is True

    def test_history_preserved_not_deleted(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-OLD", content="old content text"))
        rb = KnowledgeRollbackPolicy()
        rb.deprecate(repo, "KI-OLD")
        # 旧 item 仍存在（未被删除），且至少保留原始版本快照。
        assert repo.exists("KI-OLD") is True
        assert rb.history_preserved(repo, "KI-OLD") is True
        assert len(repo.version("KI-OLD")) >= 1

    def test_engineer_enabled_unchanged_after_rollback(self) -> None:
        before = load_engineering_enabled()
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-OLD", content="old content text"))
        rb = KnowledgeRollbackPolicy()
        rb.deprecate(repo, "KI-OLD")
        assert load_engineering_enabled() is before is False
