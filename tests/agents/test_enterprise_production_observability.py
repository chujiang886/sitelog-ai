"""Phase 3.9.3 企业生产可观测性、SRE 与事故响应准备层 —— fail-closed 测试（T25）。

覆盖 §二十二要求的 22 个用例。所有 AI 越权动作一律被 ``EnterpriseRedLineViolationError``
拦截（fail-closed）；所有人工责任节点强制 actor_kind="user"（红线⑤/⑨/⑩/⑪/⑫）。
"""

from __future__ import annotations

import pytest

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.production_observability import (
    IncidentSeverity,
    ProductionObservabilityService,
    ServiceHealthStatus,
    SLOKind,
)
from agents.enterprise.production_observability.models import (
    AlertCandidate,
    AlertStatus,
    IncidentStatus,
    RootCauseStatus,
)
from agents.enterprise.red_line import EnterpriseRedLineViolationError


ORG_A = "org-observability-A"
ORG_B = "org-observability-B"


@pytest.fixture
def svc() -> ProductionObservabilityService:
    return ProductionObservabilityService(org_id=ORG_A, audit=AuditService(org_id=ORG_A))


@pytest.fixture
def svc_b() -> ProductionObservabilityService:
    return ProductionObservabilityService(org_id=ORG_B, audit=AuditService(org_id=ORG_B))


# 1. Health UNKNOWN 不自动 HEALTHY ---------------------------------------- #
def test_health_unknown_never_auto_healthy(svc: ProductionObservabilityService) -> None:
    from agents.enterprise.production_observability.models import ServiceHealth

    snaps = [
        ServiceHealth(
            component="backend", status=ServiceHealthStatus.UNKNOWN,
            checked_at="t", source="probe",
        ),
        ServiceHealth(
            component="frontend", status=ServiceHealthStatus.UNKNOWN,
            checked_at="t", source="probe",
        ),
    ]
    assert svc.health.overall_status(snaps) == ServiceHealthStatus.UNKNOWN
    assert not svc.health.is_operational(ServiceHealthStatus.UNKNOWN)
    assert svc.health.is_operational(ServiceHealthStatus.HEALTHY)
    assert svc.health.is_operational(ServiceHealthStatus.DEGRADED)
    assert not svc.health.is_operational(ServiceHealthStatus.UNHEALTHY)


# 2. Metric 聚合 ---------------------------------------------------------- #
def test_metric_aggregation(svc: ProductionObservabilityService) -> None:
    from agents.enterprise.production_observability.models import MetricCategory, MetricSnapshot

    snaps = [
        MetricSnapshot(
            metric_id="m1", category=MetricCategory.AVAILABILITY, component="backend",
            window="5m", values={"request_count": 1000, "success_count": 990, "error_count": 10},
            source="probe", checked_at="t",
        ),
        MetricSnapshot(
            metric_id="m2", category=MetricCategory.AVAILABILITY, component="backend",
            window="5m", values={"request_count": 1000, "success_count": 980, "error_count": 20},
            source="probe", checked_at="t",
        ),
        MetricSnapshot(
            metric_id="m3", category=MetricCategory.LATENCY, component="backend",
            window="5m", values={"p50": 100.0, "p95": 250.0, "p99": 400.0},
            source="probe", checked_at="t",
        ),
    ]
    avail = svc.metrics.aggregate_availability(snaps)
    assert avail["request_count"] == 2000
    assert avail["error_count"] == 30
    assert abs(avail["availability_ratio"] - (1970 / 2000)) < 1e-9
    lat = svc.metrics.aggregate_latency([snaps[2]])
    assert lat["p50"] == 100.0 and lat["p99"] == 400.0


# 3. SLO pending threshold ------------------------------------------------ #
def test_slo_pending_threshold(svc: ProductionObservabilityService) -> None:
    slo = svc.slo.define_slo(
        slo_id="avail", name="API 可用性", component="backend",
        kind=SLOKind.AVAILABILITY, target=0.999, threshold_verified=False,
    )
    assert slo.status.value == "pending_verification"
    assert slo.threshold_verified is False
    # 真实阈值验证后，未给观测值仍 pending
    slo2 = svc.slo.define_slo(
        slo_id="avail2", name="API 可用性", component="backend",
        kind=SLOKind.AVAILABILITY, target=0.999, threshold_verified=True, observed=None,
    )
    assert slo2.status.value == "pending_verification"


