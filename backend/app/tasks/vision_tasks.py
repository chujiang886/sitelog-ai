"""Vision 异步任务（Phase 1 / T08 同步实现 + Phase 2 RQ 入口）。

Phase 1：``process_image(image_id)`` 同步执行，便于本地/CI 演练与单测覆盖；
Phase 2：替换为 ``@rq.job`` 装饰 + Redis broker，API 层只 ``enqueue`` 不执行。

调用方：
- ``backend/app/api/uploads.py::upload_image`` 上传后自动触发；
- ``backend/app/api/vision.py::analyze_image`` 用户主动重跑。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import sys
import uuid
from pathlib import Path
from typing import Any

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from app.db.models.image import (  # noqa: E402
    VISION_STATUS_DONE,
    VISION_STATUS_FAILED,
    VISION_STATUS_PROCESSING,
)
from app.db.session import SessionLocal  # noqa: E402


def _open_session(override: Session | None = None) -> Session:
    """为后台任务打开独立 Session。

    测试可通过 ``override`` 注入共享 Session；生产路径使用 ``SessionLocal``。
    """

    if override is not None:
        return override
    return SessionLocal()


def _run_agent_coroutine(coro: Any) -> Any:
    """在干净的独立事件循环中运行 Agent 协程，杜绝协程泄漏。

    编排层可能在「已有运行中的事件循环」上下文中被调用（如 Starlette
    TestClient 的 anyio portal、uvicorn 请求处理）。此时若用
    ``new_event_loop().run_until_complete`` 嵌套启动 loop，会抛
    ``Cannot run the event loop while another loop is running``，且传入的协程
    因从未被 await 而在 GC 时触发 ``coroutine was never awaited`` 告警。

    策略：
    - 无运行中的 loop：直接 ``asyncio.run``（标准做法，自动关闭 loop）；
    - 已有运行中的 loop：在独立线程中起新 loop 运行，避免嵌套。
    两条路径都保证传入协程被完整 await。
    """

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def process_image(*, image_id: uuid.UUID, db: Session | None = None) -> dict[str, Any]:
    """同步执行 Vision Agent analyze；写回 ``images.vision_status``。

    返回与 Vision Agent ``invoke`` 等价的 envelope dict（便于路由层透传）。
    测试可通过 ``db`` 注入共享 Session（避免 in-memory 多 engine 问题）。
    """

    session: Session = _open_session(db)
    try:
        from app.db.models.image import Image  # noqa: PLC0415 - 局部 import

        image: Image | None = session.get(Image, image_id)
        if image is None:
            return {
                "success": False,
                "error": {"code": "IMAGE_NOT_FOUND", "message": str(image_id)},
                "data": {},
            }

        image.vision_status = VISION_STATUS_PROCESSING
        session.commit()
        session.refresh(image)

        # 读取图片字节 → 调 Vision Agent
        from agents.vision.image_processor import process_image as img_process  # noqa: PLC0415
        from agents.vision.agent import VisionAgent  # noqa: PLC0415

        try:
            storage_path: Path = Path(image.storage_path)
            content: bytes = storage_path.read_bytes()
        except OSError as exc:
            image.vision_status = VISION_STATUS_FAILED
            session.commit()
            return {
                "success": False,
                "error": {
                    "code": "STORAGE_READ_FAILED",
                    "message": f"{type(exc).__name__}: {exc}",
                },
                "data": {"image_id": str(image.id)},
            }

        try:
            processed = img_process(
                content=content,
                filename=image.filename,
                mime_type=image.mime_type,
            )
        except Exception as exc:  # noqa: BLE001 - 校验失败兜底
            image.vision_status = VISION_STATUS_FAILED
            image.vision_result = {
                "error": f"{type(exc).__name__}: {exc}",
                "pending_verification": True,
            }
            session.commit()
            return {
                "success": False,
                "error": {"code": "IMAGE_INVALID", "message": str(exc)},
                "data": {"image_id": str(image.id)},
            }

        agent = VisionAgent()
        from agents.base import AgentContext  # noqa: PLC0415

        ctx = AgentContext(
            request_id=f"vision-{image.id}",
            input_data={
                "image_id": str(image.id),
                "image_b64": processed.base64,
                "mime_type": processed.mime_type,
            },
        )

        try:
            result = _run_agent_coroutine(agent.invoke(ctx))
            result_envelope: dict[str, Any] = result.to_envelope()
        except Exception as exc:  # noqa: BLE001 - 运行时失败兜底
            image.vision_status = VISION_STATUS_FAILED
            image.vision_result = {
                "error": f"{type(exc).__name__}: {exc}",
                "pending_verification": True,
            }
            session.commit()
            return {
                "success": False,
                "error": {"code": "VISION_FAILED", "message": str(exc)},
                "data": {"image_id": str(image.id)},
            }

        # 写回 DB
        if result_envelope.get("success"):
            image.vision_status = VISION_STATUS_DONE
        else:
            image.vision_status = VISION_STATUS_FAILED
        image.vision_result = {
            **(dict(result_envelope.get("data") or {})),
            "agent_error": dict(result_envelope["error"])
            if result_envelope.get("error")
            else None,
        }
        session.commit()
        session.refresh(image)
        return result_envelope
    finally:
        session.close()


__all__ = ["process_image"]