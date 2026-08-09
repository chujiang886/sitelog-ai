"""Engineering Workflow Orchestration Layer（Phase 3.7.8）。

在 3.7.7 图纸智能层之上，建立「工程工作流编排层」：
- ``EngineeringWorkflow``（任务1）：工作流模型（workflow_id / input_source / stages /
  status / created_at / requires_human_review）。**非图谱节点**（与 ``DesignCandidate`` 同性质，
  不进 ``KnowledgeGraphEntityType`` / ``_ENTITY_DISPATCH`` / 17 关系白名单，扩展零回归）。
- ``WorkflowStage`` / ``WorkflowEvent``：阶段可追踪载体与审计事件（stage / actor / timestamp /
  status）。
- ``EngineeringWorkflowEngine``（任务2/3）：编排器，串联 ``DrawingParser`` / ``DesignReviewQueue``
  / ``SolutionGenerator`` / ``SolutionConstraintEngine`` / ``CostEstimator``，**只编排、不改变
  模块职责**；提供 ``start_workflow`` / ``execute_stage`` / ``pause_for_review`` / ``resume_workflow``，
  每个阶段可追踪。
- ``HumanReviewCheckpoint``（任务4）：人工审核节点（drawing_verified / solution_reviewed /
  cost_reviewed），**AI 不能自动通过**（mark 必须 ``by_human=True``，否则抛
  ``SolutionRedLineViolationError``，红线②）。
- 审计追踪（任务5）：``workflow.event_log`` 记录每次阶段转移（stage / actor / timestamp / status）。

====================
最高红线（fail-closed，6 条）
====================
① 禁止开启 ``engineering_enabled``（引擎/子模块构造与每个决策路径均断言
  ``safety_invariants_ok``）；
② 禁止输出 ``engineering_approved``（forbidden 方法名 ``approve`` / ``engineering_approved``
  被 mixin 拦截；``HumanReviewCheckpoint.mark`` 仅 ``by_human=True`` 可放行，AI 调用抛
  ``SolutionRedLineViolationError``）；
③ 禁止自动确认图纸尺寸（forbidden 方法名 ``confirm_dimension`` / ``select`` / ``finalize`` /
  ``activate``）；
④ 禁止自动生成真实工程参数（forbidden 方法名 ``generate_engineering_param``）；
⑤ 禁止自动报价（forbidden 方法名 ``quote`` / ``pricing``）；
⑥ 禁止绕过 ``UnifiedActivationGate``（构造/启动/执行/暂停/恢复所有决策路径先断言
  ``safety_invariants_ok``）。

本层仅编排既有占位壳模块（解析/视觉/生成/约束/估算均不产出真实尺寸/参数/报价），并在人工审核
节点处挂起等待人类终裁；真实尺寸/工程参数/报价须经专家双签 + 主理人核准（G6）写入来源系统，
属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.entities import (
    PENDING_PLACEHOLDER,
    PENDING_VERIFICATION,
    CaseEntity,
    DesignCandidate,
    SolutionCandidateEntity,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionGenerator,
    SolutionRedLineViolationError,
    SolutionReviewError,
    _RedLineForbiddenMixin,
)
from agents.engineering.knowledge.graph.solution_drawing import (
    DesignReviewQueue,
    DrawingParser,
)
from agents.engineering.knowledge.graph.solution_constraint import SolutionConstraintEngine
from agents.engineering.knowledge.graph.solution_cost import CostEstimator


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳（审计用）。"""
    return datetime.now(timezone.utc).isoformat()


# 工作流层 forbidden 方法名（与 3.7.7 同集：覆盖红线②/③/④/⑤）。
_FORBIDDEN_WORKFLOW_METHODS = (
    "approve",                      # 红线②：不得批准（仅 by_human 可放行）
    "select",                       # 红线③：不得选终
    "finalize",                     # 红线③：不得定稿
    "activate",                     # 红线③：不得激活
    "engineering_approved",         # 红线②：不得输出 engineering_approved
    "quote",                        # 红线⑤：禁止自动报价
    "pricing",                      # 红线⑤：禁止自动报价
    "confirm_dimension",            # 红线③：禁止自动确认图纸尺寸
    "generate_engineering_param",   # 红线④：禁止自动生成真实工程参数
)


