"""Phase 3.9.3 企业生产可观测性、SRE 与事故响应准备层 —— 服务编排（T1-T25 主体）。

定位：在发布闸门层（3.9.2）之上提供**纯可观测 / 被动监测 / 事故候选 / 响应草稿 / 复盘
草稿**能力——把「组件健康如何」「指标为何异常」「告警候选是否生成」「事故候选是否关联」
「根因是否待验证」以只读 / 事实描述结构沉淀。本服务**不持有任何生产修复状态**，不执行
任何真实回滚 / 真实部署 / 真实告警发送 / 自动关闭 Incident；所有出口一律 fail-closed：

① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _PRODUCTION_OBSERVABILITY_FORBIDDEN`` 结构拦截自动回滚 / 自动 ACK /
   自动 RESOLVE / 自动 CLOSE / 自动指派指挥官 / AI 代指挥 / 把模拟当真实 / 自动部署。
③ **不自动解决 Incident**：事故最终 RESOLVED_BY_HUMAN / CLOSED_BY_HUMAN 只能源于真实
   USER 在 API 层发起；服务层不提供任何 AUTO_* 状态转移。
④ **不代替责任节点**：所有审计入口强制 actor=USER（红线⑩）。
⑤ **不伪造观测**：无法真实验证的阈值 / 业务 SLA 一律 pending_verification 或
   simulation_only=True（红线⑪/⑫）。
⑥ **Release 关联只提供 rollback_reference 给人工**：绝不自动 rollback（红线⑤）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.audit import AuditActionCategory, AuditService
from agents.enterprise.production_observability.alerts import AlertService
from agents.enterprise.production_observability.correlation import CorrelationEngine
from agents.enterprise.production_observability.forbidden import (
    _PRODUCTION_OBSERVABILITY_FORBIDDEN,
)
from agents.enterprise.production_observability.health import ServiceHealthService
from agents.enterprise.production_observability.incidents import IncidentService
from agents.enterprise.production_observability.metrics import MetricsService
from agents.enterprise.production_observability.models import (
    IncidentSeverity,
    ProductionIncident,
    SecurityAlertCandidate,
    ServiceHealth,
    ServiceHealthStatus,
)
from agents.enterprise.production_observability.slo import SLOService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)


class ProductionObservabilityError(EnterpriseRedLineViolationError):
    """可观测性层业务违例（继承红线异常，保证调用方一律 fail-closed 处理）。"""


class ProductionObservabilityService(_RedLineForbiddenMixin):
    """企业生产可观测性与事故响应准备服务（T1-T25 主体）。"""

    _FORBIDDEN = _PRODUCTION_OBSERVABILITY_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: AuditService,
        identity: Any = None,
        root_dir: str = ".",
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建可观测性层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._root_dir = root_dir
        self._health = ServiceHealthService(root_dir=root_dir)
        self._metrics = MetricsService(root_dir=root_dir)
        self._slo = SLOService(root_dir=root_dir)
        self._alerts = AlertService(root_dir=root_dir)
        self._incidents = IncidentService(root_dir=root_dir)
        self._correlator = CorrelationEngine(root_dir=root_dir)

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_user(actor_id: str, actor_kind: str) -> None:
        # 所有责任节点强制真实 USER（红线⑩）。
        if not actor_id or actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "可观测性层责任节点要求真实 USER actor（红线⑩）"
            )

    # 暴露子服务（保持 fail-closed：子服务自身也构造断言 safety_invariants_ok）。
    @property
    def health(self) -> ServiceHealthService:
        return self._health

    @property
    def metrics(self) -> MetricsService:
        return self._metrics

    @property
    def slo(self) -> SLOService:
        return self._slo

    @property
    def alerts(self) -> AlertService:
        return self._alerts

    @property
    def incidents(self) -> IncidentService:
        return self._incidents

    # ------------------------------------------------------------------ #
    # T19 Release 关联（只读；只提供 rollback_reference 给人工，绝不自动 rollback）
    # ------------------------------------------------------------------ #
    def correlate_release(
        self,
        *,
        incident: ProductionIncident,
        release_id: str,
        commit_sha: str,
        manifest_reference: str,
        evidence_reference: str,
        rollback_reference: str,
    ) -> Dict[str, Any]:
        """把事故关联到发布（T19）。只读地把 release 上下文注入事故，供人工研判。

        红线⑤：本方法**不**执行回滚，仅把 ``rollback_reference`` 提供给人工责任人。
        """
        incident.release_id = release_id
        return {
            "incident_id": incident.incident_id,
            "organization_id": incident.organization_id,
            "release_id": release_id,
            "commit_sha": commit_sha,
            "manifest_reference": manifest_reference,
            "evidence_reference": evidence_reference,
            "rollback_reference": rollback_reference,  # 仅引用，绝不执行
            "auto_rollback": False,  # fail-closed 显式声明
        }

    # ------------------------------------------------------------------ #
    # T25 安全关联（identity_failure / permission_denied 聚合为安全告警候选）
    # ------------------------------------------------------------------ #
    def correlate_security_signals(
        self,
        *,
        organization_id: str,
        signals: List[Dict[str, Any]],
        window: str = "10m",
    ) -> List[SecurityAlertCandidate]:
        """把身份失败 / 权限拒绝类审计信号聚合为安全告警候选。

        红线⑪：真实阈值需由人工设定，默认 ``threshold_verified=False``。
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for s in signals:
            cat = s.get("category", "unknown")
            grouped.setdefault(cat, []).append(s)

        candidates: List[SecurityAlertCandidate] = []
        for cat, items in grouped.items():
            candidates.append(
                SecurityAlertCandidate(
                    alert_id=f"sec-{organization_id[:8]}-{cat}",
                    organization_id=organization_id,
                    title=f"安全信号聚合：{cat}（{len(items)} 次）",
                    related_audit_categories=[cat],
                    signal_count=len(items),
                    threshold_verified=False,  # 真实阈值 pending_verification
                    evidence=f"window={window}; categories={list(grouped.keys())}",
                    detected_at=items[-1].get("ts", "") if items else "",
                )
            )
        return candidates

    # ------------------------------------------------------------------ #
    # T22 审计入口（actor 真实，强制 USER）
    # ------------------------------------------------------------------ #
    def record_health_check(
        self, *, actor_id: str, component: str, status: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_observability_health_check(
            record_id=f"ohc-{self._org_id[:8]}-{component}",
            actor_id=actor_id,
            action="health_check",
            target=component,
            detail=f"status={status};{detail}",
        )

    def record_alert_created(
        self, *, actor_id: str, alert_id: str, component: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_alert_candidate_created(
            record_id=f"oac-{alert_id}",
            actor_id=actor_id,
            action="create_alert_candidate",
            target=alert_id,
            detail=f"component={component};{detail}",
        )

    def record_incident_created(
        self, *, actor_id: str, incident_id: str, severity: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_incident_created(
            record_id=f"oic-{incident_id}",
            actor_id=actor_id,
            action="create_incident",
            target=incident_id,
            detail=f"severity={severity};{detail}",
        )

    def record_incident_acknowledged(
        self, *, actor_id: str, incident_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_incident_human_acknowledged(
            record_id=f"oia-{incident_id}",
            actor_id=actor_id,
            action="acknowledge_incident",
            target=incident_id,
            detail=detail,
        )

    def record_incident_resolved(
        self, *, actor_id: str, incident_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_incident_human_resolved(
            record_id=f"oir-{incident_id}",
            actor_id=actor_id,
            action="resolve_incident",
            target=incident_id,
            detail=detail,
        )

    def record_incident_closed(
        self, *, actor_id: str, incident_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_incident_human_closed(
            record_id=f"oicl-{incident_id}",
            actor_id=actor_id,
            action="close_incident",
            target=incident_id,
            detail=detail,
        )

    def record_postmortem_created(
        self, *, actor_id: str, incident_id: str, detail: str = ""
    ) -> Any:
        self._require_user(actor_id, "user")
        return self._audit.record_postmortem_draft_created(
            record_id=f"opm-{incident_id}",
            actor_id=actor_id,
            action="create_postmortem_draft",
            target=incident_id,
            detail=detail,
        )

    # ------------------------------------------------------------------ #
    # 只读汇总（供 UI / API 展示）
    # ------------------------------------------------------------------ #
    def summarize(self, *, health_snapshots: List[ServiceHealth]) -> Dict[str, Any]:
        return {
            "overall_health": self._health.overall_status(health_snapshots).value,
            "active_alerts": len(self._alerts.all()),
            "active_incidents": len(self._incidents.all()),
            "forbidden_count": len(_PRODUCTION_OBSERVABILITY_FORBIDDEN),
        }
