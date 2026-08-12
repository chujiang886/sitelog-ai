"""Phase 3.9.4 遥测 Provider 健康聚合（T9）。

``TelemetryHealthAggregator`` 把多个 ``TelemetryProviderHealth`` 聚合为一个整体视图。

纪律（红线⑪）：
- Provider 状态 ``UNKNOWN`` **绝不**被推断为 ``CONFIGURED`` / ``HEALTHY``（宁错杀）。
- 只要任一关键 Provider 未配置（``NOT_CONFIGURED``）或未知（``UNKNOWN``），整体 readiness
  不得声称 fully operational。
- 仅当所有核心 Provider 显式 ``CONFIGURED`` / ``DEGRADED`` 且 ``simulation_only`` 一致可解释
  时，才给出 operational 视图；否则保守降级。
"""

from __future__ import annotations

from typing import Any, Dict, List

from agents.enterprise.telemetry.models import ProviderKind, ProviderStatus, TelemetryProviderHealth


class TelemetryHealthAggregator:
    """遥测 Provider 健康聚合器（T9）。"""

    def summarize(self, healths: List[TelemetryProviderHealth]) -> Dict[str, Any]:
        """聚合一组 Provider 健康快照。"""
        items = [self._as_dict(h) for h in healths or []]
        total = len(items)
        configured = [i for i in items if i["status"] == ProviderStatus.CONFIGURED.value]
        degraded = [i for i in items if i["status"] == ProviderStatus.DEGRADED.value]
        # UNKNOWN / NOT_CONFIGURED / UNHEALTHY 一律不计入 operational。
        operational = configured + degraded
        not_configured = [i for i in items if i["status"] == ProviderStatus.NOT_CONFIGURED.value]
        unknown = [i for i in items if i["status"] == ProviderStatus.UNKNOWN.value]
        unhealthy = [i for i in items if i["status"] == ProviderStatus.UNHEALTHY.value]

        if total == 0:
            overall = "no_providers"
        elif not_configured or unknown:
            # 有未配置 / 未知 Provider → 保守降级，绝不声称 fully operational。
            overall = "partial_not_configured"
        elif unhealthy:
            overall = "unhealthy"
        elif degraded:
            overall = "degraded"
        elif len(operational) == total and total > 0:
            if all(i["simulation_only"] for i in items):
                # 红线⑪：仅合成源（全 simulation_only）绝不等于 production operational。
                overall = "synthetic_only"
            else:
                overall = "operational"
        else:
            overall = "unknown"

        return {
            "overall": overall,
            "total": total,
            "configured": len(configured),
            "degraded": len(degraded),
            "not_configured": len(not_configured),
            "unknown": len(unknown),
            "unhealthy": len(unhealthy),
            "providers": items,
            "is_operational": overall == "operational",
        }

    def overall_for_normalized_health(
        self, statuses: List[str]
    ) -> str:
        """聚合归一化 ``ServiceHealthStatus`` 字符串列表（供 drill 使用）。"""
        if not statuses:
            return "no_health"
        if any(s == "unhealthy" for s in statuses):
            return "unhealthy"
        if any(s == "degraded" for s in statuses):
            return "degraded"
        if any(s == "unknown" for s in statuses):
            return "partial_unknown"
        if all(s == "healthy" for s in statuses):
            return "healthy"
        return "mixed"

    @staticmethod
    def _as_dict(h: TelemetryProviderHealth) -> Dict[str, Any]:
        return {
            "provider_id": h.provider_id,
            "kind": h.kind.value,
            "status": h.status.value,
            "checked_at": h.checked_at,
            "capabilities": [c.value for c in h.capabilities],
            "detail": h.detail,
            "simulation_only": h.simulation_only,
        }


__all__ = ["TelemetryHealthAggregator"]