# 编排阶段顺序（与任务3要求的五个模块 + 人工审核节点一一对应）。
STAGE_ORDER = (
    "parse_drawing",     # DrawingParser
    "review_drawing",    # DesignReviewQueue
    "generate_solution", # SolutionGenerator
    "check_constraint",  # SolutionConstraintEngine
    "estimate_cost",     # CostEstimator
    "human_review",      # HumanReviewCheckpoint（挂起等待人工）
)


# ---------------------------------------------------------------------------
# 任务1：工作流模型（纯数据，非图谱节点，零回归）
# ---------------------------------------------------------------------------
@dataclass
class WorkflowStage:
    """工作流单阶段（可追踪：stage_id / name / status / actor / 时间戳 / 结果引用）。"""

    stage_id: str
    name: str
    status: str = "pending"  # pending / running / done / awaiting_human / skipped
    actor: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    result_ref: Optional[str] = None
    note: str = ""


@dataclass
class WorkflowEvent:
    """审计事件（stage / actor / timestamp / status，任务5）。"""

    stage: str
    actor: str
    timestamp: str
    status: str
    detail: str = ""


@dataclass
class EngineeringWorkflow:
    """工程工作流模型（任务1）。

    workflow_id / input_source / stages / status / created_at / requires_human_review
    （任务5 额外携带 ``event_log`` 审计追踪，不影响上述契约）。

    非图谱节点：不进 ``KnowledgeGraphEntityType`` / ``_ENTITY_DISPATCH`` / 17 关系白名单，
    扩展零回归（``len(RELATIONSHIP_SPECS) == 17`` 不受影响）。
    """

    workflow_id: str
    input_source: Any
    stages: list = field(default_factory=list)
    status: str = "draft"  # draft / running / paused_for_review / completed
    created_at: str = ""
    requires_human_review: bool = True
    event_log: list = field(default_factory=list)  # list[WorkflowEvent]

    def stage_by_name(self, name: str) -> Optional["WorkflowStage"]:
        for s in self.stages:
            if s.name == name:
                return s
        return None

    def next_pending_stage(self) -> Optional["WorkflowStage"]:
        for s in self.stages:
            if s.status in ("pending", "running"):
                return s
        return None


# ---------------------------------------------------------------------------
# 任务4：人工审核节点（AI 不能自动通过，红线②）
# ---------------------------------------------------------------------------
class HumanReviewCheckpoint:
    """人工审核节点（任务4）。

    三个门：``drawing_verified`` / ``solution_reviewed`` / ``cost_reviewed``。
    ``mark`` 必须 ``by_human=True``，否则抛 ``SolutionRedLineViolationError``（红线②：
    AI 不得自动通过人工审核节点）。
    """

    CHECKPOINTS = ("drawing_verified", "solution_reviewed", "cost_reviewed")

    def __init__(self) -> None:
        self._passed: dict[str, bool] = {c: False for c in self.CHECKPOINTS}
        self._decided_by: dict[str, Optional[str]] = {c: None for c in self.CHECKPOINTS}
        self._decided_at: dict[str, Optional[str]] = {c: None for c in self.CHECKPOINTS}
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造人工审核节点（红线①/⑥）"
            )

    def mark(self, checkpoint: str, *, by_human: bool = False) -> None:
        """放行某个审核节点（**仅人工**）。"""
        if checkpoint not in self.CHECKPOINTS:
            raise SolutionReviewError(f"未知审核节点 {checkpoint!r}")
        if not by_human:
            raise SolutionRedLineViolationError(
                f"AI 不得自动通过人工审核节点 {checkpoint!r}：mark 必须 by_human=True（红线②）。"
                "最终审核须经真实主理人/专家线下决策。"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下通过审核（红线①/⑥）"
            )
        self._passed[checkpoint] = True
        self._decided_by[checkpoint] = "human_reviewer"
        self._decided_at[checkpoint] = _utc_now()

    def is_passed(self, checkpoint: str) -> bool:
        return bool(self._passed.get(checkpoint, False))

    def all_passed(self) -> bool:
        return all(self._passed.values())

    def status(self) -> dict:
        return {
            c: {
                "passed": self._passed[c],
                "decided_by": self._decided_by[c],
                "decided_at": self._decided_at[c],
            }
            for c in self.CHECKPOINTS
        }


