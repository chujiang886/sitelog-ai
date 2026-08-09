"""Workflow Orchestration Layer 测试（Phase 3.7.8 Task 6）。

覆盖（用户要求）：
1. Workflow 测试：``EngineeringWorkflow`` 模型契约（workflow_id / input_source / stages /
   status / created_at / requires_human_review），非图谱节点零回归；
2. Stage 测试：``EngineeringWorkflowEngine`` 阶段可追踪（``WorkflowStage`` 状态机推进）；
3. Review checkpoint 测试：``HumanReviewCheckpoint``（drawing_verified / solution_reviewed /
   cost_reviewed），AI 不能自动通过（mark 必须 by_human=True，否则红线②）；
4. Audit 测试：``workflow.event_log`` 审计追踪（stage / actor / timestamp / status）；
5. RedLine 测试：6 条最高红线 fail-closed（含自动确认尺寸/生成工程参数/报价/绕过 Gate 拦截）；
6. Integration 测试：编排 DrawingParser / DesignReviewQueue / SolutionGenerator /
   SolutionConstraintEngine / CostEstimator，仅编排不改模块职责，最终挂起等待人工。

红线约束：
- 不修改 verified.json（全部用例使用内存图谱，绝不触碰磁盘 verified.json）；
- 不开启 engineering_enabled（构造/启动/执行/暂停/恢复全断言 safety_invariants_ok）；
- 不输出 engineering_approved（forbidden 方法名被 mixin 拦截 + 审核节点仅 by_human）；
- 夹具使用纯标识符（CASE-1/2/3 / RULE-1 / E-TH-01 / KI-TEST-0001 / D-1 / WF-*），不写真实值。
"""

from __future__ import annotations

import pytest