# 4. Error Budget -------------------------------------------------------- #
def test_error_budget(svc: ProductionObservabilityService) -> None:
    eb = svc.slo.compute_error_budget(
        slo_id="avail", budget_total=0.001, consumed=0.0005,
    )
    assert eb.remaining == 0.0005
    assert eb.warning is False
    eb2 = svc.slo.compute_error_budget(
        slo_id="avail", budget_total=0.001, consumed=0.0009,
    )
    assert eb2.warning is True
    # 红线⑤/③：错误预算方法绝不触发任何停发布 / 回滚
    assert eb.to_dict()["human_review_required"] is False


# 5. Alert Candidate ----------------------------------------------------- #
def test_alert_candidate_created(svc: ProductionObservabilityService) -> None:
    al = svc.alerts.create_alert(
        alert_id="a1", component="backend", title="err spike", severity="high",
        detection_source="probe", fingerprint="fp-1",
    )
    assert al.status == AlertStatus.DETECTED
    assert al.simulation_only is False


# 6. Alert dedup / correlation ------------------------------------------- #
def test_alert_dedup_correlation(svc: ProductionObservabilityService) -> None:
    svc.alerts.create_alert(
        alert_id="a1", component="backend", title="x", severity="high",
        detection_source="probe", fingerprint="fp-1", trace_ids=["t1"],
    )
    svc.alerts.create_alert(
        alert_id="a2", component="backend", title="x", severity="high",
        detection_source="probe", fingerprint="fp-1", trace_ids=["t1"],
    )
    svc.alerts.create_alert(
        alert_id="a3", component="database", title="y", severity="critical",
        detection_source="probe", fingerprint="fp-2",
    )
    corrs = svc.alerts.correlate(organization_id=ORG_A)
    # fp-1 两告警合并为 1 组（merged=True），fp-2 独立 1 组 → 共 2 组
    assert len(corrs) == 2
    merged = [c for c in corrs if c.merged]
    assert len(merged) == 1
    assert set(merged[0].related_alert_ids) == {"a1", "a2"}


# 7. Incident 创建 ------------------------------------------------------- #
def test_incident_created(svc: ProductionObservabilityService) -> None:
    inc = svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="db slow",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="database",
    )
    assert inc.status == IncidentStatus.DETECTED
    # 无 AUTO_* 状态
    assert "auto" not in inc.status.value


