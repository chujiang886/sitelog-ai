"""Approved Monitor（Phase 3.2 Sprint 3.2.5-B）。

落地 Sprint 3.2.5-A 监控设计：每次 ``engineering_approved`` 出现时 append-only
写入 ``approved_monitor.jsonl``，记录溯源必需字段。

红线：
- 仅记录**引用/标识符**（interface / threshold_version / sign_off_id /
  review_log_ref），**绝不**写入任何真实工程数值（风压 / 壁厚 / 楼层等）；
- append-only：只追加，不修改/删除历史；
- 真实写入仅发生在 ``engineering_enabled=true`` 且门禁全过之后（本阶段不触发）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_APPROVED_MONITOR_PATH: Path = (
    Path(__file__).resolve().parent / "approved_monitor.jsonl"
)

SCHEMA_VERSION: str = "1.0"


@dataclass
class ApprovedRecord:
    """单次 ``engineering_approved`` 的监控记录（仅引用，无真实数值）。"""

    interface: str
    threshold_version: str
    sign_off_id: str
    review_log_ref: str
    error: str | None = None
    timestamp: str = ""
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "interface": self.interface,
            "threshold_version": self.threshold_version,
            "sign_off_id": self.sign_off_id,
            "review_log_ref": self.review_log_ref,
            "error": self.error,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "ApprovedRecord":
        return cls(
            interface=str(data.get("interface", "")),
            threshold_version=str(data.get("threshold_version", "")),
            sign_off_id=str(data.get("sign_off_id", "")),
            review_log_ref=str(data.get("review_log_ref", "")),
            error=data.get("error"),
            timestamp=str(data.get("timestamp", "")),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
        )


def append_approved_record(
    *,
    interface: str,
    threshold_version: str,
    sign_off_id: str,
    review_log_ref: str,
    error: str | None = None,
    timestamp: str | None = None,
    monitor_path: Path | str | None = None,
) -> ApprovedRecord:
    """append-only 写入一条 approved 监控记录，返回该记录。"""

    path: Path = Path(monitor_path) if monitor_path is not None else DEFAULT_APPROVED_MONITOR_PATH
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    record = ApprovedRecord(
        interface=interface,
        threshold_version=threshold_version,
        sign_off_id=sign_off_id,
        review_log_ref=review_log_ref,
        error=error,
        timestamp=timestamp,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record


def load_approved_records(
    monitor_path: Path | str | None = None,
) -> list[ApprovedRecord]:
    """回放监控日志为记录列表（按写入顺序）。"""

    path: Path = Path(monitor_path) if monitor_path is not None else DEFAULT_APPROVED_MONITOR_PATH
    records: list[ApprovedRecord] = []
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
                records.append(ApprovedRecord.from_dict(data))
    except UnicodeDecodeError:
        return records
    return records


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_APPROVED_MONITOR_PATH",
    "ApprovedRecord",
    "append_approved_record",
    "load_approved_records",
]
