"""Drawing Intelligence Layer（Phase 3.7.7）。

在 3.7.6 成本智能层之上，建立「图纸智能解析层」：
- ``DrawingParser``：解析 PDF / CAD / Image 图纸，输出 ``DesignCandidate``；**所有解析结果
  必须带 ``source_ref`` + ``confidence`` 占位**（红线③/④：AI 不自动确认图纸尺寸、不自动
  生成真实工程参数，geometry / opening_type / glass_config / profile_config 恒为
  ``PENDING_PLACEHOLDER``）；
- ``VisionAdapter``：图像 / 图纸视觉分析（image_analysis / drawing_analysis），仅产出只读
  分析壳（``VisionAnalysisReport``），**禁止直接进入工程结论**（不输出尺寸/参数/报价）；
- ``DesignReviewQueue``：尺寸审核队列（parsed / reviewing / verified_by_human / rejected），
  **仅人工** 可进入 ``verified_by_human``（红线②：AI 不得批准/终裁）；
- ``DesignGraphConnector``：将 ``DesignCandidate`` 只读关联 Solution / Case / KnowledgeItem /
  SourceRef（产出 ``DesignKnowledgeLinkReport``），**不写图、不新增关系到 17 白名单**。

====================
最高红线（fail-closed，6 条）
====================
① 禁止开启 ``engineering_enabled``（构造/解析/分析/审核/连接全断言 ``safety_invariants_ok``）；
② 禁止输出 ``engineering_approved``（``approve`` / ``verify`` 仅 ``by_human=True`` 可入
   ``verified_by_human``，AI 调用抛 ``SolutionRedLineViolationError``）；
③ 禁止自动确认图纸尺寸（forbidden 方法名 ``confirm_dimension``；解析结果 geometry 等恒占位）；
④ 禁止自动生成真实工程参数（forbidden 方法名 ``generate_engineering_param``；glass_config /
   profile_config 等恒占位）；
⑤ 禁止自动报价（forbidden 方法名 ``quote`` / ``pricing``）；
⑥ 禁止绕过 ``UnifiedActivationGate``（所有构造/决策路径先断言 ``safety_invariants_ok``）。

本层仅承载图纸解析占位壳、视觉分析壳、人工审核队列与只读关联报告；真实尺寸/工程参数/报价
须经专家双签 + 主理人核准（G6）写入来源系统，属激活阶段，绝不在本层发生。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from agents.engineering.gate.unified_activation_gate import UnifiedActivationGate
from agents.engineering.knowledge.graph.entities import (
    PENDING_PLACEHOLDER,
    PENDING_VERIFICATION,
    DesignCandidate,
)
from agents.engineering.knowledge.graph.repository import KnowledgeGraphRepository
from agents.engineering.knowledge.graph.solution_generation import (
    SolutionRedLineViolationError,
    SolutionReviewError,
    _RedLineForbiddenMixin,
)


def _utc_now() -> str:
    """返回 UTC ISO8601 时间戳（审计用）。"""
    return datetime.now(timezone.utc).isoformat()


# 图纸智能层 forbidden 方法名（覆盖红线②/③/④/⑤，相较 3.7.6 成本层新增
# confirm_dimension / generate_engineering_param，移除 deal_price / final_price /
# market_price —— 3.7.7 红线清单不含「自动成交价 / 伪造市场价」）。
_FORBIDDEN_DRAWING_METHODS = (
    "approve",                     # 红线②：不得批准（仅 by_human 可入 verified_by_human）
    "select",                      # 红线③：不得选终
    "finalize",                    # 红线③：不得定稿
    "activate",                    # 红线③：不得激活
    "engineering_approved",        # 红线②：不得输出 engineering_approved
    "quote",                       # 红线⑤：禁止自动报价
    "pricing",                     # 红线⑤：禁止自动报价
    "confirm_dimension",           # 红线③：禁止自动确认图纸尺寸
    "generate_engineering_param",  # 红线④：禁止自动生成真实工程参数
)


# ---------------------------------------------------------------------------
# 报告载体（纯数据，含解析/分析/关联信息；不含任何决策位/报价位/真实尺寸位）
# ---------------------------------------------------------------------------
@dataclass
class ParsedDesignDraft:
    """图纸解析占位壳（仅解析，禁止确认尺寸/生成参数/报价，红线③/④/⑤）。

    所有真实尺寸/几何/型材/玻璃字段默认 ``PENDING_PLACEHOLDER``，AI 不填真实图纸尺寸、
    不生成真实工程参数、不报价。真实取值须经来源（专家双签 + 主理人核准）由人工填充。

    解析必须带 ``source_ref``（溯源）与 ``confidence``（不确定性标记，恒占位）。
    """

    parse_id: str
    design_id: str
    source_ref: str
    parse_format: str  # "pdf" / "cad" / "image"
    source_files: list[str] = field(default_factory=list)
    geometry: Any = PENDING_PLACEHOLDER
    opening_type: str = PENDING_PLACEHOLDER
    glass_config: Any = PENDING_PLACEHOLDER
    profile_config: Any = PENDING_PLACEHOLDER
    confidence: Any = PENDING_PLACEHOLDER
    verification_status: str = PENDING_VERIFICATION
    notes: list[str] = field(default_factory=list)


@dataclass
class VisionAnalysisReport:
    """视觉分析占位壳（仅描述性分析，禁止工程结论，红线③/④/⑤）。

    仅记录图像/图纸的可见特征占位（恒 ``PENDING_PLACEHOLDER``），**不下尺寸/参数结论、
    不报价**。任何工程结论须由真实主理人/专家线下给出。
    """

    analysis_id: str
    source_ref: str
    analysis_type: str  # "image_analysis" / "drawing_analysis"
    observations: list[str] = field(default_factory=list)
    geometry_hint: Any = PENDING_PLACEHOLDER
    opening_hint: str = PENDING_PLACEHOLDER
    requires_engineering_review: bool = True
    notes: list[str] = field(default_factory=list)


@dataclass
class DesignKnowledgeLinkReport:
    """设计候选知识关联报告（关联 Solution / Case / KnowledgeItem / SourceRef）。

    只读聚合（不写图、不新增关系到 17 白名单），列出 ``DesignCandidate`` 与上述四类载体的
    关联（引用 id + 状态），供人工核验图纸设计的知识溯源。
    """

    design_id: str
    referenced_solutions: list[str] = field(default_factory=list)
    referenced_cases: list[str] = field(default_factory=list)
    referenced_knowledge_items: list[str] = field(default_factory=list)
    referenced_source_refs: list[str] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    requires_human_review: bool = True


# ---------------------------------------------------------------------------
# 任务2：图纸解析适配器（PDF / CAD / Image → DesignCandidate，带 source_ref + confidence）
# ---------------------------------------------------------------------------
class DrawingParser(_RedLineForbiddenMixin):
    """图纸解析器（Drawing Parser）。

    解析 PDF / CAD / Image 图纸，输出 ``DesignCandidate``。**所有解析结果必须带
    ``source_ref`` + ``confidence`` 占位**；geometry / opening_type / glass_config /
    profile_config 恒为 ``PENDING_PLACEHOLDER``（红线③/④：AI 不自动确认图纸尺寸、不自动
    生成真实工程参数），``verification_status`` 默认 ``PENDING_VERIFICATION``。

    红线：
    - ⑥ 构造与每次解析均断言 ``safety_invariants_ok()``；
    - ③ 无 ``confirm_dimension``（mixin 拦截，禁止自动确认尺寸）；
    - ④ 无 ``generate_engineering_param``（mixin 拦截，禁止自动生成工程参数）；
    - ⑤ 无 ``quote`` / ``pricing``（mixin 拦截，禁止报价）；
    - ①/② 无 ``select`` / ``finalize`` / ``activate`` / ``approve`` / ``engineering_approved``
      （mixin 拦截）。
    """

    _FORBIDDEN = _FORBIDDEN_DRAWING_METHODS

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造图纸解析器（红线①/⑥）"
            )

    def _parse(
        self,
        *,
        design_id: str,
        file_path: str,
        parse_format: str,
        source_ref: Optional[str] = None,
    ) -> DesignCandidate:
        """内部解析：恒产出带 source_ref + confidence 占位的 DesignCandidate。

        红线③/④/⑤：geometry / opening_type / glass_config / profile_config 全部为
        ``PENDING_PLACEHOLDER``，AI 不在解析阶段填写真实尺寸/参数/报价。
        """
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下解析图纸（红线①/⑥）"
            )
        src_ref = source_ref or file_path  # source_ref 必须有值（溯源），默认用文件路径
        candidate = DesignCandidate(
            design_id=design_id,
            source_files=[file_path],
            # 红线③/④/⑤：真实取值位全部占位
            geometry=PENDING_PLACEHOLDER,
            opening_type=PENDING_PLACEHOLDER,
            glass_config=PENDING_PLACEHOLDER,
            profile_config=PENDING_PLACEHOLDER,
            confidence=PENDING_PLACEHOLDER,
            verification_status=PENDING_VERIFICATION,
            metadata={
                # 任务2：解析结果必须带 source_ref + confidence
                "source_ref": src_ref,
                "parse_format": parse_format,
                "confidence": PENDING_VERIFICATION,
                "note": (
                    "仅占位解析：真实图纸尺寸/型材/玻璃配置须经专家双签 + 主理人核准"
                    "由人工导入（红线③/④）。"
                ),
            },
        )
        return candidate

    def parse_pdf(
        self, file_path: str, *, design_id: str, source_ref: Optional[str] = None
    ) -> DesignCandidate:
        """解析 PDF 图纸 → DesignCandidate（占位，带 source_ref + confidence）。"""
        return self._parse(
            design_id=design_id,
            file_path=file_path,
            parse_format="pdf",
            source_ref=source_ref,
        )

    def parse_cad(
        self, file_path: str, *, design_id: str, source_ref: Optional[str] = None
    ) -> DesignCandidate:
        """解析 CAD 图纸 → DesignCandidate（占位，带 source_ref + confidence）。"""
        return self._parse(
            design_id=design_id,
            file_path=file_path,
            parse_format="cad",
            source_ref=source_ref,
        )

    def parse_image(
        self, file_path: str, *, design_id: str, source_ref: Optional[str] = None
    ) -> DesignCandidate:
        """解析 Image 图纸 → DesignCandidate（占位，带 source_ref + confidence）。"""
        return self._parse(
            design_id=design_id,
            file_path=file_path,
            parse_format="image",
            source_ref=source_ref,
        )


# ---------------------------------------------------------------------------
# 任务3：视觉接口（image_analysis / drawing_analysis → 只读分析壳，禁止工程结论）
# ---------------------------------------------------------------------------
class VisionAdapter(_RedLineForbiddenMixin):
    """视觉适配器（Vision Adapter）。

    提供图像/图纸视觉分析（image_analysis / drawing_analysis），仅产出只读分析壳
    （``VisionAnalysisReport``）。**禁止直接进入工程结论**（不输出真实尺寸/工程参数/报价）。

    红线：同 ``DrawingParser``（构造与每次分析断言 ``safety_invariants_ok``，拦截
    confirm_dimension / generate_engineering_param / quote / pricing / approve 等）。
    """

    _FORBIDDEN = _FORBIDDEN_DRAWING_METHODS

    def __init__(self, repository: Optional[KnowledgeGraphRepository] = None) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造视觉适配器（红线①/⑥）"
            )

    def _analyze(self, *, source_ref: str, analysis_type: str) -> VisionAnalysisReport:
        """内部分析：仅描述性占位壳，不进工程结论（红线③/④/⑤）。"""
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下做视觉分析（红线①/⑥）"
            )
        return VisionAnalysisReport(
            analysis_id=f"VIS-{analysis_type}-{_utc_now()}",
            source_ref=source_ref,
            analysis_type=analysis_type,
            observations=[
                "（占位分析）可见特征须由真实主理人/专家线下判读，AI 不进工程结论。",
            ],
            # 红线③/④：几何/开口仅为 hint 占位，绝不输出真实尺寸/参数
            geometry_hint=PENDING_PLACEHOLDER,
            opening_hint=PENDING_PLACEHOLDER,
            requires_engineering_review=True,
            notes=[
                "本层禁止确认尺寸/生成工程参数/报价（红线③/④/⑤）。",
            ],
        )

    def image_analysis(self, image_path: str, *, source_ref: Optional[str] = None) -> VisionAnalysisReport:
        """图像分析（只读描述壳，禁止工程结论）。"""
        return self._analyze(
            source_ref=source_ref or image_path,
            analysis_type="image_analysis",
        )

    def drawing_analysis(self, drawing_path: str, *, source_ref: Optional[str] = None) -> VisionAnalysisReport:
        """图纸分析（只读描述壳，禁止工程结论）。"""
        return self._analyze(
            source_ref=source_ref or drawing_path,
            analysis_type="drawing_analysis",
        )


# ---------------------------------------------------------------------------
# 任务4：尺寸人工审核队列（parsed / reviewing / verified_by_human / rejected）
# ---------------------------------------------------------------------------
@dataclass
class DesignReviewItem:
    """尺寸审核条目（状态机载体）。"""

    review_id: str
    design_id: str
    state: str
    candidate: DesignCandidate
    created_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None


class DesignReviewQueue:
    """尺寸审核队列（状态机：parsed → reviewing → verified_by_human / rejected）。

    红线：
    - ② ``verify`` 仅 ``by_human=True`` 可进入 ``verified_by_human``；AI 调用抛
      ``SolutionRedLineViolationError``（禁止输出 engineering_approved / 进入终裁态）；
    - ④/⑥ 构造/决策路径断言 ``safety_invariants_ok()``；
    - 非法状态转移抛 ``SolutionReviewError``（正常业务校验，非红线）。
    """

    STATES = ("parsed", "reviewing", "verified_by_human", "rejected")
    _REVIEWABLE = "reviewing"

    def __init__(self) -> None:
        self._items: dict[str, DesignReviewItem] = {}
        self._seq: int = 0
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造尺寸审核队列（红线①/⑥）"
            )

    def _get(self, review_id: str) -> DesignReviewItem:
        item = self._items.get(review_id)
        if item is None:
            raise SolutionReviewError(f"审核条目 {review_id!r} 不存在")
        return item

    def submit(self, candidate: DesignCandidate) -> str:
        """将解析出的设计候选提交入队（状态 parsed）。"""
        self._seq += 1
        rid = f"DREV-{candidate.design_id}-{self._seq}"
        self._items[rid] = DesignReviewItem(
            review_id=rid,
            design_id=candidate.design_id,
            state="parsed",
            candidate=candidate,
            created_at=_utc_now(),
        )
        return rid

    def begin_review(self, review_id: str) -> DesignReviewItem:
        """parsed → reviewing。"""
        item = self._get(review_id)
        if item.state != "parsed":
            raise SolutionReviewError(
                f"begin_review 失败：当前态 {item.state!r} 应为 parsed"
            )
        item.state = "reviewing"
        return item

    def verify(self, review_id: str, *, by_human: bool = False) -> DesignReviewItem:
        """reviewing → verified_by_human（**仅人工**）。"""
        item = self._get(review_id)
        if item.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"verify 失败：当前态 {item.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得批准尺寸：verify 必须 by_human=True（红线②）。"
                "最终核验须经真实主理人/专家线下决策。"
            )
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下核验尺寸（红线①/⑥）"
            )
        item.state = "verified_by_human"
        item.decided_at = _utc_now()
        item.decided_by = "human_reviewer"
        return item

    def reject(self, review_id: str, *, by_human: bool = False) -> DesignReviewItem:
        """reviewing → rejected（**仅人工**）。"""
        item = self._get(review_id)
        if item.state != self._REVIEWABLE:
            raise SolutionReviewError(
                f"reject 失败：当前态 {item.state!r} 应为 reviewing"
            )
        if not by_human:
            raise SolutionRedLineViolationError(
                "AI 不得做出终裁：reject 必须 by_human=True（红线②）。"
                "任何终裁须由真实主理人/专家驱动。"
            )
        item.state = "rejected"
        item.decided_at = _utc_now()
        item.decided_by = "human_reviewer"
        return item


# ---------------------------------------------------------------------------
# 任务5：设计候选 → 知识图谱只读连接（Solution / Case / KnowledgeItem / SourceRef）
# ---------------------------------------------------------------------------
class DesignGraphConnector:
    """设计候选知识图谱连接器（只读）。

    将 ``DesignCandidate`` 只读关联 **Solution / Case / KnowledgeItem / SourceRef** 四类
    载体（产出 ``DesignKnowledgeLinkReport``）。**不写图、不新增关系到 17 白名单**；所有
    关联以 id 列举 + 状态标注，供人工核验图纸设计的知识溯源。

    红线：只读，不写、不确认尺寸、不生成参数、不报价。
    """

    def __init__(self, repository: KnowledgeGraphRepository) -> None:
        self._repo = repository
        if not UnifiedActivationGate.safety_invariants_ok():
            raise SolutionRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造设计图谱连接器（红线①/⑥）"
            )

    def link(
        self,
        candidate: DesignCandidate,
        *,
        solution_ids: Optional[list[str]] = None,
        case_ids: Optional[list[str]] = None,
        knowledge_item_ids: Optional[list[str]] = None,
        source_ref_ids: Optional[list[str]] = None,
    ) -> DesignKnowledgeLinkReport:
        """只读聚合设计候选与四类载体的关联（不写图）。"""
        sol: list[str] = []
        cases: list[str] = []
        kis: list[str] = []
        srefs: list[str] = []

        # SolutionCandidate 关联（图谱遍历补充，若存在）
        for sid in (solution_ids or []):
            node = self._repo.get_node(sid) if self._repo is not None else None
            if node is not None and node.entity_type in ("SolutionCandidate", "Solution"):
                sol.append(sid)
            elif node is None:
                sol.append(sid)  # 仅记录关联意图，不写图

        # Case 关联
        for cid in (case_ids or []):
            node = self._repo.get_node(cid) if self._repo is not None else None
            if node is not None and node.entity_type == "Case":
                cases.append(cid)
            elif node is None:
                cases.append(cid)

        # KnowledgeItem 关联
        for kid in (knowledge_item_ids or []):
            node = self._repo.get_node(kid) if self._repo is not None else None
            if node is not None and node.entity_type == "KnowledgeItem":
                kis.append(kid)
            elif node is None:
                kis.append(kid)

        # SourceRef 关联（直接取解析期 source_ref）
        source_ref = candidate.metadata.get("source_ref")
        if source_ref:
            srefs.append(source_ref)
        for srid in (source_ref_ids or []):
            if srid not in srefs:
                srefs.append(srid)

        explanation = [
            f"设计候选 {candidate.design_id} 知识关联：",
            f"关联 Solution={sol}",
            f"关联 Case={cases}",
            f"关联 KnowledgeItem={kis}",
            f"关联 SourceRef={srefs}",
            "关联仅作知识溯源列举（只读），不写图、不新增关系到 17 白名单；"
            "真实尺寸/参数经人工核验后由激活阶段写入来源系统。",
        ]
        return DesignKnowledgeLinkReport(
            design_id=candidate.design_id,
            referenced_solutions=sol,
            referenced_cases=cases,
            referenced_knowledge_items=kis,
            referenced_source_refs=srefs,
            explanation=explanation,
            requires_human_review=True,
        )


__all__ = [
    "SolutionRedLineViolationError",
    "DrawingParser",
    "ParsedDesignDraft",
    "VisionAdapter",
    "VisionAnalysisReport",
    "DesignReviewQueue",
    "DesignReviewItem",
    "DesignGraphConnector",
    "DesignKnowledgeLinkReport",
]
