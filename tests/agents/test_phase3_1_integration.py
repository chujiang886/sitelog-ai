"""Phase 3.1 Final Integration 集成测试（Task 2 + Task 3 + Task 4）。

流程：Environment → Design → Wind Pressure → Glass Safety → Profile →
Hardware → Installation Risk。

覆盖：
- 跨模块调用链（计算器级 as_full 线程，验证 pending 状态正确传导）；
- 数据契约一致（Agent 级 invoke 五接口统一四字段）；
- Engineering Agent 总验证（五接口 + validator 流程）；
- PDF 链路（ReportGenerator 徽标逻辑对工程 pending 不误显）。

红线：engineering_enabled=false；零真实参数；verification_status 恒
pending_verification；仅新增测试、不修改任何被测试源码；防编造扫描 0 命中。
"""

from __future__ import annotations

import asyncio
from typing import Any

from agents.base import AgentContext
from agents.engineering.agent import EngineeringAgent
from agents.engineering.calc.glass_safety import GlassSafetyCalculator
from agents.engineering.calc.hardware import HardwareCalculator
from agents.engineering.calc.installation_risk import InstallationRiskCalculator
from agents.engineering.calc.profile import ProfileCalculator
from agents.engineering.calc.wind_pressure import WindPressureCalculator
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
    ExpertBackedEngineeringValidation,
    PendingEngineeringValidation,
)
from agents.report.generator import (
    BADGE_PENDING,
    BADGE_VERIFIED,
    _badge_for,
)


def _ctx() -> dict[str, Any]:
    """构造带 provenance 的完整上下文（所有字段 inferred，无真实数值）。"""

    return {
        "project": {
            "building_height": 30,
            "glass_area": 2.5,
            "support_condition": "four_side",
            "member_span": 1.2,
            "load_condition": "normal",
            "usage_scenario": "residential",
            "installation_scenario": "external_wall",
            "floor_height": 10,
            "lift_risk": "medium",
            "construction_env": "urban",
            "weather_impact": "low",
            "install_process": "standard",
        },
        "design_candidate": {
            "frame_series": "series_60",
            "frame_material": "aluminium",
            "glass_type": "double_glazed",
            "dimensions_hint": "1200x1500",
            "glass_config": "DGU",
            "opening_form_hint": "casement",
            "opening_type": "casement",
            "hardware_config": "standard",
            "field_provenance": {
                "glass_type": "inferred",
                "frame_material": "inferred",
                "frame_series": "inferred",
                "dimensions_hint": "inferred",
                "glass_config": "inferred",
                "opening_form_hint": "inferred",
                "opening_type": "inferred",
                "hardware_config": "inferred",
            },
        },
        "environment_result": {
            "field_provenance": {
                "climate_zone": "inferred",
                "prevailing_wind": "inferred",
                "solar_exposure": "inferred",
            }
        },
    }


# --------------------------------------------------------------------------- #
# Task 2: 跨模块调用链（计算器级 as_full 线程，验证 pending 传导）            #
# --------------------------------------------------------------------------- #


def test_cross_module_pipeline_all_pending_with_upstream_gaps() -> None:
    """全链路（首态，无上游 approved）：每模块 pending + 正确登记 upstream_pending。"""

    ctx = _ctx()

    wp = WindPressureCalculator().calculate(ctx)
    assert wp.verification_status == PENDING_VERIFICATION

    gs = GlassSafetyCalculator().calculate(
        {**ctx, "wind_pressure_result": wp.as_full()}
    )
    assert gs.verification_status == PENDING_VERIFICATION
    assert "w_k: upstream_pending" in gs.gaps

    pf = ProfileCalculator().calculate(
        {**ctx, "wind_pressure_result": wp.as_full()}
    )
    assert pf.verification_status == PENDING_VERIFICATION
    assert "w_k: upstream_pending" in pf.gaps

    hw = HardwareCalculator().calculate({**ctx, "profile_result": pf.as_full()})
    assert hw.verification_status == PENDING_VERIFICATION
    assert "profile_result: upstream_pending" in hw.gaps

    ir = InstallationRiskCalculator().calculate(
        {
            **ctx,
            "glass_safety_result": gs.as_full(),
            "profile_result": pf.as_full(),
            "hardware_result": hw.as_full(),
        }
    )
    # 末端聚合：三上游皆未 approved → installation_risk 仍 pending + 三 gap。
    assert ir.verification_status == PENDING_VERIFICATION
    assert "glass_safety_result: upstream_pending" in ir.gaps
    assert "profile_result: upstream_pending" in ir.gaps
    assert "hardware_result: upstream_pending" in ir.gaps


