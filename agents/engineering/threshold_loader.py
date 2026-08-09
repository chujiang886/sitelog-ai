"""Engineering 阈值治理加载器（Phase 3.1 Sprint A 起，3.2.4-A 增强）。

机制对齐 Design 侧 threshold_loader（2.2.2）：
- 读取 Engineering 签字库 ``verified.json``（E-TH-01~06），并与 Design 侧
  D-TH-01/D-TH-02（型材壁厚/玻璃配置）合并为统一阈值表；
- ``is_fully_verified`` 维持**双签**语义：除 ``verified=true`` +
  ``verified_by`` + ``verified_at``（主理人核准）外，还需
  ``expert_verified_by`` + ``expert_verified_at``（行业专家签字）俱全，
  一票否决（向后兼容，零行为变化）；
- ``build_threshold_refs`` 输出接口 → 阈值 ID 引用表，供 ExpertBackedEngineeringValidation
  解析每个分析接口所需的签字阈值。

3.2.4-A 治理增强（落地 Sprint 3.2.4 治理设计）：
- 引入 ``agents.engineering.thresholds.schema`` 的 ``ThresholdStatus`` /
  ``ThresholdSourceRef`` / ``ThresholdGovernanceView``，支持
  ``threshold_status`` / ``version`` / 结构化 ``source_ref``；
- 新增 ``governance_status`` / ``load_governed_thresholds``：不满足治理条件
  （draft/review 态、deprecated 拒绝加载、verified 态缺结构化引用或双签）
  自动降级 ``pending_verification``；
- 既有 ``verified`` 布尔镜像与 ``mgmt_signed`` / ``expert_signed`` 判定
  **不变**，现有五模块/validation 调用方式零破坏。

红线（Sprint A / 3.2.4-A）：本模块**不写入**任何 ``verified=true``、不填任何
``value``、不出现真实 ``verified_by`` / ``verified_at`` / 专家签字；所有数值
保持 ``pending_verification``。真实转正只能在专家双签 + 主理人核准后发生。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.design.threshold_loader import load_verified_thresholds as _load_design_thresholds
from agents.engineering.thresholds.schema import (
    GOV_REASON_DEPRECATED,
    GOV_REASON_EXPERT_MISSING,
    GOV_REASON_MGMT_MISSING,
    GOV_REASON_NOT_VERIFIED,
    GOV_REASON_SOURCE_REF_INCOMPLETE,
    ThresholdGovernanceView,
    ThresholdStatus,
)


DEFAULT_VERIFIED_PATH: Path = Path(__file__).resolve().parent / "thresholds" / "verified.json"

# 分析接口 → 所需签字阈值 ID。
# wind_pressure 接口对齐 Engineering 侧阈值 E-TH-01~03；hardware/installation_risk 对齐 E-TH-04~06；上述阈值均 pending_verification
# profile/glass_safety 复用 Design 侧 D-TH-01/D-TH-02（设计 §五 约定不重复定义）。
INTERFACE_THRESHOLD_MAP: Mapping[str, Sequence[str]] = {
    "wind_pressure": ("E-TH-01", "E-TH-02", "E-TH-03"),
    "glass_safety": ("D-TH-02",),
    "profile": ("D-TH-01",),
    "hardware": ("E-TH-04",),
    "installation_risk": ("E-TH-05", "E-TH-06"),
}


def _load_raw(path: Path) -> dict[str, Any]:
    """读取单个 verified.json 的 thresholds 段；缺失/损坏 → 空 dict。"""

    if not path.is_file():
        return {}
    try:
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    thresholds: Any = raw.get("thresholds")
    if not isinstance(thresholds, dict):
        return {}
    return dict(thresholds)


def load_verified_thresholds(path: Path | None = None) -> dict[str, Any]:
    """读取 Engineering 签字库并与 Design 侧 D-TH 合并为统一阈值表。

    文件缺失 / 解析失败 → 返回空 dict（等价全 ``pending_verification``），
    合入即零行为变化（ADR-03 同构降级）。
    """

    target: Path = path if path is not None else DEFAULT_VERIFIED_PATH
    merged: dict[str, Any] = {}
    merged.update(_load_design_thresholds())  # D-TH-01~05（设计侧，未双签）
    merged.update(_load_raw(target))          # E-TH-01~06（工程侧）
    return merged


def mgmt_signed(entry: Mapping[str, Any] | None) -> bool:
    """主理人核准是否完整：verified=true 且 verified_by / verified_at 俱全。"""

    if not isinstance(entry, Mapping):
        return False
    if not entry.get("verified"):
        return False
    if not entry.get("verified_by"):
        return False
    if not entry.get("verified_at"):
        return False
    return True


def expert_signed(entry: Mapping[str, Any] | None) -> bool:
    """行业专家签字是否完整：expert_verified_by / expert_verified_at 俱全。"""

    if not isinstance(entry, Mapping):
        return False
    if not entry.get("expert_verified_by"):
        return False
    if not entry.get("expert_verified_at"):
        return False
    return True


def is_fully_verified(entry: Mapping[str, Any] | None) -> bool:
    """双签完整：主理人核准 + 行业专家签字 五字段俱全（一票否决）。"""

    return mgmt_signed(entry) and expert_signed(entry)


def get_interface_thresholds(interface: str) -> tuple[str, ...]:
    """返回某分析接口所需的签字阈值 ID 列表（缺省空元组）。"""

    ref: Sequence[str] | None = INTERFACE_THRESHOLD_MAP.get((interface or "").strip())
    return tuple(ref) if ref else ()


def build_threshold_refs() -> dict[str, list[str]]:
    """输出接口 → 阈值 ID 引用表（仅引用，数值仍 pending_verification）。"""

    return {iface: list(ids) for iface, ids in INTERFACE_THRESHOLD_MAP.items()}


# ---------------------------------------------------------------------------
# 3.2.4-A 治理增强层（落地 Sprint 3.2.4 治理设计，向后兼容既有 verified 语义）
# ---------------------------------------------------------------------------

def governance_status(entry: Mapping[str, Any] | None) -> tuple[bool, str]:
    """返回单条阈值条目的治理准入判定。

    参数：
    - ``entry``：单条阈值字典（来自 verified.json）。

    返回：``(ok, reason)``
    - ``ok=True``：满足治理完备条件（status=VERIFIED + 结构化引用完整 + 双签齐全）；
    - ``ok=False``：不满足，``reason`` 给出显式降级原因（供测试/日志追溯）。

    向后兼容：缺 ``threshold_status`` 字段 → 视作 DRAFT（最保守），不纳入工程判定；
    缺结构化 ``source_ref``（仅有自由文本 standard）→ verified 态下视为引用不完整。
    """

    view: ThresholdGovernanceView = ThresholdGovernanceView.from_entry(
        threshold_id="", entry=entry
    )
    if view.status is ThresholdStatus.DEPRECATED:
        return False, GOV_REASON_DEPRECATED
    if view.status is not ThresholdStatus.VERIFIED:
        return False, GOV_REASON_NOT_VERIFIED
    if not view.source_ref.is_complete():
        return False, GOV_REASON_SOURCE_REF_INCOMPLETE
    if not view.mgmt_signed():
        return False, GOV_REASON_MGMT_MISSING
    if not view.expert_signed():
        return False, GOV_REASON_EXPERT_MISSING
    return True, "governance_ok"


def load_governed_thresholds(path: Path | None = None) -> dict[str, Any]:
    """读取并施加治理筛选的统一阈值表。

    与 ``load_verified_thresholds`` 行为一致地合并 E-TH 与 D-TH，但额外：
    - 拒绝加载 ``threshold_status=deprecated`` 的条目（从结果中剔除）；
    - 其他不满足治理条件的条目**保留**在表中（供降级展示），仅由
      ``governance_status`` 显式给出 pending 原因——不破坏既有调用方对
      原始条目的访问。

    红线：本函数不做任何写入，不修改磁盘 verified.json，不填真实值。
    """

    merged: dict[str, Any] = load_verified_thresholds(path)
    governed: dict[str, Any] = {}
    for tid, entry in merged.items():
        if not isinstance(entry, Mapping):
            continue
        view = ThresholdGovernanceView.from_entry(threshold_id=tid, entry=entry)
        # deprecated 拒绝加载：不纳入任何工程判定（强治理拦截）。
        if view.status is ThresholdStatus.DEPRECATED:
            continue
        governed[tid] = dict(entry)
    return governed


__all__ = [
    "DEFAULT_VERIFIED_PATH",
    "INTERFACE_THRESHOLD_MAP",
    "load_verified_thresholds",
    "load_governed_thresholds",
    "mgmt_signed",
    "expert_signed",
    "is_fully_verified",
    "get_interface_thresholds",
    "build_threshold_refs",
    "governance_status",
]
