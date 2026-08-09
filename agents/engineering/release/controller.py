"""Gray Release Controller（Phase 3.2 Sprint 3.2.5-F）。

灰度发布执行核心逻辑：``enable`` / ``disable`` / ``rollback`` / ``restore``。
CLI 与测试共用本模块；CLI 仅做参数解析与退出码映射。

关键不变量（红线）：
- ``enable`` 前五步强制：加载配置 → 授权存在且生效 → G1-G6 通过 → 启用前快照
  （快照失败即拒绝）→ 仅翻转灰度开关；任何前置不满足 → 拒绝且退出码非 0；
- 只操作 ``GrayReleaseConfig``（per-interface 开关 + default_enabled），
  **绝不**翻转 ``engineering_enabled``、**绝不**写 ``config.yaml``、**绝不**改
  ``verified.json``、**绝不**输出 ``engineering_approved``；
- 每次操作 append-only 写入 ``release_audit.jsonl``，仅含引用/标识符，
  不记录任何真实工程数值；
- ``rollback`` / ``restore`` 仅恢复灰度开关，**不触碰** review_log / approvals。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from agents.engineering.gray_release import (
    DEFAULT_GRAY_RELEASE_PATH,
    GrayReleaseConfig,
    GrayReleaseEntry,
    load_gray_release_config,
)
from agents.engineering.release.audit import append_audit_record
from agents.engineering.release.approval import (
    find_approval_record,
    is_approval_effective,
)
from agents.engineering.release.gate import release_precheck


DEFAULT_OPERATOR: str = "release-operator"


class ReleaseAction(str, Enum):
    """灰度发布动作枚举。"""

    PRECHECK = "precheck"
    ENABLE = "enable"
    DISABLE = "disable"
    ROLLBACK = "rollback"
    RESTORE = "restore"


class ReleaseOutcome(str, Enum):
    """操作结果标记（仅语义，非真实数值）。"""

    SUCCESS = "success"
    REJECTED_NO_APPROVAL = "rejected:no_approval"
    REJECTED_NOT_EFFECTIVE = "rejected:approval_not_effective"
    REJECTED_GATE_BLOCKED = "rejected:gate_blocked"
    REJECTED_SNAPSHOT_FAILED = "rejected:snapshot_failed"
    REJECTED_NO_SNAPSHOT = "rejected:no_snapshot"


REASON_NO_APPROVAL = "release approval 不存在或不匹配目标接口"
REASON_NOT_EFFECTIVE = "授权尚未生效（effective_time 在未来）"
REASON_GATE_BLOCKED = "发布门禁 G1-G6 未通过"
REASON_SNAPSHOT_FAILED = "启用前快照失败（snapshot 缺失）"
REASON_NO_SNAPSHOT = "无可用快照，无法恢复"


@dataclass
class ReleaseResult:
    """单次灰度发布操作的结果。"""

    success: bool
    action: str
    interface: str
    message: str
    allowed: bool = False
    reasons: list[str] | None = None
    approval_id: str = ""
    snapshot_path: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "interface": self.interface,
            "message": self.message,
            "allowed": self.allowed,
            "reasons": list(self.reasons or []),
            "approval_id": self.approval_id,
            "snapshot_path": self.snapshot_path,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _config_target(config_path: Path | str | None) -> Path:
    return Path(config_path) if config_path is not None else DEFAULT_GRAY_RELEASE_PATH


def _write_config(cfg: GrayReleaseConfig, config_path: Path | str | None) -> None:
    """原子写回灰度配置（仅开关与白名单，绝不触碰 engineering_enabled）。"""

    target = _config_target(config_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"{target.stem}.tmp.json")
    tmp.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    json.loads(tmp.read_text(encoding="utf-8"))  # 回解析校验
    tmp.replace(target)


def _snapshot_dir_of(config_path: Path | str | None, snapshot_dir: Path | str | None) -> Path:
    if snapshot_dir is not None:
        return Path(snapshot_dir)
    target = _config_target(config_path)
    return target.parent / "release_snapshots"


def _write_snapshot(cfg: GrayReleaseConfig, snapshot_dir: Path) -> Path:
    """保存当前灰度配置快照（用于回滚的回滚）；返回快照路径。"""

    snapshot_dir = Path(snapshot_dir)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = _now_iso().replace(":", "-")
    snap = snapshot_dir / f"gray_release.{stamp}.snapshot.json"
    snap.write_text(
        json.dumps(cfg.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return snap


def _latest_snapshot(snapshot_dir: Path) -> Path | None:
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.is_dir():
        return None
    files = sorted(snapshot_dir.glob("gray_release.*.snapshot.json"))
    return files[-1] if files else None


def _load_thresholds(thresholds_path: Path | str | None) -> list[Mapping[str, Any]] | None:
    """从 JSON 文件加载阈值条目注入（可选）；缺省返回 None（precheck 自动加载签字库）。"""

    if thresholds_path is None:
        return None
    p = Path(thresholds_path)
    if not p.is_file():
        return None
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, Mapping)]
    if isinstance(raw, Mapping) and isinstance(raw.get("thresholds"), Mapping):
        return list(raw["thresholds"].values())
    return None


def _audit(
    *,
    approval_id: str,
    interface: str,
    operator: str,
    action: str,
    result: str,
    audit_path: Path | str | None,
) -> None:
    """追加一条审计记录（仅引用，无真实数值）。"""

    append_audit_record(
        approval_id=approval_id or "",
        interface=interface or "*",
        operator=operator,
        action=action,
        result=result,
        audit_path=audit_path,
    )


# ---------------------------------------------------------------------------
# enable
# ---------------------------------------------------------------------------


def enable_release(
    *,
    interface: str,
    approval_id: str,
    config_path: Path | str | None = None,
    approval_path: Path | str | None = None,
    audit_path: Path | str | None = None,
    snapshot_dir: Path | str | None = None,
    thresholds_path: Path | str | None = None,
    ci_green: bool = False,
    rollback_ready: bool = False,
    review_log_path: Path | str | None = None,
    operator: str = DEFAULT_OPERATOR,
    require_audit_chain: bool = True,
) -> ReleaseResult:
    """启用某接口灰度（仅翻转灰度开关，绝不开启 engineering_enabled）。

    强制前置（任一不满足 → 拒绝，退出码非 0）：
    1. 加载灰度配置；
    2. 授权存在且 interface 匹配（G6 证据）；
    3. 授权已生效（effective_time 不在未来）；
    4. G1-G6 发布前门禁全部通过；
    5. 启用前快照成功（snapshot 缺失 → 拒绝）。

    红线：不翻转 engineering_enabled、不改 verified.json、不输出 approved。
    """

    iface = (interface or "").strip()
    cfg = load_gray_release_config(config_path)

    # 步骤 2：授权存在且匹配目标接口。
    approval = find_approval_record(approval_id, approval_path)
    if approval is None or approval.interface != iface:
        _audit(
            approval_id=approval_id,
            interface=iface,
            operator=operator,
            action=ReleaseAction.ENABLE.value,
            result=ReleaseOutcome.REJECTED_NO_APPROVAL.value,
            audit_path=audit_path,
        )
        return ReleaseResult(
            success=False,
            action=ReleaseAction.ENABLE.value,
            interface=iface,
            message=REASON_NO_APPROVAL,
        )

    # 步骤 3：授权已生效（G6 增强）。
    if not is_approval_effective(approval):
        _audit(
            approval_id=approval.approval_id,
            interface=iface,
            operator=operator,
            action=ReleaseAction.ENABLE.value,
            result=ReleaseOutcome.REJECTED_NOT_EFFECTIVE.value,
            audit_path=audit_path,
        )
        return ReleaseResult(
            success=False,
            action=ReleaseAction.ENABLE.value,
            interface=iface,
            message=REASON_NOT_EFFECTIVE,
            approval_id=approval.approval_id,
        )

    # 步骤 4：G1-G6 发布前门禁。
    thresholds = _load_thresholds(thresholds_path)
    allowed, reasons = release_precheck(
        interface=iface,
        thresholds=thresholds,
        ci_green=ci_green,
        rollback_ready=rollback_ready,
        authorization_present=True,
        review_log_path=review_log_path,
        require_audit_chain=require_audit_chain,
    )
    if not allowed:
        _audit(
            approval_id=approval.approval_id,
            interface=iface,
            operator=operator,
            action=ReleaseAction.ENABLE.value,
            result=ReleaseOutcome.REJECTED_GATE_BLOCKED.value,
            audit_path=audit_path,
        )
        return ReleaseResult(
            success=False,
            action=ReleaseAction.ENABLE.value,
            interface=iface,
            message=REASON_GATE_BLOCKED,
            allowed=allowed,
            reasons=list(reasons),
            approval_id=approval.approval_id,
        )

    # 步骤 5：启用前快照（snapshot 缺失 → 拒绝）。
    snap_dir = _snapshot_dir_of(config_path, snapshot_dir)
    try:
        snap = _write_snapshot(cfg, snap_dir)
    except OSError:
        _audit(
            approval_id=approval.approval_id,
            interface=iface,
            operator=operator,
            action=ReleaseAction.ENABLE.value,
            result=ReleaseOutcome.REJECTED_SNAPSHOT_FAILED.value,
            audit_path=audit_path,
        )
        return ReleaseResult(
            success=False,
            action=ReleaseAction.ENABLE.value,
            interface=iface,
            message=REASON_SNAPSHOT_FAILED,
            allowed=allowed,
            reasons=list(reasons),
            approval_id=approval.approval_id,
        )

    # 翻转灰度开关（绝非 engineering_enabled）。
    entry = cfg.entries.get(iface) or GrayReleaseEntry(interface=iface)
    entry.enabled = True
    if entry.rollout_pct <= 0:
        entry.rollout_pct = 100.0  # pending_verification
    cfg.entries[iface] = entry
    _write_config(cfg, config_path)

    _audit(
        approval_id=approval.approval_id,
        interface=iface,
        operator=operator,
        action=ReleaseAction.ENABLE.value,
        result=ReleaseOutcome.SUCCESS.value,
        audit_path=audit_path,
    )
    return ReleaseResult(
        success=True,
        action=ReleaseAction.ENABLE.value,
        interface=iface,
        message="已启用接口灰度（仅翻转灰度开关，未开启 engineering_enabled）",
        allowed=allowed,
        reasons=list(reasons),
        approval_id=approval.approval_id,
        snapshot_path=str(snap),
    )


# ---------------------------------------------------------------------------
# disable
# ---------------------------------------------------------------------------


def disable_release(
    *,
    interface: str,
    config_path: Path | str | None = None,
    audit_path: Path | str | None = None,
    snapshot_dir: Path | str | None = None,
    operator: str = DEFAULT_OPERATOR,
) -> ReleaseResult:
    """关闭某接口灰度（恢复 pending_verification）。"""

    iface = (interface or "").strip()
    cfg = load_gray_release_config(config_path)
    snap_dir = _snapshot_dir_of(config_path, snapshot_dir)
    try:
        _write_snapshot(cfg, snap_dir)
    except OSError:
        return ReleaseResult(
            success=False,
            action=ReleaseAction.DISABLE.value,
            interface=iface,
            message=REASON_SNAPSHOT_FAILED,
        )

    entry = cfg.entries.get(iface) or GrayReleaseEntry(interface=iface)
    entry.enabled = False
    cfg.entries[iface] = entry
    _write_config(cfg, config_path)

    _audit(
        approval_id="",
        interface=iface,
        operator=operator,
        action=ReleaseAction.DISABLE.value,
        result=ReleaseOutcome.SUCCESS.value,
        audit_path=audit_path,
    )
    return ReleaseResult(
        success=True,
        action=ReleaseAction.DISABLE.value,
        interface=iface,
        message="已关闭接口灰度（恢复 pending_verification）",
    )


# ---------------------------------------------------------------------------
# rollback
# ---------------------------------------------------------------------------


def rollback_release(
    *,
    interface: str | None = None,
    global_: bool = False,
    config_path: Path | str | None = None,
    audit_path: Path | str | None = None,
    snapshot_dir: Path | str | None = None,
    operator: str = DEFAULT_OPERATOR,
) -> ReleaseResult:
    """回滚：接口级关闭或全局熔断（恢复 pending_verification）。

    ``global_=True`` 时关闭所有接口（熔断）；否则关闭指定接口。仅翻转灰度开关，
    不触碰 review_log / approvals。
    """

    cfg = load_gray_release_config(config_path)
    snap_dir = _snapshot_dir_of(config_path, snapshot_dir)
    try:
        _write_snapshot(cfg, snap_dir)
    except OSError:
        return ReleaseResult(
            success=False,
            action=ReleaseAction.ROLLBACK.value,
            interface=interface or "*",
            message=REASON_SNAPSHOT_FAILED,
        )

    if global_:
        for entry in cfg.entries.values():
            entry.enabled = False
        cfg.default_enabled = False
        target = "*"
    else:
        iface = (interface or "").strip()
        entry = cfg.entries.get(iface) or GrayReleaseEntry(interface=iface)
        entry.enabled = False
        cfg.entries[iface] = entry
        target = iface

    _write_config(cfg, config_path)
    _audit(
        approval_id="",
        interface=target,
        operator=operator,
        action=ReleaseAction.ROLLBACK.value,
        result=ReleaseOutcome.SUCCESS.value,
        audit_path=audit_path,
    )
    return ReleaseResult(
        success=True,
        action=ReleaseAction.ROLLBACK.value,
        interface=target,
        message="已回滚（熔断/接口关闭，恢复 pending_verification）",
    )


# ---------------------------------------------------------------------------
# restore
# ---------------------------------------------------------------------------


def restore_release(
    *,
    config_path: Path | str | None = None,
    audit_path: Path | str | None = None,
    snapshot_dir: Path | str | None = None,
    operator: str = DEFAULT_OPERATOR,
) -> ReleaseResult:
    """从最近快照恢复灰度配置（回滚的回滚）；无快照 → 拒绝。"""

    snap_dir = _snapshot_dir_of(config_path, snapshot_dir)
    latest = _latest_snapshot(snap_dir)
    if latest is None:
        _audit(
            approval_id="",
            interface="*",
            operator=operator,
            action=ReleaseAction.RESTORE.value,
            result=ReleaseOutcome.REJECTED_NO_SNAPSHOT.value,
            audit_path=audit_path,
        )
        return ReleaseResult(
            success=False,
            action=ReleaseAction.RESTORE.value,
            interface="*",
            message=REASON_NO_SNAPSHOT,
        )

    try:
        raw = json.loads(latest.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ReleaseResult(
            success=False,
            action=ReleaseAction.RESTORE.value,
            interface="*",
            message=REASON_NO_SNAPSHOT,
        )
    cfg = GrayReleaseConfig.from_dict(raw)
    _write_config(cfg, config_path)

    _audit(
        approval_id="",
        interface="*",
        operator=operator,
        action=ReleaseAction.RESTORE.value,
        result=ReleaseOutcome.SUCCESS.value,
        audit_path=audit_path,
    )
    return ReleaseResult(
        success=True,
        action=ReleaseAction.RESTORE.value,
        interface="*",
        message="已从快照恢复灰度配置",
        snapshot_path=str(latest),
    )


__all__ = [
    "DEFAULT_OPERATOR",
    "ReleaseAction",
    "ReleaseOutcome",
    "REASON_NO_APPROVAL",
    "REASON_NOT_EFFECTIVE",
    "REASON_GATE_BLOCKED",
    "REASON_SNAPSHOT_FAILED",
    "REASON_NO_SNAPSHOT",
    "ReleaseResult",
    "enable_release",
    "disable_release",
    "rollback_release",
    "restore_release",
]
