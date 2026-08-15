"""Phase 3.9.13 —— Local Evidence Chain（无伪造证据链，T36-T40 支撑）。

记录每个资源的真实状态跃迁与「未伪造」标记。本模块**自包含**，复用
``resource_state_machine`` 的 BOM / Registry。

关键纪律：
- ``real_resources_provisioned`` 永为 0（无真实资源时）。
- 状态机不做跳跃（由 ``ResourceStateMachine`` 保证）。
- 证据链可确定性重建（同一输入 → 同一哈希）。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from agents.external_staging_provisioning.resource_state_machine import (
    build_default_bom,
    ProvisioningStateRegistry,
    PENDING_STATUS,
)


@dataclass
class EvidenceRecord:
    """单资源证据记录。"""

    resource_id: str
    state: str
    real_resource_provisioned: bool = False
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource_id": self.resource_id,
            "state": self.state,
            "real_resource_provisioned": self.real_resource_provisioned,
            "note": self.note,
        }


class EvidenceChain:
    """无伪造证据链。"""

    def __init__(self) -> None:
        self.records: list[EvidenceRecord] = []
        self.pending_human_items: list[str] = []
        self.fabrication_free: bool = True

    def capture_pending(self, registry: ProvisioningStateRegistry) -> None:
        """捕获所有资源当前状态（预期全 PENDING，无真实供给）。"""
        for rid, m in registry._machines.items():
            real = m.state.value not in (
                PENDING_STATUS,
                "input_received",
                "reference_validated",
                "plan_ready",
                "plan_validated",
                "human_authorization_pending",
                "authorized_for_staging_apply",
            )
            self.records.append(EvidenceRecord(
                resource_id=rid,
                state=m.state.value,
                real_resource_provisioned=False,
                note="pending_external_staging_resource — no real resource provisioned",
            ))
            if real:
                self.fabrication_free = False

    def add_pending_human_item(self, item: str) -> None:
        self.pending_human_items.append(item)

    def _canonical(self) -> str:
        body = {
            "records": [r.to_dict() for r in self.records],
            "pending_human_items": sorted(self.pending_human_items),
            "fabrication_free": self.fabrication_free,
        }
        return json.dumps(body, sort_keys=True, ensure_ascii=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "records": [r.to_dict() for r in self.records],
            "pending_human_items": self.pending_human_items,
            "fabrication_free": self.fabrication_free,
            "evidence_hash": hashlib.sha256(
                self._canonical().encode("utf-8")
            ).hexdigest(),
        }


__all__ = ["EvidenceRecord", "EvidenceChain"]
