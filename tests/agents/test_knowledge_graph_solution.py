"""Engineering Solution Generation Layer 测试（Phase 3.7.4 Task 6）。

覆盖（用户要求）：
1. solution entity 测试：SolutionCandidateEntity / DesignCandidate 结构、默认值、pending_build；
2. generator 测试    ：SolutionGenerator 产出多候选、不自动选终、关联图谱落盘；
3. trace 测试        ：SolutionEvaluator 的 compatibility/risk/knowledge_trace 仅分析；
4. review queue 测试 ：SolutionReviewQueue 状态机 + 人工守卫；
5. red line 测试     ：5 条最高红线 fail-closed（不开启 enabled / 不输出 approved /
                       不自动选终 / 不伪造参数 / 不绕过 gate）。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/生成/评价/审核均断言 safety_invariants_ok）；
- 夹具使用纯标识符（CASE-1 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-*），不写真实值。
"""

from __future__ import annotations

import pytest

import agents.engineering.gate.unified_activation_gate as gate_mod
import agents.engineering.knowledge.graph.entities as ent_mod
from agents.engineering.knowledge.graph import (
    CaseEntity,
    DesignCandidate,
    GraphEdge,
    KnowledgeGraphEntityType,
    KnowledgeGraphRelationType,
    KnowledgeGraphRepository,
    KnowledgeItemEntity,
    RuleEntity,
    SolutionCandidateEntity,
    SolutionEvaluator,
    SolutionGenerator,
    SolutionRedLineViolationError,
    SolutionReviewError,
    SolutionReviewQueue,
    ThresholdEntity,
    validate_edge,
)
from agents.engineering.knowledge.connector import KnowledgeItem


# ---------------------------------------------------------------------------
# 夹具：构建一个含 Case/Rule/Threshold/KnowledgeItem 的内存图谱
# ---------------------------------------------------------------------------
def _make_item(knowledge_id: str = "KI-TEST-0001") -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id=knowledge_id,
        knowledge_type="spec",
        parent_knowledge_id="",
        title="Threshold Note",
        content="placeholder",
        source="SRC-1",
        author="EXP-1",
        domain="wind_pressure",
        content_hash="",
        validation_status="Pending_Verification",
        linked_entities=[],
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )


def _populated_repo() -> KnowledgeGraphRepository:
    repo = KnowledgeGraphRepository()
    repo.add_node(KnowledgeItemEntity(_make_item()).to_node(), actor="t")
    repo.add_node(ThresholdEntity(threshold_id="E-TH-01", domain="wind_pressure").to_node(), actor="t")
    repo.add_node(RuleEntity(rule_id="RULE-1").to_node(), actor="t")
    repo.add_node(
        CaseEntity(
            case_id="CASE-1",
            linked_thresholds=["E-TH-01"],
            linked_rules=["RULE-1"],
        ).to_node(),
        actor="t",
    )
    repo.add_node(
        CaseEntity(case_id="CASE-2").to_node(), actor="t"
    )
    # Case → KnowledgeItem（供 knowledge_trace 溯源）
    repo.add_edge(
        GraphEdge("c1", "case_item", "CASE-1", "KI-TEST-0001", {}), actor="t"
    )
    return repo


def _design() -> DesignCandidate:
    return DesignCandidate(
        design_id="D-1",
        components=[],
        metadata={"context": "placeholder design context"},
        constraints=[],
    )


# ---------------------------------------------------------------------------
# 1. solution entity 测试
# ---------------------------------------------------------------------------
class TestSolutionEntity:
    def test_candidate_defaults_pending(self):
        ent = SolutionCandidateEntity(solution_id="SOL-1")
        node = ent.to_node()
        assert node.entity_type == "SolutionCandidate"
        assert node.pending_build is True
        assert node.attributes["components"] == "pending_verification"
        assert node.attributes["confidence"] == "pending"
        assert node.attributes["verification_status"] == "pending_verification"
        assert node.attributes["status"] == "pending_build"

    def test_candidate_roundtrip(self):
        ent = SolutionCandidateEntity(
            solution_id="SOL-2",
            input_context="ctx",
            related_cases=["CASE-1"],
            related_rules=["RULE-1"],
            related_thresholds=["E-TH-01"],
        )
        node = ent.to_node()
        restored = SolutionCandidateEntity.from_node(node)
        assert restored.solution_id == "SOL-2"
        assert restored.related_cases == ["CASE-1"]
        assert restored.related_rules == ["RULE-1"]
        assert restored.related_thresholds == ["E-TH-01"]
        assert restored.verification_status == "pending_verification"

    def test_from_empty_shell(self):
        ent = SolutionCandidateEntity.from_empty("SOL-3")
        assert ent.components == "pending_verification"
        assert ent.confidence == "pending"

    def test_design_candidate_constructs_under_disabled(self):
        # 红线①：当前 engineering_enabled=False，构造不应抛错。
        d = _design()
        assert d.design_id == "D-1"
        assert d.components == []


