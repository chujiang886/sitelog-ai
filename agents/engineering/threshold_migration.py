"""Threshold Governance Migration（Phase 3.2 Sprint 3.2.4-E）。

v1 → v2 迁移工具。落地 3.2.4-D 迁移方案 §2（M1-M8）：
- M1 快照：对输入文件生成内容哈希快照（**不修改原文件**）；
- M2 顶层 ``schema_version`` 1 → 2；
- M3 每条阈值补 ``threshold_status=draft``（缺省降级，零破坏）；
- M4 每条阈值补 ``version``（缺省 "1.0.0"）；
- M5 ``source_ref`` 自由文本 → 结构化对象（补 ``hash=""``）；
- M6 D-TH 按方案 A 补 ``expert_verified_*`` 字段位（null，**禁止自动填充**）；
- M7/M8（写 review_log / 跑门禁）由调用方（CI + 3.2.5-B 门禁）另行处理。

设计原则（红线）：
- 本工具**绝不**修改输入文件（只读输入、写入独立输出路径）；
- 绝不写入 ``verified=true``、绝不填任何真实 ``value``、绝不开启
  ``engineering_enabled``、绝不输出 ``engineering_approved``；
- 任何失败**自动回滚**：删除可能残存的输出、保留快照，全部阈值保持
  ``pending_verification``；
- 迁移只是"结构升级"，不构成任何阈值转正（转正仍须专家双签 + 主理人核准 +
  门禁全绿，且须主理人单独书面授权）。
"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from agents.engineering.thresholds.schema import (
    CURRENT_SCHEMA_VERSION,
    SCHEMA_VERSION_V1,
    SCHEMA_VERSION_V2,
    ensure_d_th_expert_sign_fields,
)


# 迁移状态常量。
MIGRATION_STATUS_SUCCESS = "success"
MIGRATION_STATUS_ROLLED_BACK = "rolled_back"
MIGRATION_STATUS_NOOP = "noop"

# D-TH 双签决策（衔接 3.2.4-D §6 与 phase3.2.4D_dth_double_sign_decision.md）。
DTH_DECISION_A = "A"  # 补专家双签位（推荐方向，待最终授权）
DTH_DECISION_B = "B"  # 保持单签（不动 D-TH 结构）

DEFAULT_DRAFT_STATUS = "draft"
DEFAULT_VERSION = "1.0.0"


@dataclass
class MigrationReport:
    """迁移结果报告（结构化、可序列化）。"""

    status: str
    input_path: str
    output_path: str
    snapshot_path: str | None
    schema_version_before: int
    schema_version_after: int
    thresholds_total: int
    thresholds_migrated: int
    dth_decision: str
    per_threshold: dict[str, dict[str, Any]] = field(default_factory=dict)
    rollback_available: bool = False
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """序列化为 JSON 友好字典。"""

        return {
            "status": self.status,
            "input_path": self.input_path,
            "output_path": self.output_path,
            "snapshot_path": self.snapshot_path,
            "schema_version_before": self.schema_version_before,
            "schema_version_after": self.schema_version_after,
            "thresholds_total": self.thresholds_total,
            "thresholds_migrated": self.thresholds_migrated,
            "dth_decision": self.dth_decision,
            "per_threshold": self.per_threshold,
            "rollback_available": self.rollback_available,
            "errors": self.errors,
        }


def _sha256_of(path: Path) -> str:
    """计算文件内容 sha256（用于快照命名与完整性）。"""

    return hashlib.sha256(path.read_bytes()).hexdigest()


def _snapshot_path_for(input_path: Path, snapshot_dir: Path) -> Path:
    """为输入文件生成确定性快照路径（内容哈希前缀，标识 v1 基线）。"""

    digest = _sha256_of(input_path)
    return snapshot_dir / f"verified.{digest[:16]}.v1.json"


def _to_structured_source_ref(raw_sr: Any) -> dict[str, str]:
    """将 v1 自由文本 / 部分结构 source_ref 升级为 v2 结构化（补 hash）。"""

    if isinstance(raw_sr, str):
        return {
            "standard": raw_sr,
            "clause": "",
            "edition": "",
            "url": "",
            "retrieved_at": "",
            "hash": "",
        }
    if isinstance(raw_sr, Mapping):
        d = {str(k): str(v or "") for k, v in raw_sr.items()}
        d.setdefault("standard", "")
        d.setdefault("clause", "")
        d.setdefault("edition", "")
        d.setdefault("url", "")
        d.setdefault("retrieved_at", "")
        d.setdefault("hash", "")
        return d
    # 缺失 → 全空结构化占位。
    return {
        "standard": "",
        "clause": "",
        "edition": "",
        "url": "",
        "retrieved_at": "",
        "hash": "",
    }


def migrate_thresholds(
    input_path: str | Path,
    output_path: str | Path,
    snapshot_dir: str | Path | None = None,
    *,
    dth_decision: str = DTH_DECISION_A,
) -> MigrationReport:
    """将 v1 阈值库迁移为 v2（结构升级），生成快照、不修改原文件、失败自动回滚。

    参数：
    - ``input_path``：v1 阈值库（JSON，`schema_version=1`）；
    - ``output_path``：迁移后 v2 文件输出路径（与输入独立，绝不覆盖输入）；
    - ``snapshot_dir``：快照目录（缺省取输出文件同级目录）；
    - ``dth_decision``：D-TH 双签决策（"A" 补专家签位 / "B" 不动）。

    返回：``MigrationReport``，``status`` 为 ``success`` / ``rolled_back`` / ``noop``。

    红线：只读输入、写独立输出；任何异常（快照失败 / 解析失败 / 写入失败）均
    进入回滚分支——删除可能残存的输出、保留快照，绝不污染原文件。
    """

    in_p = Path(input_path)
    out_p = Path(output_path)
    snap_dir = Path(snapshot_dir) if snapshot_dir is not None else out_p.parent

    report = MigrationReport(
        status=MIGRATION_STATUS_ROLLED_BACK,
        input_path=str(in_p),
        output_path=str(out_p),
        snapshot_path=None,
        schema_version_before=SCHEMA_VERSION_V1,
        schema_version_after=CURRENT_SCHEMA_VERSION,
        thresholds_total=0,  # infrastructure-config
        thresholds_migrated=0,  # infrastructure-config
        dth_decision=dth_decision,
    )

    # ---- M1 快照：先于任何写入，且只读输入，绝不修改原文件 ----
    try:
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_p = _snapshot_path_for(in_p, snap_dir)
        if not snap_p.exists():
            shutil.copy2(in_p, snap_p)
        report.snapshot_path = str(snap_p)
        report.rollback_available = True
    except Exception as exc:  # noqa: BLE001 - 快照失败即中止迁移
        report.errors.append(f"snapshot_failed:{exc}")
        # 未动原文件、未写输出，直接返回（等价于回滚完成态）。
        return report

    # ---- 读取 + 迁移（全程不碰原文件，输出写入独立 out_p） ----
    try:
        raw: dict[str, Any] = json.loads(in_p.read_text(encoding="utf-8"))
        v_before = int(raw.get("schema_version", SCHEMA_VERSION_V1))
        report.schema_version_before = v_before

        # 已是 v2（或更高）→ noop，仅保留快照。
        if v_before >= SCHEMA_VERSION_V2:
            report.status = MIGRATION_STATUS_NOOP
            report.rollback_available = True
            return report

        thresholds: Mapping[str, Any] = raw.get("thresholds", {})
        migrated: dict[str, Any] = {}
        for tid, entry in thresholds.items():
            if not isinstance(entry, Mapping):
                continue
            new_entry: dict[str, Any] = dict(entry)
            # M3 补 threshold_status（缺省 draft，零破坏降级）。
            new_entry.setdefault("threshold_status", DEFAULT_DRAFT_STATUS)
            # M4 补 version（缺省 1.0.0）。
            new_entry.setdefault("version", DEFAULT_VERSION)
            # M5 source_ref 自由文本 → 结构化（补 hash）。
            new_entry["source_ref"] = _to_structured_source_ref(
                new_entry.get("source_ref")
            )
            # M6 D-TH 双签字段（方案 A 补位；方案 B 不动）。
            if dth_decision == DTH_DECISION_A:
                new_entry = ensure_d_th_expert_sign_fields(new_entry)
            migrated[tid] = new_entry
            report.per_threshold[tid] = {"status": "migrated"}

        out_raw: dict[str, Any] = dict(raw)
        out_raw["schema_version"] = SCHEMA_VERSION_V2
        out_raw["thresholds"] = migrated

        # 原子写入：先写临时文件，校验可解析后再 rename，避免半截输出。
        tmp_p = out_p.with_name(f"{out_p.stem}.{out_p.suffix.lstrip('.')}.tmp")
        tmp_p.write_text(
            json.dumps(out_raw, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        # 回解析校验（写坏即视为失败，进入回滚）。
        json.loads(tmp_p.read_text(encoding="utf-8"))
        tmp_p.replace(out_p)

        report.status = MIGRATION_STATUS_SUCCESS
        report.thresholds_total = len(thresholds)
        report.thresholds_migrated = len(migrated)

    except Exception as exc:  # noqa: BLE001 - 任何迁移/写入异常 → 自动回滚
        report.errors.append(f"migration_failed:{exc}")
        # 回滚：删除可能残存的输出与临时文件，保留快照。
        _safe_unlink(out_p)
        if snapshot_dir is not None:
            tmp_p = out_p.with_name(f"{out_p.stem}.{out_p.suffix.lstrip('.')}.tmp")
            _safe_unlink(tmp_p)
        else:
            tmp_p = out_p.with_name(f"{out_p.stem}.{out_p.suffix.lstrip('.')}.tmp")
            _safe_unlink(tmp_p)
        report.status = MIGRATION_STATUS_ROLLED_BACK

    return report


def _safe_unlink(path: Path) -> None:
    """安全删除（忽略不存在 / 权限错误），用于回滚清理残存输出。"""

    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


__all__ = [
    "MIGRATION_STATUS_SUCCESS",
    "MIGRATION_STATUS_ROLLED_BACK",
    "MIGRATION_STATUS_NOOP",
    "DTH_DECISION_A",
    "DTH_DECISION_B",
    "DEFAULT_DRAFT_STATUS",
    "DEFAULT_VERSION",
    "MigrationReport",
    "migrate_thresholds",
]
