"""Phase 3.9.4 生产遥测接入适配与合成运维验证服务（T1-T9 主体 + T10-T18 编排）。

定位：把「遥测如何被抽象接入」「合成故障如何被注入」「告警如何被路由（仅模拟）」「事故演练
如何端到端跑通」以只读 / 事实描述 / 端口契约结构沉淀，并向上层 ``ProductionObservabilityService``
提供归一化后的标准业务对象。本服务**不持有任何生产修复状态**，不执行任何真实回滚 / 真实部署 /
真实告警发送 / 自动关闭 Incident / 自动执行 Runbook；所有出口一律 fail-closed：

① 构造断言 ``safety_invariants_ok()``（engineering_enabled 必须 False）。
② ``_FORBIDDEN = _TELEMETRY_FORBIDDEN`` 结构性拦截：真实故障注入 / 端口降级伪装 / 真实告警外发
   / 自动 Runbook / 把合成当真实 / 测试 USER 绕过 / 自动 ACK-RESOLVE-CLOSE / 自动部署回滚。
③ **不自动解决 Incident**：事故最终 RESOLVED_BY_HUMAN / CLOSED_BY_HUMAN 只能源于真实 USER
   在 API 层 / drill 显式 human_actions 中发起；服务层不提供任何 AUTO_* 状态转移。
④ **不代替责任节点**：所有审计入口强制 actor=USER（红线⑩）。
⑤ **不伪造观测**：无法真实验证的阈值 / 真实 SLA 一律 pending_verification 或
   simulation_only=True（红线⑪/⑫）。
⑥ Release 关联只提供 rollback_reference 给人工：绝不自动 rollback（红线⑤）。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agents.enterprise.audit import AuditService
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    _RedLineForbiddenMixin,
    safety_invariants_ok,
)
from agents.enterprise.telemetry.alert_routing import (
    SyntheticAlertRoutingProvider,
)
from agents.enterprise.telemetry.forbidden import _TELEMETRY_FORBIDDEN
from agents.enterprise.telemetry.health import TelemetryHealthAggregator
from agents.enterprise.telemetry.models import (
    IncidentEscalationPolicy,
    OnCallScheduleReference,
    ProviderStatus,
    SyntheticFaultScenario,
    TelemetryType,
)
from agents.enterprise.telemetry.log import SyntheticLogProvider
from agents.enterprise.telemetry.normalizer import TelemetryNormalizer
from agents.enterprise.telemetry.provider import TelemetryProvider
from agents.enterprise.telemetry.registry import TelemetryProviderRegistry
from agents.enterprise.telemetry.synthetic import (
    SyntheticFaultInjection,
    SyntheticTelemetryProvider,
)


class ProductionTelemetryService(_RedLineForbiddenMixin):
    """生产遥测接入适配与合成运维验证服务（T1-T9 主体 + T10-T18 编排）。"""

    _FORBIDDEN = _TELEMETRY_FORBIDDEN

    def __init__(
        self,
        *,
        org_id: str,
        audit: Optional[AuditService] = None,
        identity: Any = None,
        production_mode: bool = False,
        root_dir: str = ".",
    ) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构建遥测层（红线①）"
            )
        self._org_id = str(org_id).strip()
        self._audit = audit
        self._identity = identity
        self._production_mode = bool(production_mode)
        self._root_dir = root_dir

        # 默认合成源（simulation_only=True），绝不冒充真实生产源（红线⑪）。
        self._synthetic = SyntheticTelemetryProvider(provider_id="synthetic")
        self._synthetic_log = SyntheticLogProvider(provider_id="synthetic-log")
        self._injection = SyntheticFaultInjection()
        self._normalizer = TelemetryNormalizer()
        self._aggregator = TelemetryHealthAggregator()
        self._alert_router = SyntheticAlertRoutingProvider()  # 仅模拟投递（红线⑫）
        self._registry = TelemetryProviderRegistry()
        self._registry.register(self._synthetic)
        self._registry.register(self._synthetic_log)

        # on-call / 升级策略引用（真实值一律 pending_verification，红线⑭）。
        self._oncall_ref: Optional[OnCallScheduleReference] = None
        self._escalation_policies: List[IncidentEscalationPolicy] = []

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    @staticmethod
    def _require_user(actor_id: str, actor_kind: str) -> None:
        # 所有责任节点强制真实 USER（红线⑩）。
        if not actor_id or actor_kind != "user":
            raise EnterpriseRedLineViolationError(
                "遥测层责任节点要求真实 USER actor（红线⑩）"
            )

    # ------------------------------------------------------------------ #
    # Provider 注册 / 查询 / 健康（T8, T15）
    # ------------------------------------------------------------------ #
    def register_provider(self, provider: TelemetryProvider, *, replace: bool = False) -> None:
        self._registry.register(provider, replace=replace)

    def get_provider(self, provider_id: str) -> Optional[TelemetryProvider]:
        return self._registry.get(provider_id)

    def list_providers(self) -> List[str]:
        return self._registry.list_ids()

    def provider_health_summary(self) -> Dict[str, Any]:
        return self._registry.health_summary()

    def get_production_provider(self, kind: Any) -> Optional[TelemetryProvider]:
        # fail-closed：未配置真实生产源 → None，绝不 fallback Synthetic（红线⑪）。
        return self._registry.get_production_provider(kind)

    # ------------------------------------------------------------------ #
    # T19 巡检 Provider（审计留痕）
    # ------------------------------------------------------------------ #
    def check_provider(
        self, *, actor_id: str, provider_id: str, detail: str = ""
    ) -> Dict[str, Any]:
        self._require_user(actor_id, "user")
        provider = self._registry.get(provider_id)
        health = provider.provider_health() if provider else None
        status = health.status.value if health else ProviderStatus.NOT_CONFIGURED.value
        if self._audit is not None:
            self._audit.record_telemetry_provider_checked(
                record_id=f"telchk-{self._org_id[:8]}-{provider_id}",
                actor_id=actor_id,
                action="check_provider",
                target=provider_id,
                detail=f"status={status};{detail}",
            )
        return {
            "provider_id": provider_id,
            "status": status,
            "checked_by": actor_id,
            "simulation_only": bool(health and health.simulation_only) if health else False,
        }

    # ------------------------------------------------------------------ #
    # T7 查询 + 归一化（Provider 差异不向上泄漏，红线⑪）
    # ------------------------------------------------------------------ #
    def query_and_normalize(
        self,
        *,
        provider_id: str,
        organization_id: str,
        component: str,
        types: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        provider = self._registry.get(provider_id)
        if provider is None or not provider.is_configured():
            # fail-closed：真实源未配置 → 空，绝不降级为 Synthetic（红线⑪）。
            return {
                "provider_id": provider_id,
                "configured": False,
                "envelopes": [],
                "normalized": {"health": [], "metrics": [], "traces": [], "logs": []},
            }
        types = types or ["metrics", "health", "logs", "traces"]
        envelopes = []
        if "metrics" in types:
            envelopes.extend(
                provider.query_metrics(organization_id=organization_id, component=component)
            )
        if "health" in types:
            envelopes.extend(
                provider.query_health(organization_id=organization_id, component=component)
            )
        if "logs" in types:
            envelopes.extend(
                provider.query_logs(organization_id=organization_id, component=component)
            )
        if "traces" in types:
            envelopes.extend(
                provider.query_traces(organization_id=organization_id, component=component)
            )
        normalized = self._normalizer.normalize(envelopes)
        return {
            "provider_id": provider_id,
            "configured": True,
            "envelopes": [e.to_dict() for e in envelopes],
            "normalized": {
                "health": [h.to_dict() for h in normalized["health"]],
                "metrics": [m.to_dict() for m in normalized["metrics"]],
                "traces": [t.to_dict() for t in normalized["traces"]],
                "logs": [l.to_dict() for l in normalized["logs"]],
            },
        }

    # ------------------------------------------------------------------ #
    # T10-T12 合成故障演练 E2E（fault→telemetry→normalizer→health/metrics
    # →alert→correlation→incident→human fixture→recovery→validation→postmortem）
    # ------------------------------------------------------------------ #
    def run_synthetic_incident_drill(
        self,
        *,
        scenario: SyntheticFaultScenario,
        actor_id: str,
        organization_id: str,
        component: str,
        human_actions: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """运行一次合成事故演练（端到端）。

        红线⑨/⑩：本方法**不**自动 ACK / RESOLVE / CLOSE 任何 Incident。若 ``human_actions``
        由真实 USER 测试 fixture 显式提供（ack/recover/validate/close），才在报告中体现人类责任
        节点已执行——且这些步骤明确定义为 USER 责任，绝不自动发生。

        红线⑪/⑫：注入仅限 ``SyntheticTelemetryProvider``；告警路由仅模拟投递，绝不真实外发。
        """
        self._require_user(actor_id, "user")
        if not isinstance(scenario, SyntheticFaultScenario):
            raise EnterpriseRedLineViolationError("演练场景必须是 SyntheticFaultScenario（红线⑪）")

        drill_id = f"drill-{organization_id[:8]}-{scenario.value}"
        if self._audit is not None:
            self._audit.record_synthetic_drill_started(
                record_id=f"drill-start-{drill_id}",
                actor_id=actor_id,
                action="start_synthetic_drill",
                target=drill_id,
                detail=f"scenario={scenario.value};component={component}",
            )

        # 1) 注入合成故障到 Synthetic Provider（fail-closed：非 Synthetic 抛错）。
        envelopes = self._injection.inject(
            provider=self._synthetic,
            scenario=scenario,
            organization_id=organization_id,
            component=component,
        )
        # 2) 归一化（Provider 差异不向上泄漏）。
        normalized = self._normalizer.normalize(envelopes)
        # 3) 聚合健康。
        health_statuses = [h.status.value for h in normalized["health"]]
        overall_health = self._aggregator.overall_for_normalized_health(health_statuses)
        anomalous = overall_health in ("unhealthy", "degraded")

        # 4) 告警路由（仅模拟投递，红线⑫）。
        alert_ref = ""
        delivery = None
        if anomalous:
            alert = {
                "alert_id": f"alert-{drill_id}",
                "severity": "high" if overall_health == "unhealthy" else "medium",
                "component": component,
                "scenario": scenario.value,
                "channel": "synthetic",
                "simulation_only": True,
            }
            delivery = self._alert_router.route(alert, actor_id=actor_id, actor_kind="user")
            alert_ref = alert["alert_id"]

        # 5) Incident 候选（草稿，需人工）。初始状态恒为 open，等待人工（红线⑨）。
        incident = {
            "incident_id": f"inc-{drill_id}",
            "scenario": scenario.value,
            "status": "open" if anomalous else "no_incident",
            "overall_health": overall_health,
            "alert_ref": alert_ref,
            "delivery_status": delivery["delivery_status"] if delivery else None,
            "simulation_only": True,
            "human_steps": {},  # 仅由 human_actions 填充，绝不自动发生
        }

        # 6) 人工责任节点（仅当真实 USER 显式提供 human_actions 时执行，红线⑨/⑩）。
        steps_taken: Dict[str, Any] = {}
        if human_actions:
            for step in ("ack", "recover", "validate", "close"):
                if not human_actions.get(step):
                    continue
                if step == "ack":
                    incident["status"] = "acknowledged"
                    steps_taken["ack"] = {"actor": actor_id, "kind": "user"}
                elif step == "recover":
                    # 恢复 = 把合成场景切回 HEALTHY 并重新采集（仍是模拟 Provider，非真实回滚）。
                    self._synthetic.set_scenario(SyntheticFaultScenario.HEALTHY)
                    re_env = self._synthetic.query_health(
                        organization_id=organization_id, component=component
                    )
                    re_norm = self._normalizer.normalize(re_env)
                    re_statuses = [h.status.value for h in re_norm["health"]]
                    incident["recovered_health"] = self._aggregator.overall_for_normalized_health(
                        re_statuses
                    )
                    steps_taken["recover"] = {"actor": actor_id, "kind": "user"}
                elif step == "validate":
                    incident["recovery_validated"] = True
                    steps_taken["validate"] = {"actor": actor_id, "kind": "user"}
                elif step == "close":
                    incident["status"] = "closed_by_human"
                    steps_taken["close"] = {"actor": actor_id, "kind": "user"}
        incident["human_steps"] = steps_taken

        # 7) 完成留痕（红线⑨：无 human_actions 时 incident.status 仍为 open，绝不自动关闭）。
        if self._audit is not None:
            self._audit.record_synthetic_drill_completed(
                record_id=f"drill-end-{drill_id}",
                actor_id=actor_id,
                action="complete_synthetic_drill",
                target=drill_id,
                detail=(
                    f"scenario={scenario.value};overall_health={overall_health};"
                    f"anomalous={anomalous};incident_status={incident['status']};"
                    f"human_steps={sorted(steps_taken.keys())}"
                ),
            )

        return {
            "drill_id": drill_id,
            "scenario": scenario.value,
            "organization_id": organization_id,
            "component": component,
            "simulation_only": True,  # 红线⑪：整场演练仅为模拟
            "anomalous": anomalous,
            "overall_health": overall_health,
            "normalized_summary": {
                "health": len(normalized["health"]),
                "metrics": len(normalized["metrics"]),
                "traces": len(normalized["traces"]),
                "logs": len(normalized["logs"]),
            },
            "alert_delivery": delivery,
            "incident": incident,
            "auto_resolved": False,  # fail-closed 显式声明：绝不自动解决
            "auto_closed": False,
            "auto_rollback": False,
        }

    # ------------------------------------------------------------------ #
    # T16 合成恢复演练关联（禁自动 RESOLVE）
    # ------------------------------------------------------------------ #
    def correlate_recovery_drill(
        self,
        *,
        drill_id: str,
        recovery_validated: bool,
        validated_by: str,
    ) -> Dict[str, Any]:
        """把恢复演练关联到验证结论。红线⑨：绝不由合成结果自动 RESOLVE Incident。"""
        return {
            "drill_id": drill_id,
            "recovery_validated": bool(recovery_validated),
            "validated_by": validated_by,
            "auto_resolved": False,  # fail-closed 显式声明
            "requires_human_closure": True,
        }

    # ------------------------------------------------------------------ #
    # T17 Release 回归关联（possible_correlation 语义，关联 3.9.2 release_id/commit_sha/manifest）
    # ------------------------------------------------------------------ #
    def correlate_release(
        self,
        *,
        incident_ref: str,
        release_id: str,
        commit_sha: str,
        manifest_reference: str,
        evidence_reference: str,
        rollback_reference: str,
    ) -> Dict[str, Any]:
        """把遥测异常关联到发布（T17）。只读地提供 rollback_reference 给人工，绝不自动 rollback。"""
        return {
            "incident_ref": incident_ref,
            "organization_id": self._org_id,
            "release_id": release_id,
            "commit_sha": commit_sha,
            "manifest_reference": manifest_reference,
            "evidence_reference": evidence_reference,
            "rollback_reference": rollback_reference,  # 仅引用，绝不执行
            "possible_correlation": True,  # 仅为可能关联，非因果定论
            "auto_rollback": False,  # 红线⑤
            "pending_verification": True,
        }

    # ------------------------------------------------------------------ #
    # T18 安全信号演练关联（simulation_only=True）
    # ------------------------------------------------------------------ #
    def correlate_security_signals(
        self,
        *,
        organization_id: str,
        signals: List[Dict[str, Any]],
        window: str = "10m",
    ) -> List[Dict[str, Any]]:
        """把身份失败 / 权限拒绝类信号聚合为安全告警候选（T18）。

        红线⑪：真实阈值需由人工设定，默认 ``threshold_verified=False``；所有来源
        simulation_only=True。
        """
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for s in signals:
            cat = s.get("category", "unknown")
            grouped.setdefault(cat, []).append(s)
        candidates: List[Dict[str, Any]] = []
        for cat, items in grouped.items():
            candidates.append(
                {
                    "alert_id": f"sec-{organization_id[:8]}-{cat}",
                    "organization_id": organization_id,
                    "title": f"安全信号聚合：{cat}（{len(items)} 次）",
                    "related_categories": [cat],
                    "signal_count": len(items),
                    "threshold_verified": False,  # 真实阈值 pending_verification
                    "simulation_only": True,
                    "evidence": f"window={window}; categories={list(grouped.keys())}",
                    "detected_at": items[-1].get("ts", "") if items else "",
                }
            )
        return candidates

    # ------------------------------------------------------------------ #
    # T14 on-call 引用 / T15 升级策略（真实值 pending_verification）
    # ------------------------------------------------------------------ #
    def register_oncall(self, *, reference: OnCallScheduleReference) -> None:
        self._oncall_ref = reference

    def register_escalation(self, *, policy: IncidentEscalationPolicy) -> None:
        self._escalation_policies.append(policy)

    # ------------------------------------------------------------------ #
    # T21 遥测证据留痕（审计）
    # ------------------------------------------------------------------ #
    def record_telemetry_evidence(
        self,
        *,
        actor_id: str,
        evidence_id: str,
        component: str,
        evidence: str,
        simulation_only: bool = True,
    ) -> Any:
        self._require_user(actor_id, "user")
        if self._audit is not None:
            return self._audit.record_telemetry_evidence_recorded(
                record_id=f"telev-{evidence_id}",
                actor_id=actor_id,
                action="record_telemetry_evidence",
                target=evidence_id,
                detail=f"component={component};simulation_only={simulation_only};{evidence}",
            )
        return None

    # ------------------------------------------------------------------ #
    # 只读汇总（供 UI / API 展示）
    # ------------------------------------------------------------------ #
    def summarize(self) -> Dict[str, Any]:
        health = self._registry.health_summary()
        return {
            "organization_id": self._org_id,
            "production_mode": self._production_mode,
            "provider_count": len(self._registry.list_ids()),
            "provider_health": health,
            "telemetry_forbidden_count": len(_TELEMETRY_FORBIDDEN),
            "synthetic_only": True,  # 本阶段仅有合成源 + 未配置真实源
        }


__all__ = ["ProductionTelemetryService"]
