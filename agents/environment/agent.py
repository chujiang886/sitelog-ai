"""Environment Agent 实现（Phase 1 / T09）。

最小正确实现：
- 继承 ``BaseAgent``，name=environment，version=1.0.0；
- ``invoke(input_data={address, coordinates, vision_result, region_hint})`` → 调用
  ``DualTrackRouter``（按 ``agents/config.yaml::llm.enabled`` 路由）；
- LLM 启用时：构造结构化 system + user 提示，要求输出严格 JSON
  （climate_zone / prevailing_wind / solar_exposure / noise_level_hint /
   regulatory_hints / regional_material_preference / summary）；
- LLM 未启用 / Provider 抛错 / 响应非合法 JSON 时：按"不编造"原则降级，
  不让路由层崩溃；
- 真实外部数据（天气 / 地图）Phase 1 仍不可得，相关字段保持
  ``pending_verification=true`` 并标注 gaps，绝不允许凭空编造。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent


ENVIRONMENT_AGENT_NAME: str = "environment"
ENVIRONMENT_AGENT_VERSION: str = "1.0.0-phase1"
ENVIRONMENT_AGENT_DESCRIPTION: str = (
    "Environment Agent：基于地址/坐标/视觉线索推理结构化环境事实"
    "（气候区、主导风向、日照、噪音、规范提示、地域材料偏好），"
    "Phase 1 仍不连接真实天气/地图 MCP，相关数值保持 pending_verification。"
)
_ENV_PROMPT_DIR: Path = Path(__file__).resolve().parent

# 系统提示词：固定文案，确保 prompt.md 留底、运行时不漂移。
SYSTEM_PROMPT: str = (
    "你是 BOIP Environment Agent（建筑环境分析专家）。"
    "根据用户提供的地址、坐标与视觉线索，推理并输出结构化环境事实。\n\n"
    "必须输出合法 JSON，字段全部必填（不确定使用 'unknown' / '不确定' / 空数组）：\n"
    "- climate_zone（气候区，如\"夏热冬暖地区\"）\n"
    "- prevailing_wind（主导风向，如\"东南\"）\n"
    "- solar_exposure（日照/西晒评估，如\"西晒明显\"）\n"
    "- noise_level_hint（临街噪音线索，如\"中\"）\n"
    "- regulatory_hints（规范提示列表，如[\"阳台封装需符合地方管理条例\"]）\n"
    "- regional_material_preference（地域材料偏好，如\"断桥铝为主\"）\n"
    "- summary（一句话环境结论）\n\n"
    "约束：\n"
    "1. 你无法获取真实气象、地图或行业数据库，任何数值都不得编造；\n"
    "2. 仅基于地址、坐标、区域提示与视觉线索做常识性推理；\n"
    "3. 输出必须是合法 JSON，所有字段必填；\n"
    "4. 不确定时使用 'unknown' / '不确定' / 空数组；\n"
    "5. 不输出结构安全或最终设计结论。"
)

USER_PROMPT_TEMPLATE: str = (
    "请基于以下上下文输出环境事实 JSON：\n"
    "- 地址：{address}\n"
    "- 坐标：{coordinates}\n"
    "- 区域提示：{region_hint}\n"
    "- 视觉线索：{vision_hint}\n"
)


class EnvironmentAgent(BaseAgent):
    """Environment context structuring Agent (Phase 1 真实实现)。"""

    def __init__(self) -> None:
        super().__init__(
            name=ENVIRONMENT_AGENT_NAME,
            description=ENVIRONMENT_AGENT_DESCRIPTION,
            version=ENVIRONMENT_AGENT_VERSION,
        )

    @property
    def tools(self) -> Sequence[str]:
        """Declared tool identifiers (Phase 1 真实声明 + 预留扩展)。"""

        return ("weather_mcp", "gis_mcp")  # Phase 1 仅声明，不真正连接外部 MCP

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Environment Agent package."""

        return _ENV_PROMPT_DIR

    # ------------------------------------------------------------------ #
    # Phase 1 真实实现                                                       #
    # ------------------------------------------------------------------ #

    async def invoke(self, context: AgentContext) -> AgentResult:
        """根据 LLM 路由结果产出环境事实。

        ``input_data`` 推荐字段：
        - ``address``       (str)  用户填写的地址/小区名；
        - ``coordinates``   (dict) 可选，{"lat": float, "lng": float}；
        - ``vision_result`` (dict) 可选，来自 Vision Agent 的 scene_type /
                                   orientation_hint / obstructions 等；
        - ``region_hint``   (str)  可选，如"华南/汕头"。
        """

        self._validate_input(context)
        address: str = str(context.input_data.get("address", "") or "")
        coordinates_raw: Any = context.input_data.get("coordinates") or {}
        coordinates: dict[str, Any] = (
            dict(coordinates_raw) if isinstance(coordinates_raw, dict) else {}
        )
        vision_raw: Any = context.input_data.get("vision_result") or {}
        vision_result: dict[str, Any] = (
            dict(vision_raw) if isinstance(vision_raw, dict) else {}
        )
        region_hint: str = str(context.input_data.get("region_hint", "") or "")

        # 无地址、无坐标、无视觉线索 → 直接兜底，不允许在无上下文时硬编造。
        if not address and not coordinates and not vision_result:
            return self._placeholder_unavailable(
                request_id=context.request_id,
                reason="missing_address_and_context",
            )

        evidence = (
            self._emit_evidence(
                source="invoke",
                content={
                    "request_id": context.request_id,
                    "address": address,
                    "has_coordinates": bool(coordinates),
                    "has_vision": bool(vision_result),
                    "region_hint": region_hint,
                    "stage": "environment_invoke",
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
                address=address,
                coordinates=coordinates,
                vision_result=vision_result,
                region_hint=region_hint,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底降级，不让路由层崩溃
            error = {
                "code": "ENVIRONMENT_FAILED",
                "message": f"{type(exc).__name__}: {exc}",
            }
            return AgentResult(
                success=False,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "environment_failed",
                    "address": address,
                    "coordinates": coordinates,
                    "provider": provider_name,
                    "pending_verification": True,
                    "gaps": [
                        "weather_data: pending_verification",
                        "gis_data: pending_verification",
                        "environment_call: failed",
                    ],
                },
                evidence=evidence,
                error=error,
            )

        # 降级 / 占位路径（pending=True）→ facts 留空并标注 gaps。
        if pending:
            return AgentResult(
                success=True,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "environment_placeholder",
                    "address": address,
                    "coordinates": coordinates,
                    "climate_zone": parsed.get("climate_zone", "unknown"),
                    "prevailing_wind": parsed.get("prevailing_wind", "不确定"),
                    "solar_exposure": parsed.get("solar_exposure", "不确定"),
                    "noise_level_hint": parsed.get("noise_level_hint", "不确定"),
                    "regulatory_hints": list(parsed.get("regulatory_hints") or []),
                    "regional_material_preference": parsed.get(
                        "regional_material_preference", "不确定"
                    ),
                    "summary": parsed.get("summary", "unknown"),
                    "provider": provider_name,
                    "pending_verification": True,
                    "facts": {},  # 降级路径：事实为空，待真实 MCP 接入后填充
                    "gaps": [
                        "weather_data: pending_verification",
                        "gis_data: pending_verification",
                    ],
                },
                evidence=evidence,
            )

        # 真实 LLM 成功路径（pending=False）→ 字段透传，facts 填充。
        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "environment_analyzed",
                "address": address,
                "coordinates": coordinates,
                "vision_result": vision_result,
                "region_hint": region_hint,
                "climate_zone": parsed.get("climate_zone", "unknown"),
                "prevailing_wind": parsed.get("prevailing_wind", "不确定"),
                "solar_exposure": parsed.get("solar_exposure", "不确定"),
                "noise_level_hint": parsed.get("noise_level_hint", "不确定"),
                "regulatory_hints": list(parsed.get("regulatory_hints") or []),
                "regional_material_preference": parsed.get(
                    "regional_material_preference", "不确定"
                ),
                "summary": parsed.get("summary", "unknown"),
                "provider": provider_name,
                "pending_verification": False,
                "facts": self._build_facts(parsed),
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
        address: str,
        coordinates: dict[str, Any],
        vision_result: dict[str, Any],
        region_hint: str,
    ) -> tuple[dict[str, Any], str, bool]:
        """构造环境推理 LLM 请求，调用 ``DualTrackRouter``。

        返回 ``(parsed_dict, provider_name, pending_verification)``。
        LLM 未启用 / Provider 抛错 / 响应非 JSON / 解析后非 dict 时，
        统一返回占位结构或抛错，由 ``invoke`` 兜底降级。
        """

        from agents.llm.router import build_router_from_config  # noqa: PLC0415
        from agents.llm.types import LLMMessage, LLMRequest, LLMRole  # noqa: PLC0415
        from agents.config_loader import load_llm_config  # noqa: PLC0415
        from agents.llm.jsonutil import extract_json  # noqa: PLC0415

        llm_cfg = load_llm_config()
        if not llm_cfg.get("enabled", False):
            return self._placeholder_payload("llm_disabled"), "mock", True

        coordinates_str: str = (
            json.dumps(coordinates, ensure_ascii=False) if coordinates else "未知"
        )
        region_str: str = region_hint or "未知"
        vision_str: str = (
            json.dumps(vision_result, ensure_ascii=False) if vision_result else "无"
        )
        user_content: str = USER_PROMPT_TEMPLATE.format(
            address=address or "未知",
            coordinates=coordinates_str,
            region_hint=region_str,
            vision_hint=vision_str,
        )
        request = LLMRequest(
            messages=(
                LLMMessage(role=LLMRole.SYSTEM, content=SYSTEM_PROMPT),
                LLMMessage(role=LLMRole.USER, content=user_content),
            ),
            temperature=0.2,
            max_tokens=512,
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

        return parsed, response.model or "unknown", False

    def _build_facts(self, parsed: Mapping[str, Any]) -> dict[str, Any]:
        """把 LLM 解析结果压成标准化的环境事实 dict（便于下游 Agent 消费）。"""

        src: Mapping[str, Any] = parsed if isinstance(parsed, Mapping) else {}
        return {
            "climate_zone": src.get("climate_zone", "unknown"),
            "prevailing_wind": src.get("prevailing_wind", "不确定"),
            "solar_exposure": src.get("solar_exposure", "不确定"),
            "noise_level_hint": src.get("noise_level_hint", "不确定"),
            "regulatory_hints": list(src.get("regulatory_hints") or []),
            "regional_material_preference": src.get(
                "regional_material_preference", "不确定"
            ),
            "summary": src.get("summary", "unknown"),
        }

    def _placeholder_payload(self, reason: str) -> dict[str, Any]:
        """LLM 不可用 / 关闭时返回的最小骨架 schema。"""

        return {
            "climate_zone": "unknown",
            "prevailing_wind": "不确定",
            "solar_exposure": "不确定",
            "noise_level_hint": "不确定",
            "regulatory_hints": [],
            "regional_material_preference": "不确定",
            "summary": "unknown",
            "_pending_reason": reason,
        }

    def _placeholder_unavailable(
        self,
        *,
        request_id: str,
        reason: str,
    ) -> AgentResult:
        """无地址 / 无坐标 / 无视觉线索时的占位 envelope（不杜撰结果）。"""

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "environment_placeholder",
                "address": "",
                "coordinates": {},
                "climate_zone": "unknown",
                "prevailing_wind": "不确定",
                "solar_exposure": "不确定",
                "noise_level_hint": "不确定",
                "regulatory_hints": [],
                "regional_material_preference": "不确定",
                "summary": "unknown",
                "provider": "mock",
                "pending_verification": True,
                "facts": {},  # 无上下文：事实为空
                "gaps": [
                    "weather_data: pending_verification",
                    "gis_data: pending_verification",
                    f"environment_call: {reason}",
                ],
            },
            evidence=(
                self._emit_evidence(
                    source="invoke",
                    content={
                        "request_id": request_id,
                        "stage": "environment_placeholder",
                        "reason": reason,
                    },
                ),
            ),
        )


__all__ = [
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "ENVIRONMENT_AGENT_DESCRIPTION",
    "ENVIRONMENT_AGENT_NAME",
    "ENVIRONMENT_AGENT_VERSION",
    "EnvironmentAgent",
]
