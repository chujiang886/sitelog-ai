"""阈值治理基础设施门禁测试（Phase 3.2 Sprint 3.2.4-A）。

覆盖：
1. draft 状态 → 治理不通过（pending_verification 原因：非 verified）；
2. review 状态 → 治理不通过（pending_verification 原因：非 verified）；
3. verified 缺 source_ref（结构化引用不完整）→ 治理不通过；
4. verified 缺专家签（expert_verified_by/at 缺）→ 治理不通过；
5. version 冲突（deprecated 拒绝加载）→ load_governed_thresholds 剔除；
6. deprecated 拒绝加载 → governance_status 显式拒绝；
7. D-TH 双签字段兼容 → schema 能解析 D-TH 既有条目并读取预留专家签位；
8. engineering_enabled=false 保持 → ExpertBackedEngineeringValidation 在 enabled=false 下永 pending（回归守门）。

红线：本测试**不写入**任何 verified=true、不填真实 value、不出现真实专家姓名、
不输出真实 approved；仅用内存夹具与纯标识符 signer（principal-001 / expert-001）。
全部保持 pending_verification。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.engineering.thresholds.schema import (
    GOV_REASON_DEPRECATED,
    GOV_REASON_EXPERT_MISSING,
    GOV_REASON_NOT_VERIFIED,
    GOV_REASON_SOURCE_REF_INCOMPLETE,
    ThresholdGovernanceView,
    ThresholdSourceRef,
    ThresholdStatus,
)
from agents.engineering.threshold_loader import (
    governance_status,
    load_governed_thresholds,
    load_verified_thresholds,
)


# ---------------------------------------------------------------------------
# 内存夹具：不触碰磁盘 verified.json，仅构造治理态条目
# ---------------------------------------------------------------------------

def _base_entry(threshold_id: str) -> dict[str, Any]:
    """缺省 draft 态占位条目（与真实 verified.json 同构：全 null/待签）。"""

    return {
        "param": f"{threshold_id} 占位参数",
        "value": None,
        "unit": "pending_verification",
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "expert_verified_by": None,
        "expert_verified_at": None,
        "source_ref": "待行业专家签字填入规范/标准号 pending_verification",
        "applies_to": ["wind_pressure"],
    }


def _verified_entry(
    threshold_id: str,
    *,
    with_expert: bool = True,
    with_source_ref: bool = True,
    source_ref: Any = None,
) -> dict[str, Any]:
    """构造一个 status=verified 的条目；可选择性缺专家签/缺结构化引用。"""

    entry: dict[str, Any] = {
        "param": f"{threshold_id} 参数",
        "value": None,
        "unit": "pending_verification",
        "threshold_status": ThresholdStatus.VERIFIED.value,
        "version": "1.0.0",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-30T00:00:00+00:00",
        "source_ref": (
            source_ref
            if source_ref is not None
            else {"standard": "GB 50009", "clause": "8.1.1", "edition": "2012"}
        ),
        "applies_to": ["wind_pressure"],
    }
    if with_expert:
        entry["expert_verified_by"] = "expert-001"
        entry["expert_verified_at"] = "2026-07-30T01:00:00+00:00"
    else:
        entry["expert_verified_by"] = None
        entry["expert_verified_at"] = None
    if not with_source_ref:
        # 退化：仅自由文本 standard（旧形态），缺 clause → 引用不完整。
        entry["source_ref"] = "GB 50009 待补条款 pending_verification"
    return entry


# ---------------------------------------------------------------------------
# 1. draft 状态 → 治理不通过
# ---------------------------------------------------------------------------

def test_draft_status_not_governed() -> None:
    """场景1：缺 threshold_status（默认 DRAFT）→ 治理不通过（非 verified）。"""

    entry = _base_entry("E-TH-01")
    ok, reason = governance_status(entry)
    assert ok is False
    assert reason == GOV_REASON_NOT_VERIFIED
    # 向后兼容：旧布尔判定仍可用，但治理层要求更严。
    view = ThresholdGovernanceView.from_entry("E-TH-01", entry)
    assert view.status is ThresholdStatus.DRAFT


# ---------------------------------------------------------------------------
# 2. review 状态 → 治理不通过
# ---------------------------------------------------------------------------

def test_review_status_not_governed() -> None:
    """场景2：threshold_status=review → 治理不通过（非 verified）。"""

    entry = _base_entry("E-TH-01")
    entry["threshold_status"] = ThresholdStatus.REVIEW.value
    ok, reason = governance_status(entry)
    assert ok is False
    assert reason == GOV_REASON_NOT_VERIFIED
    view = ThresholdGovernanceView.from_entry("E-TH-01", entry)
    assert view.status is ThresholdStatus.REVIEW


# ---------------------------------------------------------------------------
# 3. verified 缺 source_ref（结构化引用不完整）→ 治理不通过
# ---------------------------------------------------------------------------

def test_verified_missing_source_ref_fails() -> None:
    """场景3：verified 态但结构化引用不完整（缺 clause）→ 治理不通过。"""

    entry = _verified_entry("E-TH-01", with_expert=True, with_source_ref=False)
    ok, reason = governance_status(entry)
    assert ok is False
    assert reason == GOV_REASON_SOURCE_REF_INCOMPLETE
    view = ThresholdGovernanceView.from_entry("E-TH-01", entry)
    assert view.status is ThresholdStatus.VERIFIED
    assert view.source_ref.is_complete() is False


# ---------------------------------------------------------------------------
# 4. verified 缺专家签 → 治理不通过
# ---------------------------------------------------------------------------

def test_verified_missing_expert_sign_fails() -> None:
    """场景4：verified 态但缺行业专家签字 → 治理不通过。"""

    entry = _verified_entry("E-TH-01", with_expert=False, with_source_ref=True)
    ok, reason = governance_status(entry)
    assert ok is False
    assert reason == GOV_REASON_EXPERT_MISSING
    view = ThresholdGovernanceView.from_entry("E-TH-01", entry)
    assert view.expert_signed() is False
    # 主理人核准仍在（verified=true），但专家签缺失 → 双签不全。
    assert view.mgmt_signed() is True


# ---------------------------------------------------------------------------
# 5/6. version 冲突 / deprecated 拒绝加载
# ---------------------------------------------------------------------------

def test_deprecated_rejected_from_load() -> None:
    """场景5/6：threshold_status=deprecated → load_governed_thresholds 拒绝加载（剔除）。"""

    raw: dict[str, Any] = {
        "schema_version": 1,
        "thresholds": {
            "E-TH-01": _verified_entry("E-TH-01"),
            "E-TH-02": _base_entry("E-TH-02"),
        },
    }
    raw["thresholds"]["E-TH-02"]["threshold_status"] = ThresholdStatus.DEPRECATED.value
    raw["thresholds"]["E-TH-02"]["verified"] = True
    raw["thresholds"]["E-TH-02"]["verified_by"] = "principal-001"
    raw["thresholds"]["E-TH-02"]["verified_at"] = "2026-07-30T00:00:00+00:00"

    # governance_status 对 deprecated 显式拒绝。
    dep = raw["thresholds"]["E-TH-02"]
    ok, reason = governance_status(dep)
    assert ok is False
    assert reason == GOV_REASON_DEPRECATED

    # 通过真实文件加载路径验证拒绝加载（写入临时文件）。
    tmp = Path("tests/_tmp_dep_verified.json")
    try:
        tmp.write_text(__import__("json").dumps(raw), encoding="utf-8")
        governed = load_governed_thresholds(tmp)
        assert "E-TH-01" in governed
        assert "E-TH-02" not in governed  # deprecated 被剔除
    finally:
        if tmp.is_file():
            tmp.unlink()


# ---------------------------------------------------------------------------
# 7. D-TH 双签字段兼容（schema 能解析 D-TH 既有条目）
# ---------------------------------------------------------------------------

def test_d_th_double_sign_field_compatible() -> None:
    """场景7：D-TH 既有条目（仅主理人单签 + 自由文本 source_ref）被 schema 正确解析；

    预留的 expert_verified_by/at 字段缺省为 None（即"可补 schema 能力"），
    治理态下因 status 缺省为 DRAFT → 不通过，但字段兼容解析零报错。
    """

    # 直接读取真实 Design 侧 verified.json（D-TH-01~05）。
    from agents.design.threshold_loader import DEFAULT_VERIFIED_PATH as _D_PATH
    design_thresholds = load_verified_thresholds(_D_PATH)
    assert "D-TH-01" in design_thresholds

    d01 = design_thresholds["D-TH-01"]
    view = ThresholdGovernanceView.from_entry("D-TH-01", d01)
    # 真实 D-TH 现状：verified=false、无 expert 签位 → 治理不通过（DRAFT 态）。
    assert view.status is ThresholdStatus.DRAFT
    assert view.expert_verified_by is None
    assert view.expert_verified_at is None
    # 自由文本 source_ref 解析为 standard（旧形态兼容）。
    assert isinstance(view.source_ref, ThresholdSourceRef)
    assert view.source_ref.is_complete() is False

    # 模拟"补专家签位"能力：构造带 expert 签的 D-TH（仅内存，不落盘）。
    d01_with_expert = dict(d01)
    d01_with_expert["threshold_status"] = ThresholdStatus.VERIFIED.value
    d01_with_expert["verified"] = True
    d01_with_expert["verified_by"] = "principal-001"
    d01_with_expert["verified_at"] = "2026-07-30T00:00:00+00:00"
    d01_with_expert["expert_verified_by"] = None  # 仍缺专家签
    d01_with_expert["expert_verified_at"] = None
    d01_with_expert["source_ref"] = {"standard": "GB 5237", "clause": "4.2", "edition": "2017"}
    ok, reason = governance_status(d01_with_expert)
    assert ok is False
    assert reason == GOV_REASON_EXPERT_MISSING  # 缺专家签被 schema 捕获


# ---------------------------------------------------------------------------
# 8. engineering_enabled=false 保持（回归守门）
# ---------------------------------------------------------------------------

def test_engineering_enabled_false_keeps_pending() -> None:
    """场景8：即便阈值治理完备，engineering_enabled=false 也必须保持 pending。

    通过 ExpertBackedEngineeringValidation 注入已治理完备的阈值（内存），
    但 enabled=False → 四签闸门不通过 → verification_status=pending_verification。
    """

    from agents.engineering.validation import ExpertBackedEngineeringValidation

    # 构造一个治理完备的阈值表（仅内存，不落盘、不写 verified=true 到磁盘）。
    governed: dict[str, Any] = {
        "E-TH-01": _verified_entry("E-TH-01"),
        "E-TH-02": _verified_entry("E-TH-02"),
        "E-TH-03": _verified_entry("E-TH-03"),
    }
    # 确认治理完备。
    for tid, e in governed.items():
        ok, _ = governance_status(e)
        assert ok is True, f"{tid} 应治理完备"

    # enabled=False（真实 config 恒 false，本测试不开启）。
    assert load_engineering_enabled() is False
    validator = ExpertBackedEngineeringValidation(
        engineering_enabled=False, thresholds=governed
    )
    assert validator.engineering_enabled is False

    record = validator.validate(
        interface="wind_pressure",
        payload={
            "result": "",
            "confidence": 0.0,
            "evidence": "",
            "verification_status": "pending_verification",
        },
    )
    assert record["structure_valid"] is True
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is True
    # 红线闸门：enabled=False → 永不为 approved。
    assert record["verification_status"] == "pending_verification"
    assert record["sign_off_id"] is None


# ---------------------------------------------------------------------------
# 附加：governance_status 对真实工程侧 verified.json 全 pending 的回归
# ---------------------------------------------------------------------------

def test_real_engineering_verified_json_all_pending() -> None:
    """真实 E-TH-01~06（全 verified=false、value=null）治理态应为 DRAFT 且不通过。"""

    from agents.engineering.threshold_loader import DEFAULT_VERIFIED_PATH as _E_PATH
    real = load_verified_thresholds(_E_PATH)
    assert set(real.keys()) >= {"E-TH-01", "E-TH-06"}
    for tid, entry in real.items():
        ok, reason = governance_status(entry)
        assert ok is False
        assert reason == GOV_REASON_NOT_VERIFIED  # 缺 threshold_status → DRAFT
        assert entry["verified"] is False  # 未改真实值


# ---------------------------------------------------------------------------
# 附加：ThresholdSourceRef 结构化解析与完整性
# ---------------------------------------------------------------------------

def test_source_ref_structured_roundtrip() -> None:
    """结构化 source_ref 解析：字典 → 完整；字符串 → 仅 standard（不完整）。"""

    structured = ThresholdSourceRef.from_raw(
        {"standard": "GB 50009", "clause": "8.1.1", "edition": "2012"}
    )
    assert structured.is_complete() is True
    assert structured.as_dict()["clause"] == "8.1.1"

    free_text = ThresholdSourceRef.from_raw("GB 50009 待补条款 pending_verification")
    assert free_text.is_complete() is False
    assert free_text.standard.endswith("pending_verification")
