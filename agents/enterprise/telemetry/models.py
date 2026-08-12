"""Phase 3.9.4 生产遥测接入适配与合成运维验证层 —— 领域模型（T2 信封 / T8 完整性 /
T10 故障目录 / T14 on-call / T15 升级策略）。

设计纪律（fail-closed，红线①~⑭）：

- 所有模型**只描述事实 / 端口契约**，不承载任何治理 / 修复 / 部署 / 关闭动作语义。
- Synthetic Telemetry 必须显式 ``simulation_only=True``，且**绝不**被篡改为真实生产数据
  （红线⑪）。
- Provider 未配置真实数据源时 ``status == NOT_CONFIGURED`` 或 ``PENDING_VERIFICATION``，
  不得降级伪装成生产 Provider（红线⑪）。
- on-call / escalation 真实阈值一律 ``pending_verification``，禁止编造 5/10/30 分钟等
  真实企业 SLA（红线⑭）。
- 所有人工责任节点（drill 中的 ACK / RESOLVE / CLOSE / 复盘签署）actor_kind 必须 ``"user"``
  （红线⑩），合成演练使用明确的 test-only USER fixture。
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import uuid4


# ===================================================================== #
# T1 遥测来源类型 / Provider 类别 / Provider 健康状态
# ===================================================================== #
class TelemetryType(str, Enum):
    METRIC = "metric"
    HEALTH = "health"
    LOG = "log"
    TRACE = "trace"
    EVIDENCE = "evidence"  # 审计 / 安全证据类遥测


class ProviderKind(str, Enum):
    SYNTHETIC = "synthetic"
    PROMETHEUS = "prometheus"
    OPENTELEMETRY = "opentelemetry"
    LOKI = "loki"
    ELASTICSEARCH = "elasticsearch"
    OPENSEARCH = "opensearch"
    UNKNOWN = "unknown"


class ProviderStatus(str, Enum):
    """Provider 配置 / 健康状态。

    - NOT_CONFIGURED：未配置真实数据源（fail-closed 默认态）。
    - PENDING_VERIFICATION：已声明但真实连接未经人工验证。
    - CONFIGURED：已配置且健康。
    - UNHEALTHY / DEGRADED：已连接但异常。
    - UNKNOWN：探测缺失 = 不健康，宁错杀（绝不回退为 CONFIGURED）。
    """

    CONFIGURED = "configured"
    NOT_CONFIGURED = "not_configured"
    PENDING_VERIFICATION = "pending_verification"
    UNHEALTHY = "unhealthy"
    DEGRADED = "degraded"
    UNKNOWN = "unknown"

    @classmethod
    def is_operational(cls, status: "ProviderStatus") -> bool:
        # UNKNOWN / NOT_CONFIGURED 不得自动当 CONFIGURED（红线⑪ 防御）。
        return status in (cls.CONFIGURED, cls.DEGRADED)


class IntegrityStatus(str, Enum):
    INTACT = "intact"
    TAMPERED = "tampered"
    UNVERIFIED = "unverified"


class ProviderCapability(str, Enum):
    METRICS = "metrics"
    HEALTH = "health"
    LOGS = "logs"
    TRACES = "traces"


# ===================================================================== #
# T2 统一遥测信封（TelemetryEnvelope）
# ===================================================================== #
def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(payload: Any) -> str:
    raw = repr(payload).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


class TelemetryEnvelope:
    """统一遥测信封（T2）。所有 Provider 输出均归一为此结构，Provider 差异不向上泄漏。

    红线⑪：``simulation_only`` 一旦为 True，必须**不可被改成真实生产数据**。
    """

    def __init__(
        self,
        *,
        telemetry_id: Optional[str] = None,
        provider: str,
        telemetry_type: TelemetryType,
        organization_id: str,
        component: str,
        timestamp: str,
        received_at: Optional[str] = None,
        trace_id: str = "",
        release_id: str = "",
        payload: Any = None,
        simulation_only: bool = False,
        integrity_status: IntegrityStatus = IntegrityStatus.UNVERIFIED,
    ) -> None:
        if not provider:
            raise ValueError("TelemetryEnvelope.provider 不得为空")
        if not organization_id:
            raise ValueError("TelemetryEnvelope.organization_id 不得为空")
        if not component:
            raise ValueError("TelemetryEnvelope.component 不得为空")
        self.telemetry_id = telemetry_id or f"tel-{uuid4().hex[:12]}"
        self.provider = provider
        self.telemetry_type = telemetry_type
        self.organization_id = organization_id
        self.component = component
        self.timestamp = timestamp
        self.received_at = received_at or _now()
        self.trace_id = trace_id
        self.release_id = release_id
        self.payload = payload
        # 红线⑪：合成标记不可被外部偷偷翻转。
        self.simulation_only = bool(simulation_only)
        self.integrity_status = integrity_status
        # 对可哈希原始载荷计算 SHA-256（T8 完整性）。
        self.integrity_hash = _sha256(payload)

    def verify_integrity(self) -> bool:
        """重新计算载荷哈希，校验未被篡改。"""
        return self.integrity_hash == _sha256(self.payload)

    def mark_tampered(self) -> None:
        self.integrity_status = IntegrityStatus.TAMPERED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "telemetry_id": self.telemetry_id,
            "provider": self.provider,
            "telemetry_type": self.telemetry_type.value,
            "organization_id": self.organization_id,
            "component": self.component,
            "timestamp": self.timestamp,
            "received_at": self.received_at,
            "trace_id": self.trace_id,
            "release_id": self.release_id,
            "payload": self.payload,
            "simulation_only": self.simulation_only,
            "integrity_status": self.integrity_status.value,
            "integrity_hash": self.integrity_hash,
        }


class TelemetryProviderHealth:
    """Provider 健康检查快照（T9）。"""

    def __init__(
        self,
        *,
        provider_id: str,
        kind: ProviderKind,
        status: ProviderStatus,
        checked_at: str,
        capabilities: Optional[List[ProviderCapability]] = None,
        detail: str = "",
        simulation_only: bool = False,
    ) -> None:
        self.provider_id = provider_id
        self.kind = kind
        self.status = status
        self.checked_at = checked_at
        self.capabilities = capabilities or []
        self.detail = detail
        self.simulation_only = simulation_only

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "kind": self.kind.value,
            "status": self.status.value,
            "checked_at": self.checked_at,
            "capabilities": [c.value for c in self.capabilities],
            "detail": self.detail,
            "simulation_only": self.simulation_only,
        }


# ===================================================================== #
# T7 归一化产物（Trace / Log 证据）
# ===================================================================== #
class TraceReference:
    """Trace 引用（T7）。关联 Governance Traceability / Release ID / Incident ID。"""

    def __init__(
        self,
        *,
        trace_id: str,
        service: str,
        spans: Optional[List[Dict[str, Any]]] = None,
        governance_trace_id: str = "",
        release_id: str = "",
        incident_id: str = "",
    ) -> None:
        self.trace_id = trace_id
        self.service = service
        self.spans = spans or []
        self.governance_trace_id = governance_trace_id
        self.release_id = release_id
        self.incident_id = incident_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "service": self.service,
            "spans": list(self.spans),
            "governance_trace_id": self.governance_trace_id,
            "release_id": self.release_id,
            "incident_id": self.incident_id,
        }


class LogEvidence:
    """日志证据（T7）。统一日志端口后的归一化日志条目。"""

    def __init__(
        self,
        *,
        log_id: str,
        source: str,
        level: str,
        message: str,
        timestamp: str,
        component: str,
        trace_id: str = "",
        raw: str = "",
    ) -> None:
        self.log_id = log_id
        self.source = source
        self.level = level
        self.message = message
        self.timestamp = timestamp
        self.component = component
        self.trace_id = trace_id
        self.raw = raw

    def to_dict(self) -> Dict[str, Any]:
        return {
            "log_id": self.log_id,
            "source": self.source,
            "level": self.level,
            "message": self.message,
            "timestamp": self.timestamp,
            "component": self.component,
            "trace_id": self.trace_id,
        }


# ===================================================================== #
# T10 合成故障场景目录
# ===================================================================== #
class SyntheticFaultScenario(str, Enum):
    """合成故障场景目录（T10）。所有数字阈值仅用于 test fixture，禁止写成真实企业生产阈值。"""

    BACKEND_LATENCY = "backend_latency"
    BACKEND_ERROR_SPIKE = "backend_error_spike"
    DATABASE_UNAVAILABLE = "database_unavailable"
    IDENTITY_AUTH_FAILURE = "identity_authentication_failure"
    PERMISSION_DENIAL_SPIKE = "permission_denial_spike"
    LLM_TIMEOUT = "llm_timeout"
    ASR_UNAVAILABLE = "asr_unavailable"
    TTS_UNAVAILABLE = "tts_unavailable"
    RELEASE_REGRESSION = "release_regression"
    AUDIT_UNAVAILABLE = "audit_unavailable"
    GOVERNANCE_BACKLOG = "governance_backlog"
    HEALTHY = "healthy"  # 基线健康（无故障）


# ===================================================================== #
# T14 on-call 模型（仅描述，不连接真实 PagerDuty / OpsGenie）
# ===================================================================== #
class OnCallScheduleReference:
    """on-call 排班引用（T14）。真实 on-call 一律 pending_verification。"""

    def __init__(
        self,
        *,
        schedule_id: str,
        source: str,
        current_role: str = "",
        escalation_policy_reference: str = "",
        verification_status: str = "pending_verification",  # 真实 on-call 待验证
    ) -> None:
        self.schedule_id = schedule_id
        self.source = source
        self.current_role = current_role
        self.escalation_policy_reference = escalation_policy_reference
        self.verification_status = verification_status

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schedule_id": self.schedule_id,
            "source": self.source,
            "current_role": self.current_role,
            "escalation_policy_reference": self.escalation_policy_reference,
            "verification_status": self.verification_status,
        }


# ===================================================================== #
# T15 事故升级策略模型（禁止编造真实 SLA）
# ===================================================================== #
class IncidentEscalationPolicy:
    """事故升级策略（T15）。真实 SLA 阈值（5/10/30 分钟等）一律 pending_verification。"""

    def __init__(
        self,
        *,
        policy_id: str,
        severity: str,
        required_role: str,
        escalation_level: int,
        response_expectation_reference: str = "",
        threshold_verified: bool = False,  # 真实企业 SLA 待人工配置
    ) -> None:
        self.policy_id = policy_id
        self.severity = severity
        self.required_role = required_role
        self.escalation_level = escalation_level
        self.response_expectation_reference = response_expectation_reference
        self.threshold_verified = threshold_verified

    def to_dict(self) -> Dict[str, Any]:
        return {
            "policy_id": self.policy_id,
            "severity": self.severity,
            "required_role": self.required_role,
            "escalation_level": self.escalation_level,
            "response_expectation_reference": self.response_expectation_reference,
            "threshold_verified": self.threshold_verified,
        }


__all__ = [
    "TelemetryType",
    "ProviderKind",
    "ProviderStatus",
    "IntegrityStatus",
    "ProviderCapability",
    "TelemetryEnvelope",
    "TelemetryProviderHealth",
    "TraceReference",
    "LogEvidence",
    "SyntheticFaultScenario",
    "OnCallScheduleReference",
    "IncidentEscalationPolicy",
    "TELEMETRY_FORBIDDEN_COUNT",
]
