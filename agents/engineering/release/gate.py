"""Release Pre-check Gate（Phase 3.2 Sprint 3.2.5-F）。

实现 ``release_precheck()`` —— 发布前门禁检查，统一经由
``ProductionReadinessChecker`` 生成报告（G1-G6 判定的唯一事实来源仍是
``can_enable_engineering``）。

关键不变量（红线）：
- 默认返回 ``(False, reasons)``：所有外部条件缺省取"不满足"，确保灰度闸门
  默认拒绝、不可误开；
- 本函数只判定"是否允许"，**绝不**自行翻 ``engineering_enabled``、不输出
  ``engineering_approved``、不修改任何配置或签字库。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping


def release_precheck(
    *,
    interface: str,
    thresholds: Iterable[Mapping[str, object]] | None = None,
    ci_green: bool = False,
    rollback_ready: bool = False,
    authorization_present: bool = False,
    review_log_path: Path | str | None = None,
    require_audit_chain: bool = True,
    return_report: bool = False,
):
    """执行 G1-G6 发布前检查，统一经由 ``ProductionReadinessChecker`` 生成报告。

    参数：
    - ``interface``：待启用灰度的接口（仅用于审计上下文，不参与判定）；
    - ``thresholds``：阈值条目集合；缺省加载真实签字库（当前全 draft → G1/G2 失败）；
    - ``ci_green`` / ``rollback_ready`` / ``authorization_present``：外部注入条件，
      默认 False（不满足条件）；
    - ``review_log_path`` / ``require_audit_chain``：审核链完整性检查；
    - ``return_report``：为 True 时直接返回 ``ProductionReadinessReport``（统一
      JSON 报告），否则返回兼容的 ``(allowed, blocking_reasons)`` 元组（既有调用方
      controller / production_readiness 不受影响）。

    返回：``(allowed, blocking_reasons)`` 或 ``ProductionReadinessReport``。
    所有条件默认不满足 → ``(False, reasons)``。

    红线：不修改配置、不输出 approved、不翻转 ``engineering_enabled``。
    """

    # 任务书（3.2.5-G2 Task3）：统一经由 ProductionReadinessChecker 生成报告。
    from agents.engineering.release.production_checker import (
        ProductionReadinessChecker,
    )

    checker = ProductionReadinessChecker(
        interface=interface,
        thresholds=thresholds,
        ci_green=ci_green,
        rollback_ready=rollback_ready,
        authorization_present=authorization_present,
        review_log_path=review_log_path,
        require_audit_chain=require_audit_chain,
    )
    report = checker.run()
    if return_report:
        return report
    return (report.allowed, report.blocking_reasons)


__all__ = ["release_precheck"]
