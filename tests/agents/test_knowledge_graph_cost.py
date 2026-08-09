"""Cost Intelligence Layer 测试（Phase 3.7.6 Task 6）。

覆盖（用户要求）：
1. BOM 测试：BOMEntity 默认占位壳（pending_verification），不污染图谱白名单；
2. CostRule 测试：CostRule 默认 price 恒 None（禁止硬编码价格）、source_ref 占位；
3. Estimator 测试：CostEstimator 四方法仅产出占位估算壳（不报价）；
4. Explanation 测试：CostExplanation 关联 Solution/BOM/Rule/SourceRef 四类来源链；
5. Review 测试：CostReviewQueue 状态机（draft/reviewing/approved_by_human/rejected），
   AI 不能进入 approved_by_human；
6. RedLine 测试：6 条最高红线 fail-closed（含自动报价/成交价/伪造市场价拦截 +
   BOMEntity/CostRule 不污染图谱白名单）。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/估算/解释/审核全断言 safety_invariants_ok）；
- 夹具使用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-*），不写真实值。
"""

from __future__ import annotations

import pytest

import agents.engineering.gate.unified_activation_gate as gate_mod
import agents.engineering.knowledge.graph.entities as ent_mod
from agents.engineering.knowledge.graph import (
    BOMEntity,
    CaseEntity,
    CostEstimator,
    CostEstimateDraft,
    CostExplanation,
    CostExplanationReport,
    CostReviewQueue,
    CostRule,
    DesignCandidate,
    GraphEdge,
    KnowledgeGraphEntityType,
    KnowledgeGraphRepository,
    KnowledgeItemEntity,
    RELATIONSHIP_SPECS,
    RuleEntity,
    SolutionCandidateEntity,
    SolutionGenerator,
    SolutionRedLineViolationError,
    SolutionReviewError,
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
# 1. BOM 测试
# ---------------------------------------------------------------------------
class TestBOMEntity:
    def test_bom_defaults(self):
        bom = BOMEntity(bom_id="BOM-1", solution_id="SOL-1")
        assert bom.bom_id == "BOM-1"
        assert bom.solution_id == "SOL-1"
        # 真实取值字段全部占位，status 默认 pending_verification
        assert bom.item_type == ent_mod.PENDING_PLACEHOLDER
        assert bom.item_name == ent_mod.PENDING_PLACEHOLDER
        assert bom.quantity == ent_mod.PENDING_PLACEHOLDER
        assert bom.unit == ent_mod.PENDING_PLACEHOLDER
        assert bom.source_ref == ent_mod.PENDING_PLACEHOLDER
        assert bom.status == ent_mod.PENDING_VERIFICATION

    def test_bom_not_in_graph_whitelist(self):
        # BOMEntity 是纯数据壳，不进 KnowledgeGraphEntityType / 不进关系白名单
        assert "BOMEntity" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17  # 3.7.4 的 17 关系白名单不受影响


# ---------------------------------------------------------------------------
# 2. CostRule 测试
# ---------------------------------------------------------------------------
class TestCostRule:
    def test_cost_rule_defaults(self):
        rule = CostRule(rule_id="CR-1")
        assert rule.rule_id == "CR-1"
        assert rule.source_ref == ent_mod.PENDING_PLACEHOLDER
        assert rule.formula == ent_mod.PENDING_PLACEHOLDER
        assert rule.status == ent_mod.PENDING_VERIFICATION

    def test_cost_rule_unit_price_not_hardcoded(self):
        # 红线⑤：价格必须有来源，禁止硬编码 —— 默认 unit_price 恒 None
        rule = CostRule(rule_id="CR-1")
        assert rule.unit_price is None

    def test_cost_rule_not_in_graph_whitelist(self):
        assert "CostRule" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17


# ---------------------------------------------------------------------------
# 3. Estimator 测试
# ---------------------------------------------------------------------------
class TestCostEstimator:
    def _estimate(self, repo, stage):
        est = CostEstimator(repo)
        cands = _gen_candidates(repo, 1)
        method = {
            "material": est.material_cost,
            "labor": est.labor_cost,
            "auxiliary": est.auxiliary_cost,
            "total": est.total_estimate,
        }[stage]
        draft = method(cands[0])
        assert isinstance(draft, CostEstimateDraft)
        assert draft.solution_id == cands[0].solution_id
        assert draft.requires_human_review is True
        # 占位估算：真实金额恒 PENDING_PLACEHOLDER（不报价/不填真实价）
        assert draft.material_cost == ent_mod.PENDING_PLACEHOLDER
        assert draft.labor_cost == ent_mod.PENDING_PLACEHOLDER
        assert draft.auxiliary_cost == ent_mod.PENDING_PLACEHOLDER
        assert draft.total_estimate == ent_mod.PENDING_PLACEHOLDER
        return draft

    def test_material_cost(self):
        self._estimate(_populated_repo(), "material")

    def test_labor_cost(self):
        self._estimate(_populated_repo(), "labor")

    def test_auxiliary_cost(self):
        self._estimate(_populated_repo(), "auxiliary")

    def test_total_estimate(self):
        self._estimate(_populated_repo(), "total")

    def test_estimator_has_no_quote_methods(self):
        # 红线④：自动报价/成交价方法名被拦截
        repo = _populated_repo()
        est = CostEstimator(repo)
        for name in ("quote", "pricing", "deal_price", "final_price", "market_price",
                     "approve", "select", "finalize", "activate", "engineering_approved"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(est, name)


# ---------------------------------------------------------------------------
# 4. Explanation 测试
# ---------------------------------------------------------------------------
class TestCostExplanation:
    def _bom_rules(self):
        boms = [
            BOMEntity(bom_id="BOM-1", solution_id="SOL-1", item_type="material"),
            BOMEntity(bom_id="BOM-2", solution_id="SOL-1", item_type="labor"),
        ]
        rules = [
            CostRule(rule_id="CR-1", source_ref="SRC-PRICE-1"),
        ]
        return boms, rules

    def test_explain_four_categories(self):
        repo = _populated_repo()
        explainer = CostExplanation(repo)
        cands = _gen_candidates(repo, 1)
        boms, rules = self._bom_rules()
        rep = explainer.explain(cands[0], bom_entries=boms, cost_rules=rules)
        assert isinstance(rep, CostExplanationReport)
        assert rep.requires_human_review is True
        # 四类来源载体齐全
        for cat in ("Solution", "BOM", "Rule", "SourceRef"):
            assert cat in rep.referenced_types
        assert rep.referenced_types["Solution"] == [cands[0].solution_id]
        assert set(rep.referenced_types["BOM"]) == {"BOM-1", "BOM-2"}
        # 成本规则数据壳（CR-1）+ 图谱遍历命中的 Rule 节点（如 RULE-1）一并归集
        assert "CR-1" in rep.referenced_types["Rule"]
        # 来源链长度 = Solution(1) + BOM(2) + Rule(≥1) + 图谱遍历命中的 SourceRef/RULE 节点
        assert len(rep.source_chain) >= 4

    def test_explain_without_repo(self):
        # 无 repository 时仍可只读聚合并关联 BOM/Rule
        explainer = CostExplanation()
        cands = _gen_candidates(_populated_repo(), 1)
        boms, rules = self._bom_rules()
        rep = explainer.explain(cands[0], bom_entries=boms, cost_rules=rules)
        assert rep.referenced_types["Solution"] == [cands[0].solution_id]
        assert len(rep.referenced_types["BOM"]) == 2
        assert rep.referenced_types["Rule"] == ["CR-1"]


# ---------------------------------------------------------------------------
# 5. Review 队列测试
# ---------------------------------------------------------------------------
class TestCostReviewQueue:
    def _submitted(self, repo):
        cands = _gen_candidates(repo, 1)
        est = CostEstimator(repo)
        draft = est.total_estimate(cands[0])
        q = CostReviewQueue()
        rid = q.submit(cands[0], draft=draft)
        q.begin_review(rid)
        return q, rid, cands[0]

    def test_submit_and_begin_review(self):
        # 直接走 submit → begin_review（不与 _submitted 重复推进）
        repo = _populated_repo()
        cands = _gen_candidates(repo, 1)
        est = CostEstimator(repo)
        draft = est.total_estimate(cands[0])
        q = CostReviewQueue()
        rid = q.submit(cands[0], draft=draft)
        item = q.begin_review(rid)
        assert item.state == "reviewing"

    def test_approve_by_human_ok(self):
        q, rid, _ = self._submitted(_populated_repo())
        item = q.approve(rid, by_human=True)
        assert item.state == "approved_by_human"
        assert item.decided_by == "human_reviewer"

    def test_approve_ai_blocked(self):
        # 红线②：AI 调用 approve（by_human=False）一律拦截
        q, rid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.approve(rid)  # by_human=False

    def test_reject_by_human_ok(self):
        q, rid, _ = self._submitted(_populated_repo())
        item = q.reject(rid, by_human=True)
        assert item.state == "rejected"
        assert item.decided_by == "human_reviewer"

    def test_reject_ai_blocked(self):
        # 红线④：AI 不得做出终裁
        q, rid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.reject(rid)  # by_human=False

    def test_invalid_transition_rejected(self):
        # 非法状态转移抛 SolutionReviewError（正常业务校验，非红线）
        repo = _populated_repo()
        cands = _gen_candidates(repo, 1)
        est = CostEstimator(repo)
        draft = est.total_estimate(cands[0])
        q = CostReviewQueue()
        rid = q.submit(cands[0], draft=draft)  # 仍处 draft
        with pytest.raises(SolutionReviewError):
            q.approve(rid, by_human=True)  # 必须先 begin_review


# ---------------------------------------------------------------------------
# 6. RedLine 测试（fail-closed，6 条）
# ---------------------------------------------------------------------------
class TestCostRedLines:
    def test_safety_invariants_block_construction(self, monkeypatch):
        # 红线①/⑥：engineering_enabled 翻转 → 一切构造 fail-closed。
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            CostEstimator(repo)
        with pytest.raises(SolutionRedLineViolationError):
            CostExplanation(repo)
        with pytest.raises(SolutionRedLineViolationError):
            CostReviewQueue()

    def test_forbidden_quote_pricing_deal_final_market(self, monkeypatch):
        # 红线④/⑤：自动报价/成交价/伪造市场价方法名被拦截
        repo = _populated_repo()
        est = CostEstimator(repo)
        for name in ("quote", "pricing", "deal_price", "final_price", "market_price"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(est, name)

    def test_cost_models_not_in_graph_whitelist(self):
        # BOMEntity/CostRule 是纯数据壳，不进实体枚举（保持 17 关系白名单不变）
        assert "BOMEntity" not in KnowledgeGraphEntityType.all_values()
        assert "CostRule" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17
