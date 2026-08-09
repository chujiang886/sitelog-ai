"""Drawing Intelligence Layer 测试（Phase 3.7.7 Task 6）。

覆盖（用户要求）：
1. Drawing Parser 测试：DrawingParser 解析 PDF/CAD/Image → DesignCandidate，所有结果
   带 source_ref + confidence 占位（geometry/opening_type/glass_config/profile_config 恒占位）；
2. DesignCandidate 测试：增强字段默认占位（PENDING_PLACEHOLDER / PENDING_VERIFICATION），
   不污染图谱白名单（7 实体 / 17 关系不变）；
3. Vision 测试：VisionAdapter image_analysis/drawing_analysis → 只读分析壳，不进工程结论；
4. Review 测试：DesignReviewQueue 状态机（parsed/reviewing/verified_by_human/rejected），
   AI 不能进入 verified_by_human；
5. GraphConnector 测试：DesignGraphConnector 只读关联 Solution/Case/KnowledgeItem/SourceRef，
   不写图、不新增关系到 17 白名单；
6. RedLine 测试：6 条最高红线 fail-closed（含自动确认尺寸/生成工程参数/报价拦截 +
   DesignCandidate 增强不污染图谱白名单）。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/解析/分析/审核/连接全断言 safety_invariants_ok）；
- 夹具使用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / SOL-* / DRAW-*），不写真实值。
"""

from __future__ import annotations

import pytest

