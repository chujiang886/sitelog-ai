"""Enterprise Analytics & Operation Intelligence Layer —— 风险预警（任务5，Phase 3.8.4）。

新增：``OperationRiskDetector``，输出 ``risk_candidate``，**要求人工确认**。
**禁止 AI 代替管理责任**：不提供任何 resolve / decide / auto_* 决策入口（红线③/⑥）。

红线约束（fail-closed，3.8.4 语义升级）：
- 所有风险候选按 ``org_id`` 作用域过滤；跨域访问抛 ``EnterpriseIsolationError``。
- 构造断言 ``safety_invariants_ok()``（红线①/⑤）。
- ``RiskCandidate.requires_human_confirmation`` 恒为 True（必须人工确认）。
- 不持有批准/报价/审批/记录为人工方法（红线②/③/④/⑥）；额外拦截
  resolve / decide / auto_decide / mitigate / manage 等决策入口（红线③/⑥）。
- 可选联动 ``AuditService.record_ai_action`` 如实标注检测由 AI 发起（actor=AI）。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class RiskSeverity(str, Enum):
    """风险严重程度（事实分级，不承载决策语义）。"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass
class RiskCandidate:
    """风险候选（任务5）。

    由 AI 检测输出，**要求人工确认**（``requires_human_confirmation`` 恒为 True）。
    AI 不代管理做判断（红线③/⑥）：不含任何已处理/已决策状态。
    """

    risk_id: str
    org_id: str
    risk_type: str                 # 风险类型（sla_overdue / low_completion / bottleneck ...）
    description: str = ""
    severity: RiskSeverity = RiskSeverity.MEDIUM
    evidence: str = ""             # 触发证据（事实数据）
    requires_human_confirmation: bool = True   # 恒为 True：必须人工确认
    detected_at: str = ""
    detected_by: str = "ai"        # 恒为 ai（检测方，非决策方）

    def __post_init__(self) -> None:
        # 红线③/⑥：任何风险候选都强制要求人工确认，AI 不代管理做判断。
        self.requires_human_confirmation = True


class OperationRiskDetector(_RedLineForbiddenMixin):
    """风险预警检测器（任务5）。

    输出风险候选，**要求人工确认**；**不**代管理做决策（红线③/⑥）。
    跨域访问抛 ``EnterpriseIsolationError``；构造断言 ``safety_invariants_ok()``（红线①/⑤）。
    """

    _FORBIDDEN = (
        "approve",
        "engineering_approved",
        "quote",
        "pricing",
        "sign",
        "authorize",
        "record_human_approval",
        # 3.8.4 语义升级：禁止自动经营决策 / AI 代管理责任 / 风险处置决策
        "resolve",
        "decide",
        "auto_decide",
        "mitigate",
        "manage",
        "auto_business_decision",
        "make_management_decision",
    )

    def __init__(self, org_id: str, audit: "AuditService | None" = None) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 "
                "OperationRiskDetector（红线①/⑤）"
            )
        self._org_id = org_id
        self._audit = audit
        self._candidates: dict[str, RiskCandidate] = {}

    def detect_risks(
        self,
        *,
        signals: "list[dict] | None" = None,
        detected_at: str = "",
    ) -> list[RiskCandidate]:
        """基于事实信号输出风险候选（**要求人工确认**；AI 不代管理决策；红线③/⑥）。

        ``signals`` 为外部传入的事实信号列表（每条含 risk_type / severity / description /
        evidence 等），本方法仅将其**如实**转换为 RiskCandidate，不做任何处置/决策。
        """
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下检测风险（红线①/⑤）"
            )
        out: list[RiskCandidate] = []
        for i, sig in enumerate(signals or []):
            rid = sig.get("risk_id") or f"RISK-{self._org_id}-{i+1}"
            sev_raw = sig.get("severity", "medium")
            try:
                sev = RiskSeverity(sev_raw)
            except ValueError:
                sev = RiskSeverity.MEDIUM
            cand = RiskCandidate(
                risk_id=rid,
                org_id=self._org_id,
                risk_type=sig.get("risk_type", "unknown"),
                description=sig.get("description", ""),
                severity=sev,
                evidence=sig.get("evidence", ""),
                detected_at=detected_at,
                detected_by="ai",
            )
            self._candidates[rid] = cand
            out.append(cand)
        if self._audit is not None:
            self._audit.record_ai_action(
                record_id=f"risk-detect-{self._org_id}-{detected_at}",
                actor_id="ai",
                action="detect_operation_risks",
                target=self._org_id,
                detail=f"candidates={len(out)}",
                ts=detected_at,
            )
        return out

    def list_candidates(self) -> list[RiskCandidate]:
        """列出已检测的风险候选（仅输出，不含处置）。"""
        return [c for c in self._candidates.values() if c.org_id == self._org_id]


__all__ = ["RiskSeverity", "RiskCandidate", "OperationRiskDetector"]
