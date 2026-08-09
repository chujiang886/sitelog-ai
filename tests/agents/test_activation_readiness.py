"""Activation Readiness Verification（Phase 3.4 Sprint 3.4.5）。

激活准备最终验证与加固。覆盖：

- 任务1 Unified Gate 全链：Knowledge / Threshold / Publishing 三域 G1–G6 全部失败
  原因可追踪（每条 blocking_reason 都引用 G1–G6 标签）。
- 任务2 Agent 入口扫描：WindPressure / Glass / Profile / Hardware /
  InstallationRisk 五接口全部经过 EngineeringRuntimeGuard 分区。
- 任务3 RAG 绕过测试：Pending / Deprecated / 未 Approved 知识无法进入工程上下文
  （authoritative / auxiliary 均不含 blocked 项）。
- 任务4 审计完整性：Consumption Audit / Repository Audit / Review Log 三类日志边界
  清晰、互不污染；消费审计硬拒 approved；repository 事件白名单不含 approved。

红线（全 Phase 3.4 适用，且在全程验证中守约）：
①不开 engineering_enabled  ②不输出 engineering_approved  ③不改 verified.json
④不建 ReleaseApproval  ⑤AI 不代专家授权。

夹具全部使用纯标识符 / 占位签名（KI-1 / SRC-1 / domain-A），不引入任何业务数值、
不写入 verified.json、不创建 ReleaseApproval、不输出 engineering_approved。
"""

from __future__ import annotations

import inspect
import json
import pytest
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.agent import ANALYSIS_INTERFACES, EngineeringAgent
from agents.engineering.gate.enable_gate import (
    GATE_G1_GOVERNANCE as T_G1,
    GATE_G2_DUAL_SIGN as T_G2,
    GATE_G3_CI as T_G3,
    GATE_G4_AUDIT_CHAIN as T_G4,
    GATE_G5_ROLLBACK as T_G5,
    GATE_G6_AUTHORIZATION as T_G6,
)
from agents.engineering.gate.unified_activation_gate import (
    G1,
    G2,
    G3,
    G4,
    G5,
    G6,
    ALL_GATES,
    DomainResult,
    UnifiedActivationDecision,
    UnifiedActivationGate,
)
from agents.engineering.knowledge.activation.audit_persistence import (
    DEFAULT_AUDIT_PATH,
    PersistentConsumptionAuditLog,
)
from agents.engineering.knowledge.activation.consumer_guard import (
    BLOCKED_EVENT,
    CONSUMED_EVENT,
    EngineeringKnowledgeGuard,
)
from agents.engineering.knowledge.activation.gate import (
    ActivationContext,
    GATE_G1_GOVERNANCE as K_G1,
    GATE_G2_DUAL_SIGN as K_G2,
    GATE_G3_CI as K_G3,
    GATE_G4_AUDIT_CHAIN as K_G4,
    GATE_G5_ROLLBACK as K_G5,
    GATE_G6_AUTHORIZATION as K_G6,
    KnowledgeActivationGate,
)
from agents.engineering.knowledge.activation.runtime_integration import (
    ENGINEERING_INTERFACES,
    EngineeringRuntimeGuard,
)
from agents.engineering.knowledge.connector import KnowledgeItem, PENDING_PLACEHOLDER
from agents.engineering.knowledge.rag import RAGPipeline
from agents.engineering.knowledge.repository import (
    DEFAULT_STORE_FILENAME,
    EVENT_TYPES,
    FORBIDDEN_EVENT_TYPE,
    KnowledgeEvent,
    KnowledgeEventLog,
    KnowledgeRepository,
)
from agents.engineering.review_log import (
    DEFAULT_REVIEW_LOG_PATH,
    append_review_event,
    read_log,
)

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


