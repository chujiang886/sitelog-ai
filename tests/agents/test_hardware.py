"""Hardware 计算单元测试（Sprint I 任务5）。

覆盖：E-TH-04 缺失 / profile pending 传导 / inferred 输入 / 输出结构 /
threshold_refs / evidence / 防编造扫描 / engineering_enabled=false。
零真实数值；engineering_enabled 保持 false。

阶段：Phase 3.1 Sprint I。
红线守约：不产真实五金承载值/锁点数量/寿命次数/型号规格、不填条款号、
不开启 engineering_enabled，所有参数 pending_verification。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from agents.base import AgentContext
from agents.engineering.agent import EngineeringAgent
from agents.engineering.calc.hardware import (
    HardwareCalculator,
    HardwareResult,
)
from agents.engineering.rules import hardware_rules
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
    ExpertBackedEngineeringValidation,
)
from scripts.lint.check_fabrication import scan_file

REPO_ROOT = Path(__file__).resolve().parents[2]

# 五金接口所需阈值 ID（与 INTERFACE_THRESHOLD_MAP 对齐；数值 pending_verification）。
HARDWARE_THRESHOLD_IDS = ("E-TH-04",)


# --------------------------------------------------------------------------- #
# 1. E-TH-04 缺失 → pending                                                    #
# --------------------------------------------------------------------------- #


def test_e_th_missing_yields_pending() -> None:
    """阈值库为空（E-TH-04 缺失）→ verification_status 恒 pending，gaps 登记。"""

    calculator = HardwareCalculator(thresholds={})
    result = calculator.calculate({})
    assert result.verification_status == PENDING_VERIFICATION
    assert result.result == ""  # 红线：不产出真实五金结论
    for tid in HARDWARE_THRESHOLD_IDS:
        assert f"{tid}: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 2. profile pending 传导（跨模块降级）                                       #
# --------------------------------------------------------------------------- #


def test_profile_pending_propagation() -> None:
    """上游 profile 未 approved → hardware 强制 pending + profile_result: upstream_pending。"""

    profile_pending = {
        "verification_status": PENDING_VERIFICATION,
    }
    context: dict[str, Any] = {"profile_result": profile_pending}
    result = HardwareCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    assert "profile_result: upstream_pending" in result.gaps
    assert result.result == ""
    assert result.provenance["profile_result"] == "upstream_pending"


def test_profile_approved_but_forbids_self_force_calc() -> None:
    """上游 profile approved 时仅标记可信态；本模块仍不重算型材受力、不填数值。"""

    profile_approved = {
        "verification_status": ENGINEERING_APPROVED,
        "intermediate": {"sigma": {"value": None}},
    }
    context: dict[str, Any] = {"profile_result": profile_approved}
    result = HardwareCalculator().calculate(context)
    # E-TH-04 自身未双签，结论仍 pending（仅登记上游可信态标记）。
    assert result.verification_status == PENDING_VERIFICATION
    assert result.provenance["profile_result"] == "verified"
    # 红线：即便上游可信，也不得在本模块自行计算/填入型材受力数值。
    assert result.intermediate["w_k"]["value"] is None
    assert result.result == ""


# --------------------------------------------------------------------------- #
# 3. 输入 inferred → pending（不伪造五金数值）                               #
# --------------------------------------------------------------------------- #


def test_inferred_input_stays_pending() -> None:
    """项目/设计输入全为 inferred → 结论 pending，且不伪造承载/锁点/寿命数值。"""

    context: dict[str, Any] = {
        "project": {
            "load_condition": "medium",
            "usage_scenario": "residential",
        },
        "design_candidate": {
            "opening_type": "casement",
            "hardware_config": "hw_a",
            "field_provenance": {
                "opening_type": "inferred",
                "hardware_config": "inferred",
            },
        },
    }
    result = HardwareCalculator().calculate(context)
    assert result.verification_status == PENDING_VERIFICATION
    # 关键：inferred 输入不得驱动任何真实五金承载/锁点/寿命数值。
    assert result.result == ""
    assert result.intermediate["F_hardware"]["value"] is None
    assert result.intermediate["F_demand"]["value"] is None
    assert result.intermediate["lock_system"]["value"] is None
    assert result.intermediate["cycle_life"]["value"] is None
    assert result.intermediate["load_check"]["value"] is None
    # 溯源标签应为 inferred（非 verified/measured）。
    assert result.provenance["design.opening_type"] == "inferred"
    assert "design.opening_type: pending_verification" in result.gaps


# --------------------------------------------------------------------------- #
# 4. 输出结构（四字段 + 扩展字段）                                           #
# --------------------------------------------------------------------------- #


def test_output_structure_four_fields() -> None:
    """as_interface 恰好四字段；as_full 含八扩展字段 + interface 标识。"""

    result = HardwareCalculator().calculate({})
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
    assert full["interface"] == "hardware"
    assert full["sign_off_id"] is None


def test_hardware_result_serializers() -> None:
    """HardwareResult 直接构造后 as_interface / as_full 序列化正确。"""

    res = HardwareResult(
        result="",
        confidence=PENDING_VERIFICATION,
        evidence="e",
        verification_status=PENDING_VERIFICATION,
        intermediate={"F_hardware": {"value": None}},
        provenance={"profile_result": "upstream_pending"},
        threshold_refs=list(HARDWARE_THRESHOLD_IDS),
        gaps=["E-TH-04: pending_verification", "profile_result: upstream_pending"],
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
    assert res.as_full()["threshold_refs"] == list(HARDWARE_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 5. threshold_refs                                                          #
# --------------------------------------------------------------------------- #


def test_threshold_refs_align_with_interface_map() -> None:
    """calculator.threshold_refs 与 get_interface_thresholds 一致。"""

    from agents.engineering.threshold_loader import get_interface_thresholds

    result = HardwareCalculator().calculate({})
    assert result.threshold_refs == list(get_interface_thresholds("hardware"))
    assert result.threshold_refs == list(HARDWARE_THRESHOLD_IDS)


# --------------------------------------------------------------------------- #
# 6. evidence 内容                                                           #
# --------------------------------------------------------------------------- #


def test_evidence_carries_formula_and_pending() -> None:
    """evidence 须含公式来源、阈值引用与 pending_verification 标注，无真实数值。"""

    result = HardwareCalculator().calculate({})
    evidence = result.evidence
    for formula in hardware_rules.HARDWARE_FORMULAS:
        assert formula in evidence
    assert "pending_verification" in evidence
    for tid in HARDWARE_THRESHOLD_IDS:
        assert tid in evidence
    # 红线：evidence 不得出现任何具体数值（如 1200 N / 10000 次）。
    assert "1200" not in evidence
    assert "10000" not in evidence


# --------------------------------------------------------------------------- #
# 7. 防编造扫描                                                              #
# --------------------------------------------------------------------------- #


def test_fabrication_scan_clean_on_hardware_sources() -> None:
    """源码 hardware.py / hardware_rules.py / 本测试 均零命中业务数字。"""

    targets = (
        REPO_ROOT / "agents/engineering/calc/hardware.py",
        REPO_ROOT / "agents/engineering/rules/hardware_rules.py",
        REPO_ROOT / "tests/agents/test_hardware.py",
    )
    for path in targets:
        findings = scan_file(path)
        assert findings == [], f"fabrication hit in {path}: {findings}"


def test_fabrication_scan_catches_fabricated_number() -> None:
    """扫描器能正确捕获一条伪造业务数字（验证扫描有效，非空跑）。"""

    # 故意构造含业务词（防腐等级，扫描器已登记）+ 真实数字的行写入临时文件，
    # 验证扫描器能捕获；源文件本身把各部分拆到不同行，避免被当成未验证数值误伤。
    fake_a = "某五金 "
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
# 8. engineering_enabled=false（闸门不可绕过）                               #
# --------------------------------------------------------------------------- #


def test_pending_propagation_through_validator() -> None:
    """即便注入 engineering_enabled=True，E-TH-04 未双签仍 pending（一票否决）。"""

    payload = HardwareCalculator().calculate({}).as_interface()
    # 真实系统 engineering_enabled=false；此处刻意注入 True 以验证闸门。
    validator = ExpertBackedEngineeringValidation(engineering_enabled=True)
    record = validator.validate(interface="hardware", payload=payload)
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["sign_off_id"] is None


def test_pending_propagation_through_agent_invoke() -> None:
    """Agent.invoke(analyses=[hardware]) 审核链恒 pending_verification。"""

    validator = ExpertBackedEngineeringValidation(engineering_enabled=False)
    agent = EngineeringAgent(validator=validator)
    context = AgentContext(
        request_id="hw-invoke", input_data={"analyses": ["hardware"]}
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    record = result.data["review_chain"][0]
    assert record["interface"] == "hardware"
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_unified_interface_keys_for_hardware() -> None:
    """analyze_hardware 经 Agent 接口返回恰好四字段（兼容既有 validator 测试）。"""

    agent = EngineeringAgent()
    output = agent.analyze_hardware({})
    assert set(output.keys()) == {
        "result",
        "confidence",
        "evidence",
        "verification_status",
    }
    assert output["verification_status"] == PENDING_VERIFICATION
    assert output["result"] == ""
