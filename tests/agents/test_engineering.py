"""Engineering Agent 骨架测试（Phase 2.1.5）。

覆盖：身份 / 统一输出结构 / 防编造红线 / invoke 契约 / 审核链 /
验证机制（EngineeringValidation 注入）/ 配置注册状态。
"""

from __future__ import annotations

import asyncio
from typing import Any, Mapping

from agents.base import AgentContext, BaseAgent
from agents.engineering.agent import (
    ANALYSIS_INTERFACES,
    ENGINEERING_AGENT_NAME,
    ENGINEERING_AGENT_VERSION,
    EngineeringAgent,
    build_skeleton_output,
)
from agents.engineering.validation import (
    PENDING_VERIFICATION,
    REQUIRED_OUTPUT_KEYS,
    EngineeringValidation,
    PendingEngineeringValidation,
)
from agents.loader import AgentLoader, DEFAULT_CONFIG_PATH
from agents.registry import AgentRegistry


# --------------------------------------------------------------------------- #
# 身份 / 协议                                                                    #
# --------------------------------------------------------------------------- #


def test_engineering_agent_identity() -> None:
    """EngineeringAgent 必须暴露规范名称与骨架版本，并继承 BaseAgent。"""

    agent = EngineeringAgent()
    assert agent.name == ENGINEERING_AGENT_NAME
    assert agent.version == ENGINEERING_AGENT_VERSION
    assert agent.version.startswith("0.1.0")
    assert "skeleton" in agent.version
    assert isinstance(agent, BaseAgent)


def test_engineering_agent_declares_tools_without_connecting() -> None:
    """tools 仅声明 structural_calc_mcp + engineering_rules_mcp。"""

    agent = EngineeringAgent()
    tools = list(agent.tools)
    assert tools == ["structural_calc_mcp", "engineering_rules_mcp"]


def test_engineering_agent_defines_five_interfaces() -> None:
    """接口契约必须恰好覆盖五个分析接口标识。"""

    assert ANALYSIS_INTERFACES == (
        "wind_pressure",
        "glass_safety",
        "profile",
        "hardware",
        "installation_risk",
    )


def test_engineering_agent_prompt_file_exists() -> None:
    """prompt.md 必须存在且包含统一结构与防编造硬约束。"""

    agent = EngineeringAgent()
    prompt_text = agent._load_prompt()  # noqa: SLF001 - 契约验证
    assert "verification_status" in prompt_text
    assert "pending_verification" in prompt_text
    assert "不编造风压参数" in prompt_text
    assert "不编造评分权重" in prompt_text


# --------------------------------------------------------------------------- #
# 统一输出结构 + 防编造红线                                                        #
# --------------------------------------------------------------------------- #


def test_unified_output_structure_for_each_interface() -> None:
    """五个接口必须返回且仅返回统一四字段结构。"""

    agent = EngineeringAgent()
    methods = (
        agent.analyze_wind_pressure,
        agent.analyze_glass_safety,
        agent.analyze_profile,
        agent.analyze_hardware,
        agent.analyze_installation_risk,
    )
    for method in methods:
        output = method({})
        assert tuple(output.keys()) == REQUIRED_OUTPUT_KEYS
        assert output["verification_status"] == PENDING_VERIFICATION


def test_skeleton_output_never_fabricates_content() -> None:
    """骨架输出内容字段必须为空串——任何非空即视为编造工程结论。"""

    output = build_skeleton_output()
    assert output["result"] == ""
    assert output["confidence"] == ""
    assert output["evidence"] == ""
    assert output["verification_status"] == PENDING_VERIFICATION


# --------------------------------------------------------------------------- #
# invoke 契约                                                                   #
# --------------------------------------------------------------------------- #


def test_invoke_runs_all_five_interfaces_by_default() -> None:
    """缺省 invoke 执行全部五接口，输出 analyses + review_chain + gaps。"""

    agent = EngineeringAgent()
    context = AgentContext(request_id="eng-all", input_data={})
    result = asyncio.run(agent.invoke(context))

    assert result.success is True
    data = result.data
    assert data["agent"] == "engineering"
    assert data["stage"] == "engineering_skeleton"
    assert data["pending_verification"] is True
    assert set(data["analyses"].keys()) == set(ANALYSIS_INTERFACES)
    assert len(data["review_chain"]) == len(ANALYSIS_INTERFACES)
    for name in ANALYSIS_INTERFACES:
        assert f"{name}_analysis: {PENDING_VERIFICATION}" in data["gaps"]

    envelope = result.to_envelope()
    assert envelope["success"] is True
    assert "evidence" in envelope["data"]


