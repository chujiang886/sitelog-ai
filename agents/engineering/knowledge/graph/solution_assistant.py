"""Engineering AI Assistant Interface Layer（Phase 3.7.9）。

在 3.7.8 工作流编排层之上，建立「工程 AI 助手交互层」——面向最终用户/主理人的
**会话入口**与**人机协作桥**：

- ``AssistantSession``（任务1）：会话模型（session_id / user_input / files /
  workflow_id / status / created_at）。**非图谱节点**（与 ``EngineeringWorkflow`` 同性质，
  不进 ``KnowledgeGraphEntityType`` / ``_ENTITY_DISPATCH`` / 17 关系白名单，扩展零回归）。
- ``WorkflowRequest``（任务2）：用户输入处理产物（文本 / 图片 / PDF / CAD 路径 →
  工作流请求），``direct_judgment`` **恒 False**（红线③：禁止直接工程判断）。
- ``AssistantWorkflowBridge``（任务3）：桥接 ``EngineeringWorkflowEngine``，提供
  ``create_workflow`` / ``attach_files`` / ``query_status``。**只桥接、不改编排模块职责**，
  不新增任何工程决策。
- ``AssistantResponse``（任务4）：交互层回包（workflow_status / candidate_results /
  review_required / source_trace），``results_confirmed`` **恒 False**（红线③：禁止自动
  确认工程结果）。
- ``HumanReviewPortal``（任务5）：人工审核入口，可**只读**查看 ``drawing_review`` /
  ``solution_review`` / ``cost_review`` 三节点；``submit_human_decision`` **强制
  by_human=True**（红线⑤：AI 不能自动通过人工审核）。

====================
最高红线（fail-closed，6 条，与 3.7.8 实质一致）
====================
① 禁止开启 ``engineering_enabled``（桥/会话/门户构造与每个决策路径均断言
   ``safety_invariants_ok``）；
② 禁止输出 ``engineering_approved``（forbidden 方法名 ``approve`` / ``engineering_approved``
   被 mixin 拦截；审核节点仅 ``by_human=True`` 可放行）；
③ 禁止自动确认工程结果（forbidden 方法名 ``confirm_dimension`` / ``select`` / ``finalize`` /
   ``activate`` / ``generate_engineering_param``；``results_confirmed`` / ``direct_judgment``
   恒 False；本层不生成任何真实工程参数/图纸尺寸）；
④ 禁止自动生成真实工程参数（forbidden 方法名 ``generate_engineering_param``）；
⑤ 禁止自动报价（forbidden 方法名 ``quote`` / ``pricing``）；
⑥ 禁止绕过 ``UnifiedActivationGate``（构造/建流/查状态/提交人工决策所有路径先断言
   ``safety_invariants_ok``）。

本层**仅**承载会话壳、请求/响应载体与桥接/门户，不写 verified.json、不开启
engineering_enabled、不输出 engineering_approved、绝不编造真实工程参数；所有真实工程结论
须经专家双签 + 主理人核准（G6）写入来源系统，属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionRedLineViolationError,
    SolutionReviewError,
    _RedLineForbiddenMixin,
    _utc_now,
)
from agents.engineering.knowledge.graph.solution_workflow import (
    EngineeringWorkflow,
    EngineeringWorkflowEngine,
)


# 交互层 forbidden 方法名（覆盖红线②/③/④/⑤，与 3.7.8 同集）。
_FORBIDDEN_ASSISTANT_METHODS = (
    "approve",                      # 红线②：不得批准（仅 by_human 可放行）
    "select",                       # 红线③：不得选终
    "finalize",                     # 红线③：不得定稿
    "activate",                     # 红线③：不得激活
    "engineering_approved",         # 红线②：不得输出 engineering_approved
    "quote",                        # 红线⑤：禁止自动报价
    "pricing",                      # 红线⑤：禁止自动报价
    "confirm_dimension",            # 红线③：禁止自动确认图纸尺寸/工程结果
    "generate_engineering_param",   # 红线④：禁止自动生成真实工程参数
)


# ---------------------------------------------------------------------------
# 任务1：会话模型（纯数据，非图谱节点，零回归）
# ---------------------------------------------------------------------------
@dataclass
class AssistantSession:
    """工程 AI 助手会话模型（任务1）。

    session_id / user_input / files / workflow_id / status / created_at。

    非图谱节点：不进 ``KnowledgeGraphEntityType`` / ``_ENTITY_DISPATCH`` / 17 关系白名单，
    扩展零回归（``len(RELATIONSHIP_SPECS) == 17`` 不受影响）。
    """

    session_id: str
    user_input: str
    files: list = field(default_factory=list)
    workflow_id: str = ""
    status: str = "open"  # open / attached / completed / closed
    created_at: str = ""


# ---------------------------------------------------------------------------
# 任务2：用户输入处理产物（禁止直接工程判断，红线③）
# ---------------------------------------------------------------------------
@dataclass
class WorkflowRequest:
    """用户输入 → 工作流请求（任务2）。

    ``direct_judgment`` 恒 False：交互层只把用户输入转成「待处理请求」，绝不替用户做
    任何工程判定（不得以 AI 身份确认尺寸/参数/选终/批准）。
    """

    session_id: str
    text: str
    files: list = field(default_factory=list)
    parse_format: str = "pdf"  # pdf / cad / image（由文件扩展名推断）
    design_id: Optional[str] = None
    direct_judgment: bool = False  # 红线③：恒 False


def _infer_parse_format(files: list, text: str) -> str:
    """根据文件扩展名推断解析格式（pdf / cad / image），缺省 pdf。

    纯文本（无文件）回退 pdf，由底层 ``DrawingParser`` 决定如何处理空路径。
    """
    for f in files or []:
        fl = str(f).lower()
        if fl.endswith((".dwg", ".dxf", ".cad")):
            return "cad"
        if fl.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
            return "image"
        if fl.endswith(".pdf"):
            return "pdf"
    # 文本中若显式给出 .pdf/.cad/.dwg/.dxf/.image 类路径，亦做初步推断
    tl = text.lower()
    if any(tl.endswith(ext) for ext in (".dwg", ".dxf", ".cad")):
        return "cad"
    if any(tl.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")):
        return "image"
    if tl.endswith(".pdf"):
        return "pdf"
    return "pdf"


def _build_input_source(user_input: str, files: list, parse_format: str, design_id: str) -> dict:
    """由用户输入与文件构造 ``EngineeringWorkflowEngine.start_workflow`` 所需的 input_source。"""
    file_path = files[0] if files else ""
    return {
        "file_path": file_path,
        "parse_format": parse_format,
        "design_id": design_id,
        "text": user_input,
    }


# ---------------------------------------------------------------------------
# 任务3：助手 ↔ 工作流引擎桥（只桥接，不改职责）
# ---------------------------------------------------------------------------
class AssistantWorkflowBridge(_RedLineForbiddenMixin):
    """工程 AI 助手与工作流编排引擎的桥（任务3）。

    持有 ``EngineeringWorkflowEngine`` 句柄，提供 ``create_workflow`` / ``attach_files`` /
    ``query_status``，把用户会话映射到工作流生命周期，**只桥接、不新增任何工程决策**。

    红线（fail-closed）：
    - ⑥ 构造/建流/查状态所有路径先断言 ``safety_invariants_ok()``；
    - ② 无 ``approve`` / ``engineering_approved``（mixin 拦截）；
    - ③ 无 ``confirm_dimension`` / ``select`` / ``finalize`` / ``activate`` /
        ``generate_engineering_param``（mixin 拦截），``direct_judgment`` 恒 False；
    - ④ 无 ``generate_engineering_param``（mixin 拦截）；
    - ⑤ 无 ``quote`` / ``pricing``（mixin 拦截）；
    - ① 不开启 ``engineering_enabled``。
    """

    _FORBIDDEN = _FORBIDDEN_ASSISTANT_METHODS

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造助手桥（红线①/⑥）"
            )
        # 仅持工作流引擎句柄（引擎自身构造亦断言 safety_invariants_ok）
        self.engine = EngineeringWorkflowEngine(repository)
        self._sessions: dict[str, AssistantSession] = {}
        self._workflows: dict[str, EngineeringWorkflow] = {}

    # -- 任务2：用户输入处理 → WorkflowRequest（禁止直接工程判断） --
    def _to_workflow_request(
        self,
        *,
        session_id: str,
        user_input: str,
        files: Optional[list] = None,
        design_id: Optional[str] = None,
        parse_format: str = "pdf",
    ) -> WorkflowRequest:
        """把用户输入转成 WorkflowRequest（direct_judgment 恒 False，红线③）。"""
        inferred = _infer_parse_format(files or [], user_input)
        fmt = parse_format if parse_format != "pdf" else inferred
        return WorkflowRequest(
            session_id=session_id,
            text=user_input,
            files=list(files or []),
            parse_format=fmt,
            design_id=design_id,
            direct_judgment=False,  # 红线③：绝不替用户做工程判定
        )

    # -- 任务3：核心 API --
    def create_workflow(
        self,
        *,
        session_id: str,
        user_input: str,
        files: Optional[list] = None,
        design_id: Optional[str] = None,
        parse_format: str = "pdf",
    ) -> EngineeringWorkflow:
        """由一次会话输入建立一条工作流（状态 running），返回工作流对象。

        仅桥接：``direct_judgment=False``，不评估、不判定、不生成工程参数。
        """
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下建立工作流（红线①/⑥）"
            )
        req = self._to_workflow_request(
            session_id=session_id,
            user_input=user_input,
            files=files,
            design_id=design_id,
            parse_format=parse_format,
        )
        workflow_id = f"WF-{session_id}"
        did = req.design_id or workflow_id
        input_source = _build_input_source(
            user_input=user_input, files=req.files, parse_format=req.parse_format, design_id=did
        )
        wf = self.engine.start_workflow(
            workflow_id=workflow_id,
            input_source=input_source,
            design_id=did,
            parse_format=req.parse_format,
        )
        session = AssistantSession(
            session_id=session_id,
            user_input=user_input,
            files=list(files or []),
            workflow_id=wf.workflow_id,
            status="open",
            created_at=_utc_now(),
        )
        self._sessions[session_id] = session
        self._workflows[session_id] = wf
        return wf

    def attach_files(self, *, session_id: str, files: list) -> AssistantSession:
        """为已存在的会话追加文件（仅登记，不触发任何工程判定）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下附加文件（红线①/⑥）"
            )
        session = self._sessions.get(session_id)
        if session is None:
            raise SolutionReviewError(f"会话 {session_id!r} 不存在，无法附加文件")
        session.files.extend(files or [])
        session.status = "attached"
        return session

    def query_status(self, *, session_id: str) -> "AssistantResponse":
        """查询会话对应工作流的当前状态，返回只读响应（results_confirmed 恒 False）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下查询状态（红线①/⑥）"
            )
        session = self._sessions.get(session_id)
        if session is None:
            raise SolutionReviewError(f"会话 {session_id!r} 不存在，无法查询状态")
        wf = self._workflows.get(session_id)
        if wf is None:
            raise SolutionReviewError(f"会话 {session_id!r} 尚未建立工作流")
        candidate_results = [
            {"stage": s.name, "status": s.status, "result_ref": s.result_ref}
            for s in wf.stages
        ]
        source_trace = [
            {
                "stage": ev.stage,
                "actor": ev.actor,
                "timestamp": ev.timestamp,
                "status": ev.status,
            }
            for ev in wf.event_log
        ]
        return AssistantResponse(
            session_id=session_id,
            workflow_status=wf.status,
            candidate_results=candidate_results,
            review_required=True,  # 红线③：始终需要人工复核，AI 不自动确认结果
            source_trace=source_trace,
            results_confirmed=False,  # 红线③：恒 False
        )

    # -- 便捷查询 --
    def get_session(self, session_id: str) -> AssistantSession:
        session = self._sessions.get(session_id)
        if session is None:
            raise SolutionReviewError(f"会话 {session_id!r} 不存在")
        return session

    def session_workflow_id(self, session_id: str) -> str:
        wf = self._workflows.get(session_id)
        if wf is None:
            raise SolutionReviewError(f"会话 {session_id!r} 尚未建立工作流")
        return wf.workflow_id


# ---------------------------------------------------------------------------
# 任务4：交互层响应载体（results_confirmed 恒 False，红线③）
# ---------------------------------------------------------------------------
@dataclass
class AssistantResponse:
    """工程 AI 助手响应（任务4）。

    workflow_status / candidate_results / review_required / source_trace。
    ``results_confirmed`` 恒 False：AI 不替用户确认任何工程结果（红线③）。
    """

    session_id: str
    workflow_status: str
    candidate_results: list = field(default_factory=list)
    review_required: bool = True  # 红线③：始终需要人工复核
    source_trace: list = field(default_factory=list)
    results_confirmed: bool = False  # 红线③：恒 False


# ---------------------------------------------------------------------------
# 任务5：人工审核入口（只读查看三节点 + 强制 by_human 提交，红线⑤）
# ---------------------------------------------------------------------------
class HumanReviewPortal(_RedLineForbiddenMixin):
    """人工审核入口（任务5）。

    可**只读**查看 ``drawing_review`` / ``solution_review`` / ``cost_review`` 三个审核节点；
    ``submit_human_decision`` **强制 by_human=True**（红线⑤：AI 不能自动通过人工审核）。

    仅桥接到底层 ``EngineeringWorkflowEngine.human_checkpoint(...).mark(by_human=True)``，
    不新增任何审核判定逻辑。
    """

    _FORBIDDEN = _FORBIDDEN_ASSISTANT_METHODS

    def __init__(self, bridge: AssistantWorkflowBridge) -> None:
        self._bridge = bridge
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造人工审核入口（红线①/⑥）"
            )

    def _checkpoint(self, session_id: str):
        wf_id = self._bridge.session_workflow_id(session_id)
        return self._bridge.engine.human_checkpoint(wf_id)

    def _checkpoint_status(self, session_id: str, checkpoint: str) -> dict:
        cp = self._checkpoint(session_id)
        st = cp.status().get(checkpoint, {})
        return {
            "session_id": session_id,
            "checkpoint": checkpoint,
            "passed": st.get("passed", False),
            "decided_by": st.get("decided_by"),
            "decided_at": st.get("decided_at"),
        }

    def view_drawing_review(self, *, session_id: str) -> dict:
        """只读查看图纸审核节点（drawing_verified）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下查看审核（红线①/⑥）"
            )
        return self._checkpoint_status(session_id, "drawing_verified")

    def view_solution_review(self, *, session_id: str) -> dict:
        """只读查看方案审核节点（solution_reviewed）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下查看审核（红线①/⑥）"
            )
        return self._checkpoint_status(session_id, "solution_reviewed")

    def view_cost_review(self, *, session_id: str) -> dict:
        """只读查看成本审核节点（cost_reviewed）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下查看审核（红线①/⑥）"
            )
        return self._checkpoint_status(session_id, "cost_reviewed")

    def submit_human_decision(
        self, *, session_id: str, checkpoint: str, by_human: bool = False
    ) -> None:
        """提交一次人工审核决策（**仅人工**）。

        AI 调用（``by_human=False``）一律抛 ``SolutionRedLineViolationError``（红线⑤）。
        仅当 ``by_human=True`` 时桥接到底层审核节点的 ``mark(by_human=True)``。
        """
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下提交审核（红线①/⑥）"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                f"AI 不得自动通过人工审核节点 {checkpoint!r}：submit_human_decision 必须 "
                "by_human=True（红线⑤）。最终审核须经真实主理人/专家线下决策。"
            )
        cp = self._checkpoint(session_id)
        cp.mark(checkpoint, by_human=True)


__all__ = [
    "SolutionRedLineViolationError",
    "AssistantSession",
    "WorkflowRequest",
    "AssistantWorkflowBridge",
    "AssistantResponse",
    "HumanReviewPortal",
]
