"""Phase 3.9.4 遥测 Provider 注册表（T8, T15）。

``TelemetryProviderRegistry`` 支持注册 / 查询 / 健康检查 / 能力声明。

纪律（红线⑪，§十五）：
- 未配置真实 Provider 时，**禁止**自动把 Synthetic 当生产 Provider；生产 Provider 未配置
  返回 ``NOT_CONFIGURED`` 或 ``PENDING_VERIFICATION``。
- 注册表只做登记与查询，绝不持有任何自动回滚 / 真实外发 / Runbook 执行能力（那些能力
  由 forbidden 层结构性禁止，注册表本身不提供对应方法）。
- ``get_production_provider`` 仅在真实 Provider 明确 configured() 时返回；否则显式返回
  ``None`` + 原因，绝不静默 fallback 到 Synthetic。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.telemetry.health import TelemetryHealthAggregator
from agents.enterprise.telemetry.models import (
    ProviderKind,
    ProviderStatus,
    TelemetryProviderHealth,
)
from agents.enterprise.telemetry.provider import TelemetryProvider


class TelemetryProviderRegistry:
    """遥测 Provider 注册表（T8, T15）。"""

    def __init__(self) -> None:
        self._providers: Dict[str, TelemetryProvider] = {}
        self._aggregator = TelemetryHealthAggregator()

    # ---- 注册 / 查询 ----
    def register(self, provider: TelemetryProvider, *, replace: bool = False) -> None:
        pid = provider.provider_id
        if pid in self._providers and not replace:
            raise KeyError(
                f"遥测 Provider 已存在：{pid}（如需覆盖请显式 replace=True）"
            )
        self._providers[pid] = provider

    def get(self, provider_id: str) -> Optional[TelemetryProvider]:
        return self._providers.get(provider_id)

    def all(self) -> List[TelemetryProvider]:
        return list(self._providers.values())

    def list_ids(self) -> List[str]:
        return list(self._providers.keys())

    # ---- 能力声明 ----
    def capabilities(self, provider_id: str) -> List[str]:
        p = self.get(provider_id)
        if p is None:
            return []
        return [c.value for c in p.capability_set()]

    # ---- 健康检查 ----
    def provider_health(self, provider_id: str) -> Optional[TelemetryProviderHealth]:
        p = self.get(provider_id)
        if p is None:
            return None
        return p.provider_health()

    def health_summary(self) -> Dict[str, Any]:
        healths = [p.provider_health() for p in self.all()]
        healths = [h for h in healths if h is not None]
        return self._aggregator.summarize(healths)

    # ---- 生产 Provider 解析（fail-closed，红线⑪）----
    def get_production_provider(self, kind: ProviderKind) -> Optional[TelemetryProvider]:
        """返回**已配置的真实**生产 Provider（同 kind）。未配置 → ``None``，绝不 fallback Synthetic。

        这是红线⑪ 的核心防线：调用方必须显式拿到 None 并自行决定降级策略，注册表不替它
        把 Synthetic 伪装成生产源。
        """
        for p in self.all():
            if p.kind == kind and p.is_configured():
                # 双重确认：configured 且状态非 NOT_CONFIGURED。
                if p.provider_health().status != ProviderStatus.NOT_CONFIGURED:
                    return p
        return None

    def production_providers(self) -> List[TelemetryProvider]:
        """列出所有已配置的真实生产 Provider（排除未配置的）。"""
        out: List[TelemetryProvider] = []
        for p in self.all():
            if p.is_configured() and p.provider_health().status != ProviderStatus.NOT_CONFIGURED:
                out.append(p)
        return out

    def pending_verification_providers(self) -> List[str]:
        """列出需要真实连接验证（configured 但连接未经人工核验）的 Provider。"""
        out: List[str] = []
        for p in self.all():
            if p.is_configured() and p.provider_health().status == ProviderStatus.CONFIGURED:
                out.append(p.provider_id)
        return out


__all__ = ["TelemetryProviderRegistry"]
