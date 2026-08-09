"""Runtime Integration Tests（Phase 3.4 Sprint 3.4.4 任务5）。

将 ``EngineeringKnowledgeGuard`` / ``EngineeringRuntimeGuard`` 接入真实工程 AI 入口
（WindPressure / Glass / Profile / Hardware / InstallationRisk）与 RAG 检索链路，
并在纳入任何知识前强制经过 ``UnifiedActivationGate`` + ``ConsumptionPolicy`` 判定。

覆盖：
- WindPressure 接口拒绝非 Approved 知识（任务1+2）；
- Glass 接口拒绝非 Approved 知识（任务1+2）；
- Approved 允许作权威依据；
- Pending 阻断；
- Deprecated 阻断；
- ``engineering_enabled`` 保持 False（红线不变量，全程不翻转）；
- RAG Pipeline 分区（Retriever → Consumption Guard → ContextBuilder）；
- 消费审计持久化 JSONL（不产出 approved 事件，不触碰 verified.json）；
- ``EngineeringAgent.invoke`` 接入（有 / 无 ``knowledge_items`` 两种路径，向后兼容）。

夹具全部使用纯标识符 / 占位签名（KI-1 / SRC-1 / domain-A），不引入任何业务数值，
不写入 verified.json，不创建 ReleaseApproval，不输出 engineering_approved。
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from agents.base import AgentContext
from agents.config_loader import load_engineering_enabled
from agents.engineering.agent import EngineeringAgent
from agents.engineering.gate.unified_activation_gate import (
    UnifiedActivationDecision,
    UnifiedActivationGate,
)
from agents.engineering.knowledge.activation.audit_persistence import (
    make_persistent_audit_log,
)
from agents.engineering.knowledge.activation.consumer_guard import (
    BLOCKED_EVENT,
    CONSUMED_EVENT,
)
from agents.engineering.knowledge.activation.runtime_integration import (
    ENGINEERING_INTERFACES,
    EngineeringRuntimeGuard,
    InterfaceGuardResult,
)
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    PENDING_PLACEHOLDER,
)
from agents.engineering.knowledge.rag import (
    KnowledgeRetriever,
    RAGContext,
    RAGPipeline,
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


class TestRuntimeInterfaceWindRejected:
    """任务1+2：WindPressure 接口消费入口拒绝非 Approved 知识。"""

    def test_wind_pressure_rejects_pending_as_non_authoritative(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-P", validation_status="Pending_Verification")]
        res = guard.guard_interface("wind_pressure", items, _unified(allowed=True))
        assert isinstance(res, InterfaceGuardResult)
        assert res.interface == "wind_pressure"
        assert res.has_authoritative() is False
        assert "KI-P" in res.to_dict()["blocked_ids"]

    def test_wind_pressure_rejects_expert_verified_as_authoritative(self) -> None:
        # Expert_Verified 仅辅助（auxiliary），不得作权威依据。
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-E", validation_status="Expert_Verified")]
        res = guard.guard_interface("wind_pressure", items, _unified(allowed=True))
        d = res.to_dict()
        assert d["authoritative_ids"] == []
        assert "KI-E" in d["auxiliary_ids"]
        assert "KI-E" not in d["blocked_ids"]

    def test_wind_pressure_fail_closed_without_decision(self) -> None:
        # 未提供统一决策（repository=None）→ fail-closed 全部阻断。
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-A", validation_status=_APPROVED)]
        dec = guard.resolve_decision(None)
        assert dec.allowed is False
        res = guard.guard_interface("wind_pressure", items, dec)
        assert res.is_fully_blocked() is True
        assert "KI-A" in res.to_dict()["blocked_ids"]


class TestRuntimeInterfaceGlassRejected:
    """任务1+2：Glass 接口消费入口拒绝非 Approved 知识。"""

    def test_glass_safety_rejects_deprecated(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-D", validation_status="Deprecated")]
        res = guard.guard_interface("glass_safety", items, _unified(allowed=True))
        assert res.has_authoritative() is False
        assert "KI-D" in res.to_dict()["blocked_ids"]

    def test_glass_safety_rejects_source_verified_only_auxiliary(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-S", validation_status="Source_Verified")]
        res = guard.guard_interface("glass_safety", items, _unified(allowed=True))
        d = res.to_dict()
        assert d["authoritative_ids"] == []
        assert "KI-S" in d["auxiliary_ids"]


class TestRuntimeApprovedAllowed:
    """任务2：Approved 允许作权威依据。"""

    def test_approved_is_authoritative_on_any_interface(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-A", validation_status=_APPROVED)]
        for interface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(interface, items, _unified(allowed=True))
            d = res.to_dict()
            assert d["authoritative_ids"] == ["KI-A"], interface
            assert d["blocked_ids"] == []
            assert res.has_authoritative() is True

    def test_unknown_interface_raises(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(validation_status=_APPROVED)]
        try:
            guard.guard_interface("not_a_real_interface", items, _unified(allowed=True))
            raise AssertionError("expected ValueError for unknown interface")
        except ValueError:
            pass


class TestRuntimePendingBlocked:
    """任务2：Pending 阻断。"""

    def test_pending_blocked_on_all_interfaces(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-P", validation_status="Pending_Verification")]
        for interface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(interface, items, _unified(allowed=True))
            d = res.to_dict()
            assert d["authoritative_ids"] == []
            assert "KI-P" in d["blocked_ids"]


class TestRuntimeDeprecatedBlocked:
    """任务2：Deprecated 阻断。"""

    def test_deprecated_blocked_on_all_interfaces(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-X", validation_status="Deprecated")]
        for interface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(interface, items, _unified(allowed=True))
            d = res.to_dict()
            assert d["authoritative_ids"] == []
            assert "KI-X" in d["blocked_ids"]

    def test_captured_blocked_on_all_interfaces(self) -> None:
        guard = EngineeringRuntimeGuard()
        items = [make_item(knowledge_id="KI-C", validation_status="Captured")]
        for interface in ENGINEERING_INTERFACES:
            res = guard.guard_interface(interface, items, _unified(allowed=True))
            assert "KI-C" in res.to_dict()["blocked_ids"]


class TestRuntimeEngineeringEnabledInvariant:
    """红线：engineering_enabled 必须保持 False（绝不翻转）。"""

    def test_engineering_enabled_false_before_and_after(self) -> None:
        before = load_engineering_enabled()
        assert before is False
        guard = EngineeringRuntimeGuard()
        # 即便跑完整接口 + RAG 流程，engineering_enabled 也不变。
        items = [make_item(knowledge_id="KI-A", validation_status=_APPROVED)]
        guard.guard_interface("wind_pressure", items, _unified(allowed=True))
        RAGPipeline().run("q", items, _unified(allowed=True))
        assert load_engineering_enabled() is False

    def test_safety_invariants_ok(self) -> None:
        assert EngineeringRuntimeGuard.safety_invariants_ok() is True

    def test_unified_gate_is_fail_closed(self) -> None:
        # 真实仓库（空）+ 当前 engineering_enabled=False → 统一闸门不允许。
        repo = __import__(
            "agents.engineering.knowledge.repository", fromlist=["KnowledgeRepository"]
        ).KnowledgeRepository(store_path=None)
        dec = UnifiedActivationGate().evaluate(repo)
        assert dec.allowed is False
        assert EngineeringRuntimeGuard().resolve_decision(repo).allowed is False


class TestRAGPipelinePartition:
    """任务3：Retriever → Consumption Guard → ContextBuilder 分区。"""

    def test_pipeline_partitions_authoritative_auxiliary_blocked(self) -> None:
        corpus = [
            make_item(knowledge_id="KI-A", validation_status=_APPROVED, domain="wind", content="wind pressure design spec"),
            make_item(knowledge_id="KI-E", validation_status="Expert_Verified", domain="wind", content="wind expert note"),
            make_item(knowledge_id="KI-P", validation_status="Pending_Verification", domain="wind", content="wind draft"),
            make_item(knowledge_id="KI-D", validation_status="Deprecated", domain="wind", content="wind old rule"),
        ]
        ctx: RAGContext = RAGPipeline().run(
            "wind pressure spec", corpus, _unified(allowed=True), top_k=10
        )
        assert isinstance(ctx, RAGContext)
        ids_auth = {i.knowledge_id for i in ctx.authoritative}
        ids_aux = {i.knowledge_id for i in ctx.auxiliary}
        ids_block = {i.knowledge_id for i in ctx.blocked}
        assert ids_auth == {"KI-A"}
        assert ids_aux == {"KI-E"}
        assert ids_block == {"KI-P", "KI-D"}
        # 上下文装配结构正确（auxiliary 须标 pending_verification）。
        agent_ctx = ctx.to_agent_context()
        assert agent_ctx["decision_allowed"] is True
        assert agent_ctx["authoritative_knowledge"][0]["knowledge_id"] == "KI-A"
        assert agent_ctx["auxiliary_knowledge"][0]["requires_pending_verification"] is True
        assert set(agent_ctx["blocked_knowledge_ids"]) == {"KI-P", "KI-D"}

    def test_pipeline_fail_closed_blocks_all(self) -> None:
        corpus = [make_item(knowledge_id="KI-A", validation_status=_APPROVED)]
        ctx = RAGPipeline().run("q", corpus, _unified(allowed=False))
        assert ctx.authoritative == []
        assert ctx.auxiliary == []
        assert {i.knowledge_id for i in ctx.blocked} == {"KI-A"}
        assert ctx.decision_allowed is False

    def test_retriever_lexical_returns_candidates(self) -> None:
        corpus = [
            make_item(knowledge_id="KI-1", domain="wind", content="wind pressure spec"),
            make_item(knowledge_id="KI-2", domain="glass", content="glass safety spec"),
        ]
        rr = KnowledgeRetriever(top_k=1)
        res = rr.retrieve("wind pressure", corpus)
        assert len(res) == 1
        assert res.items()[0].knowledge_id == "KI-1"


class TestAuditPersistenceJsonl:
    """任务4：消费审计持久化（独立 JSONL，不产 approved 事件）。"""

    def test_persistent_audit_writes_jsonl_no_approved(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "consumption_audit.jsonl"
            log = make_persistent_audit_log(path)
            guard = EngineeringRuntimeGuard(audit_log=log)
            # consumed（Approved）与 blocked（Pending）各一条。
            guard.guard_item(
                make_item(knowledge_id="KI-A", validation_status=_APPROVED),
                _unified(allowed=True),
            )
            guard.guard_item(
                make_item(knowledge_id="KI-P", validation_status="Pending_Verification"),
                _unified(allowed=True),
            )
            assert path.is_file()
            lines = path.read_text(encoding="utf-8").splitlines()
            assert len(lines) == 2
            types = {json.loads(line)["event_type"] for line in lines}
            assert types <= {CONSUMED_EVENT, BLOCKED_EVENT}
            assert FORBIDDEN_EVENT_TYPE not in types
            assert "approved" not in types

    def test_persistent_audit_does_not_touch_repository_whitelist(self) -> None:
        # 持久化路径不经过 repository.event_log（白名单不含 approved），
        # 因此任意知识态都不产生 approved 事件。
        with tempfile.TemporaryDirectory() as td:
            log = make_persistent_audit_log(Path(td) / "audit.jsonl")
            for status in (_APPROVED, "Expert_Verified", "Pending_Verification", "Deprecated", "Captured"):
                item = make_item(knowledge_id=f"KI-{status}", validation_status=status)
                log.record(item, allowed=True)
            for ev in log.all_events():
                assert ev.event_type != FORBIDDEN_EVENT_TYPE
                assert ev.event_type != "approved"

    def test_load_existing_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "audit.jsonl"
            log1 = make_persistent_audit_log(path)
            log1.record(
                make_item(knowledge_id="KI-A", validation_status=_APPROVED), allowed=True
            )
            # 新实例从文件回灌（幂等，不再写文件）。
            log2 = make_persistent_audit_log(path).load_existing()
            assert len(log2.all_events()) == 1
            # 文件行数仍只有 1（load_existing 不应重复落盘）。
            assert len(path.read_text(encoding="utf-8").splitlines()) == 1


class TestEngineeringAgentInvokeIntegration:
    """任务2 接入：EngineeringAgent.invoke 计算前消费守卫分区。"""

    def test_invoke_without_knowledge_items_is_backward_compatible(self) -> None:
        agent = EngineeringAgent()
        ctx = AgentContext(request_id="eng-no-kb", input_data={})
        result = asyncio.run(agent.invoke(ctx))
        assert result.success is True
        # 无 knowledge_items 输入 → 空消费字典（零副作用）。
        assert result.data["knowledge_consumption"] == {}

    def test_invoke_with_knowledge_items_partitions(self) -> None:
        agent = EngineeringAgent()
        input_data = {
            "knowledge_items": {
                "wind_pressure": [
                    make_item(knowledge_id="KI-A", validation_status=_APPROVED),
                    make_item(knowledge_id="KI-P", validation_status="Pending_Verification"),
                ],
                "glass_safety": [
                    make_item(knowledge_id="KI-D", validation_status="Deprecated"),
                ],
            },
            "unified_decision": _unified(allowed=True),
        }
        ctx = AgentContext(request_id="eng-kb", input_data=input_data)
        result = asyncio.run(agent.invoke(ctx))
        assert result.success is True
        cons = result.data["knowledge_consumption"]
        assert "wind_pressure" in cons
        assert "glass_safety" in cons
        wp = cons["wind_pressure"]
        assert wp["authoritative_ids"] == ["KI-A"]
        assert "KI-P" in wp["blocked_ids"]
        assert cons["glass_safety"]["blocked_ids"] == ["KI-D"]

    def test_invoke_fail_closed_blocks_without_decision(self) -> None:
        # 未提供 unified_decision 且无仓库 → 守卫 fail-closed 全部阻断。
        agent = EngineeringAgent()
        input_data = {
            "knowledge_items": {
                "wind_pressure": [
                    make_item(knowledge_id="KI-A", validation_status=_APPROVED),
                ],
            }
        }
        ctx = AgentContext(request_id="eng-fc", input_data=input_data)
        result = asyncio.run(agent.invoke(ctx))
        cons = result.data["knowledge_consumption"]
        assert cons["wind_pressure"]["blocked_ids"] == ["KI-A"]
        assert cons["wind_pressure"]["authoritative_ids"] == []

    def test_agent_exposes_knowledge_guard(self) -> None:
        agent = EngineeringAgent()
        assert isinstance(agent.knowledge_guard, EngineeringRuntimeGuard)
        # consume_knowledge_for 直接接入点可用。
        res = agent.consume_knowledge_for(
            "profile",
            [make_item(knowledge_id="KI-A", validation_status=_APPROVED)],
            _unified(allowed=True),
        )
        assert res.to_dict()["authoritative_ids"] == ["KI-A"]
