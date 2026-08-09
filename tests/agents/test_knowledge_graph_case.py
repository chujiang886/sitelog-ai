"""Case Knowledge Layer 测试（Phase 3.7.3 Task 6）。

覆盖（用户要求）：
1. Case Entity 测试    ：from_empty 空壳、to_node/from_node 往返、不伪造真实值、
                         真实字段默认空/PENDING_PLACEHOLDER、pending_build=True；
2. Graph 关系测试      ：3 条新关系（case_item / threshold_rule / rule_expert）注册、
                         起止约束正确、fail-closed 校验；
3. Query 测试          ：similar_case / case_path / case_impact / case_conflict_scan
                         候选正确、全只读；
4. Lifecycle 测试      ：Captured→Verified_Source→Expert_Reviewed→Engineering_Referenced
                         仅人工驱动、无 auto-advance / approve / merge / delete；
5. Red line 测试       ：5 红线全部守约（不开启 enabled / 不输出 approved / 不伪造案例 /
                         不生成真实参数 / 不自动批准案例规则）、冲突 review_required 恒 True。

红线约束：
- 全部用例使用内存图谱（无 store_path），绝不触碰磁盘 verified.json / engineering_enabled；
- 夹具一律使用纯标识符，不写任何真实 value、真实专家身份或真实案例内容；
- Case 真实字段默认空，AI 不编造（from_empty 仅占位）。
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.engineering.knowledge.connector import KnowledgeItem, PENDING_PLACEHOLDER
from agents.engineering.knowledge.graph import (
    CaseEntity,
    CaseImpactReport,
    CaseLifecycle,
    CaseLifecycleError,
    CaseLifecycleStage,
    CasePathReport,
    CaseSimilarityReport,
    GraphEdge,
    KnowledgeGraphQueryEngine,
    KnowledgeGraphRepository,
    RELATIONSHIP_SPECS,
    ReasoningConflictCandidate,
    RuleEntity,
    SourceRefEntity,
    ThresholdEntity,
    ExpertEntity,
    validate_edge,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.entities import KnowledgeItemEntity


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


def case_graph() -> KnowledgeGraphRepository:
    """构造含 Case 知识链路的完整可读图谱（纯标识符，无真实值）。

    CASE-1/CASE-2：经 case_item 关联 KI，linked_* 字段含 E-TH-01/RULE-1/EXP-1；
    CASE-A/CASE-B：同 project_ref+environment（用于重复冲突测试，无出边）。
    """
    repo = KnowledgeGraphRepository()
    repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="t")
    repo.add_node(ExpertEntity(expert_id="EXP-1").to_node(), actor="t")
    repo.add_node(SourceRefEntity(source_ref_id="SRC-1").to_node(), actor="t")
    repo.add_node(ThresholdEntity(threshold_id="E-TH-01", domain="wind_pressure").to_node(), actor="t")
    repo.add_node(RuleEntity(rule_id="RULE-1").to_node(), actor="t")  # pending_build=True
    repo.add_node(
        CaseEntity(
            case_id="CASE-1",
            linked_thresholds=["E-TH-01"],
            linked_rules=["RULE-1"],
            linked_experts=["EXP-1"],
        ).to_node(),
        actor="t",
    )
    repo.add_node(
        CaseEntity(case_id="CASE-2", linked_thresholds=["E-TH-01"]).to_node(), actor="t"
    )
    # 同 project_ref + environment 的重复案例（无出边）
    repo.add_node(CaseEntity(case_id="CASE-A", project_ref="PROJ-A", environment="site-X").to_node(), actor="t")
    repo.add_node(CaseEntity(case_id="CASE-B", project_ref="PROJ-A", environment="site-X").to_node(), actor="t")
    # 关系
    repo.add_edge(GraphEdge("e_auth", "authored_by", "KI-TEST-0001", "EXP-1", {}), actor="t")
    repo.add_edge(
        GraphEdge("e_src", "sourced_from", "KI-TEST-0001", "SRC-1",
                  {"standard": "GB 50009", "clause": "8.1.1"}), actor="t"
    )
    repo.add_edge(GraphEdge("e_basis", "basis", "KI-TEST-0001", "E-TH-01", {}), actor="t")
    repo.add_edge(GraphEdge("e_used", "used_by", "E-TH-01", "KI-TEST-0001", {}), actor="t")
    repo.add_edge(GraphEdge("e_applies", "applies", "RULE-1", "KI-TEST-0001", {}), actor="t")
    repo.add_edge(GraphEdge("e_case1", "case_item", "CASE-1", "KI-TEST-0001", {}), actor="t")
    repo.add_edge(GraphEdge("e_case2", "case_item", "CASE-2", "KI-TEST-0001", {}), actor="t")
    repo.add_edge(GraphEdge("e_tr", "threshold_rule", "E-TH-01", "RULE-1", {}), actor="t")
    repo.add_edge(GraphEdge("e_re", "rule_expert", "RULE-1", "EXP-1", {}), actor="t")
    return repo


# ---------------------------------------------------------------------------
# 1. Case Entity 测试
# ---------------------------------------------------------------------------
class TestCaseEntity:
    def test_from_empty_has_no_fabricated_values(self):
        ent = CaseEntity.from_empty("CASE-X")
        node = ent.to_node()
        assert node.entity_type == "Case"
        assert node.pending_build is True
        assert ent.status == "pending_build"
        assert ent.lifecycle_stage == "Captured"
        # 红线③：真实字段全部为空/PENDING_PLACEHOLDER
        assert ent.project_ref == ""
        assert ent.environment == ""
        assert ent.design_context == ""
        assert ent.solution == ""
        assert ent.outcome == ""
        assert ent.lessons == ""
        assert ent.title == PENDING_PLACEHOLDER
        assert ent.linked_thresholds == []
        assert ent.linked_rules == []
        assert ent.linked_experts == []

    def test_roundtrip_preserves_linked_fields(self):
        ent = CaseEntity(
            case_id="CASE-Y",
            project_ref="PROJ-1",
            environment="site-Y",
            design_context="ctx",
            solution="sol",
            outcome="out",
            lessons="les",
            linked_thresholds=["E-TH-01"],
            linked_rules=["RULE-1"],
            linked_experts=["EXP-1"],
            lifecycle_stage="Verified_Source",
        )
        node = ent.to_node()
        restored = CaseEntity.from_node(node)
        assert restored.case_id == "CASE-Y"
        assert restored.project_ref == "PROJ-1"
        assert restored.environment == "site-Y"
        assert restored.design_context == "ctx"
        assert restored.solution == "sol"
        assert restored.outcome == "out"
        assert restored.lessons == "les"
        assert restored.linked_thresholds == ["E-TH-01"]
        assert restored.linked_rules == ["RULE-1"]
        assert restored.linked_experts == ["EXP-1"]
        assert restored.lifecycle_stage == "Verified_Source"
        assert restored.status == "pending_build"

    def test_from_node_compatible_with_old_related_thresholds_key(self):
        # 兼容迁移：旧图节点仅含 related_thresholds 也能还原为 linked_thresholds
        node = CaseEntity(case_id="CASE-OLD").to_node()
        node.attributes["related_thresholds"] = ["E-TH-99"]
        node.attributes.pop("linked_thresholds", None)
        restored = CaseEntity.from_node(node)
        assert restored.linked_thresholds == ["E-TH-99"]

    def test_case_default_pending_build(self):
        ent = CaseEntity(case_id="CASE-Z")
        node = ent.to_node()
        assert node.pending_build is True
        assert CaseEntity.from_node(node).status == "pending_build"


# ---------------------------------------------------------------------------
# 2. Graph 关系测试（3 条新关系）
# ---------------------------------------------------------------------------
class TestCaseRelationships:
    def test_new_relations_registered(self):
        for rel in ("case_item", "threshold_rule", "rule_expert"):
            assert rel in RELATIONSHIP_SPECS

    def test_new_relation_from_to_constraints(self):
        assert RELATIONSHIP_SPECS["case_item"].from_entity.value == "Case"
        assert RELATIONSHIP_SPECS["case_item"].to_entity.value == "KnowledgeItem"
        assert RELATIONSHIP_SPECS["threshold_rule"].from_entity.value == "Threshold"
        assert RELATIONSHIP_SPECS["threshold_rule"].to_entity.value == "Rule"
        assert RELATIONSHIP_SPECS["rule_expert"].from_entity.value == "Rule"
        assert RELATIONSHIP_SPECS["rule_expert"].to_entity.value == "Expert"

    def test_case_item_validate_ok(self):
        repo = case_graph()
        validate_edge(repo.get_edge("e_case1"), repo._nodes)

    def test_case_item_wrong_to_type_raises(self):
        repo = case_graph()
        bad = GraphEdge("x", "case_item", "CASE-1", "EXP-1", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_threshold_rule_validate_ok(self):
        repo = case_graph()
        validate_edge(repo.get_edge("e_tr"), repo._nodes)

    def test_rule_expert_validate_ok(self):
        repo = case_graph()
        validate_edge(repo.get_edge("e_re"), repo._nodes)

    def test_unregistered_relation_still_raises(self):
        repo = case_graph()
        bad = GraphEdge("x", "not_a_relation", "CASE-1", "KI-TEST-0001", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)


# ---------------------------------------------------------------------------
# 3. Query 测试
# ---------------------------------------------------------------------------
class TestCaseQueries:
    def test_similar_case_returns_candidates(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        report = eng.similar_case("CASE-1")
        assert isinstance(report, CaseSimilarityReport)
        ids = {c["case_id"] for c in report.candidate_cases}
        assert "CASE-2" in ids  # CASE-2 共享 E-TH-01

    def test_similar_case_no_self_in_candidates(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        report = eng.similar_case("CASE-1")
        assert "CASE-1" not in {c["case_id"] for c in report.candidate_cases}

    def test_similar_case_requires_human_review(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        report = eng.similar_case("CASE-1")
        assert report.requires_human_review is True
        assert report.approval_forbidden is True

    def test_case_path_traces_full_chain(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        report = eng.case_path("CASE-1")
        assert isinstance(report, CasePathReport)
        assert report.knowledge_items == ["KI-TEST-0001"]
        assert report.thresholds == ["E-TH-01"]
        assert report.rules == ["RULE-1"]
        assert report.experts == ["EXP-1"]
        assert report.requires_human_review is True
        assert report.approval_forbidden is True

    def test_case_path_rejects_non_case(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        with pytest.raises(KeyError):
            eng.case_path("E-TH-01")

    def test_case_impact_collects_linked(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        report = eng.case_impact("CASE-1")
        assert isinstance(report, CaseImpactReport)
        assert report.affected_thresholds == ["E-TH-01"]
        assert report.affected_rules == ["RULE-1"]
        assert report.affected_knowledge_items == ["KI-TEST-0001"]
        assert report.requires_human_review is True
        assert report.approval_forbidden is True

    def test_case_impact_rejects_non_case(self):
        eng = KnowledgeGraphQueryEngine(case_graph())
        with pytest.raises(KeyError):
            eng.case_impact("KI-TEST-0001")

    def test_all_case_queries_are_read_only(self):
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        before = (g.node_count(), g.edge_count())
        eng.similar_case("CASE-1")
        eng.case_path("CASE-1")
        eng.case_impact("CASE-1")
        eng.case_conflict_scan()
        after = (g.node_count(), g.edge_count())
        assert before == after, "案例查询层任何方法都不得改动图谱（红线③）"


# ---------------------------------------------------------------------------
# 4. Lifecycle 测试
# ---------------------------------------------------------------------------
class TestCaseLifecycle:
    def test_initial_stage_is_captured(self):
        lc = CaseLifecycle(case_id="CASE-1")
        assert lc.stage == CaseLifecycleStage.CAPTURED.value
        assert lc.requires_human_review is True

    def test_advance_requires_human_reviewer(self):
        lc = CaseLifecycle(case_id="CASE-1")
        with pytest.raises(CaseLifecycleError):
            lc.advance()  # 红线⑤：AI 不得代推进

    def test_advance_human_ok(self):
        lc = CaseLifecycle(case_id="CASE-1")
        lc.advance(by_human_reviewer=True)
        assert lc.stage == CaseLifecycleStage.VERIFIED_SOURCE.value
        assert lc.requires_human_review is True

    def test_full_human_path_to_terminal(self):
        lc = CaseLifecycle(case_id="CASE-1")
        for _ in range(3):
            lc.advance(by_human_reviewer=True)
        assert lc.stage == CaseLifecycleStage.ENGINEERING_REFERENCED.value
        assert lc.can_advance() is False
        assert lc.next_stage() is None

    def test_advance_at_terminal_raises(self):
        lc = CaseLifecycle(case_id="CASE-1")
        for _ in range(3):
            lc.advance(by_human_reviewer=True)
        with pytest.raises(CaseLifecycleError):
            lc.advance(by_human_reviewer=True)

    def test_lifecycle_has_no_merge_delete_approve(self):
        for method in ("merge", "delete", "approve", "auto_resolve", "auto_advance"):
            assert not hasattr(CaseLifecycle, method), f"案例生命周期不得含 {method!r}（红线⑤）"

    def test_lifecycle_to_dict_shape(self):
        lc = CaseLifecycle(case_id="CASE-1")
        d = lc.to_dict()
        assert d["case_id"] == "CASE-1"
        assert d["stage"] == "Captured"
        assert d["can_advance"] is True
        assert d["next_stage"] == "Verified_Source"
        assert d["requires_human_review"] is True


# ---------------------------------------------------------------------------
# 5. Red line 测试
# ---------------------------------------------------------------------------
class TestCaseRedLines:
    def test_case_conflict_scan_reuses_detector(self):
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        cands = eng.case_conflict_scan()
        assert len(cands) >= 1
        for c in cands:
            assert isinstance(c, ReasoningConflictCandidate)
            assert c.review_required is True
            assert c.auto_resolvable is False

    def test_case_conflict_scan_detects_duplicate_project_env(self):
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        cands = eng.case_conflict_scan()
        assert any(c.conflict_type == "case_duplicate_project_env" for c in cands)

    def test_case_conflict_scan_no_merge_delete(self):
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        for forbidden in ("merge", "delete", "approve", "engineering_approved"):
            assert not hasattr(eng, forbidden), f"红线②④：案例冲突扫描不得暴露 {forbidden!r}"

    def test_case_queries_no_engineering_approved(self):
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        sim = eng.similar_case("CASE-1")
        path = eng.case_path("CASE-1")
        impact = eng.case_impact("CASE-1")
        cands = eng.case_conflict_scan()
        blob = (
            str(sim.to_dict())
            + str(path.to_dict())
            + str(impact.to_dict())
            + str([c.to_dict() for c in cands])
        )
        assert "engineering_approved" not in blob
        assert "approved" not in blob

    def test_no_fabricated_values_in_case_layer(self):
        g = case_graph()
        # 红线④：阈值 value 仍为 pending
        assert g.get_node("E-TH-01").attributes["value"] == "pending_verification"
        # 红线③：Case 仍为 pending_build 骨架
        assert g.get_node("CASE-1").pending_build is True
        # Rule 仍为 pending_build 骨架
        assert g.get_node("RULE-1").pending_build is True
        # 红线⑤：无真实计算主体被编造
        eng = KnowledgeGraphQueryEngine(g)
        impact = eng.case_impact("CASE-1")
        for c in impact.affected_agent_candidates:
            assert c.pending is True
            assert c.computation_body == "pending_verification"

    def test_construction_asserts_red_lines(self):
        # config.yaml 真实 engineering_enabled=False → 构造成功（红线①）
        g = case_graph()
        eng = KnowledgeGraphQueryEngine(g)
        assert eng is not None
