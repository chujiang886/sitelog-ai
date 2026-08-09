"""Wind Pressure 计算单元测试（Sprint C 任务5）。

覆盖：E-TH 缺失 / 输入 inferred / 输出结构 / evidence / threshold_refs /
pending 传导 / 防编造扫描。零真实数值；engineering_enabled 保持 false。

阶段：Phase 3.1 Sprint C。
红线守约：不产真实数值、不填系数、不写条款号、不开启 engineering_enabled，所有参数 pending_verification。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from agents.base import AgentContext
from agents.engineering.agent import EngineeringAgent
from agents.engineering.calc.wind_pressure import (
    WindPressureCalculator,
    WindPressureResult,
)
from agents.engineering.rules import wind_rules
from agents.engineering.validation import (
    PENDING_VERIFICATION,
    ExpertBackedEngineeringValidation,
)
from scripts.lint.check_fabrication import scan_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# 风压接口所需阈值 ID（与 INTERFACE_THRESHOLD_MAP 对齐；数值 pending_verification）。
WIND_THRESHOLD_IDS = ("E-TH-01", "E-TH-02", "E-TH-03")


# --------------------------------------------------------------------------- #
# 1. E-TH 缺失 → pending                                                        #
# --------------------------------------------------------------------------- #


def test_e_th_missing_yields_pending() -> None:
    """阈值库为空（E-TH 全缺失）→ verification_status 恒 pending，gaps 登记。"""

    calculator = WindPressureCalculator(thresholds={})
    result = calculator.calculate({})
    assert result.verification_status == PENDING_VERIFICATION
    assert result.result == ""  # 红线：不产出真实风压数值
    for tid in WIND_THRESHOLD_IDS:
        assert f"{tid}: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 2. 输入 inferred → pending（不伪造 w_k）                                    #
# --------------------------------------------------------------------------- #


def test_inferred_input_stays_pending() -> None:
    """项目/环境输入全为 inferred → 结论 pending，且不伪造 w_k 数值。"""

    context: dict[str, Any] = {
        "project": {"building_height": 30, "site_category": "B"},
        "environment_result": {
            "field_provenance": {
                "climate_zone": "inferred",
                "prevailing_wind": "inferred",
                "solar_exposure": "inferred",
            }
        },
        "design_candidate": {
            "field_provenance": {
                "dimensions_hint": "inferred",
                "frame_material": "inferred",
                "glass_type": "inferred",
            }
        },
    }
    result = WindPressureCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    # 关键：inferred 输入不得驱动任何真实风压数值。
    assert result.result == ""
    assert result.intermediate["w_k"]["value"] is None
    # 溯源标签应为 inferred（非 verified/measured）。
    assert result.provenance["project.building_height"] == "inferred"
    assert "project.building_height: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 3. 输出结构（四字段 + 扩展字段）                                            #
# --------------------------------------------------------------------------- #


def test_output_structure_four_fields() -> None:
    """as_interface 恰好四字段；as_full 含八扩展字段 + interface 标识。"""

    result = WindPressureCalculator().calculate({})
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
    assert full["interface"] == "wind_pressure"
    assert full["sign_off_id"] is None


def test_wind_pressure_result_serializers() -> None:
    """WindPressureResult 直接构造后 as_interface / as_full 序列化正确。"""

    res = WindPressureResult(
        result="",
        confidence=PENDING_VERIFICATION,
        evidence="e",
        verification_status=PENDING_VERIFICATION,
        intermediate={"w_k": {"value": None}},
        provenance={"project.building_height": "inferred"},
        threshold_refs=list(WIND_THRESHOLD_IDS),
        gaps=["E-TH-01: pending_verification"],
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
    assert res.as_full()["threshold_refs"] == list(WIND_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 4. evidence 内容                                                           #
# --------------------------------------------------------------------------- #


def test_evidence_carries_formula_and_pending() -> None:
    """evidence 须含公式来源、阈值引用与 pending_verification 标注，无真实数值。"""

    result = WindPressureCalculator().calculate({})
    evidence = result.evidence
    assert wind_rules.WIND_PRESSURE_FORMULA in evidence
    assert "pending_verification" in evidence
    for tid in WIND_THRESHOLD_IDS:
        assert tid in evidence
    # 红线：evidence 不得出现任何具体数值（如 1200 Pa）。
    assert "1200" not in evidence


# --------------------------------------------------------------------------- #
# 5. threshold_refs                                                          #
# --------------------------------------------------------------------------- #


def test_threshold_refs_align_with_interface_map() -> None:
    """calculator.threshold_refs 与 get_interface_thresholds 一致。"""

    from agents.engineering.threshold_loader import get_interface_thresholds

    result = WindPressureCalculator().calculate({})
    assert result.threshold_refs == list(get_interface_thresholds("wind_pressure"))
    assert result.threshold_refs == list(WIND_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 6. pending 传导（calculator → validator → agent）                          #
# --------------------------------------------------------------------------- #


def test_pending_propagation_through_validator() -> None:
    """即便注入 engineering_enabled=True，未双签阈值仍 pending（一票否决）。"""

    payload = WindPressureCalculator().calculate({}).as_interface()
    # 真实系统 engineering_enabled=false；此处刻意注入 True 以验证闸门。
    validator = ExpertBackedEngineeringValidation(engineering_enabled=True)
    record = validator.validate(interface="wind_pressure", payload=payload)
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["sign_off_id"] is None


def test_pending_propagation_through_agent_invoke() -> None:
    """Agent.invoke(analyses=[wind_pressure]) 审核链恒 pending_verification。"""

    validator = ExpertBackedEngineeringValidation(engineering_enabled=False)
    agent = EngineeringAgent(validator=validator)
    context = AgentContext(
        request_id="wp-invoke", input_data={"analyses": ["wind_pressure"]}
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    record = result.data["review_chain"][0]
    assert record["interface"] == "wind_pressure"
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


# --------------------------------------------------------------------------- #
# 7. 防编造扫描                                                              #
# --------------------------------------------------------------------------- #


def test_fabrication_scan_clean_on_wind_sources() -> None:
    """源码 wind_pressure.py / wind_rules.py / 本测试 均零命中业务数字。"""

    targets = (
        REPO_ROOT / "agents/engineering/calc/wind_pressure.py",
        REPO_ROOT / "agents/engineering/rules/wind_rules.py",
        REPO_ROOT / "tests/agents/test_wind_pressure.py",
    )
    for path in targets:
        findings = scan_file(path)
        assert findings == [], f"fabrication hit in {path}: {findings}"


def test_fabrication_scan_catches_fabricated_number() -> None:
    """扫描器能正确捕获一条伪造业务数字（验证扫描有效，非空跑）。"""

    # 故意构造含业务词 + 真实数字的行写入临时文件，验证扫描器能捕获；
    # 源文件本身把各部分拆到不同行，避免被当成未验证数值误伤。
    fake_a = "某阈值 "
    fake_b = "风压 "
    fake_c = "1200"
    fake_d = " Pa 直接写死\n"
    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as fh:
        fh.write(fake_a + fake_b + fake_c + fake_d)
        tmp_path = Path(fh.name)
    try:
        findings = scan_file(tmp_path)
        assert len(findings) == 1
        first = findings[0]
        assert "风压" in first.line
    finally:
        tmp_path.unlink()