# ===========================================================================
# 任务1：Unified Gate 全链测试（G1–G6 可追踪）
# ===========================================================================
class TestUnifiedGateFullChainTraceability:
    def test_fail_closed_all_domains_blocked(self) -> None:
        gate = UnifiedActivationGate()
        repo = KnowledgeRepository(store_path=None)
        dec = gate.evaluate(repo)
        assert dec.allowed is False
        assert set(dec.domain_results.keys()) == {"knowledge", "threshold", "publishing"}
        for dom, dr in dec.domain_results.items():
            assert isinstance(dr, DomainResult)
            assert dr.allowed is False
            # 每个未允许的域都给出可追踪的 blocking_reasons。
            assert dr.blocking_reasons, f"域 {dom} 未允许却无阻断原因"

    def test_every_blocking_reason_references_a_gate_label(self) -> None:
        gate = UnifiedActivationGate()
        repo = KnowledgeRepository(store_path=None)
        dec = gate.evaluate(repo)
        gates = {G1, G2, G3, G4, G5, G6}
        for reason in dec.blocking_reasons:
            body = reason.split("]", 1)[1].strip() if reason.startswith("[") else reason
            label = body.split("_", 1)[0]
            assert label in gates, f"不可追踪的阻断原因：{reason!r}"

    def test_three_domains_expose_full_g1_to_g6(self) -> None:
        gate = UnifiedActivationGate()
        repo = KnowledgeRepository(store_path=None)
        dec = gate.evaluate(repo)
        for dom, dr in dec.domain_results.items():
            assert set(dr.gate_results.keys()) == set(ALL_GATES), dom
            # 允许态与 gate_results 一致。
            assert dr.allowed == all(dr.gate_results.values()), dom

    def test_knowledge_domain_gates_traceable(self) -> None:
        gate = KnowledgeActivationGate()
        # G1 治理：无 Engineering_Approved 候选 → 失败且原因带 G1 标签。
        dec = gate.can_activate_knowledge(
            KnowledgeRepository(store_path=None), context=ActivationContext()
        )
        assert dec.allowed is False
        assert any(K_G1 in r for r in dec.blocking_reasons)
        # G3 / G5 / G6 由注入信号驱动，缺省失败。
        assert any(K_G3 in r for r in dec.blocking_reasons)
        assert any(K_G5 in r for r in dec.blocking_reasons)
        assert any(K_G6 in r for r in dec.blocking_reasons)

    def test_knowledge_gate_g2_dual_sign_traceable(self) -> None:
        gate = KnowledgeActivationGate()
        dec = gate.can_activate_knowledge(
            KnowledgeRepository(store_path=None),
            context=ActivationContext(dual_sign_present=False),
        )
        assert any(K_G2 in r for r in dec.blocking_reasons)

    def test_knowledge_gate_g4_audit_chain_traceable(self) -> None:
        # 白盒注入一条 forbidden 'approved' 事件，模拟审核链损坏。
        repo = KnowledgeRepository(store_path=None)
        repo.event_log._events.append(
            KnowledgeEvent(
                event_id="EVT-BAD",
                knowledge_id="KI-X",
                event_type=FORBIDDEN_EVENT_TYPE,
                actor="someone",
                timestamp=_TS,
            )
        )
        dec = KnowledgeActivationGate().can_activate_knowledge(
            repo, context=ActivationContext()
        )
        assert any(K_G4 in r for r in dec.blocking_reasons)

    def test_threshold_gate_results_mapper(self) -> None:
        gate = UnifiedActivationGate()
        # 空原因 → 全部通过。
        assert gate._threshold_gate_results([]) == {g: True for g in ALL_GATES}
        # 每条 G1–G6 reason 码映射到对应标签。
        assert gate._threshold_gate_results([T_G1])[G1] is False
        assert gate._threshold_gate_results([T_G2])[G2] is False
        assert gate._threshold_gate_results([T_G3])[G3] is False
        assert gate._threshold_gate_results([T_G4])[G4] is False
        assert gate._threshold_gate_results([T_G5])[G5] is False
        assert gate._threshold_gate_results([T_G6])[G6] is False

    def test_publishing_domain_gates_traceable(self) -> None:
        gate = UnifiedActivationGate()
        repo = KnowledgeRepository(store_path=None)
        # 默认 fail-closed：publishing 域 G2（双签）缺位 → 失败且原因可追踪。
        dec = gate.evaluate(repo)
        pub = dec.domain_results["publishing"]
        assert pub.allowed is False
        assert pub.gate_results[G1] is True  # G1 治理：engineering_enabled=False 通过
        assert pub.gate_results[G2] is False  # G2 双签缺位 → 失败
        assert any(T_G2 in r for r in pub.blocking_reasons)
        # 顶层统一决策同样含 [publishing] 前缀的可追踪原因。
        assert any(
            r.startswith("[publishing]") and T_G2 in r for r in dec.blocking_reasons
        )

    def test_top_level_safety_gate_blocks_when_enabled_simulated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # 纯测试替身（monkeypatch）：不修改任何配置文件或 verified.json；
        # 仅验证顶层 G1 安全护栏在 engineering_enabled 被（模拟）置真时仍 fail-closed。
        for mod in (
            "agents.engineering.gate.unified_activation_gate.load_engineering_enabled",
            "agents.engineering.knowledge.activation.gate.load_engineering_enabled",
            "agents.engineering.knowledge.repository.load_engineering_enabled",
        ):
            monkeypatch.setattr(mod, lambda: True)
        gate = UnifiedActivationGate()
        repo = KnowledgeRepository(store_path=None)
        dec = gate.evaluate(repo)
        assert dec.allowed is False
        assert f"{G1}_engineering_enabled_must_be_false" in dec.blocking_reasons
        # 真实 config 从未被改动：本测试模块导入的引用仍返回 False。
        assert load_engineering_enabled() is False


