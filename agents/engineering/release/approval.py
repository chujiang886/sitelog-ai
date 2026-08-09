"""Engineering Release Approval（Phase 3.2 Sprint 3.2.5-F）。

实现 ``EngineeringReleaseApproval`` 授权记录 —— G6 授权证据的唯一可信源
（设计见 3.2.5-E ``EngineeringReleaseApproval`` 七字段契约）。

关键不变量（红线）：
- append-only：只追加，不修改/删除历史授权记录；
- 仅记录**引用/标识符**（approval_id / interface / scope / authorized_by /
  effective_time / rollback_owner / approval_document_ref），**绝不**写入任何
  真实工程数值（风压 / 壁厚 / 楼层等）；
- 本模块不读取/写入 ``verified.json``、不翻转 ``engineering_enabled``、
  不输出 ``engineering_approved``；真实放量仍须主理人单独书面授权 + G1-G6 全过。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

DEFAULT_RELEASE_APPROVAL_PATH: Path = (
    Path(__file__).resolve().parent / "release_approvals.jsonl"
)

SCHEMA_VERSION: str = "1.0"


@dataclass
class EngineeringReleaseApproval:
    """单次工程灰度发布授权记录（G6 证据，仅引用，无真实数值）。

    字段（设计契约 3.2.5-E）：
    - ``approval_id``：授权唯一标识（标识符）；
    - ``interface``：授权适用的接口（首个为 wind_pressure，标识符）；
    - ``scope``：灰度范围描述（标识符/标签，如 "proj-a"）；
    - ``authorized_by``：授权签署人（标识符；须异于 3.2.4 双签主体，SoD）；
    - ``effective_time``：授权生效时间（ISO8601；未来时间视为尚未生效）；
    - ``rollback_owner``：回滚责任人（标识符；须异于 authorized_by，SoD）；
    - ``approval_document_ref``：书面授权文档引用（标识符/路径）。
    """

    approval_id: str
    interface: str
    scope: str
    authorized_by: str
    effective_time: str
    rollback_owner: str
    approval_document_ref: str
    schema_version: str = SCHEMA_VERSION
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "approval_id": self.approval_id,
            "interface": self.interface,
            "scope": self.scope,
            "authorized_by": self.authorized_by,
            "effective_time": self.effective_time,
            "rollback_owner": self.rollback_owner,
            "approval_document_ref": self.approval_document_ref,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "EngineeringReleaseApproval":
        return cls(
            approval_id=str(data.get("approval_id", "")),
            interface=str(data.get("interface", "")),
            scope=str(data.get("scope", "")),
            authorized_by=str(data.get("authorized_by", "")),
            effective_time=str(data.get("effective_time", "")),
            rollback_owner=str(data.get("rollback_owner", "")),
            approval_document_ref=str(data.get("approval_document_ref", "")),
            schema_version=str(data.get("schema_version", SCHEMA_VERSION)),
            created_at=str(data.get("created_at", "")),
        )


def append_approval_record(
    *,
    approval_id: str,
    interface: str,
    scope: str,
    authorized_by: str,
    effective_time: str,
    rollback_owner: str,
    approval_document_ref: str,
    timestamp: str | None = None,
    approval_path: Path | str | None = None,
) -> EngineeringReleaseApproval:
    """append-only 写入一条授权记录，返回该记录。

    红线：仅追加，不修改/删除历史；不写真实工程数值。
    """

    path: Path = (
        Path(approval_path)
        if approval_path is not None
        else DEFAULT_RELEASE_APPROVAL_PATH
    )
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    record = EngineeringReleaseApproval(
        approval_id=approval_id,
        interface=interface,
        scope=scope,
        authorized_by=authorized_by,
        effective_time=effective_time,
        rollback_owner=rollback_owner,
        approval_document_ref=approval_document_ref,
        created_at=timestamp,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
    return record


def load_approval_records(
    approval_path: Path | str | None = None,
) -> list[EngineeringReleaseApproval]:
    """回放授权日志为记录列表（按写入顺序）。"""

    path: Path = (
        Path(approval_path)
        if approval_path is not None
        else DEFAULT_RELEASE_APPROVAL_PATH
    )
    records: list[EngineeringReleaseApproval] = []
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
                records.append(EngineeringReleaseApproval.from_dict(data))
    except UnicodeDecodeError:
        return records
    return records


def find_approval_record(
    approval_id: str,
    approval_path: Path | str | None = None,
) -> EngineeringReleaseApproval | None:
    """按 ``approval_id`` 查找授权记录；不存在返回 None。"""

    target = (approval_id or "").strip()
    for record in load_approval_records(approval_path):
        if record.approval_id == target:
            return record
    return None


def is_approval_effective(
    approval: EngineeringReleaseApproval,
    *,
    now: str | None = None,
) -> bool:
    """判定授权是否已生效：``effective_time`` 缺省/不可解析视为已生效；未来时间视为未生效。

    用于 G6 门禁增强 —— 即便授权记录存在，若其生效时间在未来，仍视为尚未授权。
    """

    raw = (approval.effective_time or "").strip()
    if not raw:
        return True
    try:
        eff = datetime.fromisoformat(raw)
    except ValueError:
        return True
    ref = datetime.fromisoformat(now) if now else datetime.now(timezone.utc)
    if eff.tzinfo is None:
        eff = eff.replace(tzinfo=timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    return eff <= ref


__all__ = [
    "SCHEMA_VERSION",
    "DEFAULT_RELEASE_APPROVAL_PATH",
    "EngineeringReleaseApproval",
    "append_approval_record",
    "load_approval_records",
    "find_approval_record",
    "is_approval_effective",
]
