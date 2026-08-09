"""Engineering Enable Gate（Phase 3.2 Sprint 3.2.5-B）。

落地 Sprint 3.2.5-A 门禁设计文档的 ``can_enable_engineering`` 六项门禁：
- G1  threshold_governance：所有待启用阈值治理完备（``governance_status`` ok）；
- G2  dual_sign：所有待启用阈值双签齐全（``mgmt_signed`` AND ``expert_signed``）；
- G3  ci_status：CI 全绿（注入，默认红）；
- G4  audit_chain：审核链完整（review_log 链式无断裂/无损坏行）；
- G5  rollback_ready：回滚处理就绪（注入，默认不就绪）；
- G6  authorization：主理人单独书面授权到位（注入，默认缺失）。

语义边界（红线）：
- 本函数只判定"是否**允许**开启 ``engineering_enabled``"，**绝不**自行把
  ``engineering_enabled`` 翻成 True，也不输出任何 ``engineering_approved``；
- 所有外部条件默认值均取"不满足"，从而 ``can_enable_engineering()`` 默认返回
  ``(False, [全部门禁原因])``，确保灰度闸门默认拒绝、不可误开；
- 真实开启仍须主理人在 config 显式置 ``orchestrator.engineering_enabled=true``
  （且须经本门禁 G6 授权记录），违反红线将被 ``config_loader`` 拦截。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Mapping, Sequence

from agents.engineering.review_log import read_log
from agents.engineering.threshold_loader import (
    DEFAULT_VERIFIED_PATH,
    governance_status,
    is_fully_verified,
    load_verified_thresholds,
)


GATE_G1_GOVERNANCE = "G1_threshold_governance_incomplete"
GATE_G2_DUAL_SIGN = "G2_dual_sign_incomplete"
GATE_G3_CI = "G3_ci_not_green"
GATE_G4_AUDIT_CHAIN = "G4_audit_chain_incomplete"
GATE_G5_ROLLBACK = "G5_rollback_not_ready"
GATE_G6_AUTHORIZATION = "G6_authorization_missing"

# G4 真实审核链所要求的四类审计事件（3.2.5-G2 新增，空链/缺类均判 G4 失败）。
# 语义：阈值录入→主理人审核→专家复核→核验通过的完整闭环，缺一不可。
REQUIRED_REVIEW_ACTIONS: tuple[str, ...] = (
    "submit",
    "review",
    "expert_recheck",
    "verified",
)


def _chain_intact(events: Sequence[Mapping[str, object]]) -> bool:
    """审核链完整性：首条 ``prev_event_id`` 应为 None，其后每条约等于前一条 ``event_id``。"""

    prev: str | None = None
    for ev in events:
        if not isinstance(ev, Mapping):
            return False
        if ev.get("prev_event_id") != prev:
            return False
        cur = ev.get("event_id")
        if not cur:
            return False
        prev = str(cur)
    return True


def required_audit_events_present(
    events: Sequence[Mapping[str, object]],
) -> bool:
    """G4 增强（3.2.5-G2）：审核链须含全部四类必需审计事件。

    ``submit`` / ``review`` / ``expert_recheck`` /
    ``verified`` 四类 action 须全部出现，否则视为审核链不完整。
    """

    present = {
        ev.get("action")
        for ev in events
        if isinstance(ev, Mapping) and ev.get("action")
    }
    return all(action in present for action in REQUIRED_REVIEW_ACTIONS)


def required_audit_events(interface: str = "wind_pressure") -> list[str]:
    """返回指定接口通过 G4 所需的最小审核事件集合（3.2.5-G2 Task1）。

    当前所有接口一致要求四种审核事件（submit / review / expert_recheck / verified）；``interface`` 入参保留以便后续按接口
    定制（如风压类接口强制 ``expert_recheck``）。空 review_log / 缺任一
    事件 → G4 失败（见 ``required_audit_events_present`` / ``can_enable_engineering``）。
    """

    return list(REQUIRED_REVIEW_ACTIONS)


def can_enable_engineering(
    *,
    thresholds: Iterable[Mapping[str, object]] | None = None,
    ci_green: bool = False,
    rollback_ready: bool = False,
    authorization_present: bool = False,
    review_log_path: Path | str | None = None,
    require_audit_chain: bool = True,
) -> tuple[bool, list[str]]:
    """判定是否允许开启 ``engineering_enabled``。

    返回 ``(allowed, blocking_reasons)``。
    - ``thresholds`` 缺省 → 自动加载真实统一阈值表（``DEFAULT_VERIFIED_PATH``），
      因其当前全为 draft / 未双签，G1 / G2 默认失败；
    - 所有门禁默认不满足，因此默认返回 ``(False, reasons)``。

    红线：本函数不修改配置、不输出 approved、不翻转 engineering_enabled。
    """

    if thresholds is None:
        thresholds = load_verified_thresholds(DEFAULT_VERIFIED_PATH).values()

    reasons: list[str] = []

    # G1：阈值治理完备（status=verified + 结构化引用完整 + 双签齐全）。
    for entry in thresholds:
        ok, reason = governance_status(entry)
        if not ok:
            reasons.append(f"{GATE_G1_GOVERNANCE}:{reason}")
            break

    # G2：双签齐全（独立于 G1 给出精确原因；治理未过则天然双签也未齐）。
    for entry in thresholds:
        if not is_fully_verified(entry):
            reasons.append(GATE_G2_DUAL_SIGN)
            break

    # G3：CI 全绿（注入，默认红 → 阻塞）。
    if not ci_green:
        reasons.append(GATE_G3_CI)

    # G4：审核链完整（缺省要求）。
    # 3.2.5-G2 增强：空链不再真空通过，且须含全部四类必需审计事件，
    # 断裂/损坏的链仍视为不完整。
    if require_audit_chain:
        try:
            events = read_log(review_log_path)
            if not events:
                reasons.append(GATE_G4_AUDIT_CHAIN)
            elif not _chain_intact(events):
                reasons.append(GATE_G4_AUDIT_CHAIN)
            elif not required_audit_events_present(events):
                reasons.append(GATE_G4_AUDIT_CHAIN)
        except Exception:  # noqa: BLE001 - 任何读取异常都视为链路不可信
            reasons.append(GATE_G4_AUDIT_CHAIN)

    # G5：回滚就绪（注入，默认不就绪 → 阻塞）。
    if not rollback_ready:
        reasons.append(GATE_G5_ROLLBACK)

    # G6：主理人单独书面授权到位（注入，默认缺失 → 阻塞）。
    if not authorization_present:
        reasons.append(GATE_G6_AUTHORIZATION)

    return (len(reasons) == 0, reasons)


__all__ = [
    "GATE_G1_GOVERNANCE",
    "GATE_G2_DUAL_SIGN",
    "GATE_G3_CI",
    "GATE_G4_AUDIT_CHAIN",
    "GATE_G5_ROLLBACK",
    "GATE_G6_AUTHORIZATION",
    "REQUIRED_REVIEW_ACTIONS",
    "required_audit_events_present",
    "required_audit_events",
    "can_enable_engineering",
]
