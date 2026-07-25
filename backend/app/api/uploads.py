"""图片上传路由（Phase 1 / T08）。

提供 2 个端点，统一返回 ``{success, data}`` / ``{success: false, error}`` 信封：

- ``POST /api/uploads``  multipart/form-data 上传单张图片
  - 必传：``file``
  - 可选：``project_id``（UUID，挂到具体项目）
  - 返回 ``image_id`` / ``sha256`` / ``vision_status="Pending"``
- ``GET /api/uploads/{id}``  读取图片元数据 + Vision 结果

设计原则：
- 仅接收 ``image/jpeg | image/png | image/webp``，单文件 ≤ 10 MB；
- tenant 隔离通过 ``X-Tenant-Id`` 头强制；
- 落盘到本地 ``backend/storage/uploads/{tenant_id}/{sha256}.{ext}``（TD-015）；
- Vision 分析由 ``backend/app/tasks/vision_tasks.process_image`` 异步触发。
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile
from sqlalchemy.orm import Session

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.vision.image_processor import (  # noqa: E402
    ImageValidationError,
    process_image,
)
from app.core.storage import build_image_path  # noqa: E402
from app.db.models.image import (  # noqa: E402
    Image,
    VISION_STATUS_PENDING,
)
from app.db.models.project import Project  # noqa: E402
from app.db.session import get_db  # noqa: E402


router = APIRouter(prefix="/api/uploads", tags=["uploads"])


# --------------------------------------------------------------------------- #
# helpers                                                                      #
# --------------------------------------------------------------------------- #


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


def _resolve_user_id(x_user_id: str | None) -> uuid.UUID | None:
    """解析用户 ID：可选（前端可匿名上传待 Phase 2 实名接入）。"""

    if not x_user_id:
        return None
    try:
        return uuid.UUID(x_user_id)
    except (TypeError, ValueError):
        return None


def _image_to_dict(image: Image) -> dict[str, object]:
    """序列化 Image 行。"""

    return {
        "id": str(image.id),
        "tenant_id": str(image.tenant_id),
        "project_id": str(image.project_id) if image.project_id else None,
        "owner_id": str(image.owner_id) if image.owner_id else None,
        "filename": image.filename,
        "mime_type": image.mime_type,
        "size_bytes": image.size_bytes,
        "storage_path": image.storage_path,
        "sha256": image.sha256,
        "vision_status": image.vision_status,
        "vision_result": dict(image.vision_result or {}),
        "created_at": image.created_at.isoformat() if image.created_at else None,
    }


def _trigger_vision_task(image_id: uuid.UUID) -> None:
    """触发 Vision 异步任务（Phase 1 同步调用；Phase 2 切 RQ）。

    同步调用失败时不影响图片上传本身，仅记录到 ``pending_verification`` 标记。
    """

    try:
        from app.tasks.vision_tasks import process_image  # noqa: PLC0415
        process_image(image_id=image_id)
    except Exception as exc:  # noqa: BLE001 - 异步触发失败不影响上传主路径
        # 上传本身已成功；Vision 失败由后续 GET /analyze 重试。
        import logging  # noqa: PLC0415

        logging.getLogger("boip.uploads").warning(
            "vision task dispatch failed: %s: %s",
            type(exc).__name__,
            exc,
        )


# --------------------------------------------------------------------------- #
# routes                                                                       #
# --------------------------------------------------------------------------- #


@router.post("")
async def upload_image(
    file: Annotated[UploadFile, File(description="图片文件（jpg/jpeg/png/webp）")],
    project_id: Annotated[str | None, Form()] = None,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> dict[str, object]:
    """上传图片：本地落盘 + 写 images 表 + 触发 Vision 任务。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    owner_id: uuid.UUID | None = _resolve_user_id(x_user_id)

    content: bytes = await file.read()
    mime_type: str = (file.content_type or "").strip().lower() or "application/octet-stream"
    filename: str = file.filename or "upload.bin"

    # 1) 预处理（校验 + base64 + sha256）
    try:
        processed = process_image(
            content=content,
            filename=filename,
            mime_type=mime_type,
        )
    except ImageValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 2) 解析可选 project_id（必须存在 + 属于当前 tenant）
    project_uuid: uuid.UUID | None = None
    if project_id:
        try:
            project_uuid = uuid.UUID(project_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid project_id: {project_id}",
            ) from exc
        project: Project | None = (
            db.query(Project)
            .filter_by(id=project_uuid, tenant_id=tenant_id)
            .one_or_none()
        )
        if project is None:
            raise HTTPException(
                status_code=404,
                detail=f"Project not found: {project_uuid}",
            )

    # 3) 写本地存储
    storage_path: Path = build_image_path(
        tenant_id=str(tenant_id),
        sha256=processed.sha256,
        extension=processed.extension,
    )
    if not storage_path.exists():
        storage_path.write_bytes(processed.content)

    # 4) 写 DB（不重复 insert：sha256 + tenant_id 命中则复用）
    image: Image | None = (
        db.query(Image)
        .filter_by(tenant_id=tenant_id, sha256=processed.sha256)
        .one_or_none()
    )
    if image is None:
        image = Image(
            tenant_id=tenant_id,
            project_id=project_uuid,
            owner_id=owner_id,
            filename=processed.filename,
            mime_type=processed.mime_type,
            size_bytes=processed.size_bytes,
            storage_path=str(storage_path),
            sha256=processed.sha256,
            vision_status=VISION_STATUS_PENDING,
            vision_result=None,
        )
        db.add(image)
        db.commit()
        db.refresh(image)
        # 首次上传触发 Vision 任务；幂等：相同 sha256 不会重复触发。
        _trigger_vision_task(image.id)
    else:
        # 已存在：仅在显式 project_id 缺省时保留；显式传入则允许覆盖挂载。
        if project_uuid is not None and image.project_id != project_uuid:
            image.project_id = project_uuid
        db.commit()
        db.refresh(image)

    return {
        "success": True,
        "data": {
            "image_id": str(image.id),
            "sha256": image.sha256,
            "vision_status": image.vision_status,
            "storage_path": image.storage_path,
            "mime_type": image.mime_type,
            "size_bytes": image.size_bytes,
            "pending_verification": image.vision_status != "Done",
        },
    }


@router.get("/{image_id}")
async def get_image(
    image_id: str,
    db: Session = Depends(get_db),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> dict[str, object]:
    """读取图片元数据 + Vision 结果。"""

    tenant_id: uuid.UUID = _resolve_tenant_id(x_tenant_id)
    try:
        image_uuid: uuid.UUID = uuid.UUID(image_id)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid image_id: {image_id}",
        ) from exc

    image: Image | None = (
        db.query(Image)
        .filter_by(id=image_uuid, tenant_id=tenant_id)
        .one_or_none()
    )
    if image is None:
        raise HTTPException(
            status_code=404,
            detail=f"Image not found: {image_uuid}",
        )

    return {
        "success": True,
        "data": _image_to_dict(image),
    }


__all__ = ["router"]