"""Tests for Unified Activation Gate（Phase 3.4 Sprint 3.4.2）。

覆盖：知识失败 / 阈值失败 / 授权失败 / 全通过模拟 / engineering_enabled 保持 False /
默认 fail-closed / 三域 domain_results 结构 / 消费接入（禁止未 Approved 进入工程计算）/
红线（无 approved 事件、未创建 ReleaseApproval）。

夹具全部使用纯标识符 / 占位签名（TEST-MGR / TEST-EXP / KI-1 / SRC-1 / domain-A），
不引入任何业务数值，不写入 verified.json，不创建 ReleaseApproval。
"""

from __future__ import annotations

from agents.config_loader import load_engineering_enabled
from agents.engineering.gate.unified_activation_gate import (
    AUXILIARY_ONLY,
    CITABLE,
    NOT_CITABLE,
    UnifiedActivationDecision,
    UnifiedActivationGate,
    UnifiedConsumptionController,
)
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.repository import (
    FORBIDDEN_EVENT_TYPE,
    KnowledgeRepository,
)

_TS = "2026-08-01T00:00:00+00:00"
_APPROVED = "Engineering_Approved"


# --------------------------------------------------------------------------- #
# 夹具（本地自足，避免跨测试模块耦合）
# --------------------------------------------------------------------------- #
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


def make_verified_threshold() -> dict:
    """构造一条治理完备（双签齐全 + verified + 结构化引用）的占位阈值条目。"""
    return {
        "threshold_status": "verified",
        "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
        "verified": True,
        "verified_by": "TEST-MGR",
        "verified_at": "2026-08-01",
        "expert_verified_by": "TEST-EXP",
        "expert_verified_at": "2026-08-01",
    }


def make_draft_threshold() -> dict:
    """构造一条 draft 阈值（治理未过 → G1/G2 失败）。"""
    return {"threshold_id": "T-DRAFT-1", "threshold_status": "draft"}


