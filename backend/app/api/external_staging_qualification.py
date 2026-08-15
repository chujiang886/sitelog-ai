"""Backend FastAPI 路由：外部预生产环境资格验证 API（Phase 3.9.10 Task 25）。

只读为主 API（fail-closed，红线）：

- GET /external-staging/qualification/resources     8 资源登记
- GET /external-staging/qualification/status        状态摘要
- GET /external-staging/qualification/connectivity  连接性
- GET /external-staging/qualification/isolation     跨环境隔离
- GET /external-staging/qualification/runtime-health 运行时健康
- GET /external-staging/qualification/evidence      证据链
- GET /external-staging/qualification/gate          资格闸门
- GET /external-staging/qualification/package       机器可读资格包

红线：
- **禁止**任何 Production 端点 / 部署 / 回滚 / 写 Secret；
- 所有响应 ``contains_real_secret=false``、``production_activation_prohibited=true``、
  ``engineering_enabled=false``；
- 当前真实外部资源未提供 → 全部 pending，不伪造验证；
- 任何写入/部署端点（如需）须真实 USER + 特权角色 + RBAC + CSRF + 同组织 +
  External Staging 环境证明 + 审计，且绝不触及 Production。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from fastapi import APIRouter

# 让 backend/app 命名空间可解析 agents 企业包。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.external_staging_qualification import (  # noqa: E402
    ExternalStagingEnvironmentIdentity,
    QualificationPipeline,
)

router = APIRouter(
    prefix="/external-staging/qualification",
    tags=["external-staging-qualification"],
)


def _source_commit() -> str:
    """尽力获取当前 git HEAD（失败回落占位，不阻断只读响应）。"""

    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(_BOIP_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _run_pipeline() -> dict:
    """执行 resource-less 资格管线（只读评估，不产生副作用）。"""

    identity = ExternalStagingEnvironmentIdentity()
    pipeline = QualificationPipeline(
        source_commit=_source_commit(), environment_identity=identity
    )
    result = pipeline.run()
    return result.to_dict()


@router.get("/resources")
def get_resources():
    """8 资源登记（只读快照）。"""
    data = _run_pipeline()
    return {
        "environment": data["environment_identity"]["environment"],
        "production": data["environment_identity"]["production"],
        "registry_summary": data["registry_summary"],
        "resources": _resources_detail(data),
        "engineering_enabled": load_engineering_enabled(),
        "note": "8 外部预生产资源全部 pending（真实资源未提供，fail-closed 不伪造）。",
    }


@router.get("/status")
def get_status():
    """资格状态摘要。"""
    data = _run_pipeline()
    return {
        "gate_status": data["gate_status"],
        "environment": data["environment_identity"]["environment"],
        "production": False,
        "external_pending": data["registry_summary"]["pending"],
        "engineering_enabled": load_engineering_enabled(),
        "production_activation_prohibited": True,
    }


@router.get("/connectivity")
def get_connectivity():
    """连接性摘要（全部 pending）。"""
    data = _run_pipeline()
    return {
        "connectivity_summary": data["package"]["connectivity_summary"],
        "note": "真实资源未提供 → 不 fallback Production、不伪造 connectivity。",
    }


@router.get("/isolation")
def get_isolation():
    """跨环境隔离（9 项，全部 pending/未证）。"""
    data = _run_pipeline()
    return {"isolation_summary": data["isolation_summary"]}


@router.get("/runtime-health")
def get_runtime_health():
    """运行时健康（13 组件，UNKNOWN 不视作 HEALTHY）。"""
    data = _run_pipeline()
    return {"runtime_summary": data["runtime_summary"]}


@router.get("/evidence")
def get_evidence():
    """证据链（scope=external_staging，无 Secret）。"""
    data = _run_pipeline()
    return {"evidence_summary": data["evidence_summary"]}


@router.get("/gate")
def get_gate():
    """资格闸门（BLOCKED / PENDING_* / READY_*）。"""
    data = _run_pipeline()
    return {"gate_status": data["gate_status"], "gate_checks": data["gate_checks"]}


@router.get("/package")
def get_package():
    """机器可读资格包（含 SHA-256）。"""
    data = _run_pipeline()
    return data["package"]


def _resources_detail(data: dict) -> list[dict]:
    # 从 package 取 resource_registry_summary（无逐资源明细）；用 identity + summary 构造。
    summary = data["registry_summary"]
    return [
        {
            "resource_id": rid,
            "configured": False,
            "verified": False,
            "qualification_status": "pending_external_staging_resource",
        }
        for rid in summary.get("resource_ids", [])
    ]