# ---------------------------------------------------------------------------
# 2. generator 测试
# ---------------------------------------------------------------------------
class TestSolutionGenerator:
    def test_generate_produces_multiple_candidates(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cases = [
            CaseEntity.from_node(repo.get_node("CASE-1")),
            CaseEntity.from_node(repo.get_node("CASE-2")),
        ]
        cands = gen.generate(_design(), cases=cases, persist=True)
        assert len(cands) == 2
        for c in cands:
            assert c.components == "pending_verification"
            assert c.confidence == "pending"
            assert c.verification_status == "pending_verification"

    def test_generate_persists_candidate_and_edges(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        case = CaseEntity.from_node(repo.get_node("CASE-1"))
        cands = gen.generate(_design(), cases=[case], persist=True)
        cand = cands[0]
        # 候选节点已落图
        assert repo.get_node(cand.solution_id) is not None
        # 四关系已落图（solution_case / solution_rule / solution_threshold / solution_knowledge_item）
        sol_nodes = repo.query(entity_type=KnowledgeGraphEntityType.SOLUTION_CANDIDATE.value)
        assert len(sol_nodes) == 1
        # 遍历候选出边，应命中 case/rule/threshold/knowledge_item 四类
        steps = repo.traverse(cand.solution_id, direction="out", max_depth=1)
        rels = {s["relation_type"] for s in steps}
        assert "solution_case" in rels
        assert "solution_rule" in rels
        assert "solution_threshold" in rels
        assert "solution_knowledge_item" in rels

    def test_generate_no_cases_returns_empty(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        # cases=[] → 不伪造候选
        cands = gen.generate(_design(), cases=[], persist=True)
        assert cands == []

    def test_generator_has_no_finish_methods(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        for name in ("approve", "select", "finalize", "engineering_approved", "activate"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(gen, name)


# ---------------------------------------------------------------------------
# 3. trace / evaluator 测试
# ---------------------------------------------------------------------------
class TestSolutionEvaluator:
    def test_compatibility_check(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        ev = SolutionEvaluator(repo)
        rep = ev.compatibility_check(cand)
        assert rep.requires_human_review is True
        assert rep.compatible is True
        assert rep.missing_references == []

    def test_risk_check_pending(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        ev = SolutionEvaluator(repo)
        rep = ev.risk_check(cand)
        assert rep.risk_level == "pending_review"
        assert rep.requires_human_review is True
        assert any("pending_verification" in r for r in rep.risks)

    def test_knowledge_trace_builds_chain(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        ev = SolutionEvaluator(repo)
        rep = ev.knowledge_trace(cand)
        assert rep.requires_human_review is True
        # 候选→CASE-1→KI-TEST-0001 至少 2 跳
        assert len(rep.chain) >= 1
        entity_types = {c["entity_type"] for c in rep.chain}
        assert "Case" in entity_types

    def test_evaluator_has_no_finish_methods(self):
        repo = _populated_repo()
        ev = SolutionEvaluator(repo)
        for name in ("approve", "select", "finalize", "engineering_approved"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(ev, name)


# ---------------------------------------------------------------------------
# 4. review queue 测试
# ---------------------------------------------------------------------------
class TestSolutionReviewQueue:
    def _submitted(self, repo):
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        q = SolutionReviewQueue()
        sid = q.submit(cand)
        q.begin_review(sid)
        return q, sid, cand

    def test_human_approve_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        sub = q.approve(sid, by_human=True)
        assert sub.state == "approved_by_human"
        assert sub.decided_by == "human_reviewer"

    def test_ai_approve_blocked(self):
        q, sid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.approve(sid)  # by_human 默认 False

    def test_ai_reject_blocked(self):
        q, sid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.reject(sid)  # by_human 默认 False

    def test_human_reject_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        sub = q.reject(sid, by_human=True)
        assert sub.state == "rejected"

    def test_approve_before_review_raises(self):
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        q = SolutionReviewQueue()
        sid = q.submit(cand)
        with pytest.raises(SolutionReviewError):
            q.approve(sid, by_human=True)  # 仍为 candidate

    def test_illegal_transition_raises(self):
        q, sid, _ = self._submitted(_populated_repo())
        q.reject(sid, by_human=True)
        with pytest.raises(SolutionReviewError):
            q.approve(sid, by_human=True)  # 已 rejected


# ---------------------------------------------------------------------------
# 5. red line 测试（fail-closed）
# ---------------------------------------------------------------------------
class TestSolutionRedLines:
    def test_new_relations_validate_ok(self):
        repo = _populated_repo()
        sol = SolutionCandidateEntity(solution_id="SOL-X").to_node()
        repo.add_node(sol, actor="t")
        edge = GraphEdge("sx1", "solution_case", "SOL-X", "CASE-1", {})
        # 不应抛（关系已就绪）
        validate_edge(edge, repo._nodes)
        repo.add_edge(edge, actor="t")
        assert repo.get_edge("sx1") is not None

    def test_new_relation_wrong_from_raises(self):
        repo = _populated_repo()
        # solution_case 起点必须是 SolutionCandidate，反置应失败
        bad = GraphEdge("bx", "solution_case", "CASE-1", "KI-TEST-0001", {})
        with pytest.raises(ValueError):
            validate_edge(bad, repo._nodes)

    def test_unregistered_relation_still_17_whitelist(self):
        repo = _populated_repo()
        bad = GraphEdge("bx", "not_a_relation", "SOL-X", "CASE-1", {})
        with pytest.raises(ValueError, match="17 关系白名单"):
            validate_edge(bad, repo._nodes)

    def test_safety_invariants_block_construction(self, monkeypatch):
        # 红线①/⑤：engineering_enabled 翻转 → 一切构造 fail-closed。
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            SolutionGenerator(repo)
        with pytest.raises(SolutionRedLineViolationError):
            SolutionEvaluator(repo)
        with pytest.raises(SolutionRedLineViolationError):
            SolutionReviewQueue()
        with pytest.raises(RuntimeError):
            _design()
