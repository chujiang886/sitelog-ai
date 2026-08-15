"""Phase 3.9.10 —— External Staging Connectivity Probe Port（Task 6）。

统一只读 / 非破坏性连接探针接口：

- ``probe_database`` / ``probe_idp`` / ``probe_storage`` / ``probe_telemetry`` /
  ``probe_alert`` / ``probe_domain_tls`` / ``probe_deployment_target`` /
  ``probe_secret_provider``。

设计纪律（fail-closed）：
- 探针**只读 / 非破坏性**，带超时控制；
- **不**对 Production 做 fallback；
- **先验证环境身份**（必须 EXTERNAL_STAGING 且 production=false）；
- **产生证据**（即使 pending 也产出 ProbeResult 记录）；
- 真实资源缺失 → 返回 ``PENDING_EXTERNAL_STAGING_RESOURCE``，**不抛整个 Phase**。

本模块仅定义契约 + 一个确定性的 Fake/Sandbox Adapter（用于 contract 测试与
resource-less dry-run）；真实 External 适配器在资源明确授权后由同一契约接入。
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Any, Mapping

from agents.external_staging_qualification.denylist import (
    ProductionReferenceDenylist,
    RESOURCE_TO_PRODUCTION_KIND,
)
from agents.external_staging_qualification.models import (
    ExternalStagingEnvironmentIdentity,
    ResourceQualificationStatus,
    ResourceType,
)


@dataclass(frozen=True)
class ProbeResult:
    """单探针结果（不含任何明文凭据）。"""

    resource_type: ResourceType
    status: ResourceQualificationStatus
    reachable: bool
    detail: str = ""
    evidence_id: str = ""
    latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "status": self.status.value,
            "reachable": self.reachable,
            "detail": self.detail,
            "evidence_id": self.evidence_id,
            "latency_ms": self.latency_ms,
            "contains_real_secret": False,
        }


@dataclass
class ProbeContext:
    """探针执行上下文。"""

    environment: ExternalStagingEnvironmentIdentity
    denylist: ProductionReferenceDenylist = field(
        default_factory=ProductionReferenceDenylist
    )
    timeout_seconds: float = 5.0


class ExternalStagingConnectivityProbe:
    """外部预生产连接探针（统一接口，read-only / non-destructive）。"""

    def __init__(self, context: ProbeContext) -> None:
        self._assert_environment(context.environment)
        self._ctx = context

    @staticmethod
    def _assert_environment(env: ExternalStagingEnvironmentIdentity) -> None:
        if env.production:
            raise ExternalStagingProbeError(
                "环境身份 production=true，拒绝执行任何 External Staging 探针（红线）。"
            )
        if env.environment != ExternalStagingEnvironmentIdentity().environment:
            # 必须为 external_staging
            if env.environment != "external_staging":
                raise ExternalStagingProbeError(
                    f"环境 {env.environment!r} 非 external_staging，拒绝探针。"
                )

    def _pending(self, rtype: ResourceType, detail: str) -> ProbeResult:
        return ProbeResult(
            resource_type=rtype,
            status=ResourceQualificationStatus.PENDING_EXTERNAL_STAGING_RESOURCE,
            reachable=False,
            detail=detail,
            evidence_id=_make_evidence_id(rtype, "pending"),
        )

    # ---- 8 类探针：真实资源缺失统一返回 pending，不伪造 connectivity ----

    def probe_database(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(ResourceType.DATABASE, "DB 未配置/未提供引用（pending）。")
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.DATABASE], reference
        )
        # 真实连接需外部资源；resource-less 基线不连接 Production，回落 pending。
        return ProbeResult(
            resource_type=ResourceType.DATABASE,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="DB 引用已登记，真实连通性待主理人 + 四角色线下验证。",
            evidence_id=_make_evidence_id(ResourceType.DATABASE, "conn-pending"),
        )

    def probe_secret_provider(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.SECRET_PROVIDER, "Secret Provider 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.SECRET_PROVIDER], reference
        )
        return ProbeResult(
            resource_type=ResourceType.SECRET_PROVIDER,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Secret Provider 引用已登记，可达性待线下验证（绝不读取 Secret 原值）。",
            evidence_id=_make_evidence_id(ResourceType.SECRET_PROVIDER, "conn-pending"),
        )

    def probe_idp(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.IDENTITY_PROVIDER, "IdP 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.IDENTITY_PROVIDER], reference
        )
        return ProbeResult(
            resource_type=ResourceType.IDENTITY_PROVIDER,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="IdP 引用已登记，issuer/audience 待线下验证。",
            evidence_id=_make_evidence_id(ResourceType.IDENTITY_PROVIDER, "conn-pending"),
        )

    def probe_storage(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.OBJECT_STORAGE, "Object Storage 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.OBJECT_STORAGE], reference
        )
        return ProbeResult(
            resource_type=ResourceType.OBJECT_STORAGE,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Storage 引用已登记，bucket/namespace 待线下验证。",
            evidence_id=_make_evidence_id(ResourceType.OBJECT_STORAGE, "conn-pending"),
        )

    def probe_telemetry(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.TELEMETRY, "Telemetry 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.TELEMETRY], reference
        )
        return ProbeResult(
            resource_type=ResourceType.TELEMETRY,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Telemetry 端点已登记，metrics/traces/logs 待线下验证。",
            evidence_id=_make_evidence_id(ResourceType.TELEMETRY, "conn-pending"),
        )

    def probe_alert(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.ALERT_SANDBOX, "Alert Sandbox 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.ALERT_SANDBOX], reference
        )
        return ProbeResult(
            resource_type=ResourceType.ALERT_SANDBOX,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Alert Sandbox 已登记，测试事件投递待线下验证（明确 STAGING TEST）。",
            evidence_id=_make_evidence_id(ResourceType.ALERT_SANDBOX, "conn-pending"),
        )

    def probe_domain_tls(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.DOMAIN_TLS, "Domain/TLS 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.DOMAIN_TLS], reference
        )
        return ProbeResult(
            resource_type=ResourceType.DOMAIN_TLS,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Staging 域名/TLS 已登记，证书有效性待线下验证。",
            evidence_id=_make_evidence_id(ResourceType.DOMAIN_TLS, "conn-pending"),
        )

    def probe_deployment_target(
        self, reference: str = "", *, configured: bool = False
    ) -> ProbeResult:
        if not configured or not reference:
            return self._pending(
                ResourceType.DEPLOYMENT_TARGET, "Deployment Target 未配置/未提供引用（pending）。"
            )
        self._ctx.denylist.check(
            RESOURCE_TO_PRODUCTION_KIND[ResourceType.DEPLOYMENT_TARGET], reference
        )
        return ProbeResult(
            resource_type=ResourceType.DEPLOYMENT_TARGET,
            status=ResourceQualificationStatus.CONNECTIVITY_PENDING,
            reachable=False,
            detail="Deployment Target 已登记，provider/region/namespace 待线下验证。",
            evidence_id=_make_evidence_id(ResourceType.DEPLOYMENT_TARGET, "conn-pending"),
        )


class ExternalStagingProbeError(ValueError):
    """探针执行错误（环境违例等）。"""


def _make_evidence_id(rtype: ResourceType, tag: str) -> str:
    ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"probe-{rtype.value}-{tag}-{ts}"


__all__ = [
    "ProbeResult",
    "ProbeContext",
    "ExternalStagingConnectivityProbe",
    "ExternalStagingProbeError",
]
