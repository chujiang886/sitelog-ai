"""Engineering 审核日志（Phase 3.1 Sprint A，append-only）。

记录每一次阈值签字 / 审核动作，构成不可篡改的审核链：
- 每条记录含 event_id（内容哈希，确定性）、threshold_id、action、
  signer_role、signer、timestamp、source_ref、prev_event_id（链指针）；
- append-only：只追加，不修改/删除历史；
- ``prev_event_id`` 指向上一条记录，形成链式溯源。

本模块不消费任何真实工程数值，也不判定阈值真伪——真伪由 threshold_loader
+ ExpertBackedEngineeringValidation 负责，日志只记录"谁在何时做了什么动作"。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_REVIEW_LOG_PATH: Path = Path(__file__).resolve().parent / "review_log.jsonl"

REQUIRED_FIELDS: tuple[str, ...] = (
    "event_id",
    "threshold_id",
    "action",
    "signer_role",
    "signer",
    "timestamp",
    "source_ref",
    "prev_event_id",
)


def compute_event_id(
    *,
    threshold_id: str,
    action: str,
    signer_role: str,
    signer: str,
    timestamp: str,
    source_ref: str,
    prev_event_id: str | None,
) -> str:
    """确定性事件 ID：相同输入永远得到相同哈希（内容寻址）。"""

    payload: str = json.dumps(
        {
            "threshold_id": threshold_id,
            "action": action,
            "signer_role": signer_role,
            "signer": signer,
            "timestamp": timestamp,
            "source_ref": source_ref,
            "prev_event_id": prev_event_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_sign_off_id(
    *,
    interface: str,
    threshold_ids: Sequence[str],
    signs: Sequence[tuple[str, Mapping[str, Any]]],
) -> str:
    """审核通过标识：由接口 + 各签字阈值签名元数据确定性派生。

    与 ExpertBackedEngineeringValidation 产出对齐；复核时可由同一签名元数据
    重新派生并比对，确认 sign_off_id 未被篡改。
    """

    sign_bundle: dict[str, Any] = {
        tid: {
            "verified_by": entry.get("verified_by"),
            "verified_at": entry.get("verified_at"),
            "expert_verified_by": entry.get("expert_verified_by"),
            "expert_verified_at": entry.get("expert_verified_at"),
        }
        for tid, entry in signs
    }
    payload: str = json.dumps(
        {
            "interface": interface,
            "threshold_ids": list(threshold_ids),
            "signs": sign_bundle,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _read_last_event_id(path: Path) -> str | None:
    """读取日志最后一条记录的 event_id（用于链指针）；空/损坏文件返回 None。"""

    if not path.is_file():
        return None
    last: str | None = None
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, Mapping) and record.get("event_id"):
                last = record["event_id"]
    except UnicodeDecodeError:
        return None
    return last


def _append_line(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_review_event(
    *,
    threshold_id: str,
    action: str,
    signer_role: str,
    signer: str,
    source_ref: str,
    timestamp: str | None = None,
    prev_event_id: str | None = None,
    log_path: Path | str | None = None,
) -> dict[str, Any]:
    """追加一条审核事件（append-only），返回完整记录。

    - ``timestamp`` 缺省取 UTC ISO8601；
    - ``prev_event_id`` 缺省自动链接当前日志末条 event_id；
    - 返回记录含确定性 ``event_id``。
    """

    path: Path = Path(log_path) if log_path is not None else DEFAULT_REVIEW_LOG_PATH
    if timestamp is None:
        timestamp = datetime.now(timezone.utc).isoformat()
    if prev_event_id is None:
        prev_event_id = _read_last_event_id(path)
    event_id: str = compute_event_id(
        threshold_id=threshold_id,
        action=action,
        signer_role=signer_role,
        signer=signer,
        timestamp=timestamp,
        source_ref=source_ref,
        prev_event_id=prev_event_id,
    )
    record: dict[str, Any] = {
        "event_id": event_id,
        "threshold_id": threshold_id,
        "action": action,
        "signer_role": signer_role,
        "signer": signer,
        "timestamp": timestamp,
        "source_ref": source_ref,
        "prev_event_id": prev_event_id,
    }
    _append_line(path, record)
    return record


def read_log(log_path: Path | str | None = None) -> list[dict[str, Any]]:
    """回放日志为记录列表（按写入顺序）。"""

    path: Path = Path(log_path) if log_path is not None else DEFAULT_REVIEW_LOG_PATH
    records: list[dict[str, Any]] = []
    if not path.is_file():
        return records
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(record, Mapping):
                records.append(dict(record))
    except UnicodeDecodeError:
        return records
    return records


__all__ = [
    "DEFAULT_REVIEW_LOG_PATH",
    "REQUIRED_FIELDS",
    "compute_event_id",
    "compute_sign_off_id",
    "append_review_event",
    "read_log",
]
