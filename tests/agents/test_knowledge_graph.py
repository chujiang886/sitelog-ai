"""Knowledge Graph Foundation 测试（Phase 3.7.1 Task 6 + Phase 3.7.4 方案生成层扩展）。

覆盖（用户要求）：
1. schema 测试   ：7 实体类型齐全、17 关系规格齐全、起止实体约束正确、必需属性正确；
2. entity 测试   ：七实体 to_node/from_node 往返；Case/Rule/SolutionCandidate 标 pending_build=True；不伪造值；
3. relationship 测试：边校验 fail-closed（类型不符/节点缺失/未注册/缺必需属性一律抛错）；
4. audit 测试    ：add_node/add_edge 记审计、history 返回、update 递增版本、禁止 merge/delete/approve；
5. red line 测试 ：engineering_enabled=False（只读断言）、冲突 review_required 恒 True、
                   冲突检测器无 merge/delete/approve 方法、不写 verified.json、单向往 Repository 不回写。

红线约束：
- 禁止修改 verified.json value（全部用例使用内存图谱，不传 store_path，绝不触碰磁盘 verified.json）；
- 禁止开启 engineering_enabled（safety_invariants_ok 只读断言）；
- 禁止输出 engineering_approved、禁止自动 merge/delete/approve；
- 夹具一律使用纯标识符（SRC-1 / EXP-1 / E-TH-01 / KI-TEST-* / SOL-1），不写任何真实 value 或真实专家身份。
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.engineering.knowledge.connector import KnowledgeItem
from agents.engineering.knowledge.graph import (
    CaseEntity,
    ExpertEntity,
    GraphEdge,
    GraphNode,
    KnowledgeGraphConflictDetector,
    KnowledgeGraphEntityType,
    KnowledgeGraphRelationType,
    KnowledgeGraphRepository,
    KnowledgeItemEntity,
    RELATIONSHIP_SPECS,
    RuleEntity,
    SourceRefEntity,
    SolutionCandidateEntity,
    ThresholdEntity,
    validate_edge,
)
from agents.engineering.knowledge.graph.repository import (
    FORBIDDEN_GRAPH_EVENT_TYPES,
)
from agents.engineering.knowledge.repository import KnowledgeRepository
from agents.engineering.knowledge.graph import KnowledgeRepositoryToGraphSync
from agents.engineering.thresholds.schema import ThresholdStatus

EXPECTED_ENTITY_TYPES = [
    "KnowledgeItem",
    "Case",
    "Rule",
    "Threshold",
    "Expert",
    "SourceRef",
    "SolutionCandidate",
]
EXPECTED_RELATIONS = [
    "references",
    "authored_by",
    "parent_child",
    "sourced_from",
    "used_by",
    "applies",
    "cites",
    "basis",
    "witnessed_by",
    "signs",
    "case_item",
    "threshold_rule",
    "rule_expert",
    "solution_case",
    "solution_rule",
    "solution_threshold",
    "solution_knowledge_item",
]

# 关系 → (from, to) 期望约束
EXPECTED_FROM_TO = {
    "references": ("KnowledgeItem", "KnowledgeItem"),
    "authored_by": ("KnowledgeItem", "Expert"),
    "parent_child": ("KnowledgeItem", "KnowledgeItem"),
    "sourced_from": ("KnowledgeItem", "SourceRef"),
    "used_by": ("Threshold", "KnowledgeItem"),
    "applies": ("Rule", "KnowledgeItem"),
    "cites": ("KnowledgeItem", "SourceRef"),
    "basis": ("KnowledgeItem", "Threshold"),
    "witnessed_by": ("KnowledgeItem", "Expert"),
    "signs": ("Expert", "KnowledgeItem"),
    "case_item": ("Case", "KnowledgeItem"),
    "threshold_rule": ("Threshold", "Rule"),
    "rule_expert": ("Rule", "Expert"),
    "solution_case": ("SolutionCandidate", "Case"),
    "solution_rule": ("SolutionCandidate", "Rule"),
    "solution_threshold": ("SolutionCandidate", "Threshold"),
    "solution_knowledge_item": ("SolutionCandidate", "KnowledgeItem"),
}


# ---------------------------------------------------------------------------
# 夹具
# ---------------------------------------------------------------------------
def make_item(knowledge_id: str = "KI-TEST-0001", **overrides: Any) -> KnowledgeItem:
    """构造确定性 KnowledgeItem（纯标识符，无真实 value）。"""
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


def populated_graph() -> KnowledgeGraphRepository:
    """构造一个含 KI/Expert/SourceRef/Threshold 节点与三边的内存图谱。"""
    repo = KnowledgeGraphRepository()
    repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="t")
    repo.add_node(ExpertEntity(expert_id="EXP-1").to_node(), actor="t")
    repo.add_node(SourceRefEntity(source_ref_id="SRC-1").to_node(), actor="t")
    repo.add_node(ThresholdEntity(threshold_id="E-TH-01", domain="wind_pressure").to_node(), actor="t")
    repo.add_edge(
        GraphEdge("e1", "authored_by", "KI-TEST-0001", "EXP-1", {}), actor="t"
    )
    repo.add_edge(
        GraphEdge("e2", "sourced_from", "KI-TEST-0001", "SRC-1",
                  {"standard": "GB 50009", "clause": "8.1.1"}), actor="t"
    )
    repo.add_edge(
        GraphEdge("e3", "basis", "KI-TEST-0001", "E-TH-01", {}), actor="t"
    )
    return repo


# ---------------------------------------------------------------------------
# 1. schema 测试
# ---------------------------------------------------------------------------
class TestKnowledgeGraphSchema:
    def test_entity_types_complete(self):
        assert KnowledgeGraphEntityType.all_values() == EXPECTED_ENTITY_TYPES

    def test_relation_specs_complete(self):
        assert set(RELATIONSHIP_SPECS.keys()) == set(EXPECTED_RELATIONS)
        assert len(RELATIONSHIP_SPECS) == 17

    def test_relation_from_to_constraints(self):
        for rel, (frm, to) in EXPECTED_FROM_TO.items():
            spec = RELATIONSHIP_SPECS[rel]
            assert spec.from_entity.value == frm, rel
            assert spec.to_entity.value == to, rel

    def test_sourced_from_required_attrs(self):
        spec = RELATIONSHIP_SPECS["sourced_from"]
        assert "standard" in spec.required_attrs
        assert "clause" in spec.required_attrs

    def test_relation_enum_values_match(self):
        assert set(KnowledgeGraphRelationType.all_values()) == set(EXPECTED_RELATIONS)


# ---------------------------------------------------------------------------
# 2. entity 测试
# ---------------------------------------------------------------------------
class TestKnowledgeGraphEntities:
    def test_knowledge_item_roundtrip(self):
        node = KnowledgeItemEntity(make_item()).to_node()
        assert node.entity_type == "KnowledgeItem"
        restored = KnowledgeItemEntity.from_node(node)
        assert restored.item.knowledge_id == "KI-TEST-0001"
        assert restored.item.domain == "wind_pressure"

    def test_threshold_value_stays_pending(self):
        ent = ThresholdEntity(threshold_id="E-TH-01", domain="wind_pressure")
        node = ent.to_node()
        assert node.entity_type == "Threshold"
        assert node.attributes["value"] == "pending_verification"
        assert node.attributes["status"] == ThresholdStatus.DRAFT.value

    def test_expert_roundtrip(self):
        ent = ExpertEntity(expert_id="EXP-1", domains=["wind_pressure"], qualification_status="pending")
        node = ent.to_node()
        assert node.entity_type == "Expert"
        assert ExpertEntity.from_node(node).expert_id == "EXP-1"

    def test_source_ref_roundtrip(self):
        ent = SourceRefEntity(source_ref_id="SRC-1")
        node = ent.to_node()
        assert node.entity_type == "SourceRef"
        assert node.attributes["source_ref_id"] == "SRC-1"

    def test_case_pending_build_flag(self):
        ent = CaseEntity(case_id="CASE-1")
        node = ent.to_node()
        assert node.entity_type == "Case"
        assert node.pending_build is True
        assert ent.from_node(node).status == "pending_build"

    def test_rule_pending_build_flag(self):
        ent = RuleEntity(rule_id="RULE-1")
        node = ent.to_node()
        assert node.entity_type == "Rule"
        assert node.pending_build is True
        assert ent.from_node(node).expression == "pending_verification"

    def test_all_seven_entities_build_nodes(self):
        ents = [
            KnowledgeItemEntity(make_item()),
            ThresholdEntity(threshold_id="E-TH-02"),
            ExpertEntity(expert_id="EXP-2"),
            SourceRefEntity(source_ref_id="SRC-2"),
            CaseEntity(case_id="CASE-2"),
            RuleEntity(rule_id="RULE-2"),
            SolutionCandidateEntity(solution_id="SOL-2"),
        ]
        types = {e.to_node().entity_type for e in ents}
        assert types == set(EXPECTED_ENTITY_TYPES)

    def test_solution_candidate_pending_build_flag(self):
        ent = SolutionCandidateEntity(solution_id="SOL-1")
        node = ent.to_node()
        assert node.entity_type == "SolutionCandidate"
        assert node.pending_build is True
        assert node.attributes["components"] == "pending_verification"
        assert node.attributes["confidence"] == "pending"
        assert node.attributes["verification_status"] == "pending_verification"
        restored = ent.from_node(node)
        assert restored.solution_id == "SOL-1"
        assert restored.status == "pending_build"


# ---------------------------------------------------------------------------
# 3. relationship 测试（fail-closed）
# ---------------------------------------------------------------------------
class TestKnowledgeGraphRelationships:
    def test_edge_validation_ok(self):
        repo = populated_graph()
        # 已收敛，validate 不应抛
        validate_edge(repo.get_edge("e2"), repo._nodes)

    def test_wrong_from_type_raises(self):
        repo = populated_graph()
        bad = GraphEdge("x", "authored_by", "KI-TEST-0001", "SRC-1", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_wrong_to_type_raises(self):
        repo = populated_graph()
        bad = GraphEdge("x", "authored_by", "EXP-1", "KI-TEST-0001", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_missing_node_raises(self):
        repo = populated_graph()
        bad = GraphEdge("x", "authored_by", "KI-TEST-0001", "EXP-999", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_unregistered_relation_raises(self):
        repo = populated_graph()
        bad = GraphEdge("x", "not_a_relation", "KI-TEST-0001", "EXP-1", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_missing_required_attr_raises(self):
        repo = populated_graph()
        # sourced_from 缺 standard/clause
        bad = GraphEdge("x", "sourced_from", "KI-TEST-0001", "SRC-1", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_add_edge_rejects_constraint_violation(self):
        repo = populated_graph()
        with pytest.raises(ValueError):
            repo.add_edge(
                GraphEdge("bad", "authored_by", "KI-TEST-0001", "SRC-1", {}), actor="t"
            )


# ---------------------------------------------------------------------------
# 4. audit 测试
# ---------------------------------------------------------------------------
class TestKnowledgeGraphAudit:
    def test_add_node_records_audit(self):
        repo = KnowledgeGraphRepository()
        repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="tester")
        assert repo.node_count() == 1
        evs = repo.history("KI-TEST-0001")
        assert len(evs) == 1
        assert evs[0].action == "add_node"
        assert evs[0].actor == "tester"

    def test_add_edge_records_audit(self):
        repo = populated_graph()
        evs = repo.history("e2")
        assert len(evs) == 1
        assert evs[0].action == "add_edge"

    def test_update_increments_version_and_audit(self):
        repo = KnowledgeGraphRepository()
        v1 = repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="t")
        v2 = repo.add_node(KnowledgeItemEntity(make_item()).to_node(), actor="t")
        assert v1 == 1 and v2 == 2
        assert len(repo.history("KI-TEST-0001")) == 2

    def test_forbidden_audit_action_rejected(self):
        repo = KnowledgeGraphRepository()
        for forbidden in FORBIDDEN_GRAPH_EVENT_TYPES:
            with pytest.raises(ValueError):
                repo.audit_log.record("X", forbidden, actor="t")

    def test_query_filters(self):
        repo = populated_graph()
        assert len(repo.query(entity_type="KnowledgeItem")) == 1
        assert len(repo.query(entity_type="Expert")) == 1
        assert len(repo.query(node_id_prefix="KI-")) == 1
        assert len(repo.query(pending_build_only=True)) == 0

    def test_traverse_bfs(self):
        repo = populated_graph()
        out = repo.traverse("KI-TEST-0001", direction="out")
        targets = {t["node_id"] for t in out}
        assert targets == {"EXP-1", "SRC-1", "E-TH-01"}
        rels = {t["relation_type"] for t in out}
        assert rels == {"authored_by", "sourced_from", "basis"}


# ---------------------------------------------------------------------------
# 5. red line 测试
# ---------------------------------------------------------------------------
class TestKnowledgeGraphRedLines:
    def test_safety_invariants_ok(self):
        # 真实读取 config.yaml：engineering_enabled 必须为 False
        assert KnowledgeGraphRepository.safety_invariants_ok() is True

    def test_conflict_review_required_always_true(self):
        repo = populated_graph()
        reports = KnowledgeGraphConflictDetector().detect(repo)
        for r in reports:
            assert r.review_required is True

    def test_conflict_detector_has_no_merge_delete_approve(self):
        det = KnowledgeGraphConflictDetector()
        for method in ("merge", "delete", "approve", "auto_resolve"):
            assert not hasattr(det, method), f"冲突检测器不应含 {method} 方法（红线）"

    def test_detect_does_not_mutate_graph(self):
        repo = populated_graph()
        before = (repo.node_count(), repo.edge_count())
        KnowledgeGraphConflictDetector().detect(repo)
        after = (repo.node_count(), repo.edge_count())
        assert before == after

    def test_no_fabricated_values(self):
        # Threshold.value 恒 pending；Case/Rule 不填真实值
        assert ThresholdEntity(threshold_id="E-TH-X").to_node().attributes["value"] == "pending_verification"
        assert CaseEntity(case_id="CASE-X").to_node().pending_build is True
        assert RuleEntity(rule_id="RULE-X").to_node().attributes["expression"] == "pending_verification"

    def test_duplicate_node_flagged(self):
        repo = KnowledgeGraphRepository()
        repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="KI-A", title="Dup")).to_node(), actor="t")
        repo.add_node(KnowledgeItemEntity(make_item(knowledge_id="KI-B", title="Dup")).to_node(), actor="t")
        reports = KnowledgeGraphConflictDetector().detect(repo)
        assert any(r.conflict_type == "duplicate_node" for r in reports)
        for r in reports:
            assert r.review_required is True

    def test_integration_single_direction_no_writeback(self):
        kr = KnowledgeRepository()
        kr.save(make_item(), actor="t")
        before = kr.item_count()
        kg = KnowledgeGraphRepository()
        KnowledgeRepositoryToGraphSync(kg).sync_item(kr, "KI-TEST-0001")
        # Repository 仍为唯一事实源，图谱同步不得回写/改动它
        assert kr.item_count() == before
        # 图谱新增了派生节点（Expert/SourceRef/Threshold）但 Repository 未变
        assert kg.node_count() >= 1

    def test_integration_no_fabrication_on_pending(self):
        kr = KnowledgeRepository()
        pending_item = make_item(
            knowledge_id="KI-PEND",
            source="pending_verification",
            author="pending_verification",
            linked_entities=["pending_verification"],
            parent_knowledge_id="pending_verification",
        )
        kr.save(pending_item, actor="t")
        kg = KnowledgeGraphRepository()
        touched = KnowledgeRepositoryToGraphSync(kg).sync_item(kr, "KI-PEND")
        # 仅 KnowledgeItem 节点入图，无编造边/存根
        assert kg.node_count() == 1
        assert kg.edge_count() == 0
        assert len(touched) == 1