# ===========================================================================
# 任务2：Agent 入口扫描（五接口过 RuntimeGuard）
# ===========================================================================
class TestAgentEntryScan:
    def test_engineering_interfaces_declared(self) -> None:
        assert ENGINEERING_INTERFACES == (
            "wind_pressure",
            "glass_safety",
            "profile",
            "hardware",
            "installation_risk",
        )

    def test_agent_analysis_interfaces_aligned(self) -> None:
        # 运行时守卫声明的接口与 EngineeringAgent 分发器接口必须一致（入口识别）。
        assert ANALYSIS_INTERFACES == ENGINEERING_INTERFACES

    def test_all_five_interfaces_guardable_approved(self) -> None:
        guard = EngineeringRuntimeGuard()
        dec = _unified(allowed=True)
        for iface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(
                iface, [make_item(validation_status=_APPROVED)], dec
            )
            assert res.to_dict()["authoritative_ids"] == ["KI-1"], iface

    def test_all_five_interfaces_block_pending(self) -> None:
        guard = EngineeringRuntimeGuard()
        dec = _unified(allowed=True)
        for iface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(
                iface, [make_item(validation_status="Pending_Verification")], dec
            )
            assert res.to_dict()["blocked_ids"] == ["KI-1"], iface
            assert res.to_dict()["authoritative_ids"] == []

    def test_agent_knowledge_guard_wired(self) -> None:
        agent = EngineeringAgent()
        assert isinstance(agent.knowledge_guard, EngineeringRuntimeGuard)
        for iface in ENGINEERING_INTERFACES:
            res = agent.consume_knowledge_for(
                iface, [make_item(validation_status=_APPROVED)], _unified(allowed=True)
            )
            assert res.to_dict()["authoritative_ids"] == ["KI-1"], iface

    def test_agent_entry_points_exist_and_wired(self) -> None:
        for method in (
            "analyze_wind_pressure",
            "analyze_glass_safety",
            "analyze_profile",
            "analyze_hardware",
            "analyze_installation_risk",
        ):
            assert hasattr(EngineeringAgent, method), f"缺失入口：{method}"
        invoke_src = inspect.getsource(EngineeringAgent.invoke)
        # invoke 成功路径显式调用消费守卫分区，并把结果放入 knowledge_consumption。
        assert "_consume_requested_knowledge(" in invoke_src
        assert "knowledge_consumption" in invoke_src

    def test_safety_invariants_ok(self) -> None:
        assert UnifiedActivationGate.safety_invariants_ok() is True
        assert EngineeringRuntimeGuard.safety_invariants_ok() is True
        assert load_engineering_enabled() is False


# ===========================================================================
# 任务3：RAG 绕过测试（Pending / Deprecated / 未 Approved 阻断）
# ===========================================================================
def _rag_corpus() -> list[KnowledgeItem]:
    base = dict(domain="wind", content="wind pressure glass safety factor")
    return [
        make_item(knowledge_id="KI-A", validation_status=_APPROVED, **base),
        make_item(knowledge_id="KI-P", validation_status="Pending_Verification", **base),
        make_item(knowledge_id="KI-D", validation_status="Deprecated", **base),
        make_item(knowledge_id="KI-C", validation_status="Captured", **base),
        make_item(knowledge_id="KI-E", validation_status="Expert_Verified", **base),
    ]


class TestRAGBypass:
    def test_rag_blocks_pending_deprecated_captured(self) -> None:
        corpus = _rag_corpus()
        ctx = RAGPipeline().run("wind pressure glass", corpus, _unified(allowed=True), top_k=10)
        auth_ids = [i.knowledge_id for i in ctx.authoritative]
        blocked_ids = [i.knowledge_id for i in ctx.blocked]
        aux_ids = [i.knowledge_id for i in ctx.auxiliary]
        assert auth_ids == ["KI-A"]
        assert set(blocked_ids) == {"KI-P", "KI-D", "KI-C"}
        assert aux_ids == ["KI-E"]
        # 关键不变量：未 Approved 知识绝不进入 authoritative / auxiliary。
        for banned in ("KI-P", "KI-D", "KI-C"):
            assert banned not in auth_ids and banned not in aux_ids

    def test_rag_agent_context_excludes_blocked(self) -> None:
        corpus = _rag_corpus()
        ctx = RAGPipeline().run("wind pressure glass", corpus, _unified(allowed=True), top_k=10)
        agent_ctx = ctx.to_agent_context()
        assert set(agent_ctx["blocked_knowledge_ids"]) == {"KI-P", "KI-D", "KI-C"}
        auth_ctx_ids = [a["knowledge_id"] for a in agent_ctx["authoritative_knowledge"]]
        aux_ctx_ids = [a["knowledge_id"] for a in agent_ctx["auxiliary_knowledge"]]
        for banned in ("KI-P", "KI-D", "KI-C"):
            assert banned not in auth_ctx_ids and banned not in aux_ctx_ids
        # auxiliary 须显式标 pending_verification。
        assert all(a["requires_pending_verification"] is True for a in agent_ctx["auxiliary_knowledge"])

    def test_rag_all_blocked_when_gate_denied(self) -> None:
        corpus = _rag_corpus()
        ctx = RAGPipeline().run("wind pressure glass", corpus, _unified(allowed=False), top_k=10)
        assert ctx.authoritative == [] and ctx.auxiliary == []
        assert set(i.knowledge_id for i in ctx.blocked) == {
            "KI-A", "KI-P", "KI-D", "KI-C", "KI-E"
        }


