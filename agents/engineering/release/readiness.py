"""Engineering Production Readiness（Phase 3.2 Sprint 3.2.5-G2）。

首次工程灰度（wind_pressure）生产条件修复阶段的"就绪核验"工具集：

- Task1 ``check_e_th_realization``：核验 E-TH-01/02/03 的 ``value`` / ``unit`` /
  ``source_ref`` / ``version`` 已填且双签齐全；真实数值 / 签字必须由人工提供，
  本模块只读不写。
- Task2 ``check_review_log_chain``：核验 review_log 真实链含四类必需审计事件
  （submit / review / expert_recheck / verified）且链式无断裂；空链 / 缺类 / 断裂 → 不通过。
- Task3 ``validate_release_approval``：核验 ``EngineeringReleaseApproval`` 七字段
  录入齐全且格式合法（不自动创建、不填充）。
- Task3 ``manual_modified_thresholds``（别名 ``check_verified_integrity``）：检测是否
  绕过 ``ThresholdIntakeWorkflow`` 直接改动 ``verified.json``（仅读不写；填实条目须有
  完整审核链（submit / review / expert_recheck / verified），否则判绕过）。
- 复合 ``production_readiness`` / ``production_readiness_checker``：汇总上述 +
  ``release_precheck``(G1-G6) + 绕过检测，输出含 ``passed`` / ``failed`` /
  ``blocking_reasons`` 的结构化生产就绪报告。

红线总约束：本模块**只读、不落盘、不翻转 engineering_enabled、不输出
engineering_approved、不修改 verified.json / review_log / 授权库**；真实工程
数据必须由人工提供。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from agents.engineering.gate.enable_gate import REQUIRED_REVIEW_ACTIONS
from agents.engineering.release.approval import (
    EngineeringReleaseApproval,
    is_approval_effective,
    load_approval_records,
)
from agents.engineering.release.gate import release_precheck
from agents.engineering.review_log import read_log
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    is_fully_verified,
    load_verified_thresholds,
)
from agents.engineering.thresholds.schema import ThresholdSourceRef


# 占位 / 未就绪标记（视为"未真实化"）。
_PLACEHOLDER_STRINGS = ("pending_verification", "")


def _is_real_value(value: Any) -> bool:
    """``value`` 字段是否已填真实数值（非 null、非占位字符串）。"""

    if value is None:
        return False
    if isinstance(value, str) and value.strip().lower() in _PLACEHOLDER_STRINGS:
        return False
    return True


def _is_real_unit(unit: Any) -> bool:
    """``unit`` 字段是否已填且非占位。"""

    if not isinstance(unit, str):
        return False
    return unit.strip().lower() not in _PLACEHOLDER_STRINGS


def check_e_th_realization(
    interface: str = "wind_pressure",
    *,
    thresholds: Mapping[str, Mapping[str, Any]] | None = None,
    verified_path: Path | str | None = None,
) -> dict[str, Any]:
    """Task1：核验接口所需 E-TH 阈值是否已"真实化"（人工提供 + 双签）。

    检查每一条目：``value`` / ``unit`` / ``source_ref`` / ``version`` / 双签
    （主理人 + 专家）。返回结构化报告（仅读，不写）。来源必须由人工提供，
    本函数不生成任何数值、不填充任何签字。
    """

    if thresholds is None:
        thresholds = load_verified_thresholds(verified_path)
    required_ids = get_interface_thresholds(interface)
    per_id: dict[str, Any] = {}
    all_realized = True
    if not required_ids:
        all_realized = False
    for tid in required_ids:
        entry = thresholds.get(tid) if isinstance(thresholds, Mapping) else None
        if not isinstance(entry, Mapping):
            per_id[tid] = {
                "present": False,
                "value_real": False,
                "unit_real": False,
                "source_ref_complete": False,
                "version_present": False,
                "dual_signed": False,
                "realized": False,
                "missing": ["entry_absent"],
            }
            all_realized = False
            continue
        src = ThresholdSourceRef.from_raw(entry.get("source_ref"))
        value_real = _is_real_value(entry.get("value"))
        unit_real = _is_real_unit(entry.get("unit"))
        src_complete = src.is_complete()
        version_present = bool(str(entry.get("version") or "").strip())
        dual = is_fully_verified(entry)
        realized = (
            value_real and unit_real and src_complete and version_present and dual
        )
        missing = []
        if not value_real:
            missing.append("value")
        if not unit_real:
            missing.append("unit")
        if not src_complete:
            missing.append("source_ref")
        if not version_present:
            missing.append("version")
        if not dual:
            missing.append("dual_sign")
        per_id[tid] = {
            "present": True,
            "value_real": value_real,
            "unit_real": unit_real,
            "source_ref_complete": src_complete,
            "version_present": version_present,
            "dual_signed": dual,
            "realized": realized,
            "missing": missing,
        }
        if not realized:
            all_realized = False
    return {
        "interface": interface,
        "required_threshold_ids": list(required_ids),
        "per_threshold": per_id,
        "all_realized": all_realized,
    }


def check_review_log_chain(
    *,
    review_log_path: Path | str | None = None,
) -> dict[str, Any]:
    """Task2：核验 review_log 真实链：非空 + 链式无断裂 + 四类必需事件齐全。

    空链 / 断裂 / 缺类 → ``ok=False``，并报告缺失事件与是否断裂。仅读不写。
    """

    events = read_log(review_log_path)
    if not events:
        return {
            "ok": False,
            "empty": True,
            "broken": False,
            "missing_actions": list(REQUIRED_REVIEW_ACTIONS),
            "event_count": 0,
        }
    present = {
        ev.get("action")
        for ev in events
        if isinstance(ev, Mapping) and ev.get("action")
    }
    missing = [a for a in REQUIRED_REVIEW_ACTIONS if a not in present]
    # 链式完整性（首条 prev=None，其后依次衔接）。
    broken = False
    prev = None
    for ev in events:
        if not isinstance(ev, Mapping):
            broken = True
            break
        if ev.get("prev_event_id") != prev:
            broken = True
            break
        cur = ev.get("event_id")
        if not cur:
            broken = True
            break
        prev = str(cur)
    ok = (not broken) and (not missing)
    return {
        "ok": ok,
        "empty": False,
        "broken": broken,
        "missing_actions": missing,
        "event_count": len(events),
    }


def validate_release_approval(
    approval: EngineeringReleaseApproval | Mapping[str, Any],
) -> tuple[bool, list[str]]:
    """Task3：核验 ``EngineeringReleaseApproval`` 七字段录入齐全且格式合法。

    不自动创建、不填充任何字段；仅校验。返回 ``(ok, errors)``。
    SoD 软约束：``authorized_by`` 与 ``rollback_owner`` 不应相同（录入校验报错）。
    """

    if isinstance(approval, EngineeringReleaseApproval):
        data = approval.to_dict()
    elif isinstance(approval, Mapping):
        data = dict(approval)
    else:
        return False, ["approval 类型不支持（须为 EngineeringReleaseApproval 或 dict）"]
    required = [
        "approval_id",
        "interface",
        "scope",
        "authorized_by",
        "effective_time",
        "rollback_owner",
        "approval_document_ref",
    ]
    errors: list[str] = []
    for field_name in required:
        val = data.get(field_name)
        if val is None or (isinstance(val, str) and not val.strip()):
            errors.append(f"字段缺失或为空: {field_name}")
    # effective_time 若提供须为可解析 ISO8601（否则标注，不强行拒绝录入校验）。
    eff = (str(data.get("effective_time") or "")).strip()
    if eff:
        try:
            datetime.fromisoformat(eff)
        except ValueError:
            errors.append("effective_time 不是合法 ISO8601 时间")
    # SoD 软校验：授权人与回滚责任人不应相同（录入提醒，违反即报错）。
    if (
        data.get("authorized_by")
        and data.get("rollback_owner")
        and data["authorized_by"].strip() == data["rollback_owner"].strip()
    ):
        errors.append("authorized_by 与 rollback_owner 相同（违反 SoD 软约束）")
    return (len(errors) == 0, errors)


def manual_modified_thresholds(
    *,
    verified_path: Path | str | None = None,
    review_log_path: Path | str | None = None,
) -> dict[str, Any]:
    """Task3/Task4：检测是否绕过 ``ThresholdIntakeWorkflow`` 直接改 ``verified.json``。

    仅读不写（红线：本函数不修改签字库、不输出 approved）。

    判定规则：对签字库中任一"已填实"条目（``verified=true`` 或 ``value`` 非占位），
    必须在 ``review_log`` 中存在属于该 ``threshold_id`` 的**完整审核链**
    （``submit`` / ``review`` / ``expert_recheck`` /
    ``verified``）。缺少任一即视为"绕过工作流直接修改"（例如手工改库把
    某条目置 verified=true 却无审核链），报告 ``bypassed_ids`` 并阻止放行。

    当前真实态 ``verified.json`` 全 draft / ``value=null`` → 无绕过，``ok=True``。
    """

    thresholds = load_verified_thresholds(verified_path)
    events = read_log(review_log_path)
    # 按 threshold_id 归组已出现的审核 action。
    by_tid: dict[str, set[str]] = {}
    for ev in events:
        if not isinstance(ev, Mapping):
            continue
        tid = ev.get("threshold_id")
        act = ev.get("action")
        if tid and act:
            by_tid.setdefault(str(tid), set()).add(str(act))
    bypassed: list[str] = []
    checked = 0
    for tid, entry in thresholds.items():
        if not isinstance(entry, Mapping):
            continue
        filled = bool(entry.get("verified")) or _is_real_value(entry.get("value"))
        if not filled:
            continue  # 仍是 draft 占位，无绕过风险
        checked += 1
        chain = by_tid.get(str(tid), set())
        missing = [a for a in REQUIRED_REVIEW_ACTIONS if a not in chain]
        if missing:
            bypassed.append(str(tid))
    ok = len(bypassed) == 0
    return {
        "ok": ok,
        "bypassed_ids": bypassed,
        "checked_count": checked,
        "required_actions": list(REQUIRED_REVIEW_ACTIONS),
    }


# 兼容性别名（既有测试 / 调用方使用 check_verified_integrity）。
check_verified_integrity = manual_modified_thresholds


def production_readiness(
    interface: str = "wind_pressure",
    *,
    review_log_path: Path | str | None = None,
    approval_path: Path | str | None = None,
    verified_path: Path | str | None = None,
    ci_green: bool = False,
    rollback_ready: bool = False,
) -> dict[str, Any]:
    """复合生产就绪核验（Task5 报告数据源 + Task2 统一检查器）。

    汇总 Task1/2/3 + ``release_precheck``(G1-G6) + 绕过检测。仅读不写，所有外部
    条件默认不满足（ci / rollback 注入 False），``authorization_present`` 由真实
    授权库派生（存在匹配接口且已生效的授权记录 → 视为授权在场）。

    返回含 ``passed`` / ``failed`` / ``blocking_reasons`` 的结构化就绪报告：
    - ``passed`` / ``failed``：G1-G6 + ``verified_integrity`` 逐项通过/失败；
    - ``blocking_reasons``：门禁原因 + 绕过检测结果（若有）。
    """

    e_th = check_e_th_realization(
        interface, thresholds=None, verified_path=verified_path
    )
    chain = check_review_log_chain(review_log_path=review_log_path)
    approvals = load_approval_records(approval_path)
    # G6 派生：存在匹配接口且已生效的授权记录 → 视为授权在场。
    auth_present = False
    matched_approval = None
    for rec in approvals:
        if rec.interface == interface and is_approval_effective(rec):
            auth_present = True
            matched_approval = rec
            break
    allowed, reasons = release_precheck(
        interface=interface,
        ci_green=ci_green,
        rollback_ready=rollback_ready,
        authorization_present=auth_present,
        review_log_path=review_log_path,
        require_audit_chain=True,
    )
    integrity = check_verified_integrity(
        verified_path=verified_path, review_log_path=review_log_path
    )
    # 门禁逐项判定（True=通过）。
    gate_checks = {
        "G1_threshold_governance": not any(r.startswith("G1") for r in reasons),
        "G2_dual_sign": not any(r.startswith("G2") for r in reasons),
        "G3_ci": not any(r.startswith("G3") for r in reasons),
        "G4_audit_chain": not any(r.startswith("G4") for r in reasons),
        "G5_rollback": not any(r.startswith("G5") for r in reasons),
        "G6_authorization": not any(r.startswith("G6") for r in reasons),
    }
    checks: dict[str, bool] = dict(gate_checks)
    checks["verified_integrity"] = integrity["ok"]
    passed = [name for name, ok in checks.items() if ok]
    failed = [name for name, ok in checks.items() if not ok]
    blocking = list(reasons)
    if not integrity["ok"]:
        blocking.extend(f"VERIFIED_BYPASS:{tid}" for tid in integrity["bypassed_ids"])
    return {
        "interface": interface,
        "e_th_realization": e_th,
        "review_log_chain": chain,
        "approval_present": len(approvals) > 0,
        "approval_effective": auth_present,
        "matched_approval_id": (
            matched_approval.approval_id if matched_approval else None
        ),
        "verified_integrity": integrity,
        "gate": {"allowed": allowed, "reasons": reasons},
        "passed": passed,
        "failed": failed,
        "blocking_reasons": blocking,
    }


# 用户任务书命名别名（与 ``production_readiness`` 等价；输出含 passed/failed/blocking_reasons）。
production_readiness_checker = production_readiness


__all__ = [
    "check_e_th_realization",
    "check_review_log_chain",
    "validate_release_approval",
    "manual_modified_thresholds",
    "check_verified_integrity",
    "production_readiness",
    "production_readiness_checker",
]
