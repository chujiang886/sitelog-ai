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
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent
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
        """风压分析接口（骨架）：不产出任何风压数值。"""

        del context_data  # 骨架阶段不消费输入，仅锁定签名
        return build_skeleton_output()

    def analyze_glass_safety(
        self, context_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """玻璃安全接口（骨架）：不产出任何玻璃配置结论。"""

        del context_data
        return build_skeleton_output()

    def analyze_profile(self, context_data: Mapping[str, Any]) -> dict[str, Any]:
        """型材分析接口（骨架）：不产出任何型材选型结论。"""

        del context_data
        return build_skeleton_output()

    def analyze_hardware(self, context_data: Mapping[str, Any]) -> dict[str, Any]:
        """五金分析接口（骨架）：不产出任何五金选型结论。"""

        del context_data
        return build_skeleton_output()

    def analyze_installation_risk(
        self, context_data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """安装风险接口（骨架）：不产出任何风险等级结论。"""

        del context_data
        return build_skeleton_output()

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
