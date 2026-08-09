"""EngineeringCalculationResult 基类抽象测试（Phase 3.2 Sprint 3.2.1）。

覆盖：
1. 基类字段默认值（九字段）；
2. as_interface() 恰好四字段；
3. as_full() 结构（八扩展字段 + interface 标识）；
4. enforce_redline() 红线闸门；
5. 五模块兼容（继承关系 + interface 标识 + calculate() 返回类型）。

零真实数值；engineering_enabled 保持 false；全 pending_verification。

阶段：Phase 3.2 Sprint 3.2.1（结果抽象）。
红线守约：不产真实数值、不写条款号、不开启 engineering_enabled，所有参数 pending_verification。
"""

from __future__ import annotations

from typing import Any

import pytest

from agents.engineering.calc.base import EngineeringCalculationResult
from agents.engineering.calc.glass_safety import (
    GLASS_SAFETY_INTERFACE,
    GlassSafetyCalculator,
    GlassSafetyResult,
)
from agents.engineering.calc.hardware import (
    HARDWARE_INTERFACE,
    HardwareCalculator,
    HardwareResult,
)
from agents.engineering.calc.installation_risk import (
    INSTALLATION_RISK_INTERFACE,
    InstallationRiskCalculator,
    InstallationRiskResult,
)
from agents.engineering.calc.profile import (
    PROFILE_INTERFACE,
    ProfileCalculator,
    ProfileResult,
)
from agents.engineering.calc.wind_pressure import (
    WIND_PRESSURE_INTERFACE,
    WindPressureCalculator,
    WindPressureResult,
)
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PendingEngineeringValidation,
    PENDING_VERIFICATION,
)


def test_glass_upstream_wk_non_mapping_guard() -> None:
    """glass_safety 上游 w_k 非 Mapping → 闸门 False，provenance 标记 upstream_pending。

    覆盖 glass_safety.py 第 127 行非 Mapping 守卫分支（红线闸门，无真实数值）。
    """

    bad_wind: dict[str, Any] = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"w_k": "not-a-mapping"},
    }
    res: GlassSafetyResult = GlassSafetyCalculator().calculate(
        {"wind_pressure_result": bad_wind}
    )
    assert res.provenance.get("wind_pressure.w_k") == "upstream_pending"


def test_pending_validation_rejects_empty_interface() -> None:
    """PendingEngineeringValidation 对空 interface 抛 ValueError（结构校验）。"""

    validator = PendingEngineeringValidation()
    try:
        validator.validate(interface="  ", payload={})
        raise AssertionError("expected ValueError for empty interface")
    except ValueError:
        pass

# 白盒边界用例：仅验证 profile 计算器的跨模块闸门分支被覆盖，不产出真实数值、
# 不改变 verification_status（仍 pending，红线由 validator 叠加），不触碰
# verified.json / engineering_enabled。
def test_profile_upstream_approved_branch_exercises_gate() -> None:
    """上游 engineering_approved 且 w_k.value 非 None → provenance 标记 verified。

    覆盖 profile.py 的 _is_wind_pressure_approved 分支与 calculate() 的
    upstream_approved 体（267-268 行）。结果仍 pending（真实审核由 validator
    双签链在 enabled=true 阶段产出），仅验证 provenance 闸门逻辑被正确执行。
    """

    approved_wind: dict[str, Any] = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"w_k": {"value": 123, "verified": False}},
    }
    res: ProfileResult = ProfileCalculator().calculate(
        {"wind_pressure_result": approved_wind}
    )
    # 闸门逻辑生效：上游可信 → provenance 标记 verified（仍不填真实型材数值）。
    assert res.provenance.get("wind_pressure.w_k") == "verified"
    # 红线：status 仍 pending（enabled=false 下 calculator 不产出 approved）。
    assert res.verification_status == PENDING_VERIFICATION
    assert res.result == ""


def test_profile_upstream_wk_non_mapping_guard() -> None:
    """上游 w_k 非 Mapping → 闸门返回 False，provenance 标记 upstream_pending。

    覆盖 profile.py 第 128 行非 Mapping 守卫分支。
    """

    bad_wind: dict[str, Any] = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"w_k": "not-a-mapping"},
    }
    res: ProfileResult = ProfileCalculator().calculate(
        {"wind_pressure_result": bad_wind}
    )
    assert res.provenance.get("wind_pressure.w_k") == "upstream_pending"


# --------------------------------------------------------------------------- #
# 1. 基类字段默认值                                                            #
# --------------------------------------------------------------------------- #
def test_base_fields_defaults() -> None:
    """基类九字段默认值正确（含红线默认值）。"""

    b = EngineeringCalculationResult()

    assert b.result == ""
    assert b.confidence == PENDING_VERIFICATION
    assert b.evidence == ""
    assert b.verification_status == PENDING_VERIFICATION
    assert b.intermediate == {}
    assert b.provenance == {}
    assert b.threshold_refs == []
    assert b.gaps == []
    assert b.sign_off_id is None
    assert b.INTERFACE == ""  # 基类默认空（子类覆盖）


