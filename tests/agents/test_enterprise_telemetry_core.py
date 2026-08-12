"""Phase 3.9.4 遥测核心层单元测试（T1-T9, T13, T15, T22 部分）。

覆盖归一化器、健康聚合、注册表 fail-closed、告警路由、Prometheus/OTel 适配器的
未配置 fail-closed，以及 ProductionTelemetryService 的只读查询 / 巡检 / 注册表行为。
"""

from __future__ import annotations

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.telemetry.alert_routing import (
    AlertDeliveryStatus,
    NullAlertRoutingProvider,
    SyntheticAlertRoutingProvider,
)
from agents.enterprise.telemetry.health import TelemetryHealthAggregator
from agents.enterprise.telemetry.models import (
    ProviderKind,
    ProviderStatus,
    SyntheticFaultScenario,
    TelemetryProviderHealth,
)
from agents.enterprise.telemetry.normalizer import TelemetryNormalizer
from agents.enterprise.telemetry.otel import OpenTelemetryAdapter
from agents.enterprise.telemetry.prometheus import PrometheusTelemetryAdapter
from agents.enterprise.telemetry.registry import TelemetryProviderRegistry
from agents.enterprise.telemetry.service import ProductionTelemetryService
from agents.enterprise.telemetry.synthetic import (
    SyntheticFaultInjection,
    SyntheticTelemetryProvider,
)


def _svc() -> ProductionTelemetryService:
    return ProductionTelemetryService(org_id="org-test", audit=AuditService(org_id="org-test"))


# ---------------- 归一化器（T7, T13） ----------------
def test_normalizer_health_status_preserved():
    syn = SyntheticTelemetryProvider()
    syn.set_scenario(SyntheticFaultScenario.BACKEND_ERROR_SPIKE)
    envs = syn.query_health(organization_id="o", component="api")
    norm = TelemetryNormalizer().normalize(envs)
    assert len(norm["health"]) == 1
    # 状态从 synthetic payload 原样映射，未被篡改为真实生产数据
    assert norm["health"][0].status.value == "unhealthy"
    # simulation_only 透传
    assert syn.provider_health().simulation_only is True


def test_normalizer_unknown_status_fails_to_unknown():
    from agents.enterprise.telemetry.models import (
        IntegrityStatus,
        TelemetryEnvelope,
        TelemetryType,
    )

    env = TelemetryEnvelope(
        provider="x",
        telemetry_type=TelemetryType.HEALTH,
        organization_id="o",
        component="c",
        timestamp="t",
        payload={"status": "weird_status"},
        simulation_only=True,
        integrity_status=IntegrityStatus.INTACT,
    )
    norm = TelemetryNormalizer().normalize([env])
    # 红线⑪：未知状态 fail-closed 回退 UNKNOWN，绝不 HEALTHY
    assert norm["health"][0].status.value == "unknown"


def test_normalizer_metric_category_release_mapping():
    from agents.enterprise.production_observability.models import MetricCategory
    from agents.enterprise.telemetry.normalizer import _metric_category_for

    assert _metric_category_for("release_regression") == MetricCategory.RELEASE
    assert _metric_category_for("identity_authentication_failure") == MetricCategory.IDENTITY
    assert _metric_category_for("llm_timeout") == MetricCategory.AI_RUNTIME


def test_normalizer_simulation_only_preserved_on_metric():
    syn = SyntheticTelemetryProvider()
    envs = syn.query_metrics(organization_id="o", component="api")
    norm = TelemetryNormalizer().normalize(envs)
    assert norm["metrics"][0].simulation_only is True


# ---------------- 健康聚合（T9） ----------------
def test_aggregator_partial_not_configured():
    agg = TelemetryHealthAggregator()
    healths = [
        TelemetryProviderHealth(
            provider_id="p",
            kind=ProviderKind.PROMETHEUS,
            status=ProviderStatus.NOT_CONFIGURED,
            checked_at="t",
            simulation_only=False,
        ),
        TelemetryProviderHealth(
            provider_id="s",
            kind=ProviderKind.SYNTHETIC,
            status=ProviderStatus.CONFIGURED,
            checked_at="t",
            simulation_only=True,
        ),
    ]
    s = agg.summarize(healths)
    # 红线⑪：有 NOT_CONFIGURED 不得声称 operational
    assert s["overall"] == "partial_not_configured"
    assert s["is_operational"] is False


def test_aggregator_all_healthy_operational():
    agg = TelemetryHealthAggregator()
    healths = [
        TelemetryProviderHealth(
            provider_id="p",
            kind=ProviderKind.PROMETHEUS,
            status=ProviderStatus.CONFIGURED,
            checked_at="t",
            simulation_only=False,
        ),
    ]
    s = agg.summarize(healths)
    assert s["overall"] == "operational"
    assert s["is_operational"] is True


