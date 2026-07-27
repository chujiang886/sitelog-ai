"""Design 阈值治理加载器（2.2.2 / Step 2 机制）。

设计依据：`.ai/tasks/2.2.2_design_professionalization_design.md` §五。

职责：
- 从 ``verified.json`` 读取已签字阈值（缺省/文件缺失 → 返回空 dict，等价全 pending）。
- 提供「阈值 ID ↔ 设计候选字段」映射与「是否完整签字」判定。
- 计算候选字段级溯源 ``field_provenance``：
  * 真实 LLM 产出、未签字 → ``inferred``（Level 0，永远 pending）；
  * 对应阈值 ``verified=true`` 且 ``verified_by`` + ``verified_at`` 俱全 → ``verified``；
  * 未产出（占位/降级）→ ``unavailable``。

本模块**不写入**任何 ``verified=true``、不填任何 ``value``、不出现真实
``verified_by`` / ``verified_at``；所有数值保持 ``pending_verification``。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


# 默认签字库路径：agents/design/thresholds/verified.json
DEFAULT_VERIFIED_PATH: Path = (
    Path(__file__).resolve().parent / "thresholds" / "verified.json"
)

# 关键字段（决定顶层 pending_verification 的候选字段集，设计 §五 / Q5）。
KEY_FIELDS: tuple[str, ...] = (
    "frame_material",
    "glass_type",
    "dimensions_hint",
    "estimated_cost_tier",
)

# 阈值 ID → 候选字段（单一映射，驱动 provenance 与 threshold_refs）。
THRESHOLD_FIELD_MAP: Mapping[str, str] = {
    "D-TH-01": "frame_material",
    "D-TH-02": "glass_type",
    "D-TH-03": "dimensions_hint",
    "D-TH-04": "estimated_cost_tier",
    "D-TH-05": "scheme_scoring",
}

# 反查：字段 → 阈值 ID（供输出 threshold_refs 槽位，仅引用、不取值）。
FIELD_THRESHOLD_REF: Mapping[str, str] = {
    field: thr_id for thr_id, field in THRESHOLD_FIELD_MAP.items()
}


def load_verified_thresholds(path: Path | None = None) -> dict[str, Any]:
    """读取已签字阈值库；缺省指向 ``DEFAULT_VERIFIED_PATH``。

    文件不存在 / 解析失败 → 返回空 dict（等价全 ``pending_verification``），
    合入即零行为变化（ADR-03 同构降级）。
    """

    target: Path = path if path is not None else DEFAULT_VERIFIED_PATH
    if not target.is_file():
        return {}
    try:
        raw: dict[str, Any] = json.loads(target.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    thresholds: Any = raw.get("thresholds")
    if not isinstance(thresholds, dict):
        return {}
    return dict(thresholds)


def is_fully_verified(entry: Mapping[str, Any] | None) -> bool:
    """阈值是否完整签字：``verified=true`` 且 ``verified_by`` / ``verified_at`` 俱全。

    任一缺失即视为未签字 → 该字段维持 ``pending_verification``（一票否决语义）。
    """

    if not isinstance(entry, Mapping):
        return False
    if not entry.get("verified"):
        return False
    if not entry.get("verified_by"):
        return False
    if not entry.get("verified_at"):
        return False
    return True


def resolve_field_provenance(
    verified: Mapping[str, Any],
    *,
    produced: bool,
) -> dict[str, str]:
    """计算候选字段级溯源（设计 §五 对齐 ADR-2.2.1 §7）。

    - ``produced=False``（占位/降级/全缺）→ 关键字段 ``unavailable``；
    - ``produced=True``：对应阈值完整签字 → ``verified``，否则 ``inferred``。
    """

    provenance: dict[str, str] = {}
    for field in KEY_FIELDS:
        if not produced:
            provenance[field] = "unavailable"
            continue
        # 找到该字段对应的阈值 ID（仅 KEY_FIELDS 内的四类有映射）。
        thr_id: str | None = FIELD_THRESHOLD_REF.get(field)
        entry: Mapping[str, Any] | None = (
            verified.get(thr_id) if thr_id is not None else None
        )
        provenance[field] = "verified" if is_fully_verified(entry) else "inferred"
    # scheme_scoring 单独处理（非候选字段，仅用于 decision_trace 参考）。
    scoring_entry: Mapping[str, Any] | None = verified.get("D-TH-05")
    provenance["scheme_scoring"] = (
        "verified" if is_fully_verified(scoring_entry) else "inferred"
    )
    return provenance


def build_threshold_refs() -> dict[str, str]:
    """输出候选字段 → 阈值 ID 的引用槽位（仅引用，数值仍 pending）。"""

    refs: dict[str, str] = {}
    for field in KEY_FIELDS:
        ref: str | None = FIELD_THRESHOLD_REF.get(field)
        if ref is not None:
            refs[field] = ref
    refs["scheme_scoring"] = "D-TH-05"
    return refs


__all__ = [
    "DEFAULT_VERIFIED_PATH",
    "KEY_FIELDS",
    "THRESHOLD_FIELD_MAP",
    "FIELD_THRESHOLD_REF",
    "load_verified_thresholds",
    "is_fully_verified",
    "resolve_field_provenance",
    "build_threshold_refs",
]