# --------------------------------------------------------------------------- #
# 2. as_interface 恰好四字段                                                   #
# --------------------------------------------------------------------------- #
def test_base_as_interface_four_keys() -> None:
    """as_interface() 返回精确四键，无多余键。"""

    b = EngineeringCalculationResult(
        result="x",
        confidence="c",
        evidence="e",
        verification_status=PENDING_VERIFICATION,
    )
    iface: dict[str, Any] = b.as_interface()
    assert set(iface.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    assert iface["result"] == "x"
    assert iface["verification_status"] == PENDING_VERIFICATION


# --------------------------------------------------------------------------- #
# 3. as_full 结构                                                             #
# --------------------------------------------------------------------------- #
def test_base_as_full_structure() -> None:
    """as_full() 含八扩展字段 + interface 标识（基类默认空串）。"""

    b = EngineeringCalculationResult()
    full: dict[str, Any] = b.as_full()
    assert set(full.keys()) == {
        "interface",
        "result",
        "confidence",
        "evidence",
        "verification_status",
        "intermediate",
        "provenance",
        "threshold_refs",
        "gaps",
        "sign_off_id",
    }
    assert full["interface"] == ""
    assert full["sign_off_id"] is None
    assert full["intermediate"] == {}
    assert full["threshold_refs"] == []


# --------------------------------------------------------------------------- #
# 4. enforce_redline 红线闸门                                                 #
# --------------------------------------------------------------------------- #
def test_enforce_redline_pending_empty_ok() -> None:
    """pending 态 result 为空 → 通过。"""

    b = EngineeringCalculationResult()
    # 不应抛异常
    b.enforce_redline()


def test_enforce_redline_pending_nonempty_raises() -> None:
    """pending 态 result 非空 → 抛 AssertionError（红线违规）。"""

    bad = EngineeringCalculationResult(result="伪造真实数值")
    with pytest.raises(AssertionError):
        bad.enforce_redline()


def test_enforce_redline_approved_status_ok() -> None:
    """非 pending 的合法 status（如 approved）不触发 result 空校验。"""

    approved = EngineeringCalculationResult(
        result="已审核结论", verification_status="approved"
    )
    # 不应抛异常（approved 态允许非空 result）
    approved.enforce_redline()


def test_enforce_redline_invalid_status_raises() -> None:
    """未知 verification_status → 抛 AssertionError。"""

    weird = EngineeringCalculationResult(verification_status="mystery")
    with pytest.raises(AssertionError):
        weird.enforce_redline()


# --------------------------------------------------------------------------- #
# 5. 五模块兼容                                                              #
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "result_cls, expected_interface",
    [
        (WindPressureResult, WIND_PRESSURE_INTERFACE),
        (GlassSafetyResult, GLASS_SAFETY_INTERFACE),
        (ProfileResult, PROFILE_INTERFACE),
        (HardwareResult, HARDWARE_INTERFACE),
        (InstallationRiskResult, INSTALLATION_RISK_INTERFACE),
    ],
)
def test_module_result_is_subclass_and_interface(
    result_cls: type, expected_interface: str
) -> None:
    """五 Result 继承基类，且 as_full()['interface'] 等于各自接口常量。"""

    r = result_cls()
    assert isinstance(r, EngineeringCalculationResult)
    assert r.INTERFACE == expected_interface
    assert r.as_interface() == {
        "result": "",
        "confidence": PENDING_VERIFICATION,
        "evidence": "",
        "verification_status": PENDING_VERIFICATION,
    }
    assert r.as_full()["interface"] == expected_interface
    # 构造传 9 关键字参数（与旧子类一致）仍可用
    r2 = result_cls(
        result="",
        confidence=PENDING_VERIFICATION,
        evidence="e",
        verification_status=PENDING_VERIFICATION,
        intermediate={"k": 1},
        provenance={"p": "inferred"},
        threshold_refs=["E-TH-01"],
        gaps=["g: pending_verification"],
        sign_off_id=None,
    )
    assert r2.intermediate == {"k": 1}
    assert r2.as_full()["threshold_refs"] == ["E-TH-01"]


@pytest.mark.parametrize(
    "calculator_cls, result_cls, expected_interface",
    [
        (WindPressureCalculator, WindPressureResult, WIND_PRESSURE_INTERFACE),
        (GlassSafetyCalculator, GlassSafetyResult, GLASS_SAFETY_INTERFACE),
        (ProfileCalculator, ProfileResult, PROFILE_INTERFACE),
        (HardwareCalculator, HardwareResult, HARDWARE_INTERFACE),
        (InstallationRiskCalculator, InstallationRiskResult, INSTALLATION_RISK_INTERFACE),
    ],
)
def test_module_calculator_returns_typed_result(
    calculator_cls: type, result_cls: type, expected_interface: str
) -> None:
    """计算器 calculate() 返回正确的子类实例，且接口标识保留。"""

    res = calculator_cls().calculate({})
    assert isinstance(res, result_cls)
    assert isinstance(res, EngineeringCalculationResult)
    assert res.as_full()["interface"] == expected_interface
    assert res.verification_status == PENDING_VERIFICATION