def test_invoke_respects_requested_subset() -> None:
    """analyses 子集 → 只执行子集接口。"""

    agent = EngineeringAgent()
    context = AgentContext(
        request_id="eng-subset",
        input_data={"analyses": ["wind_pressure", "glass_safety"]},
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert set(result.data["analyses"].keys()) == {"wind_pressure", "glass_safety"}
    assert len(result.data["review_chain"]) == 2


def test_invoke_rejects_unknown_interface() -> None:
    """未知接口名 → success=False + ENGINEERING_UNKNOWN_INTERFACE。"""

    agent = EngineeringAgent()
    context = AgentContext(
        request_id="eng-unknown",
        input_data={"analyses": ["wind_pressure", "no_such_interface"]},
    )
    result = asyncio.run(agent.invoke(context))
    assert result.success is False
    assert result.error is not None
    assert result.error["code"] == "ENGINEERING_UNKNOWN_INTERFACE"
    assert result.data["analyses"] == {}
    assert any("no_such_interface" in gap for gap in result.data["gaps"])


# --------------------------------------------------------------------------- #
# 审核链 + 验证机制                                                              #
# --------------------------------------------------------------------------- #


def test_review_chain_records_are_structure_valid() -> None:
    """审核链记录：structure_valid=True + pending_verification 状态。"""

    agent = EngineeringAgent()
    context = AgentContext(request_id="eng-chain", input_data={})
    result = asyncio.run(agent.invoke(context))
    for record in result.data["review_chain"]:
        assert record["structure_valid"] is True
        assert record["missing_keys"] == []
        assert record["verification_status"] == PENDING_VERIFICATION
        assert record["validator"] == "PendingEngineeringValidation"
        assert record["interface"] in ANALYSIS_INTERFACES


def test_pending_validation_flags_missing_keys() -> None:
    """PendingEngineeringValidation 对缺字段 payload 返回 invalid_structure。"""

    validator = PendingEngineeringValidation()
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": ""},  # 缺 confidence / evidence / verification_status
    )
    assert record["structure_valid"] is False
    assert set(record["missing_keys"]) == {
        "confidence",
        "evidence",
        "verification_status",
    }
    assert record["verification_status"] == "invalid_structure"


def test_custom_validator_can_be_injected() -> None:
    """EngineeringValidation 实现可注入替换（审核链可演进，Agent 不改）。"""

    class RecordingValidator(EngineeringValidation):
        def __init__(self) -> None:
            self.calls: list[str] = []

        def validate(
            self, *, interface: str, payload: Mapping[str, Any]
        ) -> dict[str, Any]:
            self.calls.append(interface)
            return {
                "interface": interface,
                "structure_valid": True,
                "missing_keys": [],
                "verification_status": PENDING_VERIFICATION,
                "validator": "RecordingValidator",
            }

    validator = RecordingValidator()
    agent = EngineeringAgent(validator=validator)
    assert agent.validator is validator

    context = AgentContext(request_id="eng-custom", input_data={})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    assert validator.calls == list(ANALYSIS_INTERFACES)
    assert all(
        record["validator"] == "RecordingValidator"
        for record in result.data["review_chain"]
    )


# --------------------------------------------------------------------------- #
# 注册 / 配置状态                                                                #
# --------------------------------------------------------------------------- #


def test_engineering_registered_in_config_but_disabled() -> None:
    """config.yaml 登记 engineering 条目但 enabled=false，不进编排管道。"""

    loader = AgentLoader(config_path=DEFAULT_CONFIG_PATH, registry=AgentRegistry())
    config = loader.load_config()

    entries = {entry.name: entry for entry in config.agents}
    assert "engineering" in entries
    engineering_entry = entries["engineering"]
    assert engineering_entry.enabled is False
    assert engineering_entry.class_path == "agents.engineering.agent.EngineeringAgent"
    assert engineering_entry.stage == "engineering"

    # 编排管道保持不变（不修改已有 Agent 业务逻辑与编排）。
    assert config.pipeline == ("environment", "vision", "design")
    assert config.engineering_enabled is False

    # loader 不注册 disabled 条目。
    registered = loader.load_all()
    assert "engineering" not in {agent.name for agent in registered}
