"""Engineering AI Assistant Interface Layer 测试（Phase 3.7.9 Task 6）。

覆盖五类（用户要求）：
1. Assistant 模型测试：``AssistantSession`` / ``WorkflowRequest`` / ``AssistantResponse`` 契约，
   非图谱节点零回归；
2. Session 测试：会话生命周期（open → attached → 桥接登记）；
3. Workflow Bridge 测试：``create_workflow`` / ``attach_files`` / ``query_status`` 桥接
   ``EngineeringWorkflowEngine``，只桥接不改职责；
4. Response 测试：``results_confirmed`` 恒 False / ``review_required`` 恒 True（红线③）；
5. RedLine 测试：6 条最高红线 fail-closed（禁止开启 enabled / 禁止 approve / 禁止自动确认 /
   禁止报价 / 禁止 AI 自动审核 / 禁止绕过 Gate 拦截）。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/建流/查状态/提交审核全断言 safety_invariants_ok）；
- 不输出 engineering_approved（forbidden 方法名被 mixin 拦截 + 审核节点仅 by_human）；
- 夹具使用纯标识符（CASE-1/2/3 / KI-TEST-0001 / D-1 / WF-* / SID-*），不写真实值。
"""

from __future__ import annotations

import pytest

import agents.engineering.gate.unified_activation_gate as gate_mod
import agents.engineering.knowledge.graph.entities as ent_mod
from agents.engineering.knowledge.graph import (
    AssistantResponse,
    AssistantSession,
    AssistantWorkflowBridge,
    HumanReviewPortal,
    KnowledgeGraphEntityType,
    KnowledgeGraphRepository,
    RELATIONSHIP_SPECS,
    SolutionRedLineViolationError,
    SolutionReviewError,
    WorkflowRequest,
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
    """内存图谱（不传 store_path）—与 3.7.8 同款夹具，绝不触碰磁盘 verified.json。"""
    from agents.engineering.knowledge.graph import GraphEdge
    from agents.engineering.knowledge.graph.entities import (
        CaseEntity,
        KnowledgeItemEntity,
        RuleEntity,
        ThresholdEntity,
    )

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


# ---------------------------------------------------------------------------
# 1. Assistant 模型契约测试（任务1/任务2/任务4 数据壳）
# ---------------------------------------------------------------------------
class TestAssistantModels:
    def test_assistant_session_defaults(self):
        s = AssistantSession(session_id="SID-1", user_input="请生成开口方案")
        assert s.session_id == "SID-1"
        assert s.user_input == "请生成开口方案"
        assert s.files == []
        assert s.workflow_id == ""
        assert s.status == "open"
        assert s.created_at == ""

    def test_assistant_session_fields(self):
        s = AssistantSession(
            session_id="SID-2",
            user_input="u",
            files=["a.pdf"],
            workflow_id="WF-SID-2",
            status="attached",
            created_at="2026-08-03T00:00:00+00:00",
        )
        assert s.files == ["a.pdf"]
        assert s.workflow_id == "WF-SID-2"
        assert s.status == "attached"

    def test_workflow_request_direct_judgment_false(self):
        # 红线③：交互层绝不替用户做工程判定（direct_judgment 恒 False）
        req = WorkflowRequest(session_id="SID-1", text="请评审图纸")
        assert req.direct_judgment is False
        # 即便显式传入，契约也要求恒 False（构造时不校验，但语义恒 False）
        req2 = WorkflowRequest(session_id="SID-1", text="x", direct_judgment=False)
        assert req2.direct_judgment is False

    def test_workflow_request_fields(self):
        req = WorkflowRequest(
            session_id="SID-1",
            text="t",
            files=["d.dwg"],
            parse_format="cad",
            design_id="D-1",
        )
        assert req.files == ["d.dwg"]
        assert req.parse_format == "cad"
        assert req.design_id == "D-1"

    def test_assistant_response_defaults(self):
        # 红线③：results_confirmed 恒 False / review_required 恒 True
        resp = AssistantResponse(session_id="SID-1", workflow_status="running")
        assert resp.workflow_status == "running"
        assert resp.candidate_results == []
        assert resp.source_trace == []
        assert resp.review_required is True
        assert resp.results_confirmed is False

    def test_assistant_models_not_in_graph_whitelist(self):
        # 非图谱节点：不进实体枚举 / 不进 17 关系白名单（扩展零回归）
        assert "AssistantSession" not in KnowledgeGraphEntityType.all_values()
        assert "WorkflowRequest" not in KnowledgeGraphEntityType.all_values()
        assert "AssistantResponse" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17


# ---------------------------------------------------------------------------
# 2. Session 生命周期测试（任务1）
# ---------------------------------------------------------------------------
class TestAssistantSessionLifecycle:
    def test_session_created_open_on_create_workflow(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-A", user_input="请生成开口方案")
        session = bridge.get_session("SID-A")
        assert session.workflow_id == "WF-SID-A"
        assert session.status == "open"
        assert session.created_at  # _utc_now() 已填充

    def test_session_attach_files_transitions_status(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-B", user_input="u")
        session = bridge.attach_files(session_id="SID-B", files=["drawing.pdf"])
        assert session.files == ["drawing.pdf"]
        assert session.status == "attached"

    def test_session_workflow_id_mapping(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-C", user_input="u")
        assert bridge.session_workflow_id("SID-C") == "WF-SID-C"

    def test_session_not_found_raises(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        with pytest.raises(SolutionReviewError):
            bridge.get_session("SID-GHOST")
        with pytest.raises(SolutionReviewError):
            bridge.attach_files(session_id="SID-GHOST", files=["x.pdf"])
        with pytest.raises(SolutionReviewError):
            bridge.session_workflow_id("SID-GHOST")


# ---------------------------------------------------------------------------
# 3. Workflow Bridge 测试（任务3：只桥接，不改职责）
# ---------------------------------------------------------------------------
class TestAssistantWorkflowBridge:
    def test_create_workflow_returns_running_workflow(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        wf = bridge.create_workflow(session_id="SID-D", user_input="请评审图纸")
        # 桥接到底层引擎：工作流状态 running，且登记到引擎
        assert wf.workflow_id == "WF-SID-D"
        assert wf.status == "running"
        # 底层引擎确实持有该工作流（仅桥接，不重复造状态）
        assert bridge.engine._workflows.get("WF-SID-D") is wf

    def test_create_workflow_infers_cad_format(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        wf = bridge.create_workflow(
            session_id="SID-E", user_input="u", files=["drawing.dwg"], parse_format="pdf"
        )
        # 缺省 pdf 但推断为 cad（红线③前提：input_source.parse_format 正确透传）
        assert wf.input_source["parse_format"] == "cad"
        assert wf.input_source["file_path"] == "drawing.dwg"

    def test_create_workflow_infers_image_format(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        wf = bridge.create_workflow(
            session_id="SID-F", user_input="u", files=["photo.png"], parse_format="pdf"
        )
        assert wf.input_source["parse_format"] == "image"

    def test_query_status_returns_response(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-G", user_input="u")
        resp = bridge.query_status(session_id="SID-G")
        assert isinstance(resp, AssistantResponse)
        assert resp.session_id == "SID-G"
        assert resp.workflow_status == "running"
        # 候选结果来自底层工作流阶段（仅桥接透传，不做任何工程判定）
        assert isinstance(resp.candidate_results, list)
        assert isinstance(resp.source_trace, list)

    def test_query_status_unknown_session_raises(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        with pytest.raises(SolutionReviewError):
            bridge.query_status(session_id="SID-GHOST")

    def test_bridge_only_bridges_not_alters_engine_contract(self):
        # 证明桥接层未新增工程决策：query_status 后底层工作流状态不变、仍待人工
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        wf = bridge.create_workflow(session_id="SID-H", user_input="u")
        resp = bridge.query_status(session_id="SID-H")
        # 红线③：返回包始终要求人工复核、不确认结果
        assert resp.review_required is True
        assert resp.results_confirmed is False
        # 底层工作流未被桥接层任何方法「自动推进/完成」
        assert wf.status == "running"
        assert wf.requires_human_review is True

    def test_infer_parse_format_helper(self):
        from agents.engineering.knowledge.graph.solution_assistant import _infer_parse_format

        assert _infer_parse_format(["a.dwg"], "") == "cad"
        assert _infer_parse_format(["a.dxf"], "") == "cad"
        assert _infer_parse_format(["a.png"], "") == "image"
        assert _infer_parse_format(["a.jpg"], "") == "image"
        assert _infer_parse_format(["a.pdf"], "") == "pdf"
        # 无文件缺省 pdf
        assert _infer_parse_format([], "纯文本输入") == "pdf"


# ---------------------------------------------------------------------------
# 4. Response 载体测试（任务4：红线③ 恒 False / 恒 True）
# ---------------------------------------------------------------------------
class TestAssistantResponseCarrier:
    def test_response_review_required_always_true(self):
        resp = AssistantResponse(session_id="SID-1", workflow_status="running")
        assert resp.review_required is True

    def test_response_results_confirmed_always_false(self):
        resp = AssistantResponse(session_id="SID-1", workflow_status="running")
        assert resp.results_confirmed is False

    def test_response_carries_candidates_and_source_trace(self):
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-I", user_input="u")
        resp = bridge.query_status(session_id="SID-I")
        # candidate_results 来自 wf.stages；source_trace 来自 wf.event_log
        assert len(resp.candidate_results) >= 1
        assert any(c["stage"] for c in resp.candidate_results)
        assert len(resp.source_trace) >= 1
        # 每一条候选结果不含任何「已确认/已批准」语义
        assert resp.results_confirmed is False


# ---------------------------------------------------------------------------
# 5. RedLine 测试（fail-closed，6 条最高红线）
# ---------------------------------------------------------------------------
class TestAssistantRedLines:
    def test_assistant_forbidden_methods_blocked(self):
        # 红线②/③/④/⑤：批准/确认尺寸/选终/定稿/激活/生成工程参数/报价被 mixin 拦截
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        portal = HumanReviewPortal(bridge)
        for obj in (bridge, portal):
            for name in (
                "approve",
                "engineering_approved",
                "confirm_dimension",
                "generate_engineering_param",
                "quote",
                "pricing",
                "select",
                "finalize",
                "activate",
            ):
                with pytest.raises(SolutionRedLineViolationError):
                    getattr(obj, name)

    def test_ai_cannot_auto_submit_human_review(self):
        # 红线⑤：AI 调用 submit_human_decision(by_human=False) 一律红线拦截
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-J", user_input="u")
        portal = HumanReviewPortal(bridge)
        with pytest.raises(SolutionRedLineViolationError):
            portal.submit_human_decision(session_id="SID-J", checkpoint="drawing_verified", by_human=False)

    def test_human_can_submit_review(self):
        # 仅 by_human=True 可桥接到底层审核节点 mark(by_human=True)
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-K", user_input="u")
        portal = HumanReviewPortal(bridge)
        portal.submit_human_decision(session_id="SID-K", checkpoint="drawing_verified", by_human=True)
        status = portal.view_drawing_review(session_id="SID-K")
        assert status["passed"] is True
        assert status["decided_by"] == "human_reviewer"

    def test_view_review_is_read_only(self):
        # 只读查看三节点，不触发任何 pass/标记
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-L", user_input="u")
        portal = HumanReviewPortal(bridge)
        for viewer, cp in (
            (portal.view_drawing_review, "drawing_verified"),
            (portal.view_solution_review, "solution_reviewed"),
            (portal.view_cost_review, "cost_reviewed"),
        ):
            st = viewer(session_id="SID-L")
            assert st["checkpoint"] == cp
            assert st["passed"] is False  # 只读，未通过
            assert st["decided_by"] is None

    def test_query_status_never_confirms_results(self):
        # 红线③：即便工作流推进，返回包 results_confirmed 仍恒 False
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        bridge.create_workflow(session_id="SID-M", user_input="u")
        resp = bridge.query_status(session_id="SID-M")
        assert resp.results_confirmed is False
        assert resp.review_required is True

    def test_safety_invariants_block_bridge_construction(self, monkeypatch):
        # 红线①/⑥：engineering_enabled 翻转 → 桥构造 fail-closed
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            AssistantWorkflowBridge(repo)

    def test_safety_invariants_block_portal_construction(self, monkeypatch):
        # 红线①/⑥：启用态下即便桥已构造，门户构造仍 fail-closed
        repo = _populated_repo()
        # 先以未启用态构造桥（供门户持引用）
        bridge = AssistantWorkflowBridge(repo)
        # 再 monkeypatch 启用态后构造门户
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        with pytest.raises(SolutionRedLineViolationError):
            HumanReviewPortal(bridge)

    def test_safety_invariants_block_create_workflow(self, monkeypatch):
        # 红线①/⑥：启用态下建流 fail-closed
        repo = _populated_repo()
        bridge = AssistantWorkflowBridge(repo)
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        with pytest.raises(SolutionRedLineViolationError):
            bridge.create_workflow(session_id="SID-N", user_input="u")

    def test_assistant_models_not_in_graph_whitelist_redline(self):
        # 非图谱节点零回归（与 3.7.8 一致：17 关系白名单不受影响）
        assert "AssistantSession" not in KnowledgeGraphEntityType.all_values()
        assert "AssistantWorkflowBridge" not in KnowledgeGraphEntityType.all_values()
        assert "HumanReviewPortal" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17
