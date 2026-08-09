"""Installation Risk 计算单元测试（Sprint K 任务5）。

覆盖：E-TH-05/E-TH-06 缺失 / glass pending 传导 / profile pending 传导 /
hardware pending 传导 / inferred 输入 / 输出结构 / threshold_refs /
evidence / 防编造扫描 / engineering_enabled=false。
零真实数值；engineering_enabled 保持 false。

阶段：Phase 3.1 Sprint K。
红线守约：不产真实风险分数/承载参数/施工安全距离/施工等级、不填条款号、
不开启 engineering_enabled，所有参数 pending_verification。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from agents.base import AgentContext
from agents.engineering.agent import EngineeringAgent
from agents.engineering.calc.installation_risk import (
    InstallationRiskCalculator,
    InstallationRiskResult,
)
from agents.engineering.rules import installation_rules
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
    ExpertBackedEngineeringValidation,
)
from scripts.lint.check_fabrication import scan_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# 安装风险接口所需阈值 ID（与 INTERFACE_THRESHOLD_MAP 对齐；数值 pending_verification）。
INSTALLATION_THRESHOLD_IDS = ("E-TH-05", "E-TH-06")


# --------------------------------------------------------------------------- #
# 1. E-TH-05/E-TH-06 缺失 → pending                                            #
# --------------------------------------------------------------------------- #


def test_e_th_missing_yields_pending() -> None:
    """阈值库为空（E-TH-05/E-TH-06 缺失）→ verification_status 恒 pending，gaps 登记。"""

    calculator = InstallationRiskCalculator(thresholds={})
    result = calculator.calculate({})
    assert result.verification_status == PENDING_VERIFICATION
    assert result.result == ""  # 红线：不产出真实风险结论
    for tid in INSTALLATION_THRESHOLD_IDS:
        assert f"{tid}: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 2. glass pending 传导（跨模块降级）                                         #
# --------------------------------------------------------------------------- #


def test_glass_pending_propagation() -> None:
    """上游 glass_safety 未 approved → installation_risk 强制 pending + glass_safety_result: upstream_pending。"""

    glass_pending = {"verification_status": PENDING_VERIFICATION}
    context: dict[str, Any] = {"glass_safety_result": glass_pending}
    result = InstallationRiskCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    assert "glass_safety_result: upstream_pending" in result.gaps
    assert result.result == ""
    assert result.provenance["glass_safety_result"] == "upstream_pending"


# --------------------------------------------------------------------------- #
# 3. profile pending 传导（跨模块降级）                                       #
# --------------------------------------------------------------------------- #


def test_profile_pending_propagation() -> None:
    """上游 profile 未 approved → installation_risk 强制 pending + profile_result: upstream_pending。"""

    profile_pending = {"verification_status": PENDING_VERIFICATION}
    context: dict[str, Any] = {"profile_result": profile_pending}
    result = InstallationRiskCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    assert "profile_result: upstream_pending" in result.gaps
    assert result.result == ""
    assert result.provenance["profile_result"] == "upstream_pending"


# --------------------------------------------------------------------------- #
# 4. hardware pending 传导（跨模块降级）                                      #
# --------------------------------------------------------------------------- #


def test_hardware_pending_propagation() -> None:
    """上游 hardware 未 approved → installation_risk 强制 pending + hardware_result: upstream_pending。"""

    hardware_pending = {"verification_status": PENDING_VERIFICATION}
    context: dict[str, Any] = {"hardware_result": hardware_pending}
    result = InstallationRiskCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    assert "hardware_result: upstream_pending" in result.gaps
    assert result.result == ""
    assert result.provenance["hardware_result"] == "upstream_pending"


def test_all_upstreams_approved_but_thresholds_pending() -> None:
    """三上游均 approved 时仅标记可信态；E-TH-05/06 未双签结论仍 pending（不重算、不填数值）。"""

    approved = {"verification_status": ENGINEERING_APPROVED, "intermediate": {}}
    context: dict[str, Any] = {
        "glass_safety_result": approved,
        "profile_result": approved,
        "hardware_result": approved,
    }
    result = InstallationRiskCalculator().calculate(context)
    # E-TH-05/06 自身未双签，结论仍 pending（仅登记上游可信态标记）。
    assert result.verification_status == PENDING_VERIFICATION
    assert result.provenance["glass_safety_result"] == "verified"
    assert result.provenance["profile_result"] == "verified"
    assert result.provenance["hardware_result"] == "verified"
    # 红线：即便三上游可信，也不得在本模块自行计算/填入玻璃重量/型材/五金数值。
    assert result.intermediate["G_weight"]["value"] is None
    assert result.intermediate["profile_cond"]["value"] is None
    assert result.intermediate["hardware_cond"]["value"] is None
    assert result.intermediate["Risk_total"]["value"] is None
    assert result.intermediate["D_safe"]["value"] is None
    assert result.result == ""


# --------------------------------------------------------------------------- #
# 5. 输入 inferred → pending（不伪造风险数值）                               #
# --------------------------------------------------------------------------- #


def test_inferred_input_stays_pending() -> None:
    """项目/设计输入全为 inferred → 结论 pending，且不伪造风险分数/安全距离/承载数值。"""

    context: dict[str, Any] = {
        "project": {
            "installation_scenario": "high_rise",
            "floor_height": "high",
            "lift_risk": "medium",
            "construction_env": "confined",
            "weather_impact": "windy",
            "install_process": "dry",
        },
        "design_candidate": {
            "glass_config": "glass_a",
            "opening_form_hint": "casement",
            "field_provenance": {
                "glass_config": "inferred",
                "opening_form_hint": "inferred",
            },
        },
    }
    result = InstallationRiskCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    # 关键：inferred 输入不得驱动任何真实风险分数/承载/距离数值。
    assert result.result == ""
    assert result.intermediate["Risk_total"]["value"] is None
    assert result.intermediate["D_safe"]["value"] is None
    assert result.intermediate["lift_condition"]["value"] is None
    assert result.intermediate["personnel_risk"]["value"] is None
    assert result.intermediate["env_risk"]["value"] is None
    assert result.intermediate["process_risk"]["value"] is None
    # 溯源标签应为 inferred（非 verified/measured）。
    assert result.provenance["design.glass_config"] == "inferred"
    assert "design.glass_config: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 6. 输出结构（四字段 + 扩展字段）                                           #
# --------------------------------------------------------------------------- #


def test_output_structure_four_fields() -> None:
    """as_interface 恰好四字段；as_full 含八扩展字段 + interface 标识。"""

    result = InstallationRiskCalculator().calculate({})
    iface = result.as_interface()
    assert set(iface.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    full = result.as_full()
    for key in (
        "result",
        "confidence",
        "evidence",
        "verification_status",
        "intermediate",
        "provenance",
        "threshold_refs",
        "gaps",
        "sign_off_id",
    ):
        assert key in full
    assert full["interface"] == "installation_risk"
    assert full["sign_off_id"] is None


def test_installation_risk_result_serializers() -> None:
    """InstallationRiskResult 直接构造后 as_interface / as_full 序列化正确。"""

    res = InstallationRiskResult(
        result="",
        confidence=PENDING_VERIFICATION,
        evidence="e",
        verification_status=PENDING_VERIFICATION,
        intermediate={"Risk_total": {"value": None}},
        provenance={"glass_safety_result": "upstream_pending"},
        threshold_refs=list(INSTALLATION_THRESHOLD_IDS),
        gaps=[
            "E-TH-05: pending_verification",
            "E-TH-06: pending_verification",
            "glass_safety_result: upstream_pending",
        ],
        sign_off_id=None,
    )
    iface = res.as_interface()
    assert set(iface.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    assert res.as_full()["sign_off_id"] is None
    assert res.as_full()["threshold_refs"] == list(INSTALLATION_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 7. threshold_refs                                                          #
# --------------------------------------------------------------------------- #


def test_threshold_refs_align_with_interface_map() -> None:
    """calculator.threshold_refs 与 get_interface_thresholds 一致。"""

    from agents.engineering.threshold_loader import get_interface_thresholds

    result = InstallationRiskCalculator().calculate({})
    assert result.threshold_refs == list(
        get_interface_thresholds("installation_risk")
    )
    assert result.threshold_refs == list(INSTALLATION_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 8. evidence 内容                                                           #
# --------------------------------------------------------------------------- #


def test_evidence_carries_formula_and_pending() -> None:
    """evidence 须含公式来源、阈值引用与 pending_verification 标注，无真实数值。"""

    result = InstallationRiskCalculator().calculate({})
    evidence = result.evidence
    for formula in installation_rules.INSTALLATION_FORMULAS:
        assert formula in evidence
    assert "pending_verification" in evidence
    for tid in INSTALLATION_THRESHOLD_IDS:
        assert tid in evidence
    # 红线：evidence 不得出现任何具体数值（如风险分数 / 距离 / 等级数）。
    assert "1200" not in evidence
    assert "1000" not in evidence
    assert "3.5" not in evidence


# --------------------------------------------------------------------------- #
# 9. 防编造扫描                                                              #
# --------------------------------------------------------------------------- #


def test_fabrication_scan_clean_on_installation_sources() -> None:
    """源码 installation_risk.py / installation_rules.py / 本测试 均零命中业务数字。"""

    targets = (
        REPO_ROOT / "agents/engineering/calc/installation_risk.py",
        REPO_ROOT / "agents/engineering/rules/installation_rules.py",
        REPO_ROOT / "tests/agents/test_installation_risk.py",
    )
    for path in targets:
        findings = scan_file(path)
        assert findings == [], f"fabrication hit in {path}: {findings}"


def test_fabrication_scan_catches_fabricated_number() -> None:
    """扫描器能正确捕获一条伪造业务数字（验证扫描有效，非空跑）。"""

    # 故意构造含业务词（防腐等级，扫描器已登记）+ 真实数字的行写入临时文件，
    # 验证扫描器能捕获；源文件本身把各部分拆到不同行，避免被当成未验证数值误伤。
    fake_a = "某安装环境 "
    fake_b = "防腐等级 "
    fake_c = "2"
    fake_d = " 类 直接写死\n"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(fake_a + fake_b + fake_c + fake_d)
        tmp_path = Path(fh.name)
    try:
        findings = scan_file(tmp_path)
        assert len(findings) == 1
        first = findings[0]
        assert "防腐等级" in first.line
    finally:
        tmp_path.unlink()


# --------------------------------------------------------------------------- #
# 10. engineering_enabled=false（闸门不可绕过）                              #
# --------------------------------------------------------------------------- #


def test_pending_propagation_through_validator() -> None:
    """即便注入 engineering_enabled=True，E-TH-05/06 未双签仍 pending（一票否决）。"""

    payload = InstallationRiskCalculator().calculate({}).as_interface()
    # 真实系统 engineering_enabled=false；此处刻意注入 True 以验证闸门。
    validator = ExpertBackedEngineeringValidation(engineering_enabled=True)
    record = validator.validate(interface="installation_risk", payload=payload)
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["sign_off_id"] is None


def test_pending_propagation_through_agent_invoke() -> None:
    """Agent.invoke(analyses=[installation_risk]) 审核链恒 pending_verification。"""

    validator = ExpertBackedEngineeringValidation(engineering_enabled=False)
    agent = EngineeringAgent(validator=validator)
    context = AgentContext(
        request_id="ir-invoke", input_data={"analyses": ["installation_risk"]}
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    record = result.data["review_chain"][0]
    assert record["interface"] == "installation_risk"
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_unified_interface_keys_for_installation_risk() -> None:
    """analyze_installation_risk 经 Agent 接口返回恰好四字段（兼容既有 validator 测试）。"""

    agent = EngineeringAgent()
    output = agent.analyze_installation_risk({})
    assert set(output.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    assert output["verification_status"] == PENDING_VERIFICATION
    assert output["result"] == ""


def test_upstream_propagation_through_agent_invoke_all() -> None:
    """全链路：installation_risk 经 Agent.invoke 仍恒 pending（含上游传导链路）。"""

    validator = ExpertBackedEngineeringValidation(engineering_enabled=False)
    agent = EngineeringAgent(validator=validator)
    context = AgentContext(
        request_id="ir-all",
        input_data={
            "analyses": [
                "wind_pressure",
                "glass_safety",
                "profile",
                "hardware",
                "installation_risk",
            ]
        },
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    chain = {r["interface"]: r for r in result.data["review_chain"]}
    assert chain["installation_risk"]["verification_status"] == PENDING_VERIFICATION
    # 上游亦恒 pending（设计态），installation_risk 不依赖其结论放行。
    for iface in ("wind_pressure", "glass_safety", "profile", "hardware"):
        assert chain[iface]["verification_status"] == PENDING_VERIFICATION
