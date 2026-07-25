"""Design Agent 实现（Phase 1 / T10）。

最小正确实现：
- 继承 ``BaseAgent``，name=design，version=1.0.0-phase1；
- ``invoke(input_data={vision_result, environment_result, consultation,
  address, region_hint})`` → 调用 ``DualTrackRouter``（按
  ``agents/config.yaml::llm.enabled`` 路由）；
- LLM 启用时：综合视觉 / 环境 / 需求三类信息，要求模型输出严格 JSON，
  含恰好 3 个设计候选（candidates），每个候选含开启方式 / 型材 / 玻璃 /
  尺寸建议 / 成本档位 / 优劣势 / 推荐理由；
- LLM 未启用 / 三类输入全缺 → 返回 ``pending_verification=True`` 占位
  envelope，candidates=[]，不杜撰设计；
- LLM 抛错 / 响应非合法 JSON / 解析后非 dict / candidates 非 3 项 →
  返回 success=False 失败 envelope，error.code="DESIGN_FAILED"（异常不冒泡）；
- 任何结构安全结论、规范数值、材料力学参数 Phase 1 仍不可得，必须
  pending_verification=True 并标注 gaps，绝不允许凭空编造。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent


DESIGN_AGENT_NAME: str = "design"
DESIGN_AGENT_VERSION: str = "1.0.0-phase1"
DESIGN_AGENT_DESCRIPTION: str = (
    "Design Agent：综合 Vision/Environment Agent 输出与咨询需求，"
    "组织为可审查、可追溯的设计候选；明确依据、假设与待人工/规则引擎复核项。"
)
_DESIGN_PROMPT_DIR: Path = Path(__file__).resolve().parent

# 系统提示词：固定文案，确保 prompt.md 留底、运行时不漂移。
SYSTEM_PROMPT: str = (
    "你是 BOIP Design Agent（建筑开口设计候选整理专家）。"
    "综合用户提供的视觉观察、环境事实与咨询需求，组织出可审查的设计候选。\n\n"
    "必须输出合法 JSON，顶层字段必填：\n"
    "- candidates（数组，**恰好 3 个**，按推荐度从高到低排序）：\n"
    "  每个候选包含：\n"
    "  - id（如 \"D1\" / \"D2\" / \"D3\"）\n"
    "  - title（方案名，如\"断桥铝平开窗方案\"）\n"
    "  - opening_type（开启方式：推拉窗 / 平开窗 / 折叠门 / 落地窗 / 上悬窗 等）\n"
    "  - frame_material（型材：断桥铝合金 / 普通铝合金 / 塑钢 / 木铝复合 等）\n"
    "  - glass_type（玻璃：中空玻璃 / 低辐射 Low-E / 夹胶玻璃 / 单片钢化 等）\n"
    "  - dimensions_hint（尺寸/分格建议，字符串）\n"
    "  - estimated_cost_tier（成本档位：经济 / 标准 / 高端）\n"
    "  - pros（优势列表）\n"
    "  - cons（劣势/注意列表）\n"
    "  - rationale（推荐理由，需结合环境/视觉/需求说明）\n\n"
    "约束：\n"
    "1. 你无法获取真实结构计算、行业规范数据库或材料力学参数，任何数值都不得编造；\n"
    "2. 仅基于已提供的视觉/环境/需求信息做常识性方案整理，缺失信息用 'unknown' 标注；\n"
    "3. 输出必须是合法 JSON，candidates 恰好 3 项、顺序即推荐度；\n"
    "4. 不得声称方案已通过结构安全或法定审查；\n"
    "5. 不杜撰产品品牌、型号、规范条文编号或力学参数。"
)

USER_PROMPT_TEMPLATE: str = (
    "请基于以下上下文输出设计候选 JSON（candidates 恰好 3 项）：\n"
    "- 地址：{address}\n"
    "- 区域提示：{region_hint}\n"
    "- 视觉观察（Vision Agent）：{vision_hint}\n"
    "- 环境事实（Environment Agent）：{environment_hint}\n"
    "- 咨询需求（NLU）：{consultation_hint}\n"
)


class DesignAgent(BaseAgent):
    """Design candidate structuring Agent (Phase 1 真实实现)。"""

    def __init__(self) -> None:
        super().__init__(
            name=DESIGN_AGENT_NAME,
            description=DESIGN_AGENT_DESCRIPTION,
            version=DESIGN_AGENT_VERSION,
        )

    @property
    def tools(self) -> Sequence[str]:
        """Declared tool identifiers (Phase 1 仍不真正连接，声明保留)。"""

        return ("knowledge_mcp", "rule_engine")

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Design Agent package."""

        return _DESIGN_PROMPT_DIR

    # ------------------------------------------------------------------ #
    # Phase 1 真实实现                                                       #
    # ------------------------------------------------------------------ #

    async def invoke(self, context: AgentContext) -> AgentResult:
        """根据 LLM 路由结果产出设计候选。

        ``input_data`` 推荐字段：
        - ``vision_result``     (dict) 可选，来自 Vision Agent（scene_type /
                                      orientation_hint / obstructions / quality）；
        - ``environment_result`` (dict) 可选，来自 Environment Agent（climate_zone /
                                      prevailing_wind / solar_exposure /
                                      regulatory_hints / summary）；
        - ``consultation``       (dict) 可选，来自 T06 NLU（opening_preference /
                                      budget_tier / style_preference / constraints）；
        - ``address``            (str)  可选，地址上下文；
        - ``region_hint``        (str)  可选，区域提示。
        """

        self._validate_input(context)
        vision_raw: Any = context.input_data.get("vision_result") or {}
        vision_result: dict[str, Any] = (
            dict(vision_raw) if isinstance(vision_raw, dict) else {}
        )
        env_raw: Any = context.input_data.get("environment_result") or {}
        environment_result: dict[str, Any] = (
            dict(env_raw) if isinstance(env_raw, dict) else {}
        )
        consult_raw: Any = context.input_data.get("consultation") or {}
        consultation: dict[str, Any] = (
            dict(consult_raw) if isinstance(consult_raw, dict) else {}
        )
        address: str = str(context.input_data.get("address", "") or "")
        region_hint: str = str(context.input_data.get("region_hint", "") or "")

        # 视觉 / 环境 / 需求三类输入全缺 → 直接兜底，不允许在无上下文时硬编造。
        if not vision_result and not environment_result and not consultation:
            return self._placeholder_unavailable(
                request_id=context.request_id,
                missing=[
                    "vision_result",
                    "environment_result",
                    "consultation",
                ],
            )

        assumptions: list[str] = self._build_assumptions(
            vision_result=vision_result,
            environment_result=environment_result,
            consultation=consultation,
            address=address,
            region_hint=region_hint,
        )
        evidence = (
            self._emit_evidence(
                source="invoke",
                content={
                    "request_id": context.request_id,
                    "has_vision": bool(vision_result),
                    "has_environment": bool(environment_result),
                    "has_consultation": bool(consultation),
                    "address": address,
                    "region_hint": region_hint,
                    "stage": "design_invoke",
                },
            ),
        )

        # 走 LLM 路由 —— 失败 / 关闭时按"不编造"原则降级。
        parsed: dict[str, Any]
        pending: bool = True
        provider_name: str = "pending_verification"
        error: dict[str, Any] | None = None

        try:
            parsed, provider_name, pending = await self._call_llm(
                vision_result=vision_result,
                environment_result=environment_result,
                consultation=consultation,
                address=address,
                region_hint=region_hint,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底降级，不让路由层崩溃
            error = {
                "code": "DESIGN_FAILED",
                "message": f"{type(exc).__name__}: {exc}",
            }
            return AgentResult(
                success=False,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "design_failed",
                    "provider": provider_name,
                    "candidates": [],
                    "assumptions": assumptions,
                    "pending_verification": True,
                    "review_required": ["design_rule_engine: pending_verification"],
                    "gaps": [
                        "design_llm: failed",
                        "design_rule_engine: pending_verification",
                    ],
                },
                evidence=evidence,
                error=error,
            )

        # 降级 / 占位路径（pending=True，通常 LLM 未启用）→ 不杜撰候选。
        if pending:
            return AgentResult(
                success=True,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "design_placeholder",
                    "provider": provider_name,
                    "candidates": [],
                    "assumptions": assumptions,
                    "pending_verification": True,
                    "review_required": ["design_rule_engine: pending_verification"],
                    "gaps": [
                        "design_llm: pending_verification",
                        "design_rule_engine: pending_verification",
                    ],
                },
                evidence=evidence,
            )

        # 真实 LLM 成功路径（pending=False）→ 恰好 3 个候选透传。
        candidates: list[dict[str, Any]] = [
            self._coerce_candidate(item, idx)
            for idx, item in enumerate(parsed.get("candidates") or [])
        ]
        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "design_proposed",
                "provider": provider_name,
                "candidates": candidates,
                "assumptions": assumptions,
                "pending_verification": False,
                "review_required": ["design_rule_engine: pending_verification"],
                "gaps": [],
            },
            evidence=evidence,
        )

    # ------------------------------------------------------------------ #
    # 内部：LLM 路由（按 llm.enabled 自动降级）                                #
    # ------------------------------------------------------------------ #

    async def _call_llm(
        self,
        *,
        vision_result: dict[str, Any],
        environment_result: dict[str, Any],
        consultation: dict[str, Any],
        address: str,
        region_hint: str,
    ) -> tuple[dict[str, Any], str, bool]:
        """构造设计综合 LLM 请求，调用 ``DualTrackRouter``。

        返回 ``(parsed_dict, provider_name, pending_verification)``。
        LLM 未启用 → 返回占位结构 ``("mock", True)``；
        LLM 启用但响应非合法 JSON / 解析后非 dict / candidates 非 3 项 →
        抛 ``ValueError``，由 ``invoke`` 兜底为 DESIGN_FAILED。
        """

        from agents.llm.router import build_router_from_config  # noqa: PLC0415
        from agents.llm.types import LLMMessage, LLMRequest, LLMRole  # noqa: PLC0415
        from agents.config_loader import load_llm_config  # noqa: PLC0415
        from agents.llm.jsonutil import extract_json  # noqa: PLC0415

        llm_cfg = load_llm_config()
        if not llm_cfg.get("enabled", False):
            return self._placeholder_payload("llm_disabled"), "mock", True

        vision_str: str = (
            json.dumps(vision_result, ensure_ascii=False) if vision_result else "无"
        )
        env_str: str = (
            json.dumps(environment_result, ensure_ascii=False)
            if environment_result
            else "无"
        )
        consult_str: str = (
            json.dumps(consultation, ensure_ascii=False) if consultation else "无"
        )
        user_content: str = USER_PROMPT_TEMPLATE.format(
            address=address or "未知",
            region_hint=region_hint or "未知",
            vision_hint=vision_str,
            environment_hint=env_str,
            consultation_hint=consult_str,
        )
        request = LLMRequest(
            messages=(
                LLMMessage(role=LLMRole.SYSTEM, content=SYSTEM_PROMPT),
                LLMMessage(role=LLMRole.USER, content=user_content),
            ),
            temperature=0.3,
            max_tokens=1024,
        )

        router = build_router_from_config(llm_cfg)
        try:
            response, _ = await router.route(request)
        finally:
            await router.aclose()

        # LLM 输出必须是合法 JSON；否则视为降级失败（抛错由 invoke 兜底）。
        try:
            parsed = extract_json(response.content)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid_json_response: {exc}") from exc

        if not isinstance(parsed, dict):
            raise ValueError("parsed_response_not_dict")

        candidates = parsed.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 3:
            raise ValueError(
                f"candidates_must_be_exactly_3: got "
                f"{len(candidates) if isinstance(candidates, list) else 'non-list'}"
            )

        return parsed, response.model or "unknown", False

    # ------------------------------------------------------------------ #
    # 内部：字段标准化 / 假设构建                                          #
    # ------------------------------------------------------------------ #

    def _coerce_candidate(self, raw: Any, index: int) -> dict[str, Any]:
        """把 LLM 返回的原始候选标准化为完整 dict（缺字段补默认，不杜撰）。"""

        src: dict[str, Any] = raw if isinstance(raw, dict) else {}
        candidate_id: str = str(src.get("id") or f"D{index + 1}")
        return {
            "id": candidate_id,
            "title": str(src.get("title") or "待确认方案"),
            "opening_type": str(src.get("opening_type") or "unknown"),
            "frame_material": str(src.get("frame_material") or "unknown"),
            "glass_type": str(src.get("glass_type") or "unknown"),
            "dimensions_hint": str(src.get("dimensions_hint") or "待确认"),
            "estimated_cost_tier": str(src.get("estimated_cost_tier") or "标准"),
            "pros": list(src.get("pros") or []),
            "cons": list(src.get("cons") or []),
            "rationale": str(src.get("rationale") or "待补充推荐理由。"),
        }

    def _build_assumptions(
        self,
        *,
        vision_result: dict[str, Any],
        environment_result: dict[str, Any],
        consultation: dict[str, Any],
        address: str,
        region_hint: str,
    ) -> list[str]:
        """基于输入构建人类可读的假设列表（一律标注待复核，不杜撰结论）。"""

        assumptions: list[str] = []
        if vision_result:
            scene: str = str(vision_result.get("scene_type", "unknown"))
            assumptions.append(
                f"视觉场景按 Vision Agent 输出（scene_type={scene}）作为开口形态依据。"
            )
        else:
            assumptions.append("未提供 Vision Agent 结果，开口形态未基于现场视觉证据。")
        if environment_result:
            climate: str = str(environment_result.get("climate_zone", "unknown"))
            assumptions.append(
                f"环境结论取自 Environment Agent（climate_zone={climate}），"
                f"未接入真实气象/地图数据。"
            )
        else:
            assumptions.append("未提供 Environment Agent 结果，环境适应性未经推理。")
        if consultation:
            budget: str = str(consultation.get("budget_tier", "unknown"))
            assumptions.append(
                f"需求取自 NLU 结构化输出（budget_tier={budget}），未做人工确认。"
            )
        else:
            assumptions.append("未提供咨询需求，成本与风格偏好按默认假设。")
        assumptions.append(
            "型材力学参数、玻璃规范数值与结构安全结论未经 rule_engine/knowledge_mcp "
            "校验，待人工复核。"
        )
        return assumptions

    def _placeholder_payload(self, reason: str) -> dict[str, Any]:
        """LLM 不可用 / 关闭时返回的最小骨架 schema。"""

        return {
            "candidates": [],
            "_pending_reason": reason,
        }

    def _placeholder_unavailable(
        self,
        *,
        request_id: str,
        missing: Sequence[str],
    ) -> AgentResult:
        """视觉/环境/需求三类输入全缺时的占位 envelope（不杜撰设计）。"""

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "design_placeholder",
                "provider": "mock",
                "candidates": [],
                "assumptions": [
                    "未提供任何视觉/环境/需求输入，无法形成设计假设。"
                ],
                "pending_verification": True,
                "review_required": ["design_rule_engine: pending_verification"],
                "gaps": [f"{item}: missing" for item in missing]
                + ["design_rule_engine: pending_verification"],
            },
            evidence=(
                self._emit_evidence(
                    source="invoke",
                    content={
                        "request_id": request_id,
                        "stage": "design_placeholder",
                        "missing": list(missing),
                    },
                ),
            ),
        )


__all__ = [
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "DESIGN_AGENT_NAME",
    "DESIGN_AGENT_VERSION",
    "DESIGN_AGENT_DESCRIPTION",
    "DesignAgent",
]
