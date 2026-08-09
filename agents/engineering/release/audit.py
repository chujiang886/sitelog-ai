"""Release Audit Log（Phase 3.2 Sprint 3.2.5-F）。

每次灰度发布操作（precheck / enable / disable / rollback / restore）落
``release_audit.jsonl``，记录溯源必需字段。

红线（任务4）：
- 仅记录**引用/标识符**（approval_id / interface / operator / action /
  timestamp / result），**绝不**写入任何真实工程数值（风压 / 壁厚 / 楼层等）；
- append-only：只追加，不修改/删除历史；
- 真实写入发生在授权 + G1-G6 全过之后；本阶段所有操作均不翻转
  ``engineering_enabled``、不输出 ``engineering_approved``。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_RELEASE_AUDIT_PATH: Path = (
    Path(__file__).resolve().parent / "release_audit.jsonl"
)

SCHEMA_VERSION: str = "1.0"


@dataclass
class ReleaseAuditRecord:
    """单次灰度发布操作的审计记录（仅引用，无真实数值）。"""

    approval_id: str
    interface: str
    operator: str
    action: str
    timestamp: str
    result: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "approval_id": self.approval_id,
            "interface": self.interface,
            "operator": self.operator,
            "action": self.action,
            "timestamp": self.timestamp,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ReleaseAuditRecord":
        return cls(
            approval_id=str(data.get("approval_id", "")),
            interface=str(data.get("interface", "")),
            operator=str(data.get("operator", "")),
            action=str(data.get("action", "")),
            timestamp=str(data.get("timestamp", "")),
            result=str(data.get("result", "")),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


def append_audit_record(
    *,
    approval_id: str,
    interface: str,
    operator: str,
    action: str,
    result: str,
    timestamp: str | None = None,
    audit_path: Path | str | None = None,
) -> ReleaseAuditRecord:
    """append-only 写入一条审计记录，返回该记录。"""

    path: Path = (
        Path(audit_path) if audit_path is not None else DEFAULT_RELEASE_AUDIT_PATH
    )
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    record = ReleaseAuditRecord(
        approval_id=approval_id,
        interface=interface,
        operator=operator,
        action=action,
        timestamp=timestamp,
        result=result,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record


def load_audit_records(
    audit_path: Path | str | None = None,
) -> list[ReleaseAuditRecord]:
    """回放审计日志为记录列表（按写入顺序）。"""

    path: Path = (
        Path(audit_path) if audit_path is not None else DEFAULT_RELEASE_AUDIT_PATH
    )
    records: list[ReleaseAuditRecord] = []
    if not path.is_file():
        return records
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(data, Mapping):
                records.append(ReleaseAuditRecord.from_dict(data))
    except UnicodeDecodeError:
        return records
    return records


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_RELEASE_AUDIT_PATH",
    "ReleaseAuditRecord",
    "append_audit_record",
    "load_audit_records",
]
