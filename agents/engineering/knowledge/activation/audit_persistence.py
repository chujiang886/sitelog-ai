"""Consumption Audit Persistence（Phase 3.4 Sprint 3.4.4 任务4）。

将 ``KnowledgeConsumptionAuditLog`` 扩展为可持久化：每条事件在内存保留之外，
追加写入独立 JSONL 文件（默认 ``logs/consumption_audit.jsonl``）。

红线约束（关键设计决策）：
- 持久化文件**独立于** repository 的 ``knowledge_repository.json``，绝不经由
  repository ``event_log``（其 ``EVENT_TYPES`` 白名单刻意不含 ``approved``）；
  因此本持久化路径不会产生 ``approved`` 事件，也不触碰 verified.json；
- 不创建 ``ReleaseApproval``、不开启 ``engineering_enabled``；
- 父类 ``record`` 对 forbidden 事件（含 ``approved``）抛 ``ValueError``，本子类
  在写文件前复用该检查，故文件内容天然不含 approved。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Union

from agents.engineering.knowledge.activation.consumer_guard import (
    KnowledgeConsumptionAuditLog,
)
from agents.engineering.knowledge.repository import KnowledgeEvent

PathLike = Union[str, Path]
DEFAULT_AUDIT_PATH: str = "logs/consumption_audit.jsonl"


class PersistentConsumptionAuditLog(KnowledgeConsumptionAuditLog):
    """在父类内存记录之外，追加写入 JSONL 文件（append-only）。"""

    def __init__(self, path: Optional[PathLike] = None) -> None:
        super().__init__()
        self._path = Path(path) if path else None

    @property
    def path(self) -> Optional[Path]:
        return self._path

    def record(
        self,
        item: object,
        *,
        allowed: bool,
        actor: str = "engineering_ai",
        detail: Optional[str] = None,
    ) -> KnowledgeEvent:
        """记录一条事件并追加写入 JSONL（若配置了 path）。

        父类已对 forbidden 事件（含 approved）抛 ValueError，本方法在其后写文件，
        故文件天然不含 approved 事件。
        """

        ev = super().record(item, allowed=allowed, actor=actor, detail=detail)  # type: ignore[arg-type]
        self._append_file(ev)
        return ev

    def _append_file(self, ev: KnowledgeEvent) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(ev.to_dict(), ensure_ascii=False) + "\n")

    def load_existing(self) -> "PersistentConsumptionAuditLog":
        """从文件读取既有事件并入内存（幂等，便于重启后审计连续）。

        仅追加到内存列表，不再写文件（避免重复落盘）。
        """

        if self._path is None or not self._path.is_file():
            return self
        for line in self._path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            ev = KnowledgeEvent.from_dict(json.loads(line))
            self._events.append(ev)  # 复用父类内存列表（append-only）
        return self


def make_persistent_audit_log(
    path: Optional[PathLike] = None,
) -> PersistentConsumptionAuditLog:
    """便捷构造：默认写入 ``logs/consumption_audit.jsonl``（相对 CWD）。"""

    return PersistentConsumptionAuditLog(path=path or DEFAULT_AUDIT_PATH)


__all__ = [
    "DEFAULT_AUDIT_PATH",
    "PersistentConsumptionAuditLog",
    "make_persistent_audit_log",
]