# ---------------------------------------------------------------------------
# 任务2/3：工程工作流编排器（仅编排，不改模块职责）
# ---------------------------------------------------------------------------
class EngineeringWorkflowEngine(_RedLineForbiddenMixin):
    """工程工作流编排器（Engineering Workflow Engine）。

    串联 ``DrawingParser`` / ``DesignReviewQueue`` / ``SolutionGenerator`` /
    ``SolutionConstraintEngine`` / ``CostEstimator``，**只编排、不改变各模块职责**。
    每个阶段可追踪（``WorkflowStage``）；含人工审核节点（``HumanReviewCheckpoint``），
    AI 不能自动通过（红线②）；审计追踪记录于 ``workflow.event_log``（``WorkflowEvent``：
    stage / actor / timestamp / status）。

    红线（fail-closed）：
    - ⑥ 构造/启动/执行/暂停/恢复所有决策路径先断言 ``safety_invariants_ok()``；
    - ② 无 ``approve`` / ``engineering_approved``（mixin 拦截 + 审核节点仅 by_human）；
    - ③ 无 ``confirm_dimension`` / ``select`` / ``finalize`` / ``activate``（mixin 拦截）；
    - ④ 无 ``generate_engineering_param``（mixin 拦截）；
    - ⑤ 无 ``quote`` / ``pricing``（mixin 拦截）；
    - ① 不开启 ``engineering_enabled``。
    """

    _FORBIDDEN = _FORBIDDEN_WORKFLOW_METHODS
    STAGE_ORDER = STAGE_ORDER

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造工作流编排器（红线①/⑥）"
            )
        # 仅构造子模块句柄（不改职责）；各自构造均断言 safety_invariants_ok
        self._parser = DrawingParser(repository)
        self._review_queue = DesignReviewQueue()
        self._generator = SolutionGenerator(repository)
        self._constraint_engine = SolutionConstraintEngine(repository)
        self._cost_estimator = CostEstimator(repository)
        self._workflows: dict[str, EngineeringWorkflow] = {}
        self._checkpoints: dict[str, HumanReviewCheckpoint] = {}
        self._context: dict[str, dict[str, Any]] = {}  # workflow_id -> 中间结果

    # -- 内部工具 --
    def _log(
        self,
        wf: EngineeringWorkflow,
        *,
        stage: str,
        actor: str,
        status: str,
        detail: str = "",
    ) -> None:
        wf.event_log.append(
            WorkflowEvent(stage=stage, actor=actor, timestamp=_utc_now(), status=status, detail=detail)
        )

    def _source(self, wf: EngineeringWorkflow) -> tuple[str, str, str]:
        """解析 input_source 为 (file_path, parse_format, design_id)。"""
        src = wf.input_source if isinstance(wf.input_source, dict) else {"file_path": wf.input_source}
        fp = src.get("file_path") or ""
        fmt = src.get("parse_format", "pdf")
        did = src.get("design_id") or wf.workflow_id
        return fp, fmt, did

    # -- 任务2：核心 API --
    def start_workflow(
        self,
        *,
        workflow_id: str,
        input_source: Any,
        design_id: Optional[str] = None,
        file_path: Optional[str] = None,
        parse_format: str = "pdf",
        cases: Optional[list[CaseEntity]] = None,
    ) -> EngineeringWorkflow:
        """启动工作流（状态 running，建立 6 阶段 + 人工审核节点，记录审计事件）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下启动工作流（红线①/⑥）"
            )
        # 规范化 input_source（保留显式覆盖参数）
        src: dict[str, Any] = (
            dict(input_source) if isinstance(input_source, dict) else {"file_path": input_source}
        )
        if file_path:
            src["file_path"] = file_path
        if parse_format != "pdf":
            src["parse_format"] = parse_format
        if design_id:
            src["design_id"] = design_id
        if "design_id" not in src:
            src["design_id"] = workflow_id

        stages = [
            WorkflowStage(stage_id=f"{workflow_id}__S{i + 1}", name=name, status="pending")
            for i, name in enumerate(self.STAGE_ORDER)
        ]
        wf = EngineeringWorkflow(
            workflow_id=workflow_id,
            input_source=src,
            stages=stages,
            status="running",
            created_at=_utc_now(),
            requires_human_review=True,
            event_log=[],
        )
        self._workflows[workflow_id] = wf
        self._checkpoints[workflow_id] = HumanReviewCheckpoint()
        self._context[workflow_id] = {"cases": cases}
        self._log(
            wf,
            stage="workflow",
            actor="ai_orchestrator",
            status="started",
            detail=f"stages={list(self.STAGE_ORDER)}",
        )
        return wf

    def execute_stage(
        self, workflow_id: str, *, stage_name: Optional[str] = None
    ) -> WorkflowStage:
        """执行一个阶段（默认下一个 pending 阶段；每阶段可追踪 + 审计）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下执行工作流阶段（红线①/⑥）"
            )
        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise SolutionReviewError(f"工作流 {workflow_id!r} 不存在")
        if stage_name is None:
            stage = wf.next_pending_stage()
            if stage is None:
                raise SolutionReviewError(f"工作流 {workflow_id!r} 无待执行阶段")
        else:
            stage = wf.stage_by_name(stage_name)
            if stage is None:
                raise SolutionReviewError(f"未知阶段 {stage_name!r}")
            if stage.status in ("done", "awaiting_human"):
                raise SolutionReviewError(f"阶段 {stage_name!r} 已执行/等待中")

        stage.status = "running"
        stage.actor = "ai_orchestrator"
        stage.started_at = _utc_now()
        self._log(wf, stage=stage.name, actor="ai_orchestrator", status="running")

        try:
            result_ref = self._dispatch(wf, stage.name)
        except Exception as exc:  # 还原为 pending，记录错误事件（不吞异常）
            stage.status = "pending"
            self._log(
                wf, stage=stage.name, actor="ai_orchestrator", status="error", detail=str(exc)
            )
            raise

        stage.result_ref = result_ref
        if stage.name == "human_review":
            # 红线②：AI 不自动通过人工审核节点 → 挂起等待人工
            stage.status = "awaiting_human"
            wf.status = "paused_for_review"
            self._log(
                wf,
                stage="human_review",
                actor="ai_orchestrator",
                status="awaiting_human",
                detail="等待人工审核节点通过（红线②）",
            )
        else:
            stage.status = "done"
            stage.finished_at = _utc_now()
            self._log(
                wf,
                stage=stage.name,
                actor="ai_orchestrator",
                status="done",
                detail=f"result_ref={result_ref}",
            )
        return stage

    def _dispatch(self, wf: EngineeringWorkflow, name: str) -> Optional[str]:
        """按阶段名调用对应模块（仅编排，不改模块职责）。"""
        ctx = self._context.setdefault(wf.workflow_id, {})
        if name == "parse_drawing":
            fp, fmt, did = self._source(wf)
            parser_method = getattr(self._parser, f"parse_{fmt}", None) or self._parser.parse_pdf
            candidate = parser_method(fp, design_id=did, source_ref=fp)
            ctx["design"] = candidate
            return candidate.design_id
        if name == "review_drawing":
            candidate = ctx.get("design")
            if candidate is None:
                raise SolutionReviewError("review_drawing 前必须先 parse_drawing")
            rid = self._review_queue.submit(candidate)
            self._review_queue.begin_review(rid)
            ctx["review_id"] = rid
            return rid
        if name == "generate_solution":
            candidate = ctx.get("design")
            if candidate is None:
                raise SolutionReviewError("generate_solution 前必须先 parse_drawing")
            candidates = self._generator.generate(candidate, cases=ctx.get("cases"), persist=True)
            ctx["solutions"] = candidates
            return f"{len(candidates)}_candidates"
        if name == "check_constraint":
            candidates = ctx.get("solutions") or []
            if not candidates:
                return "no_candidates"
            rep = self._constraint_engine.check_geometry(candidates)
            ctx["constraint_report"] = rep
            return rep.check_type
        if name == "estimate_cost":
            candidates = ctx.get("solutions") or []
            if not candidates:
                return "no_candidates"
            draft = self._cost_estimator.total_estimate(candidates[0])
            ctx["cost_draft"] = draft
            return draft.estimate_id
        if name == "human_review":
            # 仅挂接/引用已建审核节点，不自动通过（AI 不能 auto-pass，红线②）
            ctx["checkpoint"] = self._checkpoints[wf.workflow_id]
            return "awaiting_human_review"
        raise SolutionReviewError(f"未编排阶段 {name!r}")

    def pause_for_review(self, workflow_id: str) -> EngineeringWorkflow:
        """显式暂停工作流以等待人工审核（状态 paused_for_review，记录审计）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下暂停工作流（红线①/⑥）"
            )
        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise SolutionReviewError(f"工作流 {workflow_id!r} 不存在")
        if wf.status == "completed":
            raise SolutionReviewError("已完成工作流不可再暂停")
        wf.status = "paused_for_review"
        self._log(wf, stage="workflow", actor="ai_orchestrator", status="paused_for_review")
        return wf

    def resume_workflow(self, workflow_id: str) -> EngineeringWorkflow:
        """恢复工作流（红线②：仅当人工审核节点全部 by_human 通过后，方可收尾为 completed）。

        若审核节点未全通过，则维持 running（仍等待人工），绝不 AI 代审/代通过。
        """
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下恢复工作流（红线①/⑥）"
            )
        wf = self._workflows.get(workflow_id)
        if wf is None:
            raise SolutionReviewError(f"工作流 {workflow_id!r} 不存在")
        cp = self._checkpoints.get(workflow_id)
        if cp is not None and cp.all_passed():
            # 依赖人工审核通过（by_human=True）→ 收尾 human_review 阶段并标记完成
            hr = wf.stage_by_name("human_review")
            if hr is not None and hr.status != "done":
                hr.status = "done"
                hr.finished_at = _utc_now()
            wf.status = "completed"
            self._log(
                wf,
                stage="human_review",
                actor="human_reviewer",
                status="done",
                detail="全部人工审核节点已通过",
            )
            self._log(
                wf,
                stage="workflow",
                actor="ai_orchestrator",
                status="completed",
                detail="工作流收尾（依赖人工审核通过）",
            )
        else:
            wf.status = "running"
            self._log(
                wf,
                stage="workflow",
                actor="ai_orchestrator",
                status="resumed",
                detail="等待人工审核节点通过",
            )
        return wf

    # 便捷：暴露某工作流的人工审核节点（供人工调用 mark(by_human=True)）
    def human_checkpoint(self, workflow_id: str) -> HumanReviewCheckpoint:
        cp = self._checkpoints.get(workflow_id)
        if cp is None:
            raise SolutionReviewError(f"工作流 {workflow_id!r} 未启动")
        return cp


__all__ = [
    "SolutionRedLineViolationError",
    "EngineeringWorkflow",
    "WorkflowStage",
    "WorkflowEvent",
    "HumanReviewCheckpoint",
    "EngineeringWorkflowEngine",
]
