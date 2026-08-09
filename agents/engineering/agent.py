"""Engineering Agent 骨架（Phase 2.1.5）。

本阶段**不实现真实工程计算**，只建立：
- Agent 结构：继承 ``BaseAgent``，与 core/environment/vision/design 同构；
- 接口契约：五个分析接口（风压 / 玻璃安全 / 型材 / 五金 / 安装风险），
  统一输出结构 ``{result, confidence, evidence, verification_status}``；
- 审核链：每个分析输出经 ``EngineeringValidation.validate`` 产出审核记录；
- 验证机制：骨架默认 ``PendingEngineeringValidation``，一切结论
  ``verification_status=pending_verification``。

防编造红线（与仓库 16 原则一致）：
- 不编造风压参数；
- 不编造楼层阈值；
- 不编造玻璃厚度；
- 不编造评分权重。
所有 ``result`` / ``confidence`` / ``evidence`` 字段在骨架阶段保持空串，
缺口通过 ``gaps`` 显式声明，等待真实规范库 / 计算引擎接入后填充。

Sprint C 起 wind_pressure 接入 WindPressureCalculator（仅结构装配，不产真实数值），
Sprint E 起 glass_safety 接入 GlassSafetyCalculator（仅结构装配，不产真实数值，
含 wind_pressure 上游 w_k 跨模块降级），
Sprint G 起 profile 接入 ProfileCalculator（仅结构装配，不产真实数值，
含 wind_pressure 上游 w_k 跨模块降级），
Sprint I 起 hardware 接入 HardwareCalculator（仅结构装配，不产真实数值，
含 profile 上游审核态跨模块降级，禁止重算型材受力）；
Sprint K 起 installation_risk 接入 InstallationRiskCalculator（仅结构装配，不产真实数值，
含 glass_safety/profile/hardware 三上游审核态跨模块降级，禁止重算玻璃重量/型材受力/五金承载）；
统一四字段契约与 validator 流程保持不变。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent
from agents.engineering.calc.glass_safety import GlassSafetyCalculator
from agents.engineering.calc.hardware import HardwareCalculator
from agents.engineering.calc.installation_risk import InstallationRiskCalculator
from agents.engineering.calc.profile import ProfileCalculator
from agents.engineering.calc.wind_pressure import WindPressureCalculator
from agents.engineering.knowledge.activation.runtime_integration import (
    EngineeringRuntimeGuard,
    InterfaceGuardResult,
)
from agents.engineering.validation import (
    PENDING_VERIFICATION,
    EngineeringValidation,
    PendingEngineeringValidation,
)


ENGINEERING_AGENT_NAME: str = "engineering"
ENGINEERING_AGENT_VERSION: str = "0.1.0-phase2.1.5-skeleton"
ENGINEERING_AGENT_DESCRIPTION: str = (
    "Engineering Agent：建筑开口工程分析能力框架（骨架）。"
    "定义风压分析、玻璃安全、型材分析、五金分析、安装风险五个接口契约，"
    "统一输出 result/confidence/evidence/verification_status 结构，"
    "全部结论保持 pending_verification，不做真实工程计算。"
)
_ENGINEERING_PROMPT_DIR: Path = Path(__file__).resolve().parent

# 五个分析接口的稳定标识（接口契约的一部分，勿随意改名）。
ANALYSIS_INTERFACES: tuple[str, ...] = (
    "wind_pressure",       # 风压分析接口
    "glass_safety",        # 玻璃安全接口
    "profile",             # 型材分析接口
    "hardware",            # 五金分析接口
    "installation_risk",   # 安装风险接口
)


def build_skeleton_output() -> dict[str, Any]:
    """构造统一输出结构（骨架：空结论 + pending_verification）。

    契约（2.1.5 任务规定的统一结构）::

        {
            "result": "",
            "confidence": "",
            "evidence": "",
            "verification_status": "pending_verification",
        }

    骨架阶段三个内容字段必须为空串——任何非空结论都意味着
    在没有真实计算引擎的情况下编造工程判断。
    """

    return {
        "result": "",
        "confidence": "",
        "evidence": "",
        "verification_status": PENDING_VERIFICATION,
    }


class EngineeringAgent(BaseAgent):
    """建筑开口工程分析 Agent（Phase 2.1.5 骨架实现）。"""

    def __init__(
        self,
        *,
        validator: EngineeringValidation | None = None,
        knowledge_guard: EngineeringRuntimeGuard | None = None,
        knowledge_repository: Any | None = None,
    ) -> None:
        super().__init__(
            name=ENGINEERING_AGENT_NAME,
            description=ENGINEERING_AGENT_DESCRIPTION,
            version=ENGINEERING_AGENT_VERSION,
        )
        # 审核链验证器：默认骨架实现，可注入真实实现（Phase 3+）。
        self._validator: EngineeringValidation = (
            validator if validator is not None else PendingEngineeringValidation()
        )
        # 任务(3.4.4) 知识消费守卫接入（计算前过 guard；缺省懒构建，零副作用）。
        # 不修改任何既有计算逻辑；仅在 invoke 提供 knowledge_items 时生效。
        self._knowledge_guard: EngineeringRuntimeGuard = (
            knowledge_guard or EngineeringRuntimeGuard()
        )
        self._knowledge_repository: Any | None = knowledge_repository

    @property
    def knowledge_guard(self) -> EngineeringRuntimeGuard:
        """返回当前知识消费守卫（供测试与运行时替换检查）。"""

        return self._knowledge_guard

    @property
    def tools(self) -> Sequence[str]:
        """声明未来工具标识（仅声明，骨架不连接任何外部服务）。"""

        return ("structural_calc_mcp", "engineering_rules_mcp")

    @property
    def validator(self) -> EngineeringValidation:
        """返回当前审核链验证器（供测试与未来编排替换检查）。"""

        return self._validator

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Engineering Agent package."""

        return _ENGINEERING_PROMPT_DIR

    # ------------------------------------------------------------------ #
    # 五个分析接口（骨架：统一输出结构，不做真实计算）                          #
    # ------------------------------------------------------------------ #

    def analyze_wind_pressure(
        self, context_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """风压分析接口（Sprint C）：调用 WindPressureCalculator，返回统一四字段。

        红线：calculator 不产出真实风压数值，verification_status 恒 pending；
        validator 流程不变（invoke 仍调用 self._validator.validate）。
        """

        calculator = WindPressureCalculator()
        wp_result = calculator.calculate(context_data)
        return wp_result.as_interface()

    def analyze_glass_safety(
        self, context_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """玻璃安全接口（Sprint E）：调用 GlassSafetyCalculator，返回统一四字段。

        红线：calculator 不产出真实玻璃安全数值，verification_status 恒 pending；
        validator 流程不变（invoke 仍调用 self._validator.validate）。
        跨模块链路（任务4）：calculator 内部消费 wind_pressure_result 的 w_k，
        上游未 approved 时强制 pending 并登记 w_k: upstream_pending。
        """

        calculator = GlassSafetyCalculator()
        gs_result = calculator.calculate(context_data)
        return gs_result.as_interface()

    def analyze_profile(self, context_data: Mapping[str, Any]) -> dict[str, Any]:
        """型材分析接口（Sprint G）：调用 ProfileCalculator，返回统一四字段。

        红线：calculator 不产出真实型材数值，verification_status 恒 pending；
        validator 流程不变（invoke 仍调用 self._validator.validate）。
        跨模块链路（任务4）：calculator 内部消费 wind_pressure_result 的 w_k，
        上游未 approved 时强制 pending 并登记 w_k: upstream_pending。
        """

        calculator = ProfileCalculator()
        pf_result = calculator.calculate(context_data)
        return pf_result.as_interface()

    def analyze_hardware(self, context_data: Mapping[str, Any]) -> dict[str, Any]:
        """五金分析接口（Sprint I）：调用 HardwareCalculator，返回统一四字段。

        红线：calculator 不产出真实五金选型/承载结论，verification_status 恒 pending；
        validator 流程不变（invoke 仍调用 self._validator.validate）。
        跨模块链路（任务4）：calculator 内部消费 profile_result 的审核态，
        上游 profile 未 approved 时强制 pending 并登记 profile_result: upstream_pending；
        **禁止**在本接口自行计算型材受力（型材受力归属 profile 模块）。
        """

        calculator = HardwareCalculator()
        hw_result = calculator.calculate(context_data)
        return hw_result.as_interface()

    def analyze_installation_risk(
        self, context_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """安装风险接口（Sprint K）：调用 InstallationRiskCalculator，返回统一四字段。

        红线：calculator 不产出真实风险评级/承载/距离结论，verification_status 恒 pending；
        validator 流程不变（invoke 仍调用 self._validator.validate）。
        跨模块链路（任务4，末端聚合）：calculator 内部消费 glass_safety_result /
        profile_result / hardware_result 的审核态，任一上游未 approved 时强制 pending
        并登记 upstream_pending；**禁止**在本接口自行计算玻璃重量/型材受力/五金承载。
        """

        calculator = InstallationRiskCalculator()
        ir_result = calculator.calculate(context_data)
        return ir_result.as_interface()

    # ------------------------------------------------------------------ #
    # 任务(3.4.4)：知识消费守卫接入（计算前过 guard，只读判定）              #
    # ------------------------------------------------------------------ #

    def consume_knowledge_for(
        self, interface: str, items: Sequence[Any], decision: Any
    ) -> "InterfaceGuardResult":
        """计算前接入点：在某工程接口计算前，对其候选知识逐项过 guard 分区。

        返回 ``InterfaceGuardResult``；仅 authoritative 可作权威依据，auxiliary
        仅辅助须 pending_verification，blocked 一律不得进入。只读判定，不修改任何
        既有计算逻辑；红线：不翻转 engineering_enabled / 不输出 engineering_approved。
        """

        return self._knowledge_guard.guard_interface(interface, list(items), decision)

    def _consume_requested_knowledge(
        self, requested: tuple[str, ...], input_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """invoke 内部：对 requested 接口提供的候选知识跑消费守卫分区。

        无 ``knowledge_items`` 输入 → 返回空 dict（向后兼容，零副作用）。
        未显式提供 ``unified_decision`` 时，由守卫按（可选）仓库解析系统级决策；
        仓库缺失则 fail-closed 全部阻断。
        """

        knowledge_items_in = input_data.get("knowledge_items")
        if not isinstance(knowledge_items_in, Mapping):
            return {}
        unified_decision = input_data.get("unified_decision")
        if unified_decision is None:
            unified_decision = self._knowledge_guard.resolve_decision(
                self._knowledge_repository
            )
        out: dict[str, Any] = {}
        for name in requested:
            candidates = knowledge_items_in.get(name, []) or []
            if not candidates:
                continue
            out[name] = self._knowledge_guard.guard_interface(
                name, list(candidates), unified_decision
            ).to_dict()
        return out

    # ------------------------------------------------------------------ #
    # BaseAgent 契约                                                        #
    # ------------------------------------------------------------------ #

    async def invoke(self, context: AgentContext) -> AgentResult:
        """执行请求的分析接口并走完审核链。

        ``input_data`` 约定：
        - ``analyses``（可选，list[str]）：要执行的接口子集，
          缺省执行全部五个接口；
        - 其余字段（``vision_result`` / ``environment_result`` /
          ``design_candidate`` 等）骨架阶段仅透传声明，不消费。

        未知接口名 → ``success=False`` + ``ENGINEERING_UNKNOWN_INTERFACE``。
        """

        self._validate_input(context)

        requested_raw: Any = context.input_data.get("analyses")
        if requested_raw is None:
            requested: tuple[str, ...] = ANALYSIS_INTERFACES
        elif isinstance(requested_raw, (list, tuple)):
            requested = tuple(str(item) for item in requested_raw)
        else:
            requested = (str(requested_raw),)

        unknown: list[str] = [
            name for name in requested if name not in ANALYSIS_INTERFACES
        ]
        if unknown:
            return AgentResult(
                success=False,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "engineering_rejected",
                    "analyses": {},
                    "review_chain": [],
                    "pending_verification": True,
                    "gaps": [f"unknown_interface: {name}" for name in unknown],
                },
                evidence=(
                    self._emit_evidence(
                        source="invoke",
                        observed_at="phase2.1.5",
                        content={
                            "request_id": context.request_id,
                            "stage": "engineering_rejected",
                            "unknown_interfaces": unknown,
                        },
                    ),
                ),
                error={
                    "code": "ENGINEERING_UNKNOWN_INTERFACE",
                    "message": f"未知分析接口：{', '.join(unknown)}",
                },
            )

        dispatch: dict[str, Any] = {
            "wind_pressure": self.analyze_wind_pressure,
            "glass_safety": self.analyze_glass_safety,
            "profile": self.analyze_profile,
            "hardware": self.analyze_hardware,
            "installation_risk": self.analyze_installation_risk,
        }

        analyses: dict[str, dict[str, Any]] = {}
        review_chain: list[dict[str, Any]] = []
        for name in requested:
            output: dict[str, Any] = dispatch[name](context.input_data)
            record: dict[str, Any] = self._validator.validate(
                interface=name, payload=output
            )
            analyses[name] = output
            review_chain.append(record)

        # 任务(3.4.4)：知识消费接入——若 input_data 提供候选知识，计算前过 guard。
        knowledge_consumption: dict[str, Any] = self._consume_requested_knowledge(
            requested, context.input_data
        )

        gaps: list[str] = [
            f"{name}_analysis: {PENDING_VERIFICATION}" for name in requested
        ]

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "engineering_skeleton",
                "analyses": analyses,
                "review_chain": review_chain,
                "pending_verification": True,
                "gaps": gaps,
                "knowledge_consumption": knowledge_consumption,
            },
            evidence=(
                self._emit_evidence(
                    source="invoke",
                    observed_at="phase2.1.5",
                    content={
                        "request_id": context.request_id,
                        "stage": "engineering_skeleton",
                        "requested_analyses": list(requested),
                        "validator": type(self._validator).__name__,
                    },
                ),
            ),
        )


__all__ = [
    "ANALYSIS_INTERFACES",
    "ENGINEERING_AGENT_DESCRIPTION",
    "ENGINEERING_AGENT_NAME",
    "ENGINEERING_AGENT_VERSION",
    "EngineeringAgent",
    "build_skeleton_output",
]