# ===========================================================================
# 任务4：审计完整性（三类日志边界）
# ===========================================================================
class TestAuditBoundaries:
    def test_consumption_audit_persisted_and_free_of_approved(self, tmp_path: Path) -> None:
        p = tmp_path / "consumption_audit.jsonl"
        log = PersistentConsumptionAuditLog(path=p)
        guard = EngineeringKnowledgeGuard(audit_log=log)
        guard.consume_knowledge(make_item(validation_status=_APPROVED), _unified(allowed=True))
        guard.consume_knowledge(
            make_item(knowledge_id="KI-P", validation_status="Pending_Verification"),
            _unified(allowed=True),
        )
        assert p.is_file()
        lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
        assert len(lines) == 2
        for ln in lines:
            obj = json.loads(ln)
            assert obj["event_type"] in (CONSUMED_EVENT, BLOCKED_EVENT)
            assert obj["event_type"] != FORBIDDEN_EVENT_TYPE
            assert obj["event_type"] != "approved"
        assert len(log.all_events()) == 2

    def test_consumption_audit_does_not_write_repository_events(self) -> None:
        # 消费审计与 repository event_log 完全独立：消费不产生任何 repository 事件。
        repo = KnowledgeRepository(store_path=None)
        log = PersistentConsumptionAuditLog(path=None)
        guard = EngineeringKnowledgeGuard(audit_log=log)
        guard.consume_knowledge(make_item(validation_status=_APPROVED), _unified(allowed=True))
        assert repo.event_log.all_events() == []
        assert log.all_events() != []

    def test_consumption_audit_records_blocked_under_gate_denied(self) -> None:
        log = PersistentConsumptionAuditLog(path=None)
        guard = EngineeringKnowledgeGuard(audit_log=log)
        guard.consume_knowledge(make_item(validation_status=_APPROVED), _unified(allowed=False))
        events = log.all_events()
        assert events and events[0].event_type == BLOCKED_EVENT

    def test_repository_event_log_rejects_approved(self) -> None:
        # Repository 审计白名单刻意不含 approved（红线）。
        assert EVENT_TYPES == ("create", "update", "verify", "deprecated")
        assert FORBIDDEN_EVENT_TYPE == "approved"
        with pytest.raises(ValueError):
            KnowledgeEventLog().record("KI-X", FORBIDDEN_EVENT_TYPE)
        # repo.record_event 委托给 event_log，同样拒绝 approved（item 须先存在）。
        repo = KnowledgeRepository(store_path=None)
        repo.save(make_item(knowledge_id="KI-X"))
        with pytest.raises(ValueError):
            repo.record_event("KI-X", FORBIDDEN_EVENT_TYPE)

    def test_three_log_paths_are_distinct(self) -> None:
        # Consumption Audit / Repository Store / Review Log 三类日志落点彼此独立。
        assert "consumption_audit" in DEFAULT_AUDIT_PATH
        assert "review_log" in str(DEFAULT_REVIEW_LOG_PATH)
        assert DEFAULT_AUDIT_PATH != str(DEFAULT_REVIEW_LOG_PATH)
        # repository 自有 store 文件名亦独立。
        assert DEFAULT_STORE_FILENAME == "knowledge_repository.json"

    def test_review_log_append_only_and_required_fields(self, tmp_path: Path) -> None:
        lp = tmp_path / "review_log.jsonl"
        append_review_event(
            threshold_id="T1",
            action="submit",
            signer_role="expert",
            signer="E1",
            source_ref="S1",
            log_path=lp,
        )
        append_review_event(
            threshold_id="T2",
            action="verified",
            signer_role="mgmt",
            signer="M1",
            source_ref="S2",
            log_path=lp,
        )
        records = read_log(lp)
        assert len(records) == 2
        for r in records:
            for f in (
                "event_id",
                "threshold_id",
                "action",
                "signer_role",
                "signer",
                "timestamp",
                "source_ref",
                "prev_event_id",
            ):
                assert f in r
        # 链式：第二条 prev_event_id 指向第一条 event_id。
        assert records[1]["prev_event_id"] == records[0]["event_id"]
