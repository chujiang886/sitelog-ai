"""Engineering 工程计算统一结果基类（Phase 3.2 Sprint 3.2.1）。

承载五工程模块 Result（wind_pressure / glass_safety / profile / hardware /
installation_risk）共享的九字段 + as_interface() + as_full()，消除约 200 行
重复，并将红线不变量集中到本类。

设计依据：Phase 3.1 Final Integration 同构分析（.ai/tasks/
phase3.1_result_abstraction_analysis.md §4 迁移方案草案）。

红线（Sprint 3.2.1，强制）：
- 本基类**不新增**任何工程计算逻辑，仅重构 Result 模型结构；
- 不修改五模块输入输出语义；不填真实工程参数；
- verification_status 默认 PENDING_VERIFICATION；result 在 pending 态为空串；
- engineering_enabled 保持 false；不输出 engineering_approved。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from agents.engineering.validation import PENDING_VERIFICATION

# 合法 verification_status 取值（pending 为默认；approved / invalid_structure
# 由 validator 双签链在真实闭环阶段产生，本 Sprint 不触达）。
_RED_LINE_STATUSES: tuple[str, ...] = (
    PENDING_VERIFICATION,
    "approved",
    "invalid_structure",
)


@dataclass
class EngineeringCalculationResult:
    """工程计算统一结果基类（Sprint 3.2.1 任务：结果抽象）。

    九字段（result / confidence / evidence / verification_status /
    intermediate / provenance / threshold_refs / gaps / sign_off_id）下沉于此；
    两方法（as_interface / as_full）统一实现；红线闸门 enforce_redline() 集中。

    子类须覆盖类级常量 ``INTERFACE``（接口标识，如 "wind_pressure"）。
    """

    result: str = ""
    confidence: str = PENDING_VERIFICATION
    evidence: str = ""
    verification_status: str = PENDING_VERIFICATION
    intermediate: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    threshold_refs: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    sign_off_id: str | None = None

    # 子类覆盖：接口标识（如 "wind_pressure"）。ClassVar 防止成为 dataclass 字段。
    INTERFACE: ClassVar[str] = ""

    # 接口契约：返回恰好四字段（保持 EngineeringAgent 接口不变）。
    def as_interface(self) -> dict[str, Any]:
        """返回 EngineeringAgent 接口所需的统一四字段结构（精确四键）。"""

        return {
            "result": self.result,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
        }

    # 完整内部表示（供计算器自测 / 编排增强消费）。
    def as_full(self) -> dict[str, Any]:
        """返回含扩展字段的完整结果（八字段 + interface 标识）。"""

        return {
            "interface": type(self).INTERFACE,
            "result": self.result,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
            "intermediate": self.intermediate,
            "provenance": self.provenance,
            "threshold_refs": self.threshold_refs,
            "gaps": self.gaps,
            "sign_off_id": self.sign_off_id,
        }

    # 红线闸门（任务要求：pending 态 result 必须为空、verification_status 必须 pending）。
    def enforce_redline(self) -> None:
        """红线闸门：pending 态下 result 必须为空、verification_status 必须 pending。

        用于 AgentResult 装配前调用，防未来误填真实数值或误置 approved。
        """

        if self.verification_status == PENDING_VERIFICATION:
            assert self.result == "", (
                "红线违规：pending 态 result 必须为空串（不得产出真实工程数值）"
            )
        assert self.verification_status in _RED_LINE_STATUSES, (
            f"未知 verification_status: {self.verification_status!r}"
        )


__all__ = [
    "EngineeringCalculationResult",
    "PENDING_VERIFICATION",
]