def test_aggregator_overall_for_normalized():
    agg = TelemetryHealthAggregator()
    assert agg.overall_for_normalized_health(["healthy", "healthy"]) == "healthy"
    assert agg.overall_for_normalized_health(["healthy", "unhealthy"]) == "unhealthy"
    assert agg.overall_for_normalized_health(["healthy", "unknown"]) == "partial_unknown"


# ---------------- 注册表 fail-closed（T8, T15, 红线⑪） ----------------
def test_registry_production_provider_none_for_unconfigured_real_kind():
    reg = TelemetryProviderRegistry()
    reg.register(SyntheticTelemetryProvider())
    # 仅注册了 Synthetic，请求真实 PROMETHEUS 源 → 绝不 fallback Synthetic（红线⑪）
    assert reg.get_production_provider(ProviderKind.PROMETHEUS) is None
    # 合成源虽 configured，但绝非「生产 PROMETHEUS」
    assert reg.production_providers()  # 含 synthetic（已 configured）
    assert "synthetic" in reg.pending_verification_providers()


def test_registry_returns_configured_real_provider():
    reg = TelemetryProviderRegistry()
    reg.register(SyntheticTelemetryProvider())
    real = PrometheusTelemetryAdapter(prometheus_url="http://prom.local")
    reg.register(real)
    # 已配置真实源 → 解析为生产 Provider（不 fallback Synthetic）
    got = reg.get_production_provider(ProviderKind.PROMETHEUS)
    assert got is real
    assert real in reg.production_providers()


# ---------------- 告警路由（T13, 红线⑫） ----------------
def test_synthetic_alert_router_only_simulated():
    r = SyntheticAlertRoutingProvider()
    out = r.route({"alert_id": "a1"}, actor_id="user-1", actor_kind="user")
    assert out["delivery_status"] == AlertDeliveryStatus.SIMULATED_DELIVERY.value
    assert out["simulation_only"] is True


def test_null_alert_router_not_configured_no_fake_delivery():
    r = NullAlertRoutingProvider()
    out = r.route({"alert_id": "a1"}, actor_id="user-1", actor_kind="user")
    assert out["delivery_status"] == AlertDeliveryStatus.NOT_CONFIGURED.value
    assert out["simulation_only"] is False


def test_alert_router_rejects_non_user_actor():
    r = SyntheticAlertRoutingProvider()
    try:
        r.route({"alert_id": "a1"}, actor_id="agent-1", actor_kind="agent")
        assert False, "should have raised"
    except EnterpriseRedLineViolationError:
        pass


# ---------------- Prometheus / OTel 适配器 fail-closed（T4, T5, 红线⑪） ----------------
def test_prometheus_unconfigured_fails_closed():
    p = PrometheusTelemetryAdapter()
    assert p.is_configured() is False
    assert p.provider_health().status == ProviderStatus.NOT_CONFIGURED
    assert p.query_metrics(organization_id="o", component="c") == []


def test_otel_unconfigured_fails_closed():
    o = OpenTelemetryAdapter()
    assert o.is_configured() is False
    assert o.provider_health().status == ProviderStatus.NOT_CONFIGURED
    assert o.query_traces(organization_id="o", component="c") == []


# ---------------- 服务层只读查询 / 巡检（T8, T19） ----------------
def test_service_list_providers_synthetic_only():
    svc = _svc()
    assert set(svc.list_providers()) >= {"synthetic", "synthetic-log"}
    summary = svc.provider_health_summary()
    assert summary["is_operational"] is False  # 仅合成源，绝不算 operational


def test_service_query_unconfigured_real_provider_empty():
    svc = _svc()
    # 真实源未注册 → 空返回，绝不降级为 Synthetic（红线⑪）
    out = svc.query_and_normalize(
        provider_id="prometheus", organization_id="o", component="c"
    )
    assert out["configured"] is False
    assert out["normalized"]["metrics"] == []
    assert out["normalized"]["health"] == []


def test_service_query_synthetic_returns_normalized():
    svc = _svc()
    out = svc.query_and_normalize(
        provider_id="synthetic", organization_id="o", component="c", types=["metrics"]
    )
    assert out["configured"] is True
    assert len(out["normalized"]["metrics"]) >= 1
    assert out["normalized"]["metrics"][0]["simulation_only"] is True


def test_service_check_provider_records_audit():
    svc = _svc()
    out = svc.check_provider(actor_id="user-1", provider_id="synthetic")
    assert out["provider_id"] == "synthetic"
    assert out["checked_by"] == "user-1"
    assert out["simulation_only"] is True