# --------------------------------------------------------------------------- #
# 任务1+2+3：UnifiedActivationGate
# --------------------------------------------------------------------------- #
class TestUnifiedFailClosed:
    def test_default_is_fail_closed(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        gate = UnifiedActivationGate()
        dec = gate.evaluate(repo)
        assert isinstance(dec, UnifiedActivationDecision)
        assert dec.allowed is False
        assert dec.blocking_reasons  # 必有原因

    def test_three_domains_present(self) -> None:
        repo = KnowledgeRepository(store_path=None)
        gate = UnifiedActivationGate()
        dec = gate.evaluate(repo)
        for d in ("knowledge", "threshold", "publishing"):
            assert d in dec.domain_results
        # 每域均含统一 G1–G6 标签。
        for dr in dec.domain_results.values():
            for g in ("G1", "G2", "G3", "G4", "G5", "G6"):
                assert g in dr.gate_results

    def test_default_no_engineering_enabled_flip(self) -> None:
        before = load_engineering_enabled()
        repo = KnowledgeRepository(store_path=None)
        UnifiedActivationGate().evaluate(repo)
        assert load_engineering_enabled() is before is False


class TestUnifiedKnowledgeFailure:
    def test_knowledge_failure_blocks_unified(self) -> None:
        # 知识仓库为空（无 Engineering_Approved 候选）→ 知识域 G1 失败。
        repo = KnowledgeRepository(store_path=None)
        gate = UnifiedActivationGate()
        ctx = _all_green_context()
        dec = gate.evaluate(
            repo,
            context=ctx,
            thresholds=[make_verified_threshold()],
        )
        assert dec.allowed is False
        assert any(r.startswith("[knowledge] G1_") for r in dec.blocking_reasons)
        # 阈值域与发布域本应通过，但因知识域失败整体被阻。
        assert dec.domain_results["threshold"].allowed is True
        assert dec.domain_results["publishing"].allowed is True


class TestUnifiedThresholdFailure:
    def test_threshold_failure_blocks_unified(self) -> None:
        # 知识域通过（双签 approved 仓库），但阈值域用 draft → G1/G2 失败。
        repo = build_approved_repo(dual_sign=True)
        gate = UnifiedActivationGate()
        ctx = _all_green_context()
        dec = gate.evaluate(
            repo,
            context=ctx,
            thresholds=[make_draft_threshold()],
        )
        assert dec.allowed is False
        assert any(r.startswith("[threshold] G1_") for r in dec.blocking_reasons)
        assert dec.domain_results["knowledge"].allowed is True
        assert dec.domain_results["publishing"].allowed is True


class TestUnifiedAuthorizationFailure:
    def test_authorization_missing_blocks_all_domains(self) -> None:
        # authorization_present=False → 三域 G6 全部失败。
        repo = build_approved_repo(dual_sign=True)
        gate = UnifiedActivationGate()
        ctx = _all_green_context(authorization_present=False)
        dec = gate.evaluate(
            repo,
            context=ctx,
            thresholds=[make_verified_threshold()],
        )
        assert dec.allowed is False
        # 三域均出现 G6 原因。
        assert any(r.startswith("[knowledge] G6_") for r in dec.blocking_reasons)
        assert any(r.startswith("[threshold] G6_") for r in dec.blocking_reasons)
        assert any(r.startswith("[publishing] G6_") for r in dec.blocking_reasons)


class TestUnifiedAllGreen:
    def test_all_domains_pass_simulation(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = UnifiedActivationGate()
        ctx = _all_green_context()
        dec = gate.evaluate(
            repo,
            context=ctx,
            thresholds=[make_verified_threshold()],
        )
        assert dec.allowed is True
        assert dec.blocking_reasons == []
        for name in ("knowledge", "threshold", "publishing"):
            assert dec.domain_results[name].allowed is True
        # 每域六门全绿。
        for dr in dec.domain_results.values():
            assert all(dr.gate_results.values()) is True

    def test_engineering_enabled_unchanged_after_all_green(self) -> None:
        before = load_engineering_enabled()
        repo = build_approved_repo(dual_sign=True)
        gate = UnifiedActivationGate()
        ctx = _all_green_context()
        gate.evaluate(repo, context=ctx, thresholds=[make_verified_threshold()])
        assert load_engineering_enabled() is before is False

    def test_no_approved_event_recorded(self) -> None:
        repo = build_approved_repo(dual_sign=True)
        gate = UnifiedActivationGate()
        ctx = _all_green_context()
        gate.evaluate(repo, context=ctx, thresholds=[make_verified_threshold()])
        for ev in repo.event_log.all_events():
            assert ev.event_type != FORBIDDEN_EVENT_TYPE


# --------------------------------------------------------------------------- #
# 任务4：Consumption 接入（禁止未 Approved 知识进入工程计算）
# --------------------------------------------------------------------------- #
class TestUnifiedConsumption:
    def _unified(self, allowed: bool) -> UnifiedActivationDecision:
        return UnifiedActivationDecision(allowed=allowed, blocking_reasons=[], domain_results={})

    def test_unified_blocked_forbids_any_knowledge(self) -> None:
        ctrl = UnifiedConsumptionController()
        item = make_item(validation_status=_APPROVED)
        d = ctrl.evaluate(item, self._unified(allowed=False))
        assert d.permitted is False
        assert d.reason == "unified_gate_blocked"

    def test_approved_is_authoritative(self) -> None:
        ctrl = UnifiedConsumptionController()
        item = make_item(validation_status=_APPROVED)
        d = ctrl.evaluate(item, self._unified(allowed=True))
        assert d.permitted is True
        assert d.as_authoritative is True
        assert d.requires_pending_verification is False
        assert d.policy == CITABLE

    def test_auxiliary_only_requires_pending_verification(self) -> None:
        ctrl = UnifiedConsumptionController()
        item = make_item(validation_status="Expert_Verified")
        d = ctrl.evaluate(item, self._unified(allowed=True))
        assert d.permitted is True
        assert d.as_authoritative is False
        assert d.requires_pending_verification is True
        assert d.policy == AUXILIARY_ONLY

    def test_not_citable_forbidden_from_engineering(self) -> None:
        # 未 Approved（Pending / Captured / Deprecated）禁止进入工程计算。
        ctrl = UnifiedConsumptionController()
        for status in ("Pending_Verification", "Captured", "Deprecated"):
            item = make_item(validation_status=status)
            d = ctrl.evaluate(item, self._unified(allowed=True))
            assert d.permitted is False
            assert d.as_authoritative is False
            assert d.reason == "not_citable_forbidden"
            assert d.policy == NOT_CITABLE


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #
def _all_green_context(**overrides: bool) -> "object":
    from agents.engineering.knowledge.activation.gate import ActivationContext

    kwargs = {
        "ci_green": True,
        "rollback_ready": True,
        "authorization_present": True,
        "dual_sign_present": True,
        "require_audit_chain": False,  # 模拟审核链已在上游满足
    }
    kwargs.update(overrides)
    return ActivationContext(**kwargs)
