"""三 Agent 分析链路端点（T14 / Phase 2）。

提供 1 个端点，统一返回 ``{success, data}`` 信封：

- ``POST /api/analysis/run`` 依次调用 Vision → Environment → Design 三个
  Agent，把结果聚合为
  ``{"vision": <data>, "environment": <data>, "design": <data>,
  "pending_verification": <bool>, "gaps": [...]}``。

设计要点：
- 直接 ``await`` 三个 Agent 的 ``invoke(AgentContext(...))``，复用项目既有
  ``agents/vision|environment|design/agent.py`` 实现（不重写 orchestrator）；
- 端点本身是 ``async def``，在既有运行中的事件循环上 ``await`` 协程，不会
  嵌套 loop，因此不会出现 ``coroutine was never awaited`` 告警；
- 无真实 LLM key 时三 Agent 自动走 pending_verification 占位（Agent 内部已
  处理），端点正常返回占位聚合 JSON —— 这是验证链路通的关键；
- 任一 Agent ``invoke`` 抛错也不影响整体聚合，错误被收敛进该段的
  pending_verification / gaps，保证链路「不崩」。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Mapping, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.base import AgentContext  # noqa: E402
from agents.design.agent import DesignAgent  # noqa: E402
from agents.environment.agent import EnvironmentAgent  # noqa: E402
from agents.vision.agent import VisionAgent  # noqa: E402
from app.core.security import CurrentUser, require_permission  # noqa: E402


router = APIRouter(prefix="/api/analysis", tags=["analysis"])


class AnalysisRequest(BaseModel):
    """``/api/analysis/run`` 请求体（灵活兼容 NLU / consult 输出形态）。"""

    image_id: Optional[str] = Field(default=None, description="可选图片 UUID")
    address: Optional[str] = Field(default=None, description="用户填写的地址")
    coordinates: Optional[dict[str, Any]] = Field(
        default=None, description="可选坐标 {lat, lng}"
    )
    consultation: Optional[dict[str, Any]] = Field(
        default=None, description="可选 NLU 结构化咨询需求"
    )
    vision_result: Optional[dict[str, Any]] = Field(
        default=None, description="可选预置 Vision 结果（提供则跳过 Vision Agent）"
    )
    region_hint: Optional[str] = Field(default=None, description="可选区域提示")


def _safe_dict(value: Any) -> dict[str, Any]:
    """把 Agent 输出安全转成普通 dict（None / 非 Mapping → 空 dict）。"""

    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return {}


async def _invoke_agent(agent: Any, ctx: AgentContext) -> dict[str, Any]:
    """``await`` 单个 Agent；任何异常都收敛为 pending_verification 占位 dict。

    保证单个 Agent 失败不会中断整条分析链路，调用方始终拿到可序列化的 dict。
    """

    try:
        result = await agent.invoke(ctx)
        data: dict[str, Any] = _safe_dict(getattr(result, "data", None))
    except Exception as exc:  # noqa: BLE001 - 单 Agent 失败兜底
        data = {
            "agent": getattr(agent, "name", "unknown"),
            "success": False,
            "pending_verification": True,
            "error": f"{type(exc).__name__}: {exc}",
            "gaps": ["agent_invoke: failed"],
        }
    return data


@router.post("/run")
async def run_analysis(
    body: AnalysisRequest,
    current_user: CurrentUser = Depends(require_permission("analysis:create")),
) -> dict[str, Any]:
    """串联 Vision → Environment → Design，返回聚合分析结果（需 analysis:create）。"""

    request_id: str = str(uuid.uuid4())
    vision_agent = VisionAgent()
    env_agent = EnvironmentAgent()
    design_agent = DesignAgent()

    # 1) Vision：若前端已预置结果则直接采用，否则跑 Vision Agent（无图走占位）。
    if body.vision_result is not None:
        vision_data: dict[str, Any] = _safe_dict(body.vision_result)
    else:
        vision_ctx = AgentContext(
            request_id=f"{request_id}-vision",
            input_data={
                "image_id": body.image_id or "",
                "image_b64": "",  # 分析链路无原始图，Vision 内部走占位
                "mime_type": "image/jpeg",
            },
        )
        vision_data = await _invoke_agent(vision_agent, vision_ctx)

    # 2) Environment：消费 address / coordinates / vision 结果 / region_hint。
    env_ctx = AgentContext(
        request_id=f"{request_id}-environment",
        input_data={
            "address": body.address or "",
            "coordinates": body.coordinates or {},
            "vision_result": vision_data,
            "region_hint": body.region_hint or "",
        },
    )
    env_data: dict[str, Any] = await _invoke_agent(env_agent, env_ctx)

    # 3) Design：综合 Vision / Environment / 咨询需求。
    design_ctx = AgentContext(
        request_id=f"{request_id}-design",
        input_data={
            "vision_result": vision_data,
            "environment_result": env_data,
            "consultation": body.consultation or {},
            "address": body.address or "",
            "region_hint": body.region_hint or "",
        },
    )
    design_data: dict[str, Any] = await _invoke_agent(design_agent, design_ctx)

    # 聚合：任一 Agent pending_verification 即整体待核实；收集各段 gaps。
    gaps: list[str] = []
    for seg in (vision_data, env_data, design_data):
        for gap in seg.get("gaps", []) or []:
            if gap not in gaps:
                gaps.append(str(gap))
    pending: bool = bool(
        vision_data.get("pending_verification", True)
        or env_data.get("pending_verification", True)
        or design_data.get("pending_verification", True)
    )

    return {
        "success": True,
        "data": {
            "vision": vision_data,
            "environment": env_data,
            "design": design_data,
            "pending_verification": pending,
            "gaps": gaps,
        },
    }


__all__ = ["AnalysisRequest", "router"]
