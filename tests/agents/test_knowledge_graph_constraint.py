"""Solution Constraint & Optimization Layer 测试（Phase 3.7.5 Task 6）。

覆盖（用户要求）：
1. constraint 测试：SolutionConstraintEngine 四检查（geometry/dependency/compatibility/conflict）仅过滤明显冲突；
2. comparison 测试：SolutionComparison 比较 A/B/C，输出 difference/risk/knowledge_trace，winner 恒 None；
3. explain 测试：SolutionExplanation 构建 Case/Rule/Threshold/KnowledgeItem 完整来源链；
4. review 测试：SolutionReviewQueue 扩展 constraint_review / expert_review / human_decision 三阶段，AI 不能进入；
5. red line 测试：6 条最高红线 fail-closed（含新增自动报价拦截 + SolutionConstraint 不污染图谱白名单）。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/检查/解释全断言 safety_invariants_ok）；
- 夹具使用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-*），不写真实值。
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
    KnowledgeGraphRepository,
    KnowledgeItemEntity,
    RELATIONSHIP_SPECS,
    RuleEntity,
    SolutionCandidateEntity,
    SolutionComparison,
    SolutionComparisonReport,
    SolutionConstraint,
    SolutionConstraintEngine,
    SolutionConstraintReport,
    SolutionExplanation,
    SolutionExplanationReport,
    SolutionGenerator,
    SolutionRedLineViolationError,
    SolutionReviewError,
    SolutionReviewQueue,
    ThresholdEntity,
)
from agents.engineering.knowledge.connector import KnowledgeItem


# ---------------------------------------------------------------------------
# 夹具：构建一个含 Case/Rule/Threshold/KnowledgeItem 的内存图谱（CASE-1/2/3）
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
    for cid in ("CASE-1", "CASE-2", "CASE-3"):
        repo.add_node(
            CaseEntity(
                case_id=cid,
                linked_thresholds=["E-TH-01"] if cid == "CASE-1" else [],
                linked_rules=["RULE-1"] if cid == "CASE-1" else [],
            ).to_node(),
            actor="t",
        )
    repo.add_edge(GraphEdge("c1", "case_item", "CASE-1", "KI-TEST-0001", {}), actor="t")
    return repo


def _design() -> DesignCandidate:
    return DesignCandidate(
        design_id="D-1",
        components=[],
        metadata={"context": "placeholder design context"},
        constraints=[],
    )


def _gen_candidates(repo: KnowledgeGraphRepository, n: int = 3) -> list[SolutionCandidateEntity]:
    gen = SolutionGenerator(repo)
    cases = [CaseEntity.from_node(repo.get_node(f"CASE-{i}")) for i in range(1, n + 1)]
    return gen.generate(_design(), cases=cases, persist=True)


# ---------------------------------------------------------------------------
# 1. constraint 测试
# ---------------------------------------------------------------------------
class TestSolutionConstraint:
    def test_constraint_model_defaults(self):
        con = SolutionConstraint(constraint_id="CON-1")
        # 占位壳默认值：type/source/severity/description = PENDING_PLACEHOLDER，
        # status = PENDING_VERIFICATION（两者同值 "pending_verification"，语义独立）。
        assert con.type == ent_mod.PENDING_PLACEHOLDER
        assert con.source == ent_mod.PENDING_PLACEHOLDER
        assert con.severity == ent_mod.PENDING_PLACEHOLDER
        assert con.description == ent_mod.PENDING_PLACEHOLDER
        assert con.status == ent_mod.PENDING_VERIFICATION

    def test_engine_geometry_detects_duplicate(self):
        repo = _populated_repo()
        engine = SolutionConstraintEngine(repo)
        cands = _gen_candidates(repo, 2)
        dup = SolutionCandidateEntity(solution_id=cands[0].solution_id, input_context="X")
        rep = engine.check_geometry(cands + [dup])
        assert isinstance(rep, SolutionConstraintReport)
        assert rep.requires_human_review is True
        assert rep.has_conflicts is True
        assert any("duplicate_solution_id" in c[1] for c in rep.conflicts)

    def test_engine_dependency_detects_missing_ref(self):
        repo = _populated_repo()
        engine = SolutionConstraintEngine(repo)
        bad = SolutionCandidateEntity(solution_id="SOL-BAD", related_cases=["CASE-999"])
        rep = engine.check_dependency([bad])
        assert rep.has_conflicts is True
        assert any("missing_case" in c[1] for c in rep.conflicts)

    def test_engine_compatibility_pending_only(self):
        repo = _populated_repo()
        engine = SolutionConstraintEngine(repo)
        cands = _gen_candidates(repo, 2)
        cons = [SolutionConstraint(constraint_id="CON-1")]
        rep = engine.check_compatibility(cands, cons)
        assert rep.requires_human_review is True
        # 候选未转正 → 标 pending，不判定违反（无确定 conflict）
        assert rep.has_conflicts is False

    def test_engine_conflict_detects_context_mismatch(self):
        repo = _populated_repo()
        engine = SolutionConstraintEngine(repo)
        a = SolutionCandidateEntity(solution_id="SOL-DUP", input_context="ctxA")
        b = SolutionCandidateEntity(solution_id="SOL-DUP", input_context="ctxB")
        rep = engine.check_conflict([a, b])
        assert rep.has_conflicts is True
        assert any("conflicting_context_same_id" in c[1] for c in rep.conflicts)


# ---------------------------------------------------------------------------
# 2. comparison 测试
# ---------------------------------------------------------------------------
class TestSolutionComparison:
    def test_compare_outputs_no_winner(self):
        repo = _populated_repo()
        comp = SolutionComparison(repo)
        cands = _gen_candidates(repo, 3)
        rep = comp.compare(cands)
        assert isinstance(rep, SolutionComparisonReport)
        assert rep.winner is None
        assert rep.requires_human_review is True
        assert len(rep.difference) == 3
        assert len(rep.candidate_ids) == 3

    def test_compare_knowledge_trace_present(self):
        repo = _populated_repo()
        comp = SolutionComparison(repo)
        cands = _gen_candidates(repo, 1)
        rep = comp.compare(cands)
        assert any(t["entity_type"] == "Case" for t in rep.knowledge_trace)

    def test_comparison_has_no_finish_methods(self):
        repo = _populated_repo()
        comp = SolutionComparison(repo)
        for name in ("select", "finalize", "approve", "quote", "pricing", "engineering_approved"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(comp, name)


# ---------------------------------------------------------------------------
# 3. explain 测试
# ---------------------------------------------------------------------------
class TestSolutionExplanation:
    def test_explain_builds_source_chain(self):
        repo = _populated_repo()
        explainer = SolutionExplanation(repo)
        cands = _gen_candidates(repo, 1)
        rep = explainer.explain(cands[0])
        assert isinstance(rep, SolutionExplanationReport)
        assert rep.requires_human_review is True
        assert "Case" in rep.referenced_types
        assert len(rep.referenced_types["Case"]) >= 1

    def test_explain_references_four_types(self):
        repo = _populated_repo()
        explainer = SolutionExplanation(repo)
        cands = _gen_candidates(repo, 1)  # CASE-1 挂 Threshold/Rule/KnowledgeItem
        rep = explainer.explain(cands[0])
        for t in ("Case", "Rule", "Threshold", "KnowledgeItem"):
            assert t in rep.referenced_types


# ---------------------------------------------------------------------------
# 4. review queue（三阶段扩展）测试
# ---------------------------------------------------------------------------
class TestSolutionReviewQueueV2:
    def _submitted(self, repo):
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        q = SolutionReviewQueue()
        sid = q.submit(cand)
        q.begin_review(sid)
        return q, sid, cand

    def test_constraint_review_human_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        sub = q.record_constraint_review(sid, by_human=True)
        assert sub.constraint_review_done is True
        assert sub.review_stage == "expert"

    def test_constraint_review_ai_blocked(self):
        q, sid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.record_constraint_review(sid)

    def test_expert_review_requires_constraint_first(self):
        q, sid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionReviewError):
            q.record_expert_review(sid, by_human=True)

    def test_expert_review_human_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        q.record_constraint_review(sid, by_human=True)
        sub = q.record_expert_review(sid, by_human=True)
        assert sub.expert_review_done is True
        assert sub.review_stage == "human_decision"

    def test_human_decision_requires_both_reviews(self):
        q, sid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionReviewError):
            q.human_decision(sid, by_human=True, approve=True)

    def test_human_decision_ai_blocked(self):
        q, sid, _ = self._submitted(_populated_repo())
        q.record_constraint_review(sid, by_human=True)
        q.record_expert_review(sid, by_human=True)
        with pytest.raises(SolutionRedLineViolationError):
            q.human_decision(sid, approve=True)  # by_human 默认 False

    def test_human_decision_approve_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        q.record_constraint_review(sid, by_human=True)
        q.record_expert_review(sid, by_human=True)
        sub = q.human_decision(sid, by_human=True, approve=True)
        assert sub.state == "approved_by_human"
        assert sub.decided_by == "human_reviewer"

    def test_human_decision_reject_ok(self):
        q, sid, _ = self._submitted(_populated_repo())
        q.record_constraint_review(sid, by_human=True)
        q.record_expert_review(sid, by_human=True)
        sub = q.human_decision(sid, by_human=True, approve=False)
        assert sub.state == "rejected"


# ---------------------------------------------------------------------------
# 5. red line 测试（fail-closed，6 条）
# ---------------------------------------------------------------------------
class TestSolutionConstraintRedLines:
    def test_safety_invariants_block_construction(self, monkeypatch):
        # 红线①/⑥：engineering_enabled 翻转 → 一切构造 fail-closed。
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            SolutionConstraintEngine(repo)
        with pytest.raises(SolutionRedLineViolationError):
            SolutionComparison(repo)
        with pytest.raises(SolutionRedLineViolationError):
            SolutionExplanation(repo)

    def test_forbidden_quote_pricing(self, monkeypatch):
        # 红线④：自动报价方法名被拦截
        repo = _populated_repo()
        engine = SolutionConstraintEngine(repo)
        comp = SolutionComparison(repo)
        for obj, name in (
            (engine, "quote"),
            (engine, "pricing"),
            (comp, "quote"),
            (comp, "pricing"),
        ):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(obj, name)

    def test_review_queue_forbidden_without_human(self):
        # 红线②/③：三阶段审查与终裁均需 by_human=True，AI 调用一律拦截
        repo = _populated_repo()
        gen = SolutionGenerator(repo)
        cand = gen.generate(_design(), cases=[CaseEntity.from_node(repo.get_node("CASE-1"))])[0]
        q = SolutionReviewQueue()
        sid = q.submit(cand)
        q.begin_review(sid)
        with pytest.raises(SolutionRedLineViolationError):
            q.record_constraint_review(sid)  # by_human=False
        with pytest.raises(SolutionRedLineViolationError):
            q.record_expert_review(sid, by_human=False)
        with pytest.raises(SolutionRedLineViolationError):
            q.human_decision(sid, approve=True)  # by_human=False

    def test_solution_constraint_not_in_graph_whitelist(self):
        # SolutionConstraint 是纯数据壳，不进 KnowledgeGraphEntityType / 不进关系白名单
        assert "SolutionConstraint" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17  # 3.7.4 的 17 关系白名单不受影响