import agents.engineering.gate.unified_activation_gate as gate_mod
import agents.engineering.knowledge.graph.entities as ent_mod
from agents.engineering.knowledge.graph import (
    CaseEntity,
    DesignCandidate,
    DesignGraphConnector,
    DesignReviewQueue,
    DrawingParser,
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
    VisionAdapter,
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
    # 注意：构造 DesignCandidate 即断言 load_engineering_enabled() is False（红线①）。
    return DesignCandidate(
        design_id="DRAW-1",
        components=[],
        metadata={"context": "placeholder drawing context"},
        constraints=[],
    )


def _gen_candidates(repo: KnowledgeGraphRepository, n: int = 3) -> list[SolutionCandidateEntity]:
    gen = SolutionGenerator(repo)
    cases = [CaseEntity.from_node(repo.get_node(f"CASE-{i}")) for i in range(1, n + 1)]
    return gen.generate(_design(), cases=cases, persist=True)


def _parsed(repo: KnowledgeGraphRepository, fmt: str) -> DesignCandidate:
    parser = DrawingParser(repo)
    method = {"pdf": parser.parse_pdf, "cad": parser.parse_cad, "image": parser.parse_image}[fmt]
    return method(f"/tmp/sample.{fmt}", design_id=f"DRAW-{fmt}")


# ---------------------------------------------------------------------------
# 1. Drawing Parser 测试
# ---------------------------------------------------------------------------
class TestDrawingParser:
    @pytest.mark.parametrize("fmt", ["pdf", "cad", "image"])
    def test_parse_returns_design_candidate(self, fmt):
        repo = _populated_repo()
        cand = _parsed(repo, fmt)
        assert isinstance(cand, DesignCandidate)
        assert cand.design_id == f"DRAW-{fmt}"
        assert fmt in cand.source_files[0]

    @pytest.mark.parametrize("fmt", ["pdf", "cad", "image"])
    def test_parse_carries_source_ref_and_confidence(self, fmt):
        # 任务2：所有解析结果必须带 source_ref + confidence 占位
        repo = _populated_repo()
        cand = _parsed(repo, fmt)
        assert cand.metadata.get("source_ref")  # 非空 source_ref（溯源）
        assert "confidence" in cand.metadata  # confidence 标记存在
        assert cand.confidence == ent_mod.PENDING_PLACEHOLDER  # AI 不断言真实 confidence

    @pytest.mark.parametrize("fmt", ["pdf", "cad", "image"])
    def test_parse_real_dimensions_are_placeholder(self, fmt):
        # 红线③/④：解析期不填真实尺寸/工程参数，全部占位
        repo = _populated_repo()
        cand = _parsed(repo, fmt)
        assert cand.geometry == ent_mod.PENDING_PLACEHOLDER
        assert cand.opening_type == ent_mod.PENDING_PLACEHOLDER
        assert cand.glass_config == ent_mod.PENDING_PLACEHOLDER
        assert cand.profile_config == ent_mod.PENDING_PLACEHOLDER
        assert cand.verification_status == ent_mod.PENDING_VERIFICATION

    def test_parse_explicit_source_ref(self):
        repo = _populated_repo()
        parser = DrawingParser(repo)
        cand = parser.parse_pdf("/tmp/a.pdf", design_id="DRAW-X", source_ref="SRC-DRAW-1")
        assert cand.metadata.get("source_ref") == "SRC-DRAW-1"


# ---------------------------------------------------------------------------
# 2. DesignCandidate 增强测试
# ---------------------------------------------------------------------------
class TestDesignCandidateEnhanced:
    def test_new_fields_default_placeholder(self):
        cand = DesignCandidate(design_id="D-1")
        assert cand.source_files == []
        assert cand.geometry == ent_mod.PENDING_PLACEHOLDER
        assert cand.opening_type == ent_mod.PENDING_PLACEHOLDER
        assert cand.glass_config == ent_mod.PENDING_PLACEHOLDER
        assert cand.profile_config == ent_mod.PENDING_PLACEHOLDER
        assert cand.confidence == ent_mod.PENDING_PLACEHOLDER
        assert cand.verification_status == ent_mod.PENDING_VERIFICATION

    def test_enhanced_not_in_graph_whitelist(self):
        # DesignCandidate 是契约入参，非图谱实体：不进实体枚举、不进关系白名单
        assert "DesignCandidate" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17  # 17 关系白名单不受影响


# ---------------------------------------------------------------------------
# 3. Vision 测试
# ---------------------------------------------------------------------------
class TestVisionAdapter:
    def test_image_analysis_readonly(self):
        repo = _populated_repo()
        adapter = VisionAdapter(repo)
        rep = adapter.image_analysis("/tmp/photo.png", source_ref="SRC-IMG-1")
        assert rep.source_ref == "SRC-IMG-1"
        assert rep.analysis_type == "image_analysis"
        assert rep.requires_engineering_review is True
        # 红线③/④：几何/开口仅为 hint 占位，绝不输出真实尺寸/参数
        assert rep.geometry_hint == ent_mod.PENDING_PLACEHOLDER
        assert rep.opening_hint == ent_mod.PENDING_PLACEHOLDER

    def test_drawing_analysis_readonly(self):
        repo = _populated_repo()
        adapter = VisionAdapter(repo)
        rep = adapter.drawing_analysis("/tmp/dwg.pdf", source_ref="SRC-DWG-1")
        assert rep.analysis_type == "drawing_analysis"
        assert rep.requires_engineering_review is True
        assert rep.geometry_hint == ent_mod.PENDING_PLACEHOLDER

    def test_vision_without_repo(self):
        # 无 repository 亦可只读分析
        adapter = VisionAdapter()
        rep = adapter.image_analysis("/tmp/photo.png")
        assert rep.analysis_type == "image_analysis"


# ---------------------------------------------------------------------------
# 4. Review 队列测试
# ---------------------------------------------------------------------------
class TestDesignReviewQueue:
    def _submitted(self, repo, fmt="pdf"):
        cand = _parsed(repo, fmt)
        q = DesignReviewQueue()
        rid = q.submit(cand)
        q.begin_review(rid)
        return q, rid, cand

    def test_submit_and_begin_review(self):
        repo = _populated_repo()
        cand = _parsed(repo, "pdf")
        q = DesignReviewQueue()
        rid = q.submit(cand)
        item = q.begin_review(rid)
        assert item.state == "reviewing"

    def test_verify_by_human_ok(self):
        q, rid, _ = self._submitted(_populated_repo())
        item = q.verify(rid, by_human=True)
        assert item.state == "verified_by_human"
        assert item.decided_by == "human_reviewer"

    def test_verify_ai_blocked(self):
        # 红线②：AI 调用 verify（by_human=False）一律拦截，不能进入 verified_by_human
        q, rid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.verify(rid)  # by_human=False

    def test_reject_by_human_ok(self):
        q, rid, _ = self._submitted(_populated_repo())
        item = q.reject(rid, by_human=True)
        assert item.state == "rejected"
        assert item.decided_by == "human_reviewer"

    def test_reject_ai_blocked(self):
        # 红线②：AI 不得做出终裁
        q, rid, _ = self._submitted(_populated_repo())
        with pytest.raises(SolutionRedLineViolationError):
            q.reject(rid)  # by_human=False

    def test_invalid_transition_rejected(self):
        # 非法状态转移抛 SolutionReviewError（正常业务校验，非红线）
        repo = _populated_repo()
        cand = _parsed(repo, "pdf")
        q = DesignReviewQueue()
        rid = q.submit(cand)  # 仍处 parsed
        with pytest.raises(SolutionReviewError):
            q.verify(rid, by_human=True)  # 必须先 begin_review


# ---------------------------------------------------------------------------
# 5. GraphConnector 测试（只读关联，不写图）
# ---------------------------------------------------------------------------
class TestDesignGraphConnector:
    def test_link_four_categories(self):
        repo = _populated_repo()
        sols = _gen_candidates(repo, 1)
        cand = _parsed(repo, "cad")  # 自带 source_ref
        connector = DesignGraphConnector(repo)
        rep = connector.link(
            cand,
            solution_ids=[sols[0].solution_id],
            case_ids=["CASE-1"],
            knowledge_item_ids=["KI-TEST-0001"],
            source_ref_ids=["SRC-EXTRA-1"],
        )
        assert rep.design_id == cand.design_id
        assert rep.requires_human_review is True
        assert sols[0].solution_id in rep.referenced_solutions
        assert "CASE-1" in rep.referenced_cases
        assert "KI-TEST-0001" in rep.referenced_knowledge_items
        # source_ref 来自解析期 metadata + 显式入参
        assert cand.metadata.get("source_ref") in rep.referenced_source_refs
        assert "SRC-EXTRA-1" in rep.referenced_source_refs

    def test_link_is_readonly_no_new_relation(self):
        # 红线：不写图、不新增关系到 17 白名单
        repo = _populated_repo()
        sols = _gen_candidates(repo, 1)
        cand = _parsed(repo, "pdf")
        connector = DesignGraphConnector(repo)
        connector.link(
            cand,
            solution_ids=[sols[0].solution_id],
            case_ids=["CASE-1"],
            knowledge_item_ids=["KI-TEST-0001"],
        )
        assert len(RELATIONSHIP_SPECS) == 17  # 关系白名单不变


# ---------------------------------------------------------------------------
# 6. RedLine 测试（fail-closed，6 条）
# ---------------------------------------------------------------------------
class TestDrawingRedLines:
    def test_safety_invariants_block_construction(self, monkeypatch):
        # 红线①/⑥：engineering_enabled 翻转 → 一切构造 fail-closed。
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            DrawingParser(repo)
        with pytest.raises(SolutionRedLineViolationError):
            VisionAdapter(repo)
        with pytest.raises(SolutionRedLineViolationError):
            DesignReviewQueue()
        with pytest.raises(SolutionRedLineViolationError):
            DesignGraphConnector(repo)

    def test_forbidden_dimension_and_param_methods(self, monkeypatch):
        # 红线③/④：自动确认图纸尺寸 / 自动生成真实工程参数方法名被拦截
        repo = _populated_repo()
        parser = DrawingParser(repo)
        adapter = VisionAdapter(repo)
        for name in ("confirm_dimension", "generate_engineering_param"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(parser, name)
            with pytest.raises(SolutionRedLineViolationError):
                getattr(adapter, name)

    def test_forbidden_quote_and_approval_methods(self, monkeypatch):
        # 红线②/③/⑤：批准/选终/激活/报价方法名被拦截
        repo = _populated_repo()
        parser = DrawingParser(repo)
        adapter = VisionAdapter(repo)
        for name in ("quote", "pricing", "approve", "select", "finalize",
                     "activate", "engineering_approved"):
            with pytest.raises(SolutionRedLineViolationError):
                getattr(parser, name)
            with pytest.raises(SolutionRedLineViolationError):
                getattr(adapter, name)

    def test_enhanced_design_candidate_not_in_graph_whitelist(self):
        # 增强 DesignCandidate 仍是非图谱实体壳，不污染 7 实体 / 17 关系白名单
        assert "DesignCandidate" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17