import agents.engineering.gate.unified_activation_gate as gate_mod
import agents.engineering.knowledge.graph.entities as ent_mod
from agents.engineering.knowledge.graph import (
    CaseEntity,
    EngineeringWorkflow,
    EngineeringWorkflowEngine,
    GraphEdge,
    HumanReviewCheckpoint,
    KnowledgeGraphEntityType,
    KnowledgeGraphRepository,
    KnowledgeItemEntity,
    RELATIONSHIP_SPECS,
    RuleEntity,
    SolutionRedLineViolationError,
    SolutionReviewError,
    ThresholdEntity,
    WorkflowEvent,
    WorkflowStage,
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


def _cases(repo: KnowledgeGraphRepository) -> list[CaseEntity]:
    out = []
    for i in (1, 2, 3):
        node = repo.get_node(f"CASE-{i}")
        if node is not None:
            out.append(CaseEntity.from_node(node))
    return out


# ---------------------------------------------------------------------------
# 1. Workflow 模型测试（任务1）
# ---------------------------------------------------------------------------
class TestEngineeringWorkflowModel:
    def test_workflow_fields(self):
        wf = EngineeringWorkflow(
            workflow_id="WF-1",
            input_source={"file_path": "d.pdf", "design_id": "D-1"},
            stages=[],
            status="draft",
            created_at="2026-08-03T00:00:00+00:00",
            requires_human_review=True,
        )
        assert wf.workflow_id == "WF-1"
        assert wf.input_source["design_id"] == "D-1"
        assert wf.status == "draft"
        assert wf.requires_human_review is True
        assert wf.event_log == []

    def test_stage_by_name(self):
        wf = EngineeringWorkflow(
            workflow_id="WF-1",
            input_source="d.pdf",
            stages=[WorkflowStage(stage_id="S1", name="parse_drawing")],
        )
        assert wf.stage_by_name("parse_drawing").stage_id == "S1"
        assert wf.stage_by_name("nope") is None

    def test_next_pending_stage(self):
        wf = EngineeringWorkflow(
            workflow_id="WF-1",
            input_source="d.pdf",
            stages=[
                WorkflowStage(stage_id="S1", name="a", status="done"),
                WorkflowStage(stage_id="S2", name="b", status="pending"),
            ],
        )
        assert wf.next_pending_stage().name == "b"

    def test_workflow_not_in_graph_whitelist(self):
        # 非图谱节点：不进实体枚举 / 不进 17 关系白名单（扩展零回归）
        assert "EngineeringWorkflow" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17


# ---------------------------------------------------------------------------
# 2. Stage / Event 载体测试
# ---------------------------------------------------------------------------
class TestWorkflowStageAndEvent:
    def test_stage_defaults(self):
        s = WorkflowStage(stage_id="S1", name="parse_drawing")
        assert s.status == "pending"
        assert s.actor is None
        assert s.started_at is None
        assert s.result_ref is None

    def test_event_fields(self):
        e = WorkflowEvent(stage="parse_drawing", actor="ai_orchestrator", timestamp="t", status="done", detail="x")
        assert e.stage == "parse_drawing"
        assert e.actor == "ai_orchestrator"
        assert e.timestamp == "t"
        assert e.status == "done"
        assert e.detail == "x"


# ---------------------------------------------------------------------------
# 3. Engine 阶段执行测试（任务2：可追踪推进）
# ---------------------------------------------------------------------------
class TestWorkflowEngineStageExecution:
    def _engine(self, repo):
        return EngineeringWorkflowEngine(repo)

    def test_start_creates_six_stages(self):
        repo = _populated_repo()
        eng = self._engine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        assert len(wf.stages) == len(EngineeringWorkflowEngine.STAGE_ORDER)
        assert [s.name for s in wf.stages] == list(EngineeringWorkflowEngine.STAGE_ORDER)
        assert wf.status == "running"
        assert wf.requires_human_review is True

    def test_sequential_stage_progression(self):
        repo = _populated_repo()
        eng = self._engine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        # 依次执行前 5 个（非人工）阶段，应全部 done
        for _ in range(5):
            eng.execute_stage("WF-1")
        non_human = [n for n in EngineeringWorkflowEngine.STAGE_ORDER if n != "human_review"]
        for name in non_human:
            assert wf.stage_by_name(name).status == "done"
        # 每个非人工阶段都应带 result_ref（可追踪）
        for name in non_human:
            assert wf.stage_by_name(name).result_ref is not None

    def test_execute_specific_stage(self):
        repo = _populated_repo()
        eng = self._engine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        stage = eng.execute_stage("WF-1", stage_name="parse_drawing")
        assert stage.name == "parse_drawing"
        assert stage.status == "done"
        # 重复执行已 done 阶段 → SolutionReviewError（正常业务校验）
        with pytest.raises(SolutionReviewError):
            eng.execute_stage("WF-1", stage_name="parse_drawing")

    def test_execute_missing_workflow_raises(self):
        repo = _populated_repo()
        eng = self._engine(repo)
        with pytest.raises(SolutionReviewError):
            eng.execute_stage("WF-GHOST")


# ---------------------------------------------------------------------------
# 4. 人工审核节点测试（任务4：AI 不可自动通过，红线②）
# ---------------------------------------------------------------------------
class TestHumanReviewCheckpoint:
    def test_ai_cannot_mark(self):
        cp = HumanReviewCheckpoint()
        with pytest.raises(SolutionRedLineViolationError):
            cp.mark("drawing_verified")  # by_human 默认 False

    def test_human_can_mark(self):
        cp = HumanReviewCheckpoint()
        cp.mark("drawing_verified", by_human=True)
        assert cp.is_passed("drawing_verified") is True
        assert cp.all_passed() is False

    def test_unknown_checkpoint_raises(self):
        cp = HumanReviewCheckpoint()
        with pytest.raises(SolutionReviewError):
            cp.mark("not_a_checkpoint", by_human=True)

    def test_checkpoint_status_dict(self):
        cp = HumanReviewCheckpoint()
        cp.mark("drawing_verified", by_human=True)
        cp.mark("solution_reviewed", by_human=True)
        cp.mark("cost_reviewed", by_human=True)
        assert cp.all_passed() is True
        st = cp.status()
        for c in HumanReviewCheckpoint.CHECKPOINTS:
            assert st[c]["passed"] is True
            assert st[c]["decided_by"] == "human_reviewer"


# ---------------------------------------------------------------------------
# 5. 审计追踪测试（任务5：workflow_event_log）
# ---------------------------------------------------------------------------
class TestWorkflowAuditLog:
    def test_started_event_recorded(self):
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        assert any(e.stage == "workflow" and e.status == "started" for e in wf.event_log)
        assert all(isinstance(e, WorkflowEvent) for e in wf.event_log)

    def test_stage_done_events_recorded(self):
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        for _ in range(5):
            eng.execute_stage("WF-1")
        # 5 个非人工阶段各自产生 running + done 事件
        done_events = [e for e in wf.event_log if e.status == "done"]
        assert len(done_events) == 5
        assert all(e.actor == "ai_orchestrator" for e in done_events)

    def test_completed_events_recorded_after_human(self):
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        for _ in range(len(EngineeringWorkflowEngine.STAGE_ORDER)):
            eng.execute_stage("WF-1")
        cp = eng.human_checkpoint("WF-1")
        cp.mark("drawing_verified", by_human=True)
        cp.mark("solution_reviewed", by_human=True)
        cp.mark("cost_reviewed", by_human=True)
        eng.resume_workflow("WF-1")
        assert any(e.stage == "workflow" and e.status == "completed" for e in wf.event_log)
        assert any(e.stage == "human_review" and e.status == "done" for e in wf.event_log)


# ---------------------------------------------------------------------------
# 6. 红线测试（fail-closed，6 条）
# ---------------------------------------------------------------------------
class TestWorkflowRedLines:
    def test_safety_invariants_block_construction(self, monkeypatch):
        # 红线①/⑥：engineering_enabled 翻转 → 构造 fail-closed。
        monkeypatch.setattr(gate_mod, "load_engineering_enabled", lambda: True)
        monkeypatch.setattr(ent_mod, "load_engineering_enabled", lambda: True)
        repo = _populated_repo()
        with pytest.raises(SolutionRedLineViolationError):
            EngineeringWorkflowEngine(repo)
        with pytest.raises(SolutionRedLineViolationError):
            HumanReviewCheckpoint()

    def test_forbidden_methods_blocked(self):
        # 红线②/③/④/⑤：批准/确认尺寸/生成工程参数/报价方法名被 mixin 拦截
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
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
                getattr(eng, name)

    def test_engine_pauses_at_human_review_not_auto_pass(self):
        # 红线②：执行到 human_review 阶段后挂起，绝不 AI 自动通过
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        for _ in range(len(EngineeringWorkflowEngine.STAGE_ORDER)):
            eng.execute_stage("WF-1")
        assert wf.stage_by_name("human_review").status == "awaiting_human"
        assert wf.status == "paused_for_review"
        # 即使 resume 但审核节点未过，仍维持等待（绝不 AI 代审）
        eng.resume_workflow("WF-1")
        assert wf.status == "running"
        assert wf.stage_by_name("human_review").status == "awaiting_human"

    def test_resume_completes_only_after_human(self):
        # 红线②：仅当三个审核节点全部 by_human 通过，resume 才收尾 completed
        repo = _populated_repo()
        eng = EngineeringWorkflowEngine(repo)
        wf = eng.start_workflow(
            workflow_id="WF-1",
            input_source={"file_path": "drawing.pdf", "design_id": "D-1"},
            cases=_cases(repo),
        )
        for _ in range(len(EngineeringWorkflowEngine.STAGE_ORDER)):
            eng.execute_stage("WF-1")
        cp = eng.human_checkpoint("WF-1")
        cp.mark("drawing_verified", by_human=True)
        cp.mark("solution_reviewed", by_human=True)
        cp.mark("cost_reviewed", by_human=True)
        eng.resume_workflow("WF-1")
        assert cp.all_passed() is True
        assert wf.status == "completed"
        assert wf.stage_by_name("human_review").status == "done"

    def test_workflow_models_not_in_graph_whitelist(self):
        # EngineeringWorkflow / WorkflowStage 等纯数据壳不进 17 关系白名单
        assert "EngineeringWorkflow" not in KnowledgeGraphEntityType.all_values()
        assert "WorkflowStage" not in KnowledgeGraphEntityType.all_values()
        assert len(RELATIONSHIP_SPECS) == 17
