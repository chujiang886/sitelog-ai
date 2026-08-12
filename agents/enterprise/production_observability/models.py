"""Phase 3.9.3 企业生产可观测性、SRE 与事故响应准备层 —— 领域模型（T1, T2, T6, T8-T16）。

设计纪律（fail-closed，红线①~⑫）：

- 所有模型**只描述事实**，不承载任何治理 / 修复 / 部署 / 关闭动作语义。
- 健康状态 UNKNOWN **永不**被推断为 HEALTHY（红线⑨/⑩/⑪）。
- 告警 / 事故状态无 AUTO_RESOLVED / AUTO_CLOSED / AI_APPROVED（红线⑨/⑩）。
- 所有人工责任节点（ACK / RESOLVE / CLOSE / 指派指挥官 / 复盘签署）的 actor_kind
  必须 ``"user"``（红线⑩）。
- 无法真实验证的阈值 / 业务 SLA 一律 ``pending_verification`` 或 ``simulation_only=True``
  （红线⑪：禁止把测试阈值写成生产承诺）。
- 复盘 Root Cause 无证据时 ``root_cause_status == PENDING_VERIFICATION``，禁止 AI 编造
  （红线⑫）。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4

from agents.enterprise.production_observability.forbidden import (
    PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT,
)


# ===================================================================== #
# T2 服务健康
# ===================================================================== #
class ServiceHealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"

    @classmethod
    def is_operational(cls, status: "ServiceHealthStatus") -> bool:
        # UNKNOWN 不得自动当 HEALTHY（红线⑨/⑪）。
        return status in (cls.HEALTHY, cls.DEGRADED)


class ObservableComponent(str, Enum):
    """可被监测的组件（T2 要求的 11+ 类）。"""

    BACKEND = "backend"
    FRONTEND = "frontend"
    DATABASE = "database"
    IDENTITY = "identity"
    GOVERNANCE_WORKFLOW = "governance_workflow"
    AUDIT = "audit"
    RELEASE_GATE = "release_gate"
    VOICE_RUNTIME = "voice_runtime"
    LLM_PROVIDER = "llm_provider"
    ASR = "asr"
    TTS = "tts"


class ServiceHealth:
    """统一健康状态快照（T2）。"""

    def __init__(
        self,
        *,
        component: str,
        status: ServiceHealthStatus,
        checked_at: str,
        source: str,
        evidence: str = "",
        latency_ms: Optional[float] = None,
        error: str = "",
        trace_reference: str = "",
    ) -> None:
        self.component = component
        self.status = status
        self.checked_at = checked_at
        self.source = source
        self.evidence = evidence
        self.latency_ms = latency_ms
        self.error = error
        self.trace_reference = trace_reference

    def to_dict(self) -> Dict[str, Any]:
        return {
            "component": self.component,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "source": self.source,
            "evidence": self.evidence,
            "latency_ms": self.latency_ms,
            "error": self.error,
            "trace_reference": self.trace_reference,
        }


# ===================================================================== #
# T3 指标层
# ===================================================================== #
class MetricCategory(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    IDENTITY = "identity"
    GOVERNANCE = "governance"
    AI_RUNTIME = "ai_runtime"
    RELEASE = "release"


class MetricSnapshot:
    """标准指标快照（T3）。所有数值均为**事实描述**，标记来源是否为模拟。"""

    def __init__(
        self,
        *,
        metric_id: str,
        category: MetricCategory,
        component: str,
        window: str,  # 例如 "5m" / "1h"
        values: Dict[str, float],  # 例如 {"request_count": 1200, "availability_ratio": 0.999}
        source: str,
        simulation_only: bool = False,  # 红线⑪：模拟数据必须显式标记
        checked_at: str,
    ) -> None:
        self.metric_id = metric_id
        self.category = category
        self.component = component
        self.window = window
        self.values = values
        self.source = source
        self.simulation_only = simulation_only
        self.checked_at = checked_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "category": self.category.value,
            "component": self.component,
            "window": self.window,
            "values": dict(self.values),
            "source": self.source,
            "simulation_only": self.simulation_only,
            "checked_at": self.checked_at,
        }


# ===================================================================== #
# T4 SLI / SLO
# ===================================================================== #
class SLOKind(str, Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    ERROR_RATE = "error_rate"


class SLIDefinition:
    """服务等级指标（SLI）定义。"""

    def __init__(
        self,
        *,
        sli_id: str,
        name: str,
        component: str,
        expression: str,
        simulation_only: bool = True,  # 仓库无真实业务目标，默认模拟
    ) -> None:
        self.sli_id = sli_id
        self.name = name
        self.component = component
        self.expression = expression
        self.simulation_only = simulation_only

    def to_dict(self) -> Dict[str, Any]:
        return {
            "sli_id": self.sli_id,
            "name": self.name,
            "component": self.component,
            "expression": self.expression,
            "simulation_only": self.simulation_only,
        }


class SLOStatus(str, Enum):
    MET = "met"
    AT_RISK = "at_risk"
    BREACHED = "breached"
    PENDING_VERIFICATION = "pending_verification"


class SLODefinition:
    """服务等级目标（SLO）。阈值若无法真实验证一律 pending_verification。"""

    def __init__(
        self,
        *,
        slo_id: str,
        name: str,
        component: str,
        kind: SLOKind,
        target: float,  # 例如 0.999
        window: str = "30d",
        threshold_verified: bool = False,  # 真实业务阈值？否则 pending_verification
        status: SLOStatus = SLOStatus.PENDING_VERIFICATION,
    ) -> None:
        self.slo_id = slo_id
        self.name = name
        self.component = component
        self.kind = kind
        self.target = target
        self.window = window
        self.threshold_verified = threshold_verified
        self.status = status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slo_id": self.slo_id,
            "name": self.name,
            "component": self.component,
            "kind": self.kind.value,
            "target": self.target,
            "window": self.window,
            "threshold_verified": self.threshold_verified,
            "status": self.status.value,
        }


# ===================================================================== #
# T5 错误预算
# ===================================================================== #
class ErrorBudget:
    """错误预算（T5）。只生成状态 / 证据 / 警告，绝不自动停发布 / 自动回滚。"""

    def __init__(
        self,
        *,
        slo_id: str,
        budget_total: float,  # 允许的失败额度（例如 0.1% → 0.001）
        consumed: float,
        window: str = "30d",
        human_review_required: bool = False,
    ) -> None:
        self.slo_id = slo_id
        self.budget_total = budget_total
        self.consumed = consumed
        self.window = window
        self.human_review_required = human_review_required

    @property
    def remaining(self) -> float:
        return max(0.0, self.budget_total - self.consumed)

    @property
    def warning(self) -> bool:
        if self.budget_total <= 0:
            return False
        return (self.consumed / self.budget_total) >= 0.8

    def to_dict(self) -> Dict[str, Any]:
        return {
            "slo_id": self.slo_id,
            "budget_total": self.budget_total,
            "consumed": self.consumed,
            "remaining": self.remaining,
            "window": self.window,
            "warning": self.warning,
            "human_review_required": self.human_review_required,
        }


# ===================================================================== #
# T6 / T7 告警候选 + 关联
# ===================================================================== #
class AlertStatus(str, Enum):
    DETECTED = "detected"
    ACKNOWLEDGEMENT_REQUIRED = "acknowledgement_required"
    ACKNOWLEDGED_BY_HUMAN = "acknowledged_by_human"
    RESOLVED_BY_HUMAN = "resolved_by_human"


class AlertCandidate:
    """告警候选（T6）。AI 可检测 / 聚合 / 生成；确认 / 解决必须人工。"""

    def __init__(
        self,
        *,
        alert_id: str,
        component: str,
        title: str,
        severity: str,
        status: AlertStatus = AlertStatus.DETECTED,
        detection_source: str,
        fingerprint: str,
        related_incident_id: Optional[str] = None,
        trace_ids: Optional[List[str]] = None,
        workflow_ids: Optional[List[str]] = None,
        release_id: Optional[str] = None,
        evidence: str = "",
        simulation_only: bool = False,
        detected_at: str,
    ) -> None:
        self.alert_id = alert_id
        self.component = component
        self.title = title
        self.severity = severity
        self.status = status
        self.detection_source = detection_source
        self.fingerprint = fingerprint
        self.related_incident_id = related_incident_id
        self.trace_ids = trace_ids or []
        self.workflow_ids = workflow_ids or []
        self.release_id = release_id
        self.evidence = evidence
        self.simulation_only = simulation_only
        self.detected_at = detected_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "component": self.component,
            "title": self.title,
            "severity": self.severity,
            "status": self.status.value,
            "detection_source": self.detection_source,
            "fingerprint": self.fingerprint,
            "related_incident_id": self.related_incident_id,
            "trace_ids": list(self.trace_ids),
            "workflow_ids": list(self.workflow_ids),
            "release_id": self.release_id,
            "evidence": self.evidence,
            "simulation_only": self.simulation_only,
            "detected_at": self.detected_at,
        }


class ObservabilityCorrelation:
    """关联结果（T7）。确定性优先：仅当能证明同一根因才合并。"""

    def __init__(
        self,
        *,
        correlation_id: str,
        fingerprint: str,
        component: str,
        organization_id: str,
        related_alert_ids: List[str],
        related_incident_id: Optional[str] = None,
        time_window: str = "",
        merged: bool = False,  # 仅当确证同一根因才 True
        evidence: str = "",
    ) -> None:
        self.correlation_id = correlation_id
        self.fingerprint = fingerprint
        self.component = component
        self.organization_id = organization_id
        self.related_alert_ids = related_alert_ids
        self.related_incident_id = related_incident_id
        self.time_window = time_window
        self.merged = merged
        self.evidence = evidence

    def to_dict(self) -> Dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "fingerprint": self.fingerprint,
            "component": self.component,
            "organization_id": self.organization_id,
            "related_alert_ids": list(self.related_alert_ids),
            "related_incident_id": self.related_incident_id,
            "time_window": self.time_window,
            "merged": self.merged,
            "evidence": self.evidence,
        }


# ===================================================================== #
# T8 / T9 / T13 事故模型 + 严重度 + 时间线
# ===================================================================== #
class IncidentStatus(str, Enum):
    DETECTED = "detected"
    HUMAN_ACKNOWLEDGED = "human_acknowledged"
    INVESTIGATING = "investigating"
    MITIGATION_IN_PROGRESS = "mitigation_in_progress"
    RECOVERY_VALIDATION = "recovery_validation"
    RESOLVED_BY_HUMAN = "resolved_by_human"
    POSTMORTEM_PENDING = "postmortem_pending"
    CLOSED_BY_HUMAN = "closed_by_human"


class IncidentSeverity(str, Enum):
    SEV0 = "sev0"
    SEV1 = "sev1"
    SEV2 = "sev2"
    SEV3 = "sev3"


class IncidentCandidate:
    """事故候选（T6/T8）。由 AI 基于告警聚合生成；仍需人工确认后才成为正式 Incident。"""

    def __init__(
        self,
        *,
        candidate_id: str,
        organization_id: str,
        title: str,
        severity: IncidentSeverity,
        related_alert_ids: List[str],
        component: str,
        evidence: str = "",
        detected_at: str,
    ) -> None:
        self.candidate_id = candidate_id
        self.organization_id = organization_id
        self.title = title
        self.severity = severity
        self.related_alert_ids = related_alert_ids
        self.component = component
        self.evidence = evidence
        self.detected_at = detected_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "organization_id": self.organization_id,
            "title": self.title,
            "severity": self.severity.value,
            "related_alert_ids": list(self.related_alert_ids),
            "component": self.component,
            "evidence": self.evidence,
            "detected_at": self.detected_at,
        }


class IncidentTimelineEvent:
    """事故时间线事件（T10）。append-only，复用 AuditService 理念，禁止修改/删除历史。"""

    def __init__(
        self,
        *,
        event_id: str,
        incident_id: str,
        timestamp: str,
        actor_id: str,
        actor_kind: str,  # 必须 "user"
        action: str,
        evidence: str = "",
        trace_reference: str = "",
    ) -> None:
        if actor_kind != "user":
            # 红线⑩：任何时间线责任节点必须由真实 USER 发起。
            raise ValueError("IncidentTimelineEvent.actor_kind 必须为 'user'（红线⑩）")
        self.event_id = event_id
        self.incident_id = incident_id
        self.timestamp = timestamp
        self.actor_id = actor_id
        self.actor_kind = actor_kind
        self.action = action
        self.evidence = evidence
        self.trace_reference = trace_reference

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "incident_id": self.incident_id,
            "timestamp": self.timestamp,
            "actor_id": self.actor_id,
            "actor_kind": self.actor_kind,
            "action": self.action,
            "evidence": self.evidence,
            "trace_reference": self.trace_reference,
        }


class ProductionIncident:
    """正式事故（T8）。状态机无 AUTO_*；最终 RESOLVED/CLOSED 必须由 USER。"""

    def __init__(
        self,
        *,
        incident_id: str,
        organization_id: str,
        title: str,
        severity: IncidentSeverity,
        status: IncidentStatus = IncidentStatus.DETECTED,
        detected_at: str,
        acknowledged_at: Optional[str] = None,
        resolved_at: Optional[str] = None,
        commander: Optional[str] = None,
        affected_components: Optional[List[str]] = None,
        evidence: str = "",
        trace_ids: Optional[List[str]] = None,
        release_id: Optional[str] = None,
        workflow_ids: Optional[List[str]] = None,
        runbook_reference: Optional[str] = None,
    ) -> None:
        self.incident_id = incident_id
        self.organization_id = organization_id
        self.title = title
        self.severity = severity
        self.status = status
        self.detected_at = detected_at
        self.acknowledged_at = acknowledged_at
        self.resolved_at = resolved_at
        self.commander = commander
        self.affected_components = affected_components or []
        self.evidence = evidence
        self.trace_ids = trace_ids or []
        self.release_id = release_id
        self.workflow_ids = workflow_ids or []
        self.runbook_reference = runbook_reference

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "organization_id": self.organization_id,
            "title": self.title,
            "severity": self.severity.value,
            "status": self.status.value,
            "detected_at": self.detected_at,
            "acknowledged_at": self.acknowledged_at,
            "resolved_at": self.resolved_at,
            "commander": self.commander,
            "affected_components": list(self.affected_components),
            "evidence": self.evidence,
            "trace_ids": list(self.trace_ids),
            "release_id": self.release_id,
            "workflow_ids": list(self.workflow_ids),
            "runbook_reference": self.runbook_reference,
        }


# ===================================================================== #
# T11 事故指挥官指派
# ===================================================================== #
class IncidentCommanderAssignment:
    """事故指挥官指派（T11）。actor_kind 必须 USER；AI 不能 self-assign。"""

    def __init__(
        self,
        *,
        assignment_id: str,
        incident_id: str,
        commander_id: str,
        assigned_by: str,
        actor_kind: str = "user",
        assigned_at: str,
        recommended_by_ai: bool = False,  # AI 可推荐候选角色，但最终指派必须 USER
    ) -> None:
        if actor_kind != "user":
            raise ValueError("IncidentCommanderAssignment.actor_kind 必须为 'user'（红线⑩）")
        self.assignment_id = assignment_id
        self.incident_id = incident_id
        self.commander_id = commander_id
        self.assigned_by = assigned_by
        self.actor_kind = actor_kind
        self.assigned_at = assigned_at
        self.recommended_by_ai = recommended_by_ai

    def to_dict(self) -> Dict[str, Any]:
        return {
            "assignment_id": self.assignment_id,
            "incident_id": self.incident_id,
            "commander_id": self.commander_id,
            "assigned_by": self.assigned_by,
            "actor_kind": self.actor_kind,
            "assigned_at": self.assigned_at,
            "recommended_by_ai": self.recommended_by_ai,
        }


# ===================================================================== #
# T12 事故 Runbook 注册表引用
# ===================================================================== #
class IncidentRunbookReference:
    """事故可关联的 Runbook 引用（T12）。AI 只引用，不执行。"""

    def __init__(
        self,
        *,
        runbook_id: str,
        path: str,
        title: str,
        applicable: bool = False,  # 由人工判定是否适用
    ) -> None:
        self.runbook_id = runbook_id
        self.path = path
        self.title = title
        self.applicable = applicable

    def to_dict(self) -> Dict[str, Any]:
        return {
            "runbook_id": self.runbook_id,
            "path": self.path,
            "title": self.title,
            "applicable": self.applicable,
        }


# ===================================================================== #
# T13 事故响应草稿
# ===================================================================== #
class IncidentResponseDraft:
    """事故响应草稿（T13）。requires_human_review 恒 True；AI 不执行修复。"""

    def __init__(
        self,
        *,
        draft_id: str,
        incident_id: str,
        facts: str,
        impact_scope: str,
        known_anomalies: List[str],
        trace_reference: str = "",
        related_release_id: Optional[str] = None,
        related_runbook_ids: Optional[List[str]] = None,
        suggested_human_steps: List[str],
        requires_human_review: bool = True,
    ) -> None:
        self.draft_id = draft_id
        self.incident_id = incident_id
        self.facts = facts
        self.impact_scope = impact_scope
        self.known_anomalies = known_anomalies
        self.trace_reference = trace_reference
        self.related_release_id = related_release_id
        self.related_runbook_ids = related_runbook_ids or []
        self.suggested_human_steps = suggested_human_steps
        self.requires_human_review = requires_human_review

    def to_dict(self) -> Dict[str, Any]:
        return {
            "draft_id": self.draft_id,
            "incident_id": self.incident_id,
            "facts": self.facts,
            "impact_scope": self.impact_scope,
            "known_anomalies": list(self.known_anomalies),
            "trace_reference": self.trace_reference,
            "related_release_id": self.related_release_id,
            "related_runbook_ids": list(self.related_runbook_ids),
            "suggested_human_steps": list(self.suggested_human_steps),
            "requires_human_review": self.requires_human_review,
        }


# ===================================================================== #
# T14 恢复校验
# ===================================================================== #
class IncidentRecoveryValidation:
    """恢复校验结果（T14）。AI 执行只读校验；不得宣布 resolved。"""

    def __init__(
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
        passed: bool,
        validated_by: str,
        actor_kind: str = "user",
        validated_at: str = "",
    ) -> None:
        if actor_kind != "user":
            raise ValueError("IncidentRecoveryValidation.actor_kind 必须为 'user'（红线⑩）")
        self.validation_id = validation_id
        self.incident_id = incident_id
        self.service_health = service_health
        self.error_rate_ok = error_rate_ok
        self.dependency_health_ok = dependency_health_ok
        self.database_health_ok = database_health_ok
        self.identity_health_ok = identity_health_ok
        self.governance_health_ok = governance_health_ok
        self.passed = passed
        self.validated_by = validated_by
        self.actor_kind = actor_kind
        self.validated_at = validated_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "incident_id": self.incident_id,
            "service_health": self.service_health.value,
            "error_rate_ok": self.error_rate_ok,
            "dependency_health_ok": self.dependency_health_ok,
            "database_health_ok": self.database_health_ok,
            "identity_health_ok": self.identity_health_ok,
            "governance_health_ok": self.governance_health_ok,
            "passed": self.passed,
            "validated_by": self.validated_by,
            "actor_kind": self.actor_kind,
            "validated_at": self.validated_at,
        }


# ===================================================================== #
# T15 复盘草稿
# ===================================================================== #
class RootCauseStatus(str, Enum):
    IDENTIFIED = "identified"
    PENDING_VERIFICATION = "pending_verification"


class IncidentPostmortemDraft:
    """复盘草稿（T15）。root cause 无证据时 PENDING_VERIFICATION；禁止 AI 编造。"""

    def __init__(
        self,
        *,
        postmortem_id: str,
        incident_id: str,
        summary: str,
        timeline: List[Dict[str, Any]],
        impact: str,
        evidence: str = "",
        root_cause_status: RootCauseStatus = RootCauseStatus.PENDING_VERIFICATION,
        root_cause: str = "",
        contributing_factors: List[str],
        mitigation: str = "",
        recovery: str = "",
        unresolved_questions: List[str],
        follow_up_candidates: List[str],
        authored_by: str,
        actor_kind: str = "user",
    ) -> None:
        if actor_kind != "user":
            raise ValueError("IncidentPostmortemDraft.actor_kind 必须为 'user'（红线⑩）")
        self.postmortem_id = postmortem_id
        self.incident_id = incident_id
        self.summary = summary
        self.timeline = timeline
        self.impact = impact
        self.evidence = evidence
        self.root_cause_status = root_cause_status
        if root_cause_status == RootCauseStatus.IDENTIFIED and not root_cause:
            # 红线⑫：声称已定位根因却无描述 = 伪造。
            raise ValueError("root_cause_status=identified 时 root_cause 不得为空（红线⑫）")
        self.root_cause = root_cause
        self.contributing_factors = contributing_factors
        self.mitigation = mitigation
        self.recovery = recovery
        self.unresolved_questions = unresolved_questions
        self.follow_up_candidates = follow_up_candidates
        self.authored_by = authored_by
        self.actor_kind = actor_kind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "postmortem_id": self.postmortem_id,
            "incident_id": self.incident_id,
            "summary": self.summary,
            "timeline": list(self.timeline),
            "impact": self.impact,
            "evidence": self.evidence,
            "root_cause_status": self.root_cause_status.value,
            "root_cause": self.root_cause,
            "contributing_factors": list(self.contributing_factors),
            "mitigation": self.mitigation,
            "recovery": self.recovery,
            "unresolved_questions": list(self.unresolved_questions),
            "follow_up_candidates": list(self.follow_up_candidates),
            "authored_by": self.authored_by,
            "actor_kind": self.actor_kind,
        }


# ===================================================================== #
# T16 后续治理联动候选（复用既有治理编排，不直接修改治理知识）
# ===================================================================== #
class IncidentFollowUpCandidate:
    """事故后续事项候选（T16）。创建 Governance Workflow / Knowledge / Improvement
    候选，但必须复用既有治理编排 / 人工审阅，禁止 Incident 层直接修改治理知识。"""

    def __init__(
        self,
        *,
        candidate_id: str,
        incident_id: str,
        kind: str,  # "governance_workflow" | "knowledge" | "improvement"
        title: str,
        detail: str = "",
        pending_human_review: bool = True,
    ) -> None:
        self.candidate_id = candidate_id
        self.incident_id = incident_id
        self.kind = kind
        self.title = title
        self.detail = detail
        self.pending_human_review = pending_human_review

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidate_id": self.candidate_id,
            "incident_id": self.incident_id,
            "kind": self.kind,
            "title": self.title,
            "detail": self.detail,
            "pending_human_review": self.pending_human_review,
        }


# ===================================================================== #
# 安全关联候选（T25 安全关联）
# ===================================================================== #
class SecurityAlertCandidate:
    """由身份失败 / 权限拒绝聚合而成的安全告警候选（T25）。真实阈值 pending_verification。"""

    def __init__(
        self,
        *,
        alert_id: str,
        organization_id: str,
        title: str,
        related_audit_categories: List[str],  # 例如 ["identity_failure", "permission_denied"]
        signal_count: int,
        threshold_verified: bool = False,  # 真实阈值需由人工设定
        evidence: str = "",
        detected_at: str,
    ) -> None:
        self.alert_id = alert_id
        self.organization_id = organization_id
        self.title = title
        self.related_audit_categories = related_audit_categories
        self.signal_count = signal_count
        self.threshold_verified = threshold_verified
        self.evidence = evidence
        self.detected_at = detected_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "organization_id": self.organization_id,
            "title": self.title,
            "related_audit_categories": list(self.related_audit_categories),
            "signal_count": self.signal_count,
            "threshold_verified": self.threshold_verified,
            "evidence": self.evidence,
            "detected_at": self.detected_at,
        }


__all__ = [
    "ServiceHealthStatus",
    "ObservableComponent",
    "ServiceHealth",
    "MetricCategory",
    "MetricSnapshot",
    "SLOKind",
    "SLIDefinition",
    "SLOStatus",
    "SLODefinition",
    "ErrorBudget",
    "AlertStatus",
    "AlertCandidate",
    "ObservabilityCorrelation",
    "IncidentStatus",
    "IncidentSeverity",
    "IncidentCandidate",
    "IncidentTimelineEvent",
    "ProductionIncident",
    "IncidentCommanderAssignment",
    "IncidentRunbookReference",
    "IncidentResponseDraft",
    "IncidentRecoveryValidation",
    "RootCauseStatus",
    "IncidentPostmortemDraft",
    "IncidentFollowUpCandidate",
    "SecurityAlertCandidate",
    "PRODUCTION_OBSERVABILITY_FORBIDDEN_COUNT",
]
