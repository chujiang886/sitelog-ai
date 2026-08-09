"""Production Readiness Checker（Phase 3.2 Sprint 3.2.5-G2, Task2/Task3）。

统一生产就绪核验器 ``ProductionReadinessChecker``：聚合 G1-G6 门禁 +
E-TH 真实化 + 审核链完整性 + 授权在场 + verified.json 绕过检测
（``manual_modified_thresholds``），输出结构化 ``ProductionReadinessReport``。

红线总约束：本模块**只读、不落盘、不翻转 engineering_enabled、不输出
engineering_approved、不修改 verified.json / review_log / 授权库**；真实工程
数据必须由人工提供。门禁判定的唯一事实来源仍是
``agents.engineering.gate.enable_gate.can_enable_engineering``。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from agents.engineering.gate.enable_gate import (
    can_enable_engineering,
    required_audit_events,
)
from agents.engineering.release.approval import (
    is_approval_effective,
    load_approval_records,
)
from agents.engineering.release.readiness import (
    check_e_th_realization,
    check_review_log_chain,
    manual_modified_thresholds,
)


@dataclass
class ProductionReadinessReport:
    """统一生产就绪报告（Task2 指定字段：passed / blocking_reasons / gate_status）。

    - ``passed``：通过的检查项名称列表；
    - ``failed``：未通过的检查项名称列表；
    - ``blocking_reasons``：门禁阻断原因（G1-G6 原因 + 绕过标记）；
    - ``gate_status``：G1-G6 + verified_integrity 逐项 bool；
    - ``details``：各子检查的详细上下文（opaque，供报告渲染）。
    """

    interface: str
    passed: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    blocking_reasons: list[str] = field(default_factory=list)
    gate_status: dict[str, Any] = field(default_factory=dict)
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def allowed(self) -> bool:
        """G1-G6 是否全部通过（verified_integrity 不计入放行判定）。"""

        core = (
            "G1_threshold_governance",
            "G2_dual_sign",
            "G3_ci",
            "G4_audit_chain",
            "G5_rollback",
            "G6_authorization",
        )
        return all(self.gate_status.get(k, False) for k in core)

    def to_dict(self) -> dict[str, Any]:
        """序列化为统一 JSON 报告。"""

        return {
            "interface": self.interface,
            "passed": list(self.passed),
            "failed": list(self.failed),
            "blocking_reasons": list(self.blocking_reasons),
            "gate_status": dict(self.gate_status),
            "details": dict(self.details),
        }


class ProductionReadinessChecker:
    """统一生产就绪核验器（Task2）。

    仅读不写；所有外部条件默认不满足（``ci_green`` / ``rollback_ready`` 注入
    False，``authorization_present`` 由真实授权库派生）。``run()`` 返回
    ``ProductionReadinessReport``。
    """

    def __init__(
        self,
        *,
        interface: str = "wind_pressure",
        thresholds: Iterable[Mapping[str, object]] | None = None,
        ci_green: bool = False,
        rollback_ready: bool = False,
        authorization_present: bool = False,
        review_log_path: Path | str | None = None,
        require_audit_chain: bool = True,
        approval_path: Path | str | None = None,
        verified_path: Path | str | None = None,
    ) -> None:
        self.interface = interface
        self.thresholds = thresholds
        self.ci_green = ci_green
        self.rollback_ready = rollback_ready
        self.authorization_present = authorization_present
        self.review_log_path = review_log_path
        self.require_audit_chain = require_audit_chain
        self.approval_path = approval_path
        self.verified_path = verified_path

    def required_audit_events(self) -> list[str]:
        """返回本接口通过 G4 所需的审核事件集合（委托 enable_gate）。"""

        return required_audit_events(self.interface)

    def run(self) -> ProductionReadinessReport:
        """执行统一核验，返回 ``ProductionReadinessReport``。"""

        # —— G1-G6 门禁（单一事实来源：can_enable_engineering）。
        allowed, reasons = can_enable_engineering(
            thresholds=self.thresholds,
            ci_green=self.ci_green,
            rollback_ready=self.rollback_ready,
            authorization_present=self.authorization_present,
            review_log_path=self.review_log_path,
            require_audit_chain=self.require_audit_chain,
        )

        # —— 子检查上下文（用于报告 details）。
        e_th = check_e_th_realization(
            self.interface,
            thresholds=self.thresholds,
            verified_path=self.verified_path,
        )
        chain = check_review_log_chain(review_log_path=self.review_log_path)
        integrity = manual_modified_thresholds(
            verified_path=self.verified_path,
            review_log_path=self.review_log_path,
        )
        approvals = load_approval_records(self.approval_path)
        auth_present = self.authorization_present or any(
            rec.interface == self.interface and is_approval_effective(rec)
            for rec in approvals
        )

        # —— 逐项门禁状态（True=通过）。
        gate_status: dict[str, Any] = {
            "G1_threshold_governance": not any(r.startswith("G1") for r in reasons),
            "G2_dual_sign": not any(r.startswith("G2") for r in reasons),
            "G3_ci": not any(r.startswith("G3") for r in reasons),
            "G4_audit_chain": not any(r.startswith("G4") for r in reasons),
            "G5_rollback": not any(r.startswith("G5") for r in reasons),
            "G6_authorization": not any(r.startswith("G6") for r in reasons),
            "verified_integrity": bool(integrity.get("ok")),
        }

        checks: dict[str, bool] = dict(gate_status)
        passed = [name for name, ok in checks.items() if ok]
        failed = [name for name, ok in checks.items() if not ok]

        blocking = list(reasons)
        if not integrity.get("ok"):
            bypassed = integrity.get("bypassed_ids", [])
            blocking.extend(f"VERIFIED_BYPASS:{tid}" for tid in bypassed)

        return ProductionReadinessReport(
            interface=self.interface,
            passed=passed,
            failed=failed,
            blocking_reasons=blocking,
            gate_status=gate_status,
            details={
                "e_th_realization": e_th,
                "review_log_chain": chain,
                "verified_integrity": integrity,
                "approval_present": len(approvals) > 0,
                "approval_effective": auth_present,
                "required_audit_events": self.required_audit_events(),
            },
        )


__all__ = [
    "ProductionReadinessReport",
    "ProductionReadinessChecker",
]
