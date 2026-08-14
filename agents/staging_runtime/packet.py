"""Phase 3.9.9 Real Staging Runtime Integration & Validation Layer —— Packet / Validator / Scanner / Checklist（Task 35-38）。

- ``StagingEvidencePacket``：把证据模型 + Gate 结论打包为**机器可读**数据包（JSON 友好）。
- ``validate_packet``：校验包结构 + 重算完整性哈希 + 检测 production 泄漏。
- ``StagingPacketScanner``：fail-closed 扫描器，发现任何 production 标记即拒绝认证
  （红线：不把 Staging 说成 Production / 不输出 GO / 不推导 Production Approved）。
- ``HUMAN_VERIFICATION_CHECKLIST``：人工验证清单（四角色线下验证/签署后才可授权真实部署）。

终端态恒为 ``PHASE_3_9_9_REAL_STAGING_RUNTIME_VALIDATION_BUILT_NO_GO``。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from agents.staging_runtime.config import load_staging_identity
from agents.staging_runtime.environment import EnvironmentIdentity
from agents.staging_runtime.evidence import build_staging_evidence
from agents.staging_runtime.gate import StagingValidationGate, TERMINAL_STATE

SCHEMA_VERSION = "1.0.0"

# 任何出现在包中的「production / GO / APPROVED」态都视为泄漏标记（fail-closed 拒绝认证）。
_PROHIBITED_TERMINAL_STATES = frozenset(
    {
        "PRODUCTION_READY",
        "APPROVED",
        "GO",
        "PRODUCTION_ACTIVATED",
        "PRODUCTION_CHANGE_CONTROL_EXECUTION_READINESS_BUILT_NO_GO",
    }
)


@dataclass(frozen=True)
class StagingEvidencePacket:
    """机器可读证据包（JSON 友好）。"""

    schema_version: str
    phase: str
    terminal_state: str
    environment: str
    is_production: bool
    external_pending: bool
    human_verification_required: bool
    evidence: dict[str, Any]
    gate: dict[str, Any]
    integrity_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "phase": self.phase,
            "terminal_state": self.terminal_state,
            "environment": self.environment,
            "is_production": self.is_production,
            "external_pending": self.external_pending,
            "human_verification_required": self.human_verification_required,
            "evidence": self.evidence,
            "gate": self.gate,
            "integrity_hash": self.integrity_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StagingEvidencePacket":
        return cls(
            schema_version=data["schema_version"],
            phase=data["phase"],
            terminal_state=data["terminal_state"],
            environment=data["environment"],
            is_production=data["is_production"],
            external_pending=data["external_pending"],
            human_verification_required=data["human_verification_required"],
            evidence=data.get("evidence", {}),
            gate=data.get("gate", {}),
            integrity_hash=data["integrity_hash"],
        )


def build_staging_packet(
    identity: EnvironmentIdentity | None = None,
    *,
    secret_names: tuple[str, ...] = (),
    production_refs: dict[str, tuple[str, ...]] | None = None,
) -> StagingEvidencePacket:
    """聚合证据模型 + Gate，产出机器可读证据包（不执行真实动作）。"""

    ident = identity or load_staging_identity()
    evidence_model = build_staging_evidence(
        ident, secret_names=list(secret_names), production_refs=production_refs
    )
    gate = StagingValidationGate(ident).run(
        secret_names=list(secret_names), production_refs=production_refs
    )

    evidence_dict = evidence_model.to_dict()
    gate_dict = gate.to_dict()

    canonical = json.dumps(
        {"evidence": evidence_dict, "gate": gate_dict},
        sort_keys=True,
        ensure_ascii=False,
    )
    packet_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    return StagingEvidencePacket(
        schema_version=SCHEMA_VERSION,
        phase=evidence_model.to_dict()["phase"],
        terminal_state=TERMINAL_STATE,
        environment=ident.kind.value,
        is_production=ident.kind.is_production,
        external_pending=gate.external_pending,
        human_verification_required=gate.human_verification_required,
        evidence=evidence_dict,
        gate=gate_dict,
        integrity_hash=packet_hash,
    )


@dataclass(frozen=True)
class PacketValidationVerdict:
    valid: bool
    errors: tuple[str, ...]

    def require_valid(self) -> None:
        if not self.valid:
            raise StagingPacketValidationError("; ".join(self.errors))


class StagingPacketValidationError(Exception):
    """证据包校验失败（fail-closed）。"""


def validate_packet(data: dict[str, Any]) -> PacketValidationVerdict:
    """校验证据包结构 + 完整性 + production 泄漏。"""

    errors: list[str] = []
    required = (
        "schema_version", "phase", "terminal_state", "environment",
        "is_production", "evidence", "gate", "integrity_hash",
    )
    for key in required:
        if key not in data:
            errors.append(f"缺少字段 {key}")

    if not errors:
        if data["is_production"] is True:
            errors.append("is_production=True：证据包不得声称 production。")
        if data["terminal_state"] in _PROHIBITED_TERMINAL_STATES:
            errors.append(f"terminal_state={data['terminal_state']} 为禁止态（GO/APPROVED/Production）。")
        # 重算完整性哈希
        try:
            canonical = json.dumps(
                {"evidence": data["evidence"], "gate": data["gate"]},
                sort_keys=True,
                ensure_ascii=False,
            )
            recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            if recomputed != data["integrity_hash"]:
                errors.append("integrity_hash 不匹配：包可能被篡改。")
        except Exception as e:  # noqa: BLE001
            errors.append(f"完整性重算失败：{e}")

    return PacketValidationVerdict(valid=len(errors) == 0, errors=tuple(errors))


@dataclass(frozen=True)
class PacketScanVerdict:
    certifiable: bool
    findings: tuple[str, ...]

    def require_certifiable(self) -> None:
        if not self.certifiable:
            raise StagingPacketScanError("; ".join(self.findings))


class StagingPacketScanError(Exception):
    """证据包扫描发现 production 泄漏（fail-closed 拒绝认证）。"""


class StagingPacketScanner:
    """fail-closed 扫描器：发现任何 production 标记即拒绝认证。"""

    def scan(self, packet: StagingEvidencePacket) -> PacketScanVerdict:
        findings: list[str] = []
        if packet.is_production:
            findings.append("is_production=True：拒绝认证（红线：不把 Staging 说成 Production）。")
        if packet.terminal_state in _PROHIBITED_TERMINAL_STATES:
            findings.append(f"terminal_state={packet.terminal_state}：拒绝认证（红线：不输出 GO/APPROVED）。")
        # 证据项中的 production 泄漏
        for item in packet.evidence.get("items", []):
            if item.get("is_production"):
                findings.append(f"证据项 {item.get('component')} 声称 production：拒绝认证。")
        if packet.gate.get("is_production"):  # pragma: no cover - defensive
            findings.append("gate.is_production=True：拒绝认证。")
        return PacketScanVerdict(
            certifiable=len(findings) == 0,
            findings=tuple(findings),
        )


# 人工验证清单（四角色线下验证/签署后才可授权真实部署）。
HUMAN_VERIFICATION_CHECKLIST: tuple[dict[str, str], ...] = (
    {
        "id": "HV-1",
        "owner_role": "production-owner",
        "item": "确认 staging 资源均为非生产（DB/Secret/IdP/Storage/Alert 不与生产重合）",
    },
    {
        "id": "HV-2",
        "owner_role": "release-manager",
        "item": "确认本地预生产部署计划已由人工在授权后执行（非系统自动）",
    },
    {
        "id": "HV-3",
        "owner_role": "security-owner",
        "item": "确认无真实 PII / 生产数据落入 staging，数据策略已复核",
    },
    {
        "id": "HV-4",
        "owner_role": "auditor",
        "item": "确认 evidence packet 完整性哈希与 git provenance 一致，无篡改",
    },
    {
        "id": "HV-5",
        "owner_role": "all-four-roles",
        "item": "四角色线下签署后，由主理人在人类终端显式置 engineering_enabled=true（唯一 AI 不代执行之动作）",
    },
)


__all__ = [
    "SCHEMA_VERSION",
    "StagingEvidencePacket",
    "build_staging_packet",
    "validate_packet",
    "PacketValidationVerdict",
    "StagingPacketValidationError",
    "StagingPacketScanner",
    "PacketScanVerdict",
    "StagingPacketScanError",
    "HUMAN_VERIFICATION_CHECKLIST",
]
