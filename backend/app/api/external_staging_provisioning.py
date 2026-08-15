"""Backend FastAPI 路由：外部预生产供给算子就绪 API（Phase 3.9.12 Tasks 28）。

只读为主 API（fail-closed，红线）：

- GET  /api/external-staging-provisioning/status           供给就绪状态摘要
- GET  /api/external-staging-provisioning/bom              8 资源供给 BOM
- GET  /api/external-staging-provisioning/gate             Operator Gate（独立 3 态）
- GET  /api/external-staging-provisioning/iac-dry-run     IaC 干跑校验结果
- GET  /api/external-staging-provisioning/package          机器可读供给算子包（含 SHA-256）
- GET  /api/external-staging-provisioning/runbook          供给/清理 Runbook 引用 + 人工输入表
- POST /api/external-staging-provisioning/human-input-record  人工登记（仅登记，绝不执行/部署）

红线：
- **禁止**任何 Production 端点 / 真实部署 / 回滚 / 写 Secret / 权限授予；
- 所有响应 ``contains_real_secret=false``、``production_activation_prohibited=true``、
  ``engineering_enabled=false``；
- 当前真实外部资源未提供 → 全部 pending，不伪造验证 / 不宣称真实供给；
- human-input-record 仅登记事实（如「已查看 Runbook」「已登记人工输入」），不做副作用、
  不改业务数据、不翻转 enabled、不触发任何 apply。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

# 让 backend/app 命名空间可解析 agents 企业包。
_BOIP_ROOT = Path(__file__).resolve().parents[3]
if str(_BOIP_ROOT) not in sys.path:
    sys.path.insert(0, str(_BOIP_ROOT))

from agents.config_loader import load_engineering_enabled  # noqa: E402
from agents.external_staging_qualification.models import (  # noqa: E402
    ExternalStagingEnvironmentIdentity,
)
from agents.external_staging_provisioning import (  # noqa: E402
    build_provisioning_package,
    ProvisioningBom,
    IacDryRunGuard,
    ExternalStagingProvisioningOperatorGate,
    ExternalStagingProvisioningSecurityValidator,
    StagingCostGuard,
    PROVISIONING_AUDIT_CATEGORIES,
    build_provisioning_audit_event,
)
from agents.external_staging_provisioning.bom import PENDING_STATUS  # noqa: E402

router = APIRouter(
    prefix="/api/external-staging-provisioning",
    tags=["external-staging-provisioning"],
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


def _build_package() -> dict[str, Any]:
    """重算确定性供给算子包（运行时自包含，不依赖落盘文件）。"""

    src = _source_commit()
    bom = ProvisioningBom.build_default()
    env_identity = ExternalStagingEnvironmentIdentity(
        organization_id="ext-staging-org",
        domain_reference="staging.example.com",
        deployment_target_reference="ext-staging-deployment_target",
        database_reference="ext-staging-database",
        idp_reference="ext-staging-identity_provider",
        storage_reference="ext-staging-object_storage",
        telemetry_reference="ext-staging-telemetry",
        alert_reference="ext-staging-alert_sandbox",
    )
    iac = IacDryRunGuard().evaluate()
    gate = ExternalStagingProvisioningOperatorGate().evaluate(
        bom=bom,
        environment_identity=env_identity.to_dict(),
        iac_dry_run_ok=iac.all_ok,
        adapter_contract_ok=True,
        engineering_enabled=load_engineering_enabled(),
        human_input_required=True,
    )
    return build_provisioning_package(
        source_commit=src,
        environment_identity=env_identity,
        bom=bom,
        gate=gate,
        iac_dry_run_summary=iac.to_dict(),
        pending_resources=tuple(e.resource_id for e in bom.entries),
        baseline_commit=src,
        package_generated_from_commit=src,
    )


@router.get("/status")
def get_status():
    """供给就绪状态摘要（fail-closed，非生产）。"""
    pkg = _build_package()
    return {
        "phase": pkg["phase"],
        "terminal_state": pkg["terminal_state"],
        "operator_gate_status": pkg["operator_gate"]["status"],
        "environment": pkg["environment_identity"]["environment"],
        "production": False,
        "pending_resources": len(pkg["pending_resources"]),
        "engineering_enabled": load_engineering_enabled(),
        "production_activation_prohibited": True,
        "contains_real_secret": pkg["contains_real_secret"],
        "note": "8 外部预生产资源全部 pending（真实资源未提供，fail-closed 不伪造）。",
    }


@router.get("/bom")
def get_bom():
    """8 资源供给 BOM（全 PENDING，无真实账号/密钥）。"""
    bom = ProvisioningBom.build_default()
    return {
        "environment": "external_staging",
        "production": False,
        "total": bom.summary()["total"],
        "pending": bom.summary()["pending"],
        "resources": [
            {
                "resource_id": e.resource_id,
                "resource_type": e.resource_type.value,
                "required": e.required,
                "owner_role": e.owner_role,
                "default_provider_service": e.default_provider_service,
                "iac_module": e.iac_module,
                "status": e.status,
            }
            for e in bom.entries
        ],
        "engineering_enabled": load_engineering_enabled(),
    }


@router.get("/gate")
def get_gate():
    """Operator Gate（独立 3 态，禁 GO/APPROVED/PRODUCTION_READY）。"""
    pkg = _build_package()
    return {
        "operator_gate_status": pkg["operator_gate"]["status"],
        "gate_checks": pkg["operator_gate"]["checks"],
    }


@router.get("/iac-dry-run")
def get_iac_dry_run():
    """IaC 干跑校验结果（凭据扫描 / count=0 占位 / 默认 provider）。"""
    iac = IacDryRunGuard().evaluate()
    return iac.to_dict()


@router.get("/package")
def get_package():
    """机器可读供给算子包（含 SHA-256，确定性）。"""
    return _build_package()


@router.get("/runbook")
def get_runbook():
    """供给/清理 Runbook 引用 + 人工输入表摘要（只读）。"""
    return {
        "environment": "external_staging",
        "production": False,
        "provisioning_runbook": "docs/EXTERNAL_STAGING_PROVISIONING_RUNBOOK.md",
        "cleanup_rollback_runbook": "docs/EXTERNAL_STAGING_CLEANUP_ROLLBACK_RUNBOOK.md",
        "human_input_table": ".ai/staging/external_staging_human_input_table.json",
        "operator_gate_doc": "docs/EXTERNAL_STAGING_OPERATOR_GATE.md",
        "capacity_baseline": "docs/EXTERNAL_STAGING_CAPACITY_BASELINE.md",
        "execution_mode": ["plan", "validate", "dry_run", "human_authorized_apply"],
        "forbidden_execution_mode": ["auto", "production"],
        "operator_gate_states": [
            "blocked",
            "pending_human_input",
            "ready_for_human_provisioning_review",
        ],
        "engineering_enabled": load_engineering_enabled(),
    }


@router.post("/human-input-record")
async def post_human_input_record(request: Request):
    """人工登记（fail-closed，仅登记事实，绝不执行/部署/翻转 enabled）。

    请求体（JSON）：
      - record_id: str（调用方提供，唯一）
      - actor_id: str（必须为真实 USER id）
      - actor_kind: str（必须为 "USER"）
      - category: str（须为 3.9.12 供给审计类别之一）
      - action: str（如 "view" / "register_input"）
      - target: str（可选，资源 id 或文档）
      - detail: str（可选，自由文本，不得含明文密钥）
    """

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid JSON body")

    actor_kind = body.get("actor_kind")
    if actor_kind != "USER":
        raise HTTPException(
            status_code=403,
            detail="human-input-record 必须由真实 USER 发起（红线⑥ human-gating）",
        )
    actor_id = body.get("actor_id")
    if not actor_id:
        raise HTTPException(status_code=400, detail="actor_id 必填（真实 USER id）")
    category = body.get("category")
    if category not in PROVISIONING_AUDIT_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=f"category 须为 3.9.12 供给审计类别之一：{sorted(PROVISIONING_AUDIT_CATEGORIES)}",
        )

    # fail-closed：若 detail 疑似携带明文凭据，拒绝（不落盘）。
    sec = ExternalStagingProvisioningSecurityValidator()
    if sec.scan_text(body.get("detail") or ""):
        raise HTTPException(status_code=400, detail="detail 疑似含明文凭据，拒绝登记")

    event = build_provisioning_audit_event(
        record_id=body.get("record_id", "unknown"),
        actor_kind="USER",
        actor_id=actor_id,
        category=category,
        action=body.get("action", "view"),
        target=body.get("target", ""),
        detail=body.get("detail", ""),
    )

    # 注意：本端点仅构造审计形态事件并返回回执；不写业务数据、不翻转
    # engineering_enabled、不触发任何 apply/destroy。真实审计落盘由审计服务在
    # 离线授权后处理（不在 AI 运行时代执行）。
    return {
        "accepted": True,
        "event": event.to_dict(),
        "engineering_enabled_unchanged": load_engineering_enabled(),
        "note": "仅登记事实；不执行/不部署/不翻转 enabled。",
    }
