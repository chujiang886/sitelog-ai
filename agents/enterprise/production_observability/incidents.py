"""Phase 3.9.3 事故服务（T8-T16）。状态机无 AUTO_*；ACK/RESOLVE/CLOSE 必须 USER。

红线纪律：
- 时间线 append-only（T10）：只追加，禁止修改 / 删除历史（复用 AuditService 理念）。
- 指挥官指派 actor_kind 必须 USER（T11）；AI 不得 self-assign（forbidden 名已拦截）。
- 恢复校验只读（T14）；不得宣布 resolved（红线⑨）。
- 复盘 Root Cause 无证据必须 PENDING_VERIFICATION（T15，红线⑫）。
- 后续事项仅创建候选，复用既有治理编排 / 人工审阅，不直接改治理知识（T16）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from agents.enterprise.production_observability.models import (
    IncidentCandidate,
    IncidentCommanderAssignment,
    IncidentFollowUpCandidate,
    IncidentPostmortemDraft,
    IncidentRecoveryValidation,
    IncidentResponseDraft,
    IncidentRunbookReference,
    IncidentSeverity,
    IncidentStatus,
    IncidentTimelineEvent,
    ProductionIncident,
    RootCauseStatus,
    ServiceHealthStatus,
)
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class IncidentService(_RedLineForbiddenMixin):
    """事故服务（T8-T16）。"""

    _FORBIDDEN = ()  # 本服务无自身禁名增量；AI 越权动作由 forbidden.py 全局集拦截。

    def __init__(self, *, root_dir: str = ".") -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._root_dir = root_dir
        self._incidents: Dict[str, ProductionIncident] = {}
        self._timelines: Dict[str, List[IncidentTimelineEvent]] = {}
        self._postmortems: Dict[str, IncidentPostmortemDraft] = {}
        self._validations: Dict[str, List[IncidentRecoveryValidation]] = {}

    # ------------------------------------------------------------------ #
    # 创建（AI 可由告警候选生成正式 Incident，DETECTED 态）
    # ------------------------------------------------------------------ #
    def create_incident(
        self,
        *,
        incident_id: str,
        organization_id: str,
        title: str,
        severity: IncidentSeverity,
        related_alert_ids: List[str],
        component: str,
        evidence: str = "",
        detected_at: Optional[str] = None,
    ) -> ProductionIncident:
        inc = ProductionIncident(
            incident_id=incident_id,
            organization_id=organization_id,
            title=title,
            severity=severity,
            status=IncidentStatus.DETECTED,
            detected_at=detected_at or _now(),
            affected_components=[component],
            evidence=evidence,
            trace_ids=[],
            workflow_ids=[],
            release_id=None,
        )
        self._incidents[incident_id] = inc
        self._timelines[incident_id] = []
        return inc

    def from_candidate(
        self, *, candidate: IncidentCandidate, incident_id: str
    ) -> ProductionIncident:
        return self.create_incident(
            incident_id=incident_id,
            organization_id=candidate.organization_id,
            title=candidate.title,
            severity=candidate.severity,
            related_alert_ids=candidate.related_alert_ids,
            component=candidate.component,
            evidence=candidate.evidence,
            detected_at=candidate.detected_at,
        )

    # ------------------------------------------------------------------ #
    # 时间线 append-only（T10）
    # ------------------------------------------------------------------ #
    def append_timeline(
        self,
        *,
        incident_id: str,
        actor_id: str,
        actor_kind: str,
        action: str,
        evidence: str = "",
        trace_reference: str = "",
        timestamp: Optional[str] = None,
        event_id: Optional[str] = None,
    ) -> IncidentTimelineEvent:
        # 所有时间线责任节点必须 USER（红线⑩），模型构造即校验。
        ev = IncidentTimelineEvent(
            event_id=event_id or f"tle-{len(self._timelines.get(incident_id, []))}",
            incident_id=incident_id,
            timestamp=timestamp or _now(),
            actor_id=actor_id,
            actor_kind=actor_kind,
            action=action,
            evidence=evidence,
            trace_reference=trace_reference,
        )
        self._timelines.setdefault(incident_id, []).append(ev)
        return ev

    def timeline(self, incident_id: str) -> List[Dict[str, Any]]:
        # 返回不可变拷贝，禁止调用方篡改历史。
        return [e.to_dict() for e in self._timelines.get(incident_id, [])]

    # ------------------------------------------------------------------ #
    # 人工 ACK（USER 强制）
    # ------------------------------------------------------------------ #
    def acknowledge(
        self, *, incident_id: str, actor_id: str, actor_kind: str,
        acknowledged_at: Optional[str] = None,
    ) -> ProductionIncident:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "事故 ACK 必须由真实 USER 执行（红线⑩）"
            )
        inc = self._incidents[incident_id]
        inc.status = IncidentStatus.HUMAN_ACKNOWLEDGED
        inc.acknowledged_at = acknowledged_at or _now()
        self.append_timeline(
            incident_id=incident_id, actor_id=actor_id, actor_kind=actor_kind,
            action="acknowledge", evidence=f"ack_by={actor_id}",
        )
        return inc

    # ------------------------------------------------------------------ #
    # 指挥官指派（USER 强制，T11）
    # ------------------------------------------------------------------ #
    def assign_commander(
        self,
        *,
        assignment_id: str,
        incident_id: str,
        commander_id: str,
        assigned_by: str,
        actor_kind: str,
        assigned_at: Optional[str] = None,
        recommended_by_ai: bool = False,
    ) -> IncidentCommanderAssignment:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "指挥官指派必须由真实 USER 执行（红线⑩）"
            )
        assignment = IncidentCommanderAssignment(
            assignment_id=assignment_id,
            incident_id=incident_id,
            commander_id=commander_id,
            assigned_by=assigned_by,
            actor_kind=actor_kind,
            assigned_at=assigned_at or _now(),
            recommended_by_ai=recommended_by_ai,
        )
        inc = self._incidents.get(incident_id)
        if inc is not None:
            inc.commander = commander_id
            inc.status = IncidentStatus.INVESTIGATING
            self.append_timeline(
                incident_id=incident_id, actor_id=assigned_by, actor_kind=actor_kind,
                action="assign_commander", evidence=f"commander={commander_id}",
            )
        return assignment

    # ------------------------------------------------------------------ #
    # Runbook 引用（T12，只引用不执行）
    # ------------------------------------------------------------------ #
    def reference_runbook(
        self, *, runbook_id: str, path: str, title: str, incident_id: str,
        applicable: bool = False,
    ) -> IncidentRunbookReference:
        ref = IncidentRunbookReference(
            runbook_id=runbook_id, path=path, title=title, applicable=applicable
        )
        inc = self._incidents.get(incident_id)
        if inc is not None:
            inc.runbook_reference = path
        return ref

    # ------------------------------------------------------------------ #
    # 响应草稿（T13，requires_human_review 恒 True）
    # ------------------------------------------------------------------ #
    def build_response_draft(
        self,
        *,
        draft_id: str,
        incident_id: str,
        facts: str,
        impact_scope: str,
        known_anomalies: List[str],
        suggested_human_steps: List[str],
        trace_reference: str = "",
        related_release_id: Optional[str] = None,
        related_runbook_ids: Optional[List[str]] = None,
    ) -> IncidentResponseDraft:
        return IncidentResponseDraft(
            draft_id=draft_id,
            incident_id=incident_id,
            facts=facts,
            impact_scope=impact_scope,
            known_anomalies=known_anomalies,
            trace_reference=trace_reference,
            related_release_id=related_release_id,
            related_runbook_ids=related_runbook_ids,
            suggested_human_steps=suggested_human_steps,
            requires_human_review=True,
        )

    # ------------------------------------------------------------------ #
    # 恢复校验（T14，只读；不得宣布 resolved）
    # ------------------------------------------------------------------ #
    def record_recovery_validation(
        self,
        *,
        validation_id: str,
        incident_id: str,
        service_health: ServiceHealthStatus,
        error_rate_ok: bool,
        dependency_health_ok: bool,
        database_health_ok: bool,
        identity_health_ok: bool,
        governance_health_ok: bool,
        validated_by: str,
        actor_kind: str,
        validated_at: Optional[str] = None,
    ) -> IncidentRecoveryValidation:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "恢复校验必须由真实 USER 执行（红线⑩）"
            )
        passed = (
            service_health != ServiceHealthStatus.UNHEALTHY
            and error_rate_ok
            and dependency_health_ok
            and database_health_ok
            and identity_health_ok
            and governance_health_ok
        )
        val = IncidentRecoveryValidation(
            validation_id=validation_id,
            incident_id=incident_id,
            service_health=service_health,
            error_rate_ok=error_rate_ok,
            dependency_health_ok=dependency_health_ok,
            database_health_ok=database_health_ok,
            identity_health_ok=identity_health_ok,
            governance_health_ok=governance_health_ok,
            passed=passed,
            validated_by=validated_by,
            actor_kind=actor_kind,
            validated_at=validated_at or _now(),
        )
        self._validations.setdefault(incident_id, []).append(val)
        inc = self._incidents.get(incident_id)
        if inc is not None:
            # 校验通过仅推进到 RECOVERY_VALIDATION；最终 RESOLVED 仍须 USER（红线⑨）。
            if passed and inc.status != IncidentStatus.RESOLVED_BY_HUMAN:
                inc.status = IncidentStatus.RECOVERY_VALIDATION
            self.append_timeline(
                incident_id=incident_id, actor_id=validated_by, actor_kind=actor_kind,
                action="recovery_validation", evidence=f"passed={passed}",
            )
        return val

    # ------------------------------------------------------------------ #
    # 人工 RESOLVE（USER 强制）
    # ------------------------------------------------------------------ #
    def resolve(
        self, *, incident_id: str, actor_id: str, actor_kind: str,
        resolved_at: Optional[str] = None,
    ) -> ProductionIncident:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "事故 RESOLVE 必须由真实 USER 执行（红线⑨/⑩）"
            )
        inc = self._incidents[incident_id]
        inc.status = IncidentStatus.RESOLVED_BY_HUMAN
        inc.resolved_at = resolved_at or _now()
        self.append_timeline(
            incident_id=incident_id, actor_id=actor_id, actor_kind=actor_kind,
            action="resolve", evidence=f"resolved_by={actor_id}",
        )
        return inc

    # ------------------------------------------------------------------ #
    # 复盘草稿（T15，USER 强制，root cause 无证据 pending）
    # ------------------------------------------------------------------ #
    def create_postmortem(
        self,
        *,
        postmortem_id: str,
        incident_id: str,
        summary: str,
        timeline: List[Dict[str, Any]],
        impact: str,
        authored_by: str,
        actor_kind: str,
        contributing_factors: List[str],
        unresolved_questions: List[str],
        follow_up_candidates: List[str],
        evidence: str = "",
        root_cause: str = "",
        root_cause_status: RootCauseStatus = RootCauseStatus.PENDING_VERIFICATION,
        mitigation: str = "",
        recovery: str = "",
    ) -> IncidentPostmortemDraft:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "复盘草稿必须由真实 USER 撰写（红线⑩）"
            )
        pm = IncidentPostmortemDraft(
            postmortem_id=postmortem_id,
            incident_id=incident_id,
            summary=summary,
            timeline=timeline,
            impact=impact,
            evidence=evidence,
            root_cause_status=root_cause_status,
            root_cause=root_cause,
            contributing_factors=contributing_factors,
            mitigation=mitigation,
            recovery=recovery,
            unresolved_questions=unresolved_questions,
            follow_up_candidates=follow_up_candidates,
            authored_by=authored_by,
            actor_kind=actor_kind,
        )
        self._postmortems[incident_id] = pm
        inc = self._incidents.get(incident_id)
        if inc is not None:
            inc.status = IncidentStatus.POSTMORTEM_PENDING
        return pm

    # ------------------------------------------------------------------ #
    # 人工 CLOSE（USER 强制）
    # ------------------------------------------------------------------ #
    def close(
        self, *, incident_id: str, actor_id: str, actor_kind: str,
        closed_at: Optional[str] = None,
    ) -> ProductionIncident:
        if actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "事故 CLOSE 必须由真实 USER 执行（红线⑨/⑩）"
            )
        inc = self._incidents[incident_id]
        inc.status = IncidentStatus.CLOSED_BY_HUMAN
        self.append_timeline(
            incident_id=incident_id, actor_id=actor_id, actor_kind=actor_kind,
            action="close", evidence=f"closed_by={actor_id}",
        )
        return inc

    # ------------------------------------------------------------------ #
    # 后续事项候选（T16，仅候选，复用既有治理编排由调用方负责）
    # ------------------------------------------------------------------ #
    def create_follow_up_candidate(
        self,
        *,
        candidate_id: str,
        incident_id: str,
        kind: str,
        title: str,
        detail: str = "",
    ) -> IncidentFollowUpCandidate:
        return IncidentFollowUpCandidate(
            candidate_id=candidate_id,
            incident_id=incident_id,
            kind=kind,
            title=title,
            detail=detail,
            pending_human_review=True,
        )

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #
    def get(self, incident_id: str) -> Optional[ProductionIncident]:
        return self._incidents.get(incident_id)

    def all(self) -> List[ProductionIncident]:
        return list(self._incidents.values())

    def postmortem(self, incident_id: str) -> Optional[IncidentPostmortemDraft]:
        return self._postmortems.get(incident_id)

    def validations(self, incident_id: str) -> List[Dict[str, Any]]:
        return [v.to_dict() for v in self._validations.get(incident_id, [])]
