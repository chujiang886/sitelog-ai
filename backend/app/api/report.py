"""PDF 方案书生成端点（T14 / Phase 2）。

提供 1 个端点，统一返回 ``{success, data}`` 信封（PDF 场景用二进制
``Response`` 落地，错误走项目既有的 error envelope）：

- ``POST /api/report/generate`` 根据前端提交的三 Agent 输出聚合 dossier，
  调用 ``agents.report.generator.generate_project_report`` 生成中文方案书
  PDF 字节流并返回。

入参形态（与 ``generate_project_report(dossier)`` 一致）：
``{"project": {...}, "vision": <dict|None>, "environment": <dict|None>,
"design": <dict|None>}``。

健壮性：dossier 字段缺失 / 为 None 时 generator 自身已能兜底（不抛），
端点再包一层 try 捕获意外异常，按项目 error envelope 风格返回 500。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

# 让 uvicorn 从 backend/ 运行时也能 ``import agents``
_REPO_ROOT: Path = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from agents.report.generator import generate_project_report  # noqa: E402


router = APIRouter(prefix="/api/report", tags=["report"])


class ReportRequest(BaseModel):
    """``/api/report/generate`` 请求体，与 ``generate_project_report`` 入参一致。"""

    project: dict[str, Any] = Field(
        default_factory=dict,
        description="可选元信息，如 address / request_id",
    )
    vision: Optional[dict[str, Any]] = Field(
        default=None,
        description="Vision Agent 的 data dict 或 None",
    )
    environment: Optional[dict[str, Any]] = Field(
        default=None,
        description="Environment Agent 的 data dict 或 None",
    )
    design: Optional[dict[str, Any]] = Field(
        default=None,
        description="Design Agent 的 data dict 或 None",
    )


@router.post("/generate")
async def generate_report(body: ReportRequest) -> Response:
    """聚合三 Agent 输出，生成并返回方案书 PDF 字节流。

    返回 ``application/pdf`` 二进制流；dossier 任意段为 None / 字段缺失时
    generator 会渲染占位章节，不抛异常。仅当发生未预期异常时回落到 500。
    """

    dossier: dict[str, Any] = {
        "project": body.project or {},
        "vision": body.vision,
        "environment": body.environment,
        "design": body.design,
    }

    try:
        pdf_bytes: bytes = generate_project_report(dossier)
    except Exception as exc:  # noqa: BLE001 - 兜底降级，避免 PDF 生成崩溃透传
        raise HTTPException(
            status_code=500,
            detail=f"report_generation_failed: {type(exc).__name__}: {exc}",
        ) from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=boip_proposal.pdf"},
    )


__all__ = ["ReportRequest", "router"]