# 8. AI acknowledge 拒绝 ------------------------------------------------- #
def test_ai_acknowledge_rejected(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.incidents.acknowledge(incident_id="i1", actor_id="ai", actor_kind="ai")


# 9. USER acknowledge ---------------------------------------------------- #
def test_user_acknowledge(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    inc = svc.incidents.acknowledge(
        incident_id="i1", actor_id="u1", actor_kind="user",
    )
    assert inc.status == IncidentStatus.HUMAN_ACKNOWLEDGED
    svc.record_incident_acknowledged(actor_id="u1", incident_id="i1")


# 10. AI resolve 拒绝 ---------------------------------------------------- #
def test_ai_resolve_rejected(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.incidents.resolve(incident_id="i1", actor_id="ai", actor_kind="ai")


# 11. USER resolve ------------------------------------------------------- #
def test_user_resolve(svc: ProductionObservabilityService) -> None:
    inc = svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    svc.incidents.acknowledge(incident_id="i1", actor_id="u1", actor_kind="user")
    resolved = svc.incidents.resolve(incident_id="i1", actor_id="u1", actor_kind="user")
    assert resolved.status == IncidentStatus.RESOLVED_BY_HUMAN
    svc.record_incident_resolved(actor_id="u1", incident_id="i1")


# 12. AI close 拒绝 ------------------------------------------------------ #
def test_ai_close_rejected(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.incidents.close(incident_id="i1", actor_id="ai", actor_kind="ai")


# 13. USER close --------------------------------------------------------- #
def test_user_close(svc: ProductionObservabilityService) -> None:
    inc = svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    svc.incidents.acknowledge(incident_id="i1", actor_id="u1", actor_kind="user")
    svc.incidents.resolve(incident_id="i1", actor_id="u1", actor_kind="user")
    closed = svc.incidents.close(incident_id="i1", actor_id="u1", actor_kind="user")
    assert closed.status == IncidentStatus.CLOSED_BY_HUMAN
    svc.record_incident_closed(actor_id="u1", incident_id="i1")


# 14. Commander 必须 USER ------------------------------------------------ #
def test_commander_must_be_user(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.incidents.assign_commander(
            assignment_id="as1", incident_id="i1", commander_id="c1",
            assigned_by="ai", actor_kind="ai",
        )
    asg = svc.incidents.assign_commander(
        assignment_id="as2", incident_id="i1", commander_id="c1",
        assigned_by="u1", actor_kind="user", recommended_by_ai=True,
    )
    assert asg.actor_kind == "user"
    assert asg.recommended_by_ai is True


# 15. Timeline append-only ---------------------------------------------- #
def test_timeline_append_only(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    svc.incidents.append_timeline(
        incident_id="i1", actor_id="u1", actor_kind="user", action="acknowledge",
    )
    svc.incidents.append_timeline(
        incident_id="i1", actor_id="u1", actor_kind="user", action="resolve",
    )
    tl = svc.incidents.timeline("i1")
    assert len(tl) == 2
    assert tl[0]["action"] == "acknowledge" and tl[1]["action"] == "resolve"
    # 返回的是不可变拷贝
    tl.append({"hacked": True})  # type: ignore
    assert len(svc.incidents.timeline("i1")) == 2


# 16. Runbook 只引用不执行 ---------------------------------------------- #
def test_runbook_reference_only(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    ref = svc.incidents.reference_runbook(
        runbook_id="rb1", path=".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
        title="回滚", incident_id="i1", applicable=True,
    )
    assert ref.applicable is True
    inc = svc.incidents.get("i1")
    assert inc is not None and inc.runbook_reference.endswith("PRODUCTION_ROLLBACK_RUNBOOK.md")
    # 确认服务层没有"执行"方法（forbidden 名由全局集拦截，此处只验证引用存在）
    assert not hasattr(svc.incidents, "execute_runbook")


# 17. Recovery Validation (只读) ---------------------------------------- #
def test_recovery_validation(svc: ProductionObservabilityService) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    val = svc.incidents.record_recovery_validation(
        validation_id="v1", incident_id="i1",
        service_health=ServiceHealthStatus.HEALTHY, error_rate_ok=True,
        dependency_health_ok=True, database_health_ok=True,
        identity_health_ok=True, governance_health_ok=True,
        validated_by="u1", actor_kind="user",
    )
    assert val.passed is True
    inc = svc.incidents.get("i1")
    # 红线⑨：恢复校验通过仅推进到 RECOVERY_VALIDATION，不自动 RESOLVED
    assert inc is not None and inc.status == IncidentStatus.RECOVERY_VALIDATION
    # AI 校验拒绝
    with pytest.raises(EnterpriseRedLineViolationError):
        svc.incidents.record_recovery_validation(
            validation_id="v2", incident_id="i1",
            service_health=ServiceHealthStatus.HEALTHY, error_rate_ok=True,
            dependency_health_ok=True, database_health_ok=True,
            identity_health_ok=True, governance_health_ok=True,
            validated_by="ai", actor_kind="ai",
        )


# 18. Root Cause pending verification ----------------------------------- #
def test_root_cause_pending_verification(svc: ProductionObservabilityService) -> None:
    # 无证据 → PENDING_VERIFICATION 合法
    pm = svc.incidents.create_postmortem(
        postmortem_id="pm1", incident_id="i1", summary="s",
        timeline=[], impact="i", authored_by="u1", actor_kind="user",
        contributing_factors=["f"], unresolved_questions=["q"],
        follow_up_candidates=["fu"],
    )
    assert pm.root_cause_status == RootCauseStatus.PENDING_VERIFICATION
    assert pm.root_cause == ""
    # 声称 identified 却无 root_cause → 伪造，红线⑫拒绝
    with pytest.raises(ValueError):
        svc.incidents.create_postmortem(
            postmortem_id="pm2", incident_id="i1", summary="s",
            timeline=[], impact="i", authored_by="u1", actor_kind="user",
            root_cause_status=RootCauseStatus.IDENTIFIED, root_cause="",
            contributing_factors=["f"], unresolved_questions=["q"],
            follow_up_candidates=["fu"],
        )


# 19. Release correlation (只提供 rollback_reference) ------------------- #
def test_release_correlation(svc: ProductionObservabilityService) -> None:
    inc = svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="x",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    corr = svc.correlate_release(
        incident=inc, release_id="RC-3.9.2", commit_sha="abc",
        manifest_reference="docs/...", evidence_reference="evidence/...",
        rollback_reference=".ai/runbooks/PRODUCTION_ROLLBACK_RUNBOOK.md",
    )
    assert corr["release_id"] == "RC-3.9.2"
    # 红线⑤：绝不自动 rollback
    assert corr["auto_rollback"] is False
    assert corr["rollback_reference"].endswith("PRODUCTION_ROLLBACK_RUNBOOK.md")


# 20. Security correlation ----------------------------------------------- #
def test_security_correlation(svc: ProductionObservabilityService) -> None:
    signals = [
        {"category": "identity_failure", "ts": "t1"},
        {"category": "identity_failure", "ts": "t2"},
        {"category": "permission_denied", "ts": "t3"},
    ]
    cands = svc.correlate_security_signals(organization_id=ORG_A, signals=signals)
    cats = {c.related_audit_categories[0] for c in cands}
    assert "identity_failure" in cats and "permission_denied" in cats
    # 红线⑪：真实阈值默认未验证
    assert all(not c.threshold_verified for c in cands)


# 21. Cross-org isolation ------------------------------------------------ #
def test_cross_org_isolation(
    svc: ProductionObservabilityService, svc_b: ProductionObservabilityService
) -> None:
    svc.incidents.create_incident(
        incident_id="i1", organization_id=ORG_A, title="a-inc",
        severity=IncidentSeverity.SEV1, related_alert_ids=["a1"], component="backend",
    )
    svc_b.incidents.create_incident(
        incident_id="i1", organization_id=ORG_B, title="b-inc",
        severity=IncidentSeverity.SEV2, related_alert_ids=["a2"], component="database",
    )
    a = svc.incidents.get("i1")
    b = svc_b.incidents.get("i1")
    assert a is not None and a.organization_id == ORG_A
    assert b is not None and b.organization_id == ORG_B
    assert a.title == "a-inc" and b.title == "b-inc"
    # 安全关联按组织隔离输出
    ca = svc.correlate_security_signals(
        organization_id=ORG_A, signals=[{"category": "identity_failure", "ts": "t"}]
    )
    cb = svc_b.correlate_security_signals(
        organization_id=ORG_B, signals=[{"category": "identity_failure", "ts": "t"}]
    )
    assert ca[0].organization_id == ORG_A and cb[0].organization_id == ORG_B


# 22. forbidden 名结构拦截（AI 代指挥 / 自动回滚 / 自动关闭）----------- #
def test_forbidden_methods_structurally_blocked(
    svc: ProductionObservabilityService
) -> None:
    for name in (
        "auto_rollback_incident",
        "auto_resolve_incident",
        "auto_close_incident",
        "assign_self_as_commander",
        "act_as_incident_commander",
        "silence_alert",
        "fabricate_observability_evidence",
    ):
        with pytest.raises(EnterpriseRedLineViolationError):
            getattr(svc, name)()


# 附加：审计类存在性复校（禁止硬编码总数；权威总数断言仅见
# tests/agents/test_enterprise_knowledge_governance_audit.py）。此处仅校验 Phase 3.9.3
# 可观测性 / 事故响应类确实已注册，避免重复硬编码 == N 破坏全仓唯一性红线。
def test_audit_category_observability_present() -> None:
    present = set(AuditActionCategory.__members__)
    assert {
        "OBSERVABILITY_HEALTH_CHECK",
        "ALERT_CANDIDATE_CREATED",
        "INCIDENT_CREATED",
        "INCIDENT_HUMAN_ACKNOWLEDGED",
        "INCIDENT_HUMAN_RESOLVED",
        "INCIDENT_HUMAN_CLOSED",
        "POSTMORTEM_DRAFT_CREATED",
    } <= present


# 附加：engineering_enabled 仍 False（红线①）
def test_engineering_enabled_still_false() -> None:
    from agents.config_loader import load_engineering_enabled

    assert load_engineering_enabled() is False
