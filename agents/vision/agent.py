"""Vision Agent 实现（Phase 1 / T08）。

最小正确实现：
- 继承 ``BaseAgent``，name=vision，version=1.0.0；
- ``invoke(input_data={"image_id", "image_b64", "mime_type"})`` → 调用
  ``DualTrackRouter``（按 ``agents/config.yaml::llm.enabled`` 路由）；
- LLM 启用时：构造结构化 system + user 提示，要求输出严格 JSON
  （scene_type / obstructions / orientation_hint / quality / recommendations）；
- LLM 未启用 / 鉴权失败 / Provider 抛错时：返回
  ``pending_verification=true`` 占位 envelope，不让路由层崩溃；
- 不修改设计文档的"不猜测"原则 —— system prompt 显式声明不得编造。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

from agents.base import AgentContext, AgentResult, BaseAgent
from agents.vision.image_processor import ProcessedImage


VISION_AGENT_NAME: str = "vision"
VISION_AGENT_VERSION: str = "1.0.0-phase1"
VISION_AGENT_DESCRIPTION: str = (
    "Vision Agent：分析建筑阳台/窗户照片，输出结构化场景字段。"
)

_VISION_PROMPT_DIR: Path = Path(__file__).resolve().parent

# 系统提示词：固定文案，确保 prompt.md 留底、运行时不漂移。
SYSTEM_PROMPT: str = (
    "你是 BOIP Vision Agent。分析建筑阳台照片，输出结构化字段：\n"
    "- scene_type（开放阳台 / 封闭阳台 / 落地窗 / 飘窗 / 未知）\n"
    "- obstructions（障碍物列表，如空调外机、晾衣架、护栏等）\n"
    "- orientation_hint（朝向线索：东南西北或不确定）\n"
    "- quality（清晰度评估：high / medium / low）\n"
    "- recommendations（视觉相关建议列表）\n\n"
    "约束：\n"
    "1. 不得编造不在图像中的信息（楼层、面积、材质等）；\n"
    "2. 输出必须是合法 JSON，所有字段必填；\n"
    "3. 不确定时使用 'unknown' / '不确定' / 空数组；\n"
    "4. 不输出结构安全或最终设计结论。"
)

USER_PROMPT_TEMPLATE: str = (
    "请分析这张建筑阳台/窗户照片并按 JSON schema 输出。"
)


class VisionAgent(BaseAgent):
    """Vision observation structuring Agent (Phase 1 真实实现)。"""

    def __init__(self) -> None:
        super().__init__(
            name=VISION_AGENT_NAME,
            description=VISION_AGENT_DESCRIPTION,
            version=VISION_AGENT_VERSION,
        )

    @property
    def tools(self) -> Sequence[str]:
        """Declared tool identifiers (Phase 1 真实声明 + 预留扩展)。"""

        return ("vision_model", "file_storage")

    def _default_prompt_dir(self) -> Path:
        """Resolve the prompt directory to the Vision Agent package."""

        return _VISION_PROMPT_DIR

    # ------------------------------------------------------------------ #
    # Phase 1 真实实现                                                       #
    # ------------------------------------------------------------------ #

    async def invoke(self, context: AgentContext) -> AgentResult:
        """根据 LLM 路由结果产出 Vision 观察。

        ``input_data`` 推荐字段：
        - ``image_id``  (str) 图片 UUID，便于回写；
        - ``image_b64`` (str) base64 编码后的图片字节；
        - ``mime_type`` (str) MIME（image/jpeg / image/png 等）；
        - ``request_id`` (str) 由 AgentContext 提供。
        """

        self._validate_input(context)
        image_id: str = str(context.input_data.get("image_id", "") or "")
        image_b64: str = str(context.input_data.get("image_b64", "") or "")
        mime_type: str = str(context.input_data.get("mime_type", "image/jpeg"))

        # 没有图就直接兜底 —— 不允许 Vision Agent 在无图时硬编造。
        if not image_b64:
            return self._placeholder_unavailable(
                request_id=context.request_id,
                image_id=image_id,
                reason="missing_image_b64",
            )

        evidence = (
            self._emit_evidence(
                source="invoke",
                content={
                    "request_id": context.request_id,
                    "image_id": image_id,
                    "mime_type": mime_type,
                    "stage": "vision_invoke",
                },
            ),
        )

        # 走 LLM 路由 —— 失败 / 关闭时返回 pending_verification 占位。
        parsed: dict[str, Any]
        pending: bool = True
        provider_name: str = "pending_verification"
        error: dict[str, Any] | None = None

        try:
            parsed, provider_name, pending = await self._call_llm(
                image_b64=image_b64,
                mime_type=mime_type,
            )
        except Exception as exc:  # noqa: BLE001 - 兜底降级
            error = {"code": "VISION_FAILED", "message": f"{type(exc).__name__}: {exc}"}
            return AgentResult(
                success=False,
                data={
                    "agent": self.name,
                    "version": self.version,
                    "stage": "vision_failed",
                    "image_id": image_id,
                    "provider": provider_name,
                    "pending_verification": True,
                    "gaps": [
                        "vision_model: pending_verification",
                        "vision_call: failed",
                    ],
                },
                evidence=evidence,
                error=error,
            )

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "vision_analyzed",
                "image_id": image_id,
                "provider": provider_name,
                "scene_type": parsed.get("scene_type", "unknown"),
                "obstructions": list(parsed.get("obstructions") or []),
                "orientation_hint": parsed.get("orientation_hint", "不确定"),
                "quality": parsed.get("quality", "low"),
                "recommendations": list(parsed.get("recommendations") or []),
                "pending_verification": pending,
            },
            evidence=evidence,
        )

    # ------------------------------------------------------------------ #
    # 内部：LLM 路由（按 llm.enabled 自动降级）                                #
    # ------------------------------------------------------------------ #

    async def _call_llm(
        self,
        *,
        image_b64: str,
        mime_type: str,
    ) -> tuple[dict[str, Any], str, bool]:
        """构造多模态 LLM 请求，调用 ``DualTrackRouter``。

        返回 ``(parsed_dict, provider_name, pending_verification)``。
        LLM 未启用 / Provider 抛错 / 响应非 JSON 时，统一返回占位结构。
        """

        from agents.llm.router import build_router_from_config  # noqa: PLC0415
        from agents.llm.types import LLMMessage, LLMRequest, LLMRole  # noqa: PLC0415
        from agents.config_loader import load_llm_config  # noqa: PLC0415
        from agents.llm.jsonutil import extract_json  # noqa: PLC0415
        from agents.llm.base import LLMRouterError  # noqa: PLC0415

        llm_cfg = load_llm_config()
        if not llm_cfg.get("enabled", False):
            return self._placeholder_payload("llm_disabled"), "mock", True

        # 多模态消息：把图片以 markdown data url 注入（OpenAI 兼容多模态约定）。
        user_content: str = (
            f"![upload](data:{mime_type};base64,{image_b64})\n\n"
            f"{USER_PROMPT_TEMPLATE}"
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
        except LLMRouterError:
            # 双轨均失败（LLM 不可用 / 鉴权失败 / Provider 抛错）→ 优雅降级为
            # pending_verification 占位，不让路由层崩溃（符合 agent docstring 契约）。
            return self._placeholder_payload("llm_unavailable"), "pending_verification", True
        finally:
            await router.aclose()

        parsed: dict[str, Any]
        try:
            parsed = extract_json(response.content)
        except (TypeError, ValueError):
            # LLM 输出不是合法 JSON —— 包一层 schema 但保留原始文本以便审计。
            parsed = self._placeholder_payload("invalid_json_response")
            parsed["raw_response"] = str(getattr(response, "content", ""))
            return parsed, response.model or "unknown", True

        # JSON 解析成功但未必符合 schema；统一做一次 coerce 让 pending_verification 生效。
        if not isinstance(parsed, dict):
            parsed = self._placeholder_payload("invalid_json_response")
            return parsed, response.model or "unknown", True

        return parsed, response.model or "unknown", False

    def _placeholder_payload(self, reason: str) -> dict[str, Any]:
        """LLM 不可用 / 失败时返回的最小骨架 schema。"""

        return {
            "scene_type": "unknown",
            "obstructions": [],
            "orientation_hint": "不确定",
            "quality": "low",
            "recommendations": [],
            "_pending_reason": reason,
        }

    def _placeholder_unavailable(
        self,
        *,
        request_id: str,
        image_id: str,
        reason: str,
    ) -> AgentResult:
        """无图 / LLM 关闭时的占位 envelope。"""

        return AgentResult(
            success=True,
            data={
                "agent": self.name,
                "version": self.version,
                "stage": "vision_placeholder",
                "image_id": image_id,
                "request_id": request_id,
                "scene_type": "unknown",
                "obstructions": [],
                "orientation_hint": "不确定",
                "quality": "low",
                "recommendations": [],
                "pending_verification": True,
                "gaps": [
                    f"vision_call: {reason}",
                    "vision_model: pending_verification",
                ],
            },
            evidence=(
                self._emit_evidence(
                    source="invoke",
                    content={
                        "request_id": request_id,
                        "image_id": image_id,
                        "stage": "vision_placeholder",
                        "reason": reason,
                    },
                ),
            ),
        )


def vision_result_from_image(processed: ProcessedImage) -> dict[str, Any]:
    """便捷 helper：把预处理结果压成 ``input_data`` 给 ``invoke``。"""

    return {
        "image_id": processed.sha256[:8],  # 占位 id；真上传时由 route 写入 UUID
        "image_b64": processed.base64,
        "mime_type": processed.mime_type,
    }


__all__ = [
    "SYSTEM_PROMPT",
    "USER_PROMPT_TEMPLATE",
    "VISION_AGENT_DESCRIPTION",
    "VISION_AGENT_NAME",
    "VISION_AGENT_VERSION",
    "VisionAgent",
    "vision_result_from_image",
]