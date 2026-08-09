"""Glass Safety 计算单元测试（Sprint E 任务5）。

覆盖：D-TH-02 缺失 / wind_pressure pending 传导 / inferred 输入 / 输出结构 /
threshold_refs / evidence / 防编造扫描 / engineering_enabled=false。
零真实数值；engineering_enabled 保持 false。

阶段：Phase 3.1 Sprint E。
红线守约：不产真实玻璃厚度/安全系数/允许应力、不填条款号、不开启 engineering_enabled，所有参数 pending_verification。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from agents.base import AgentContext
from agents.engineering.agent import EngineeringAgent
from agents.engineering.calc.glass_safety import (
    GlassSafetyCalculator,
    GlassSafetyResult,
)
from agents.engineering.rules import glass_rules
from agents.engineering.validation import (
    PENDING_VERIFICATION,
    ENGINEERING_APPROVED,
    ExpertBackedEngineeringValidation,
)
from scripts.lint.check_fabrication import scan_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# 玻璃安全接口所需阈值 ID（与 INTERFACE_THRESHOLD_MAP 对齐；数值 pending_verification）。
GLASS_THRESHOLD_IDS = ("D-TH-02",)


# --------------------------------------------------------------------------- #
# 1. D-TH-02 缺失 → pending                                                    #
# --------------------------------------------------------------------------- #


def test_d_th_missing_yields_pending() -> None:
    """阈值库为空（D-TH-02 缺失）→ verification_status 恒 pending，gaps 登记。"""

    calculator = GlassSafetyCalculator(thresholds={})
    result = calculator.calculate({})
    assert result.verification_status == PENDING_VERIFICATION
    assert result.result == ""  # 红线：不产出真实玻璃安全数值
    for tid in GLASS_THRESHOLD_IDS:
        assert f"{tid}: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 2. wind_pressure pending 传导（跨模块降级）                                  #
# --------------------------------------------------------------------------- #


def test_wind_pressure_pending_propagation() -> None:
    """上游 wind_pressure 未 approved → glass_safety 强制 pending + w_k: upstream_pending。"""

    wind_pending = {
        "verification_status": PENDING_VERIFICATION,
        "intermediate": {"w_k": {"value": None, "verified": False}},
    }
    context: dict[str, Any] = {"wind_pressure_result": wind_pending}
    result = GlassSafetyCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    assert "w_k: upstream_pending" in result.gaps
    assert result.result == ""
    assert result.intermediate["w_k"]["value"] is None


def test_wind_pressure_approved_but_unavailable_wk_still_pending() -> None:
    """上游状态为 approved 但 w_k 无真实取值 → 仍视为不可信，强制 pending。"""

    wind_approved_no_value = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"w_k": {"value": None, "verified": True}},
    }
    context: dict[str, Any] = {"wind_pressure_result": wind_approved_no_value}
    result = GlassSafetyCalculator().calculate(context)
    # D-TH-02 自身未双签，叠加上游 w_k 无取值 → 仍 pending（仅登记上游可信态标记）。
    assert result.verification_status == PENDING_VERIFICATION
    assert result.intermediate["w_k"]["value"] is None


# --------------------------------------------------------------------------- #
# 3. 输入 inferred → pending（不伪造 glass 数值）                             #
# --------------------------------------------------------------------------- #


def test_inferred_input_stays_pending() -> None:
    """项目/设计输入全为 inferred → 结论 pending，且不伪造玻璃应力/面积数值。"""

    context: dict[str, Any] = {
        "project": {
            "glass_area": 2.5,
            "support_condition": "four_side",
            "building_height": 30,
        },
        "design_candidate": {
            "glass_type": "tempered",
            "field_provenance": {
                "glass_type": "inferred",
                "dimensions_hint": "inferred",
            },
        },
    }
    result = GlassSafetyCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    # 关键：inferred 输入不得驱动任何真实玻璃安全数值。
    assert result.result == ""
    assert result.intermediate["sigma_g"]["value"] is None
    assert result.intermediate["sigma_allow"]["value"] is None
    assert result.intermediate["A_max"]["value"] is None
    # 溯源标签应为 inferred（非 verified/measured）。
    assert result.provenance["design.glass_type"] == "inferred"
    assert "design.glass_type: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 4. 输出结构（四字段 + 扩展字段）                                            #
# --------------------------------------------------------------------------- #


def test_output_structure_four_fields() -> None:
    """as_interface 恰好四字段；as_full 含八扩展字段 + interface 标识。"""

    result = GlassSafetyCalculator().calculate({})
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
    assert full["interface"] == "glass_safety"
    assert full["sign_off_id"] is None


def test_glass_safety_result_serializers() -> None:
    """GlassSafetyResult 直接构造后 as_interface / as_full 序列化正确。"""

    res = GlassSafetyResult(
        result="",
        confidence=PENDING_VERIFICATION,
        evidence="e",
        verification_status=PENDING_VERIFICATION,
        intermediate={"sigma_g": {"value": None}},
        provenance={"design.glass_type": "inferred"},
        threshold_refs=list(GLASS_THRESHOLD_IDS),
        gaps=["D-TH-02: pending_verification", "w_k: upstream_pending"],
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
    assert res.as_full()["threshold_refs"] == list(GLASS_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 5. threshold_refs                                                          #
# --------------------------------------------------------------------------- #


def test_threshold_refs_align_with_interface_map() -> None:
    """calculator.threshold_refs 与 get_interface_thresholds 一致。"""

    from agents.engineering.threshold_loader import get_interface_thresholds

    result = GlassSafetyCalculator().calculate({})
    assert result.threshold_refs == list(get_interface_thresholds("glass_safety"))
    assert result.threshold_refs == list(GLASS_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 6. evidence 内容                                                           #
# --------------------------------------------------------------------------- #


def test_evidence_carries_formula_and_pending() -> None:
    """evidence 须含公式来源、阈值引用与 pending_verification 标注，无真实数值。"""

    result = GlassSafetyCalculator().calculate({})
    evidence = result.evidence
    for formula in glass_rules.GLASS_SAFETY_FORMULAS:
        assert formula in evidence
    assert "pending_verification" in evidence
    for tid in GLASS_THRESHOLD_IDS:
        assert tid in evidence
    # 红线：evidence 不得出现任何具体数值（如 1200 Pa / 6 mm）。
    assert "1200" not in evidence
    assert "6 mm" not in evidence


# --------------------------------------------------------------------------- #
# 7. 防编造扫描                                                              #
# --------------------------------------------------------------------------- #


def test_fabrication_scan_clean_on_glass_sources() -> None:
    """源码 glass_safety.py / glass_rules.py / 本测试 均零命中业务数字。"""

    targets = (
        REPO_ROOT / "agents/engineering/calc/glass_safety.py",
        REPO_ROOT / "agents/engineering/rules/glass_rules.py",
        REPO_ROOT / "tests/agents/test_glass_safety.py",
    )
    for path in targets:
        findings = scan_file(path)
        assert findings == [], f"fabrication hit in {path}: {findings}"


def test_fabrication_scan_catches_fabricated_number() -> None:
    """扫描器能正确捕获一条伪造业务数字（验证扫描有效，非空跑）。"""

    # 故意构造含业务词 + 真实数字的行写入临时文件，验证扫描器能捕获；
    # 源文件本身把各部分拆到不同行，避免被当成未验证数值误伤。
    fake_a = "某配置 "
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


# --------------------------------------------------------------------------- #
# 8. engineering_enabled=false（闸门不可绕过）                               #
# --------------------------------------------------------------------------- #


def test_pending_propagation_through_validator() -> None:
    """即便注入 engineering_enabled=True，D-TH-02 未双签仍 pending（一票否决）。"""

    payload = GlassSafetyCalculator().calculate({}).as_interface()
    # 真实系统 engineering_enabled=false；此处刻意注入 True 以验证闸门。
    validator = ExpertBackedEngineeringValidation(engineering_enabled=True)
    record = validator.validate(interface="glass_safety", payload=payload)
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["sign_off_id"] is None


def test_pending_propagation_through_agent_invoke() -> None:
    """Agent.invoke(analyses=[glass_safety]) 审核链恒 pending_verification。"""

    validator = ExpertBackedEngineeringValidation(engineering_enabled=False)
    agent = EngineeringAgent(validator=validator)
    context = AgentContext(
        request_id="gs-invoke", input_data={"analyses": ["glass_safety"]}
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    record = result.data["review_chain"][0]
    assert record["interface"] == "glass_safety"
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_unified_interface_keys_for_glass_safety() -> None:
    """analyze_glass_safety 经 Agent 接口返回恰好四字段（兼容既有 validator 测试）。"""

    agent = EngineeringAgent()
    output = agent.analyze_glass_safety({})
    assert set(output.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    assert output["verification_status"] == PENDING_VERIFICATION
    assert output["result"] == ""
