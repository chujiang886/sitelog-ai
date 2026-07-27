"""Environment Agent 实现（Phase 1 / T09 + Phase 2.2 / 2.2.1 数据接入）。

Phase 1 基础（保留）：
- 继承 ``BaseAgent``，name=environment；
- LLM 启用时构造结构化提示要求严格 JSON 输出；
- LLM 未启用 / Provider 抛错 / 响应非合法 JSON 时按"不编造"原则降级。

Phase 2.2 / 2.2.1 增强（ADR-2.2.1）：
- invoke 前置数据获取段：``agents/environment/providers/`` 抽象层
  （GeoProvider / WeatherProvider，配置驱动，默认 disabled → 零行为变化）；
- 字段级溯源 ``field_provenance``：measured（真实源）/ mock / inferred（LLM）
  / unavailable；
- **顶层 pending_verification 语义修正**：存在任一非 measured 关键字段
  （climate_zone / prevailing_wind / solar_exposure）即为 true——LLM 推理
  属 Level 0（inferred），永远保持 pending；只有真实数据源（real_data=True）
  命中的字段才允许 measured（Level 1）；
- 数据源失败/未配置 → 降级回 LLM 推理路径，只增强、绝不阻断（ADR-03）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent, Evidence
from agents.environment.providers.base import (
    GeoProvider,
    GeoResult,
    WeatherProvider,
    WindClimate,
)


ENVIRONMENT_AGENT_NAME: str = "environment"
ENVIRONMENT_AGENT_VERSION: str = "1.1.0-phase2.2.1"
ENVIRONMENT_AGENT_DESCRIPTION: str = (
    "Environment Agent：基于地址/坐标/视觉线索推理结构化环境事实"
    "（气候区、主导风向、日照、噪音、规范提示、地域材料偏好），"
    "2.2.1 起支持 Provider 抽象层接入真实地理/风况数据（默认 disabled）；"
    "非真实数据字段保持 pending_verification。"
)
_ENV_PROMPT_DIR: Path = Path(__file__).resolve().parent

# 关键字段：任一非 measured 即顶层 pending_verification=true（ADR-2.2.1 §7）。
KEY_FIELDS: tuple[str, ...] = ("climate_zone", "prevailing_wind", "solar_exposure")

# 构造注入哨兵：区分"未注入（走配置）"与"显式注入 None（禁用）"。
_UNSET: object = object()

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
    "5. 不输出结构安全或最终设计结论；\n"
    "6. 若用户消息中提供了标记为『实测数据』的字段值，必须原样采用，禁止改写或重新推理。"
)

USER_PROMPT_TEMPLATE: str = (
    "请基于以下上下文输出环境事实 JSON：\n"
    "- 地址：{address}\n"
    "- 坐标：{coordinates}\n"
    "- 区域提示：{region_hint}\n"
    "- 视觉线索：{vision_hint}\n"
)


class EnvironmentAgent(BaseAgent):
    """Environment context structuring Agent（Phase 1 真实实现 + 2.2.1 数据接入）。"""

    def __init__(
        self,
        *,
        geo_provider: GeoProvider | None | object = _UNSET,
        weather_provider: WeatherProvider | None | object = _UNSET,
    ) -> None:
        super().__init__(
            name=ENVIRONMENT_AGENT_NAME,
            description=ENVIRONMENT_AGENT_DESCRIPTION,
            version=ENVIRONMENT_AGENT_VERSION,
        )
        # 测试/上层可显式注入 Provider；未注入时按 config.yaml 构建（默认 disabled）。
        self._geo_provider: GeoProvider | None | object = geo_provider
        self._weather_provider: WeatherProvider | None | object = weather_provider

    @property
    def tools(self) -> Sequence[str]:
        """Declared tool identifiers (Phase 1 声明 + 2.2.1 Provider 抽象层)。"""

        return ("weather_mcp", "gis_mcp")  # 声明保留；真实接入走 providers/ 抽象层

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Environment Agent package."""

        return _ENV_PROMPT_DIR

    # ------------------------------------------------------------------ #
    # invoke 主流程                                                          #
    # ------------------------------------------------------------------ #

    async def invoke(self, context: AgentContext) -> AgentResult:
        """产出环境事实：Provider 真实数据优先，LLM 推理兜底（永远 pending）。

        ``input_data`` 推荐字段：
        - ``address``       (str)  用户填写的地址/小区名；
        - ``coordinates``   (dict) 可选，{"lat": float, "lng": float}；
        - ``vision_result`` (dict) 可选，来自 Vision Agent；
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

        evidence_items: list[Evidence] = [
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
        ]

        # ── 2.2.1 数据获取段（LLM 之前；失败绝不阻断，ADR-03）─────────── #
        geo_result, wind_result, provider_notes, provider_evidence = (
            await self._gather_provider_data(address=address, coordinates=coordinates)
        )
        evidence_items.extend(provider_evidence)

        # 真实地理编码命中且输入无坐标 → 补全坐标供 LLM/下游使用。
        if (
            not coordinates
            and geo_result is not None
            and geo_result.ok
            and geo_result.lat is not None
            and geo_result.lng is not None
        ):
            coordinates = {"lat": geo_result.lat, "lng": geo_result.lng}

        measured_facts: dict[str, Any] = self._collect_measured_facts(
            geo_result=geo_result, wind_result=wind_result
        )

        # ── LLM 推理段（Provider 未覆盖的字段继续走推理，保持 pending）── #
        parsed: dict[str, Any]
        pending_llm: bool = True
        provider_name: str = "pending_verification"

        try:
            parsed, provider_name, pending_llm = await self._call_llm(
                address=address,
                coordinates=coordinates,
                vision_result=vision_result,
                region_hint=region_hint,
                measured_facts=measured_facts,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底降级，不让路由层崩溃
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
                        *self._provider_gaps(geo_result, wind_result),
                        *provider_notes,
                        "environment_call: failed",
                    ],
                },
                evidence=tuple(evidence_items),
                error={
                    "code": "ENVIRONMENT_FAILED",
                    "message": f"{type(exc).__name__}: {exc}",
                },
            )

        # ── 合并输出：Provider 命中字段覆盖 LLM 值；字段级溯源 ─────────── #
        merged: dict[str, Any] = self._merge_fields(
            parsed=parsed, wind_result=wind_result
        )
        field_provenance: dict[str, str] = self._build_provenance(
            wind_result=wind_result,
            geo_result=geo_result,
            llm_succeeded=not pending_llm,
        )
        # 顶层语义（ADR-2.2.1 §7）：任一关键字段非 measured 即 pending=true。
        # LLM 推理属 Level 0（inferred），因此 LLM 成功不再豁免 pending。
        pending_top: bool = any(
            field_provenance.get(key) != "measured" for key in KEY_FIELDS
        )
        stage: str = "environment_placeholder" if pending_llm else "environment_analyzed"
        facts: dict[str, Any] = {} if pending_llm else self._build_facts(merged)
        if measured_facts and not pending_llm:
            facts.update(measured_facts)

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": stage,
                "address": address,
                "coordinates": coordinates,
                "vision_result": vision_result,
                "region_hint": region_hint,
                "climate_zone": merged.get("climate_zone", "unknown"),
                "prevailing_wind": merged.get("prevailing_wind", "不确定"),
                "solar_exposure": merged.get("solar_exposure", "不确定"),
                "noise_level_hint": merged.get("noise_level_hint", "不确定"),
                "regulatory_hints": list(merged.get("regulatory_hints") or []),
                "regional_material_preference": merged.get(
                    "regional_material_preference", "不确定"
                ),
                "summary": merged.get("summary", "unknown"),
                "provider": provider_name,
                "data_providers": {
                    "geo": geo_result.source if geo_result is not None else "disabled",
                    "weather": (
                        wind_result.source if wind_result is not None else "disabled"
                    ),
                },
                "field_provenance": field_provenance,
                "pending_verification": pending_top,
                "facts": facts,
                "gaps": [
                    *self._provider_gaps(geo_result, wind_result),
                    *provider_notes,
                ],
            },
            evidence=tuple(evidence_items),
        )

    # ------------------------------------------------------------------ #
    # 内部：2.2.1 Provider 数据获取（默认 disabled → 全部跳过）              #
    # ------------------------------------------------------------------ #

    def _resolve_providers(
        self,
    ) -> tuple[GeoProvider | None, WeatherProvider | None, list[str]]:
        """解析生效的 Provider：优先构造注入，否则按 config.yaml 构建。

        配置错误（未注册源名等）不抛出——降级为 None 并留痕（ADR-03：
        数据源问题绝不阻断 invoke）。
        """

        notes: list[str] = []
        geo: GeoProvider | None
        weather: WeatherProvider | None

        if self._geo_provider is not _UNSET or self._weather_provider is not _UNSET:
            geo = self._geo_provider if self._geo_provider is not _UNSET else None  # type: ignore[assignment]
            weather = (
                self._weather_provider if self._weather_provider is not _UNSET else None  # type: ignore[assignment]
            )
            return geo, weather, notes

        from agents.config_loader import load_environment_data_config  # noqa: PLC0415
        from agents.environment.providers.factory import (  # noqa: PLC0415
            build_geo_provider,
            build_weather_provider,
        )

        cfg: Mapping[str, Any] = load_environment_data_config()
        try:
            geo = build_geo_provider(cfg)
        except Exception as exc:  # noqa: BLE001 - 配置错误降级不阻断
            geo = None
            notes.append(f"geo_provider: config_error ({type(exc).__name__})")
        try:
            weather = build_weather_provider(cfg)
        except Exception as exc:  # noqa: BLE001 - 配置错误降级不阻断
            weather = None
            notes.append(f"weather_provider: config_error ({type(exc).__name__})")
        return geo, weather, notes

    async def _gather_provider_data(
        self,
        *,
        address: str,
        coordinates: Mapping[str, Any],
    ) -> tuple[GeoResult | None, WindClimate | None, list[str], list[Evidence]]:
        """按序调用 Geo/Weather Provider；任何失败均降级留痕，绝不抛出。"""

        geo_provider, weather_provider, notes = self._resolve_providers()
        evidence: list[Evidence] = []
        geo_result: GeoResult | None = None
        wind_result: WindClimate | None = None

        if geo_provider is not None and address:
            try:
                geo_result = await geo_provider.geocode(address)
            except Exception as exc:  # noqa: BLE001 - ADR-03 降级语义
                notes.append(f"geo_provider: fetch_failed ({type(exc).__name__})")
            else:
                evidence.append(self._provider_evidence("geo_provider", geo_result))

        lat: Any = coordinates.get("lat") if coordinates else None
        lng: Any = coordinates.get("lng") if coordinates else None
        if (lat is None or lng is None) and geo_result is not None and geo_result.ok:
            lat, lng = geo_result.lat, geo_result.lng

        if weather_provider is not None and lat is not None and lng is not None:
            try:
                wind_result = await weather_provider.wind_climate(
                    float(lat), float(lng)
                )
            except Exception as exc:  # noqa: BLE001 - ADR-03 降级语义
                notes.append(f"weather_provider: fetch_failed ({type(exc).__name__})")
            else:
                evidence.append(
                    self._provider_evidence("weather_provider", wind_result)
                )

        return geo_result, wind_result, notes, evidence

    def _provider_evidence(
        self, source_suffix: str, result: GeoResult | WindClimate
    ) -> Evidence:
        """把 Provider 结果转为溯源 evidence（source/fetched_at/raw_ref 全留痕）。"""

        confidence: str
        if not result.ok:
            confidence = "unavailable"
        elif result.real_data:
            confidence = "measured"
        else:
            confidence = "mock"
        content: dict[str, Any] = {
            "provider": result.source,
            "raw_ref": result.raw_ref,
            "real_data": result.real_data,
            "ok": result.ok,
        }
        if isinstance(result, WindClimate):
            content.update(
                {
                    "field": "prevailing_wind",
                    "value": result.prevailing_wind,
                    "avg_wind_speed_ms": result.avg_wind_speed_ms,
                    "stat_years": result.stat_years,
                }
            )
        else:
            content.update(
                {
                    "field": "geocode",
                    "province": result.province,
                    "city": result.city,
                    "district": result.district,
                }
            )
        if result.error:
            content["error"] = result.error
        return self._emit_evidence(
            source=source_suffix,
            confidence=confidence,
            observed_at=result.fetched_at,
            content=content,
        )

    @staticmethod
    def _collect_measured_facts(
        *,
        geo_result: GeoResult | None,
        wind_result: WindClimate | None,
    ) -> dict[str, Any]:
        """只收集真实源（real_data=True）命中的字段——mock 永远不进实测集。"""

        measured: dict[str, Any] = {}
        if (
            wind_result is not None
            and wind_result.ok
            and wind_result.real_data
            and wind_result.prevailing_wind
        ):
            measured["prevailing_wind"] = wind_result.prevailing_wind
        if geo_result is not None and geo_result.ok and geo_result.real_data:
            location: dict[str, Any] = {
                "province": geo_result.province,
                "city": geo_result.city,
                "district": geo_result.district,
            }
            measured["geocode"] = {k: v for k, v in location.items() if v}
        return measured

    @staticmethod
    def _merge_fields(
        *,
        parsed: Mapping[str, Any],
        wind_result: WindClimate | None,
    ) -> dict[str, Any]:
        """Provider 命中字段覆盖 LLM 推理值（mock 命中同样覆盖，值自带标记）。"""

        merged: dict[str, Any] = dict(parsed)
        if (
            wind_result is not None
            and wind_result.ok
            and wind_result.prevailing_wind
        ):
            merged["prevailing_wind"] = wind_result.prevailing_wind
        return merged

    @staticmethod
    def _build_provenance(
        *,
        wind_result: WindClimate | None,
        geo_result: GeoResult | None,
        llm_succeeded: bool,
    ) -> dict[str, str]:
        """字段级溯源（ADR-2.2.1 §7）：measured / mock / inferred / unavailable。"""

        llm_level: str = "inferred" if llm_succeeded else "unavailable"

        def _classify(result: GeoResult | WindClimate | None) -> str:
            if result is None or not result.ok:
                return llm_level
            return "measured" if result.real_data else "mock"

        return {
            "climate_zone": llm_level,          # 本 Sprint 无区划 Provider（ADR §5 静态表待签字）
            "prevailing_wind": _classify(wind_result),
            "solar_exposure": llm_level,        # Solar 本地算法挂起至 Step 2（ADR §6）
            "geocode": _classify(geo_result),
        }

    @staticmethod
    def _provider_gaps(
        geo_result: GeoResult | None,
        wind_result: WindClimate | None,
    ) -> list[str]:
        """真实源未命中的领域保持 pending gaps（measured 命中才移除）。"""

        gaps: list[str] = []
        if not (
            wind_result is not None and wind_result.ok and wind_result.real_data
        ):
            gaps.append("weather_data: pending_verification")
        if not (geo_result is not None and geo_result.ok and geo_result.real_data):
            gaps.append("gis_data: pending_verification")
        return gaps

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
        measured_facts: Mapping[str, Any] | None = None,
    ) -> tuple[dict[str, Any], str, bool]:
        """构造环境推理 LLM 请求，调用 ``DualTrackRouter``。

        返回 ``(parsed_dict, provider_name, llm_pending)``——``llm_pending``
        仅表示 LLM 推理是否成功产出（占位=True），**不再**决定顶层
        pending_verification（顶层语义由 field_provenance 计算，ADR §7）。
        """

        from agents.llm.router import ProviderRole, build_router_from_config  # noqa: PLC0415
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
        if measured_facts:
            user_content += (
                "\n实测数据（来自真实数据源，禁止改写，输出时原样采用）：\n"
                + json.dumps(dict(measured_facts), ensure_ascii=False)
                + "\n"
            )
        request = LLMRequest(
            messages=(
                LLMMessage(role=LLMRole.SYSTEM, content=SYSTEM_PROMPT),
                LLMMessage(role=LLMRole.USER, content=user_content),
            ),
            temperature=0.2,
            max_tokens=512,
        )

        router = build_router_from_config(llm_cfg, role=ProviderRole.TEXT)
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
        """把合并结果压成标准化的环境事实 dict（便于下游 Agent 消费）。"""

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
                "data_providers": {"geo": "disabled", "weather": "disabled"},
                "field_provenance": {
                    "climate_zone": "unavailable",
                    "prevailing_wind": "unavailable",
                    "solar_exposure": "unavailable",
                    "geocode": "unavailable",
                },
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
    "KEY_FIELDS",
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "ENVIRONMENT_AGENT_DESCRIPTION",
    "ENVIRONMENT_AGENT_NAME",
    "ENVIRONMENT_AGENT_VERSION",
    "EnvironmentAgent",
]