def test_upstream_fake_approved_consumes_signal_but_stays_pending() -> None:
    """上游伪造 approved（仅验证闸门消费信号，不写真实数值）：

    - 下游 provenance 翻为 verified、gap 移除 w_k: upstream_pending；
    - 但下游自身阈值未双签 + enabled=false → 仍 pending_verification（不误判 approved）。
    """

    ctx = _ctx()
    # 占位非真实数值：value=123 仅作「非 None」信号，单位 Pa，无工程含义。
    fake_wp_full = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"w_k": {"value": 123, "unit": "Pa"}},
    }

    gs = GlassSafetyCalculator().calculate(
        {**ctx, "wind_pressure_result": fake_wp_full}
    )
    # 信号被消费：上游不可信标记消失，provenance 标记为 verified。
    assert gs.provenance.get("wind_pressure.w_k") == "verified"
    assert "w_k: upstream_pending" not in gs.gaps
    # 但玻璃自身仍 pending（红线：enabled=false + 阈值未双签）。
    assert gs.verification_status == PENDING_VERIFICATION


def test_agent_invoke_installation_risk_pending_when_no_upstream_approved() -> None:
    """Task 2-3：Agent 级 invoke（默认空上游）下，installation_risk 仍 pending。"""

    agent = EngineeringAgent()
    context = AgentContext(request_id="integ-ir", input_data=_ctx())
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    ir_out = result.data["analyses"]["installation_risk"]
    assert ir_out["verification_status"] == PENDING_VERIFICATION
    assert ir_out["result"] == ""


# --------------------------------------------------------------------------- #
# Task 3: Engineering Agent 总验证（五接口统一四字段 + validator 流程）          #
# --------------------------------------------------------------------------- #


def test_agent_invoke_five_interfaces_uniform_four_field_contract() -> None:
    """五接口统一四字段契约：result/confidence/evidence/verification_status。"""

    agent = EngineeringAgent()
    context = AgentContext(request_id="integ-contract", input_data=_ctx())
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    data = result.data
    expected = {
        "wind_pressure",
        "glass_safety",
        "profile",
        "hardware",
        "installation_risk",
    }
    assert set(data["analyses"].keys()) == expected
    for name, out in data["analyses"].items():
        assert set(out.keys()) == {
            "result",
            "confidence",
            "evidence",
            "verification_status",
        }
        assert out["verification_status"] == PENDING_VERIFICATION
        assert out["result"] == ""
    # review_chain 与接口一一对应，且结构合法、状态 pending。
    assert len(data["review_chain"]) == 5
    for rec in data["review_chain"]:
        assert rec["structure_valid"] is True
        assert rec["verification_status"] == PENDING_VERIFICATION
    assert data["pending_verification"] is True


def test_validator_flow_pending_and_expert_backed_still_pending() -> None:
    """validator 流程：默认 + 专家双签（enabled=false）均不输出 engineering_approved。"""

    payload = {
        "result": "",
        "confidence": PENDING_VERIFICATION,
        "evidence": "",
        "verification_status": PENDING_VERIFICATION,
    }
    # 默认 validator：结构合法 → pending。
    rec_pending = PendingEngineeringValidation().validate(
        interface="wind_pressure", payload=payload
    )
    assert rec_pending["structure_valid"] is True
    assert rec_pending["verification_status"] == PENDING_VERIFICATION

    # 专家双签 validator：即便结构合法，engineering_enabled=false → 仍 pending。
    rec_expert = ExpertBackedEngineeringValidation(engineering_enabled=False).validate(
        interface="wind_pressure", payload=payload
    )
    assert rec_expert["structure_valid"] is True
    assert rec_expert["verification_status"] == PENDING_VERIFICATION
    assert rec_expert.get("sign_off_id") is None


# --------------------------------------------------------------------------- #
# Task 4: PDF 链路（ReportGenerator 消费工程 pending 不误显）                  #
# --------------------------------------------------------------------------- #


def test_report_generator_handles_engineering_pending_as_unverified() -> None:
    """ReportGenerator 徽标逻辑对工程 pending 一律 [待确认]，不误显 [已验证]。"""

    agent = EngineeringAgent()
    context = AgentContext(request_id="integ-pdf", input_data=_ctx())
    data = asyncio.run(agent.invoke(context)).data

    # 1) 顶层 pending_verification 保证章节徽标为 [待确认]。
    section_pending = bool(data.get("pending_verification", True))
    assert section_pending is True

    # 2) 每个接口的 verification_status 经 ReportGenerator._badge_for 必为 [待确认]。
    for name, out in data["analyses"].items():
        badge_text, _style = _badge_for(out.get("verification_status"))
        assert badge_text == BADGE_PENDING
        assert badge_text != BADGE_VERIFIED
        # 软断言：eng 结果形态可被 ReportGenerator 的安全取值 helper 消费。
        assert isinstance(out, dict)

    # 3) 即便直接喂 pending_verification 字符串，亦不等于 [已验证]。
    assert _badge_for(PENDING_VERIFICATION)[0] == BADGE_PENDING
    assert _badge_for(PENDING_VERIFICATION)[0] != BADGE_VERIFIED
