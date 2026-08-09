"""Case Knowledge Layer — 案例生命周期状态机（Phase 3.7.3 Task 3）。

定义案例从采集到工程引用的四阶生命周期：
    Captured → Verified_Source → Expert_Reviewed → Engineering_Referenced

红线⑤：AI 不自动批准案例规则。本状态机**仅允许由人工触发的单步前向转移**：
- 无 auto-advance（不自动推进）；
- 无 approve / merge / delete（不提供任何处置方法）；
- 每个转移目标态 ``requires_human_review`` 恒 True；
- 逆向/跳阶/AI 驱动转移一律抛 ``CaseLifecycleError``（fail-closed）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class CaseLifecycleError(ValueError):
    """案例生命周期非法转移（fail-closed 抛错）。"""


class CaseLifecycleStage(str, Enum):
    """案例生命周期阶段（值即落库字符串）。"""

    CAPTURED = "Captured"
    VERIFIED_SOURCE = "Verified_Source"
    EXPERT_REVIEWED = "Expert_Reviewed"
    ENGINEERING_REFERENCED = "Engineering_Referenced"

    @classmethod
    def all_values(cls) -> list[str]:
        return [m.value for m in cls]


# 合法单步前向转移（仅相邻阶，禁止跳阶/逆向）。
_LIFECYCLE_TRANSITIONS: dict[str, str] = {
    CaseLifecycleStage.CAPTURED.value: CaseLifecycleStage.VERIFIED_SOURCE.value,
    CaseLifecycleStage.VERIFIED_SOURCE.value: CaseLifecycleStage.EXPERT_REVIEWED.value,
    CaseLifecycleStage.EXPERT_REVIEWED.value: CaseLifecycleStage.ENGINEERING_REFERENCED.value,
}


@dataclass
class CaseLifecycle:
    """案例生命周期状态机（人工驱动，只读校验）。

    唯一的前向转移入口是 ``advance()``，调用方须声明 ``by_human_reviewer=True``
    以证明由真实人工触发；否则抛 ``CaseLifecycleError``（红线⑤）。
    """

    case_id: str
    stage: str = CaseLifecycleStage.CAPTURED.value

    @property
    def requires_human_review(self) -> bool:
        """任何阶段都须人工审核（红线⑤）。"""
        return True

    def can_advance(self) -> bool:
        """是否还存在合法前向阶段。"""
        return self.stage in _LIFECYCLE_TRANSITIONS

    def next_stage(self) -> str | None:
        """下一合法前向阶段（无则 None）。"""
        return _LIFECYCLE_TRANSITIONS.get(self.stage)

    def advance(self, *, by_human_reviewer: bool = False) -> "CaseLifecycle":
        """单步前向转移；**仅**允许由真实人工审核者触发。

        红线⑤：``by_human_reviewer`` 必须显式 ``True``，AI 不得代触发；
        逆向/跳阶/终态再推进均抛 ``CaseLifecycleError``（fail-closed）。
        """
        if not by_human_reviewer:
            raise CaseLifecycleError(
                f"红线⑤违例：案例 {self.case_id!r} 生命周期推进须由真实人工审核者触发，"
                f"AI 不得代推进（stage={self.stage!r}）"
            )
        nxt = _LIFECYCLE_TRANSITIONS.get(self.stage)
        if nxt is None:
            raise CaseLifecycleError(
                f"案例 {self.case_id!r} 当前阶段 {self.stage!r} 无可前向阶段"
                f"（已达终态或非法态）"
            )
        self.stage = nxt
        return self

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "stage": self.stage,
            "can_advance": self.can_advance(),
            "next_stage": self.next_stage(),
            "requires_human_review": self.requires_human_review,
        }


__all__ = [
    "CaseLifecycleStage",
    "CaseLifecycle",
    "CaseLifecycleError",
]
