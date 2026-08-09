"""Knowledge Graph Query & Reasoning Layer 测试（Phase 3.7.2 Task 6）。

覆盖（用户要求）：
1. query 测试    ：node_query / edge_query / path_query 正确寻路、过滤；
2. path 测试     ：KnowledgeItem→Threshold→Rule 候选链追踪；
3. impact 测试   ：threshold impact 收集 Agent/Case/Rule 候选，仅报告；
4. audit 测试    ：推理层全只读（node/edge count 不变、无写方法）；
5. red line 测试 ：5 红线全部守约（不开启 enabled / 不输出 approved / 不改状态 /
                   不自动解决冲突 / 不伪造参数）。

红线约束：
- 全部用例使用内存图谱（无 store_path），绝不触碰磁盘 verified.json / engineering_enabled；
- 夹具一律使用纯标识符，不写任何真实 value 或真实专家身份；
- CalcAgent 恒为 pending 候选，绝不编造真实计算主体。
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.knowledge.graph import (
    CaseEntity,
    ExpertEntity,
    GraphEdge,
    KnowledgeGraphConflictDetector,
    KnowledgeGraphQueryEngine,
    KnowledgeItemEntity,
    ReasoningConflictCandidate,
    RedLineViolationError,
    RuleEntity,
    SourceRefEntity,
    ThresholdEntity,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
def make_item(knowledge_id: str = "KI-TEST-0001", **overrides: Any) -> KnowledgeItem:
    base = dict(
        knowledge_id=knowledge_id,
        knowledge_type="spec",
        parent_knowledge_id="",
        title="Example Threshold Note",
        content="placeholder content body",
        source="SRC-1",
        author="EXP-1",
        domain="wind_pressure",
        content_hash="",
        validation_status="Pending_Verification",
        linked_entities=["E-TH-01"],
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    base.update(overrides)
    return KnowledgeItem(**base)


def reasoning_graph() -> KnowledgeGraphRepository:
    """构造含 KI/Expert/SourceRef/Threshold/Rule/Case 与多关系的可读图谱。

    RULE-1 为 pending_build 骨架，其 applies→KI 会触发 pending_build_edge 冲突，
    用于冲突保持人工审核测试。
    """
    repo = KnowledgeGraphRepository()
    repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="t")
    repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="KI-TEST-0002", parent_knowledge_id="KI-TEST-0001")).to_node(), actor="t")
    repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="KI-TEST-0003")).to_node(), actor="t")
    repo.add_node(ExpertEntity(expert_id="EXP-1").to_node(), actor="t")
    repo.add_node(SourceRefEntity(source_ref_id="SRC-1").to_node(), actor="t")
    repo.add_node(ThresholdEntity(threshold_id="E-TH-01", domain="wind_pressure").to_node(), actor="t")
    repo.add_node(RuleEntity(rule_id="RULE-1").to_node(), actor="t")  # pending_build=True
    repo.add_node(CaseEntity(case_id="CASE-1", linked_thresholds=["E-TH-01"]).to_node(), actor="t")  # pending_build=True
    # 关系
    repo.add_edge(GraphEdge("e_auth", "authored_by", "KI-TEST-0001", "EXP-1", {}), actor="t")
    repo.add_edge(GraphEdge("e_src", "sourced_from", "KI-TEST-0001", "SRC-1",
                            {"standard": "GB 50009", "clause": "8.1.1"}), actor="t")
    repo.add_edge(GraphEdge("e_basis", "basis", "KI-TEST-0001", "E-TH-01", {}), actor="t")
    repo.add_edge(GraphEdge("e_used", "used_by", "E-TH-01", "KI-TEST-0002", {}), actor="t")
    repo.add_edge(GraphEdge("e_applies", "applies", "RULE-1", "KI-TEST-0001", {}), actor="t")
    repo.add_edge(GraphEdge("e_parent", "parent_child", "KI-TEST-0001", "KI-TEST-0002", {"no_cycle": True}), actor="t")
    repo.add_edge(GraphEdge("e_ref", "references", "KI-TEST-0001", "KI-TEST-0003", {}), actor="t")
    repo.add_edge(GraphEdge("e_cites", "cites", "KI-TEST-0001", "SRC-1", {}), actor="t")
    return repo


def orphan_graph() -> KnowledgeGraphRepository:
    repo = KnowledgeGraphRepository()
    repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="KI-ORPHAN")).to_node(), actor="t")
    repo.add_node(ExpertEntity(expert_id="EXP-9").to_node(), actor="t")
    repo.add_edge(GraphEdge("o_auth", "authored_by", "KI-ORPHAN", "EXP-9", {}), actor="t")
    return repo


# ---------------------------------------------------------------------------
# 1. query 测试
# ---------------------------------------------------------------------------
class TestKnowledgeGraphQuery:
    def test_node_query_filters_by_type(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        items = eng.node_query(entity_type="KnowledgeItem")
        assert {n.node_id for n in items} == {"KI-TEST-0001", "KI-TEST-0002", "KI-TEST-0003"}
        asserts = eng.node_query(entity_type="Case")
        assert {n.node_id for n in asserts} == {"CASE-1"}

    def test_node_query_pending_build_only(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        pending = eng.node_query(pending_build_only=True)
        assert {n.node_id for n in pending} == {"RULE-1", "CASE-1"}

    def test_edge_query_by_relation(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        basis_edges = eng.edge_query(relation_type="basis")
        assert len(basis_edges) == 1
        assert basis_edges[0].source_id == "KI-TEST-0001"
        assert basis_edges[0].target_id == "E-TH-01"

    def test_edge_query_by_source_target(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        out = eng.edge_query(source_id="E-TH-01")
        assert {e.relation_type for e in out} == {"used_by"}
        both = eng.edge_query(source_id="KI-TEST-0001", relation_type="basis")
        assert len(both) == 1

    def test_path_query_finds_direct_edge(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        path = eng.path_query("KI-TEST-0001", "E-TH-01", relation_types=["basis"])
        assert path[0]["node_id"] == "KI-TEST-0001"
        assert path[-1]["node_id"] == "E-TH-01"
        assert path[-1]["relation_type"] == "basis"

    def test_path_query_finds_multi_hop(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        path = eng.path_query("KI-TEST-0001", "RULE-1")
        assert path[0]["node_id"] == "KI-TEST-0001"
        assert path[-1]["node_id"] == "RULE-1"

    def test_path_query_unreachable_returns_empty(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        # 把孤儿图谱单独测：KI-ORPHAN 与推理图谱不连通
        g2 = orphan_graph()
        eng2 = KnowledgeGraphQueryEngine(g2)
        assert eng2.path_query("KI-ORPHAN", "EXP-9", relation_types=["authored_by"]) != []
        # 推理图谱里 CASE-1 无出边且未被引用 → 从 KI 无法抵达（无 relation 连到它）
        assert eng.path_query("KI-TEST-0001", "CASE-1") == []

    def test_path_query_respects_max_depth(self):
        # 构造纯 2 跳链 A→B→C（references），C 仅 2 跳可达
        repo = KnowledgeGraphRepository()
        repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="A")).to_node(), actor="t")
        repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="B")).to_node(), actor="t")
        repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="C")).to_node(), actor="t")
        repo.add_edge(GraphEdge("r1", "references", "A", "B", {}), actor="t")
        repo.add_edge(GraphEdge("r2", "references", "B", "C", {}), actor="t")
        eng = KnowledgeGraphQueryEngine(repo)
        # max_depth=1：A→C 不可达（需 2 跳）
        assert eng.path_query("A", "C", max_depth=1) == []
        # max_depth=2：可达
        path = eng.path_query("A", "C", max_depth=2)
        assert path[0]["node_id"] == "A"
        assert path[-1]["node_id"] == "C"
        assert len(path) == 3  # A -> B -> C


# ---------------------------------------------------------------------------
# 2. path 测试（KnowledgeItem → Threshold → Rule → CalcAgent 候选）
# ---------------------------------------------------------------------------
class TestKnowledgePathTrace:
    def test_trace_returns_threshold_rule_calcagent(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        trace = eng.trace_knowledge_path("KI-TEST-0001")
        assert trace.knowledge_item_id == "KI-TEST-0001"
        assert trace.thresholds == ["E-TH-01"]
        assert trace.rules == ["RULE-1"]
        assert len(trace.calc_agent_candidates) == 1
        assert trace.calc_agent_candidates[0].source_rule_id == "RULE-1"

    def test_trace_never_approves(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        trace = eng.trace_knowledge_path("KI-TEST-0001")
        assert trace.requires_human_review is True
        assert trace.approval_forbidden is True

    def test_calc_agent_is_pending_candidate(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        trace = eng.trace_knowledge_path("KI-TEST-0001")
        cand = trace.calc_agent_candidates[0]
        assert cand.is_candidate is True
        assert cand.pending is True
        # 红线⑤：绝不编造真实计算主体
        assert cand.computation_body == "pending_verification"

    def test_trace_rejects_non_knowledge_item(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        with pytest.raises(KeyError):
            eng.trace_knowledge_path("E-TH-01")


# ---------------------------------------------------------------------------
# 3. impact 测试
# ---------------------------------------------------------------------------
class TestThresholdImpact:
    def test_impact_collects_items_rules_cases_agents(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        report = eng.impact_analysis("E-TH-01")
        assert report.threshold_id == "E-TH-01"
        assert set(report.affected_knowledge_items) == {"KI-TEST-0001", "KI-TEST-0002"}
        assert report.affected_rules == ["RULE-1"]
        assert report.affected_cases == ["CASE-1"]
        assert len(report.affected_agent_candidates) == 1
        assert report.affected_agent_candidates[0].source_rule_id == "RULE-1"

    def test_impact_only_report_no_approval(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        report = eng.impact_analysis("E-TH-01")
        assert report.requires_human_review is True
        assert report.approval_forbidden is True

    def test_impact_agent_candidates_pending(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        report = eng.impact_analysis("E-TH-01")
        for c in report.affected_agent_candidates:
            assert c.pending is True
            assert c.computation_body == "pending_verification"

    def test_impact_rejects_non_threshold(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        with pytest.raises(KeyError):
            eng.impact_analysis("KI-TEST-0001")


# ---------------------------------------------------------------------------
# 4. audit 测试（推理层全只读）
# ---------------------------------------------------------------------------
class TestReasoningAudit:
    def test_engine_has_no_write_methods(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        for forbidden in ("approve", "merge", "delete", "engineering_approved", "add_node", "add_edge"):
            assert not hasattr(eng, forbidden), f"推理引擎不得暴露 {forbidden!r}（红线③）"

    def test_all_queries_are_read_only(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        before = (g.node_count(), g.edge_count())
        # 跑一遍所有只读方法
        eng.node_query(entity_type="KnowledgeItem")
        eng.edge_query(relation_type="basis")
        eng.path_query("KI-TEST-0001", "E-TH-01")
        eng.trace_knowledge_path("KI-TEST-0001")
        eng.impact_analysis("E-TH-01")
        eng.reason_associations("KI-TEST-0001")
        eng.conflict_scan()
        after = (g.node_count(), g.edge_count())
        assert before == after, "推理层任何方法都不得改动图谱（红线③）"

    def test_conflict_scan_does_not_mutate_graph(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        before = (g.node_count(), g.edge_count())
        eng.conflict_scan()
        assert (g.node_count(), g.edge_count()) == before

    def test_conflict_scan_returns_reasoning_candidates(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        cands = eng.conflict_scan()
        assert len(cands) >= 1
        for c in cands:
            assert isinstance(c, ReasoningConflictCandidate)
            assert c.review_required is True
            assert c.auto_resolvable is False


# ---------------------------------------------------------------------------
# 5. red line 测试
# ---------------------------------------------------------------------------
class TestReasoningRedLines:
    def test_constructor_asserts_safety_invariants(self):
        # config.yaml 真实 engineering_enabled=False → 构造成功
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        assert eng is not None

    def test_engine_has_no_approval_or_merge_delete(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        for forbidden in ("approve", "merge", "delete", "engineering_approved"):
            assert not hasattr(eng, forbidden), f"红线②④：不得暴露 {forbidden!r}"

    def test_trace_approval_forbidden(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        trace = eng.trace_knowledge_path("KI-TEST-0001")
        assert trace.approval_forbidden is True
        assert trace.requires_human_review is True

    def test_impact_no_fabrication(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        report = eng.impact_analysis("E-TH-01")
        # 红线⑤：不伪造工程参数；受影响阈值节点 value 仍为 pending
        th_node = g.get_node("E-TH-01")
        assert th_node.attributes["value"] == "pending_verification"
        # 受影响 Rule 仍为 pending_build 骨架
        assert g.get_node("RULE-1").pending_build is True
        assert report.approval_forbidden is True

    def test_conflict_review_required_always_true(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        cands = eng.conflict_scan()
        # 至少存在一个 pending_build_edge 冲突（RULE-1 applies KI）
        assert any(c.conflict_type == "pending_build_edge" for c in cands)
        for c in cands:
            assert c.review_required is True

    def test_conflict_reuses_detector_no_merge_delete(self):
        # 复用基础检测器；其无 merge/delete/approve（红线④延续）
        det = KnowledgeGraphConflictDetector()
        for method in ("merge", "delete", "approve", "auto_resolve"):
            assert not hasattr(det, method)

    def test_no_engineering_approved_output_anywhere(self):
        g = reasoning_graph()
        eng = KnowledgeGraphQueryEngine(g)
        trace = eng.trace_knowledge_path("KI-TEST-0001")
        report = eng.impact_analysis("E-TH-01")
        cands = eng.conflict_scan()
        blob = str(trace.to_dict()) + str(report.to_dict()) + str([c.to_dict() for c in cands])
        assert "engineering_approved" not in blob
        assert "approved" not in blob
