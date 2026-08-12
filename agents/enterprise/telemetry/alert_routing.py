"""Phase 3.9.4 告警路由端口与 Provider（T13）。

- ``AlertRoutingProvider``：告警路由端口。高层只依赖此端口，不依赖具体 PagerDuty /
  企业微信 / Slack / Email 实现。
- ``NullAlertRoutingProvider``：未配置路由目标 → 返回 ``NOT_CONFIGURED``，绝不静默丢弃
  也不真实外发（fail-closed）。
- ``SyntheticAlertRoutingProvider``：演练用，**仅**返回 ``SIMULATED_DELIVERY``（
  simulation_only=True），**绝不**真实发送 PagerDuty / 企业微信 / Slack / Email。

纪律（红线⑫）：本层任何 Provider **不**持有真实外发能力；真实外发方法名（
``deliver_real_alert`` / ``send_real_pagerduty`` / ``send_real_slack`` / ``send_real_wechat`` /
``send_real_email`` / ``send_real_webhook`` / ``mark_delivery_real``）由
``_RedLineForbiddenMixin`` 在全服务层结构性拦截。若有人试图在 Provider 上调用这些方法，
会因未被定义而走 ``__getattr__`` 拦截并抛 ``EnterpriseRedLineViolationError``。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict

from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
)
from agents.enterprise.telemetry.forbidden import _TELEMETRY_FORBIDDEN


class AlertDeliveryStatus(str, Enum):
    """告警投递状态（仅端口层可表达的几种，绝不包含『已真实外发』之外的伪造态）。"""

    SIMULATED_DELIVERY = "simulated_delivery"  # 仅模拟投递（演练用）
    NOT_CONFIGURED = "not_configured"  # 路由目标未配置（fail-closed）
    SUPPRESSED = "suppressed"  # 显式抑制（不投递，但明确记录原因）


class AlertRoutingProvider(ABC, _RedLineForbiddenMixin):
    """告警路由端口（T13）。"""

    _FORBIDDEN = _TELEMETRY_FORBIDDEN

    @abstractmethod
    def route(self, alert: Dict[str, Any], *, actor_id: str, actor_kind: str) -> Dict[str, Any]:
        """对一条告警候选执行路由。返回投递结果（含 delivery_status / simulation_only）。

        ``actor_id`` / ``actor_kind`` 仅用于责任留痕；本方法**不**做真实外发。
        """

    def _require_user(self, actor_id: str, actor_kind: str) -> None:
        if not actor_id or actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "告警路由责任节点要求真实 USER actor（红线⑩）"
            )


class NullAlertRoutingProvider(AlertRoutingProvider):
    """未配置路由目标的空实现（fail-closed）。"""

    @property
    def provider_id(self) -> str:
        return "null-alert-router"

    def route(self, alert: Dict[str, Any], *, actor_id: str, actor_kind: str) -> Dict[str, Any]:
        self._require_user(actor_id, actor_kind)
        return {
            "provider_id": self.provider_id,
            "delivery_status": AlertDeliveryStatus.NOT_CONFIGURED.value,
            "simulation_only": False,
            "alert_ref": alert.get("alert_id", ""),
            "detail": "no alert routing target configured (fail-closed; nothing delivered)",
        }


class SyntheticAlertRoutingProvider(AlertRoutingProvider):
    """演练用合成告警路由（T13）。仅模拟投递，绝不真实外发（红线⑫）。"""

    @property
    def provider_id(self) -> str:
        return "synthetic-alert-router"

    def route(self, alert: Dict[str, Any], *, actor_id: str, actor_kind: str) -> Dict[str, Any]:
        self._require_user(actor_id, actor_kind)
        return {
            "provider_id": self.provider_id,
            "delivery_status": AlertDeliveryStatus.SIMULATED_DELIVERY.value,
            "simulation_only": True,  # 红线⑫：明确标记仅为模拟，非真实外发
            "alert_ref": alert.get("alert_id", ""),
            "channel": alert.get("channel", "synthetic"),
            "detail": "SIMULATED delivery only; no real PagerDuty/WeChat/Slack/Email sent (red line ⑫)",
        }


__all__ = [
    "AlertDeliveryStatus",
    "AlertRoutingProvider",
    "NullAlertRoutingProvider",
    "SyntheticAlertRoutingProvider",
]
