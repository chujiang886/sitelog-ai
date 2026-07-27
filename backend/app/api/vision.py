"""Vision API 路由（Phase 1 / T08）。

提供 1 个端点，统一返回 ``{success, data}`` 信封：

- ``POST /api/vision/analyze``  触发 Vision Agent 分析指定图片
  - body: ``{"image_id": "<UUID>"}``
  - 返回 ``image_id`` / ``vision_result`` / ``vision_status``

调用流程：
1. 根据 ``X-Tenant-Id`` 头定位 tenant；
2. 校验图片归属；
3. 调 ``backend.app.tasks.vision_tasks.process_image``（Phase 1 同步实现）；
4. 回写 ``images.vision_status`` / ``vision_result``。

Phase 2.1.4：DB 会话切换为 ``async_get_db``（AsyncSession）；``process_image`` 为同步阻塞
调用，经 ``asyncio.to_thread`` 卸载到线程池，避免阻塞事件循环（不修改其内部业务逻辑）。
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from app.db.models.image import Image  # noqa: E402
from app.db.session import async_get_db  # noqa: E402


router = APIRouter(prefix="/api/vision", tags=["vision"])


class AnalyzeBody(BaseModel):
    """analyze 请求体。"""

    image_id: str


def _resolve_tenant_id(x_tenant_id: str | None) -> uuid.UUID:
    """解析租户 ID：要求 ``X-Tenant-Id`` 头存在且为合法 UUID。"""

    if not x_tenant_id:
        raise HTTPException(
            status_code=400,
            detail="Missing X-Tenant-Id header",
        )
    try:
        return uuid.UUID(x_tenant_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid X-Tenant-Id header: {x_tenant_id}",
        ) from exc


@router.post("/analyze")
async def analyze_image(
    body: AnalyzeBody,
    db: AsyncSession = Depends(async_get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, object]:
    """触发 Vision Agent 分析，返回结构化结果。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    try:
        image_uuid: uuid.UUID = uuid.UUID(body.image_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image_id: {body.image_id}",
        ) from exc

    image: Image | None = (
        await db.scalars(
            select(Image).filter_by(id=image_uuid, tenant_id=tenant_id)
        )
    ).one_or_none()
    if image is None:
        raise HTTPException(
            status_code=404,
            detail=f"Image not found: {image_uuid}",
        )

    # 触发 Vision 处理（Phase 1 同步实现）。
    # 通过 asyncio.to_thread 卸载阻塞调用，避免阻塞事件循环（2.1.4）。
    from app.tasks.vision_tasks import process_image  # noqa: PLC0415

    result_envelope: dict[str, object] = await asyncio.to_thread(
        process_image, image_id=image.id
    )

    # 任务在独立线程 + 独立连接中已 commit；当前 async 会话可能持有旧事务快照，
    # 且 identity-map 缓存了原始 Pending 实例。结束当前事务快照后 refresh，
    # 确保读到其他线程提交后的最新 vision_status / vision_result。
    await db.rollback()
    await db.refresh(image)

    return {
        "success": True,
        "data": {
            "image_id": str(image.id),
            "vision_status": image.vision_status,
            "vision_result": dict(image.vision_result or {}),
            "agent_envelope": result_envelope,
            "pending_verification": image.vision_status != "Done",
        },
    }


__all__ = ["router"]
