"""Phase 3.9.4 合成事故演练 E2E 与 fail-closed 守卫（T10-T12, T22 部分）。

覆盖：故障注入 → 遥测归一化 → 健康/指标聚合 → 告警路由（仅模拟）→ 关联 →
事故草稿 → 人工动作 fixture → 恢复 → 验证；以及不可真实验证项 / 无人工动作不自动关闭 /
不自动回滚 / 不真实外发等红线。
"""

from __future__ import annotations

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import EnterpriseRedLineViolationError
from agents.enterprise.telemetry.models import ProviderKind, SyntheticFaultScenario
from agents.enterprise.telemetry.prometheus import PrometheusTelemetryAdapter
from agents.enterprise.telemetry.service import ProductionTelemetryService
from agents.enterprise.telemetry.synthetic import SyntheticFaultInjection, SyntheticTelemetryProvider


def _svc() -> ProductionTelemetryService:
    return ProductionTelemetryService(org_id="org-test", audit=AuditService(org_id="org-test"))


# ---------------- 故障注入 fail-closed（红线⑥/⑭） ----------------
def test_injection_rejects_real_provider():
    inj = SyntheticFaultInjection()
    real = PrometheusTelemetryAdapter(prometheus_url="http://x")
    try:
        inj.inject(
            provider=real,
            scenario=SyntheticFaultScenario.BACKEND_ERROR_SPIKE,
            organization_id="o",
            component="c",
        )
        assert False, "should have raised"
    except EnterpriseRedLineViolationError:
        pass


def test_injection_only_synthetic():
    inj = SyntheticFaultInjection()
    syn = SyntheticTelemetryProvider()
    envs = inj.inject(
        provider=syn,
        scenario=SyntheticFaultScenario.BACKEND_ERROR_SPIKE,
        organization_id="o",
        component="c",
    )
    assert len(envs) > 0
    assert all(e.simulation_only for e in envs)


# ---------------- E2E 演练：异常场景 ----------------
def test_drill_anomalous_pipeline():
    svc = _svc()
    res = svc.run_synthetic_incident_drill(
        scenario=SyntheticFaultScenario.BACKEND_ERROR_SPIKE,
        actor_id="user-1",
        organization_id="o",
        component="c",
    )
    assert res["simulation_only"] is True
    assert res["anomalous"] is True
    assert res["overall_health"] == "unhealthy"
    assert res["alert_delivery"]["delivery_status"] == "simulated_delivery"
    # 无 human_actions → 事故恒为 open，绝不自动关闭
    assert res["incident"]["status"] == "open"
    assert res["auto_resolved"] is False
    assert res["auto_closed"] is False
    assert res["auto_rollback"] is False


def test_drill_healthy_no_incident():
    svc = _svc()
    res = svc.run_synthetic_incident_drill(
        scenario=SyntheticFaultScenario.HEALTHY,
        actor_id="user-1",
        organization_id="o",
        component="c",
    )
    assert res["anomalous"] is False
    assert res["incident"]["status"] == "no_incident"


# ---------------- 人工动作 fixture（红线⑨/⑩） ----------------
def test_drill_human_close_reaches_closed_by_human():
    svc = _svc()
    res = svc.run_synthetic_incident_drill(
        scenario=SyntheticFaultScenario.BACKEND_ERROR_SPIKE,
        actor_id="user-1",
        organization_id="o",
        component="c",
        human_actions={"ack": True, "recover": True, "validate": True, "close": True},
    )
    assert res["incident"]["status"] == "closed_by_human"
    assert res["incident"]["human_steps"]["close"]["kind"] == "user"
    assert res["incident"]["human_steps"]["ack"]["kind"] == "user"
    # 恢复后仍声明非真实回滚
    assert res["auto_rollback"] is False


def test_drill_empty_actor_rejected():
    svc = _svc()
    try:
        svc.run_synthetic_incident_drill(
            scenario=SyntheticFaultScenario.BACKEND_ERROR_SPIKE,
            actor_id="",
            organization_id="o",
            component="c",
        )
        assert False, "should have raised"
    except EnterpriseRedLineViolationError:
        pass


# ---------------- 关联方法 fail-closed 声明 ----------------
def test_correlate_recovery_drill_no_auto_resolve():
    svc = _svc()
    out = svc.correlate_recovery_drill(
        drill_id="d1", recovery_validated=True, validated_by="user-1"
    )
    assert out["auto_resolved"] is False
    assert out["requires_human_closure"] is True


def test_correlate_release_no_auto_rollback():
    svc = _svc()
    out = svc.correlate_release(
        incident_ref="inc-1",
        release_id="RC-3.9.2",
        commit_sha="abc",
        manifest_reference="m",
        evidence_reference="e",
        rollback_reference="r",
    )
    assert out["auto_rollback"] is False
    assert out["pending_verification"] is True
    assert out["possible_correlation"] is True


def test_correlate_security_signals_simulation_only():
    svc = _svc()
    out = svc.correlate_security_signals(
        organization_id="o",
        signals=[
            {"category": "identity_auth_failure", "ts": "t1"},
            {"category": "identity_auth_failure", "ts": "t2"},
        ],
    )
    assert len(out) == 1
    assert out[0]["threshold_verified"] is False
    assert out[0]["simulation_only"] is True


# ---------------- 发布关联回滚引用只读（红线⑤） ----------------
def test_release_correlation_does_not_execute_rollback():
    svc = _svc()
    out = svc.correlate_release(
        incident_ref="inc-1",
        release_id="RC-3.9.2",
        commit_sha="abc",
        manifest_reference="m",
        evidence_reference="e",
        rollback_reference="rollback-plan.md",
    )
    # rollback_reference 仅作引用返回，绝不在本层执行
    assert out["rollback_reference"] == "rollback-plan.md"
    assert "executed" not in out


# ---------------- 全链路：注入→归一化→聚合→告警（仅模拟）→关联 ----------------
def test_e2e_drill_metrics_and_health_normalized():
    svc = _svc()
    # 1) 注入
    envs = svc._injection.inject(
        provider=svc._synthetic,
        scenario=SyntheticFaultScenario.DATABASE_UNAVAILABLE,
        organization_id="o",
        component="c",
    )
    # 2) 归一化
    norm = svc._normalizer.normalize(envs)
    assert len(norm["health"]) >= 1
    assert len(norm["metrics"]) >= 1
    # 3) 聚合健康
    statuses = [h.status.value for h in norm["health"]]
    overall = svc._aggregator.overall_for_normalized_health(statuses)
    assert overall == "unhealthy"
    # 4) 告警路由仅模拟
    delivery = svc._alert_router.route(
        {"alert_id": "a", "channel": "synthetic"}, actor_id="user-1", actor_kind="user"
    )
    assert delivery["delivery_status"] == "simulated_delivery"
    # 5) 发布关联只读引用
    corr = svc.correlate_release(
        incident_ref="inc-1",
        release_id="RC-3.9.2",
        commit_sha="abc",
        manifest_reference="m",
        evidence_reference="e",
        rollback_reference="r",
    )
    assert corr["auto_rollback"] is False
