"""Sprint 3.2.5-B 灰度发布基础设施测试。

覆盖任务要求的 7 点：
1. gate 默认拒绝
2. missing verified 拒绝
3. enabled=false 保护
4. gray allowlist
5. monitor 写入
6. rollback 恢复 pending
7. 不可绕过 engineering_enabled

以及门禁正向分支（逻辑分支验证，不落盘、不翻 engineering_enabled、不输出 approved）。

红线守约：全部 pending_verification，不读真实参数、不写 verified.json、不开启
engineering_enabled、不输出真实 approved。
"""

from __future__ import annotations

from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.approved_monitor import (
    ApprovedRecord,
    append_approved_record,
    load_approved_records,
)
from agents.engineering.gate import (
    GATE_G1_GOVERNANCE,
    GATE_G2_DUAL_SIGN,
    GATE_G4_AUDIT_CHAIN,
    GATE_G6_AUTHORIZATION,
    can_enable_engineering,
)
from agents.engineering.gray_release import (
    GrayReleaseConfig,
    GrayReleaseEntry,
    is_interface_gray_allowed,
    load_gray_release_config,
)
from agents.engineering.rollback import RollbackHandler


# ---------------------------------------------------------------------------
# 1. gate 默认拒绝
# ---------------------------------------------------------------------------

def test_gate_default_denies():
    """无任何注入时，门禁默认拒绝（G1/G2/G3/G5/G6 均不满足）。"""

    allowed, reasons = can_enable_engineering()
    assert allowed is False
    assert reasons  # 非空阻塞原因
    assert GATE_G6_AUTHORIZATION in reasons  # 授权默认缺失


# ---------------------------------------------------------------------------
# 2. missing verified 拒绝
# ---------------------------------------------------------------------------

def test_gate_missing_verified_rejected():
    """阈值未 verified / 未双签 → G1 + G2 阻塞。"""

    entry = {"threshold_id": "E-TH-01", "verified": False}
    allowed, reasons = can_enable_engineering(
        thresholds=[entry],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        require_audit_chain=False,
    )
    assert allowed is False
    assert any(r.startswith(GATE_G1_GOVERNANCE) for r in reasons)
    assert GATE_G2_DUAL_SIGN in reasons


# ---------------------------------------------------------------------------
# 门禁正向分支（逻辑验证，不真实激活）
# ---------------------------------------------------------------------------

def _fully_verified_entry(tid: str) -> dict:
    return {
        "threshold_id": tid,
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-31T00:00:00+00:00",
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-31T00:00:00+00:00",
        "threshold_status": "verified",
        "version": "1.0",
        "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
    }


def test_gate_positive_path_all_green():
    """六项门禁全部满足（内存注入，非真实激活）→ allowed=True 且无阻塞原因。"""

    allowed, reasons = can_enable_engineering(
        thresholds=[_fully_verified_entry("E-TH-01")],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        require_audit_chain=False,
    )
    assert allowed is True
    assert reasons == []


def test_gate_audit_chain_broken_rejected(tmp_path: Path):
    """审核链断裂 → G4 阻塞（其余门禁已满足）。"""

    broken = tmp_path / "review_log.jsonl"
    broken.write_text(
        '{"event_id":"a","threshold_id":"E-TH-01","action":"verify","signer_role":"principal","signer":"principal-001","timestamp":"t","source_ref":"x","prev_event_id":null}\n'
        '{"event_id":"b","threshold_id":"E-TH-01","action":"verify","signer_role":"expert","signer":"expert-001","timestamp":"t","source_ref":"x","prev_event_id":"WRONG"}\n',
        encoding="utf-8",
    )
    allowed, reasons = can_enable_engineering(
        thresholds=[],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        review_log_path=broken,
        require_audit_chain=True,
    )
    assert allowed is False
    assert GATE_G4_AUDIT_CHAIN in reasons


# ---------------------------------------------------------------------------
# 3. enabled=false 保护 + 7. 不可绕过 engineering_enabled
# ---------------------------------------------------------------------------

def _wind_config(enabled: bool = True, tags=None, pct: float = 100.0) -> GrayReleaseConfig:
    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(
        interface="wind_pressure",
        enabled=enabled,
        allowed_project_tags=list(tags or []),
        rollout_pct=pct,
    )
    return cfg


def test_enabled_false_protects():
    """全局 engineering_enabled=false 时，即使灰度条目 enabled=true 也恒 False。"""

    cfg = _wind_config(enabled=True, pct=100.0)
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=False) is False


def test_cannot_bypass_engineering_enabled():
    """不可绕过全局闸门：门禁允许 ≠ 激活；全局 false 时灰度恒 False。"""

    # 门禁即使全绿，也不翻转 engineering_enabled（全局闸仍由 config 控制）。
    allowed, _ = can_enable_engineering(
        thresholds=[_fully_verified_entry("E-TH-01")],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        require_audit_chain=False,
    )
    assert allowed is True
    # 但真实 config 仍 false → 灰度仍拒绝（不可绕过）。
    assert load_engineering_enabled() is False
    assert is_interface_gray_allowed(_wind_config(), "wind_pressure", engineering_enabled=False) is False

    # 即便全局 true，条目未启用也拒绝。
    assert is_interface_gray_allowed(_wind_config(enabled=False), "wind_pressure", engineering_enabled=True) is False


# ---------------------------------------------------------------------------
# 4. gray allowlist
# ---------------------------------------------------------------------------

def test_gray_allowlist():
    """项目标签白名单：命中放行，未命中 / 缺标签拒绝。"""

    cfg = _wind_config(enabled=True, tags=["proj-a"], pct=100.0)
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-a", engineering_enabled=True) is True
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-b", engineering_enabled=True) is False
    assert is_interface_gray_allowed(cfg, "wind_pressure", None, engineering_enabled=True) is False
    # 缺省条目（无白名单配置）→ 用 default_enabled（False）→ 拒绝
    empty = GrayReleaseConfig()
    assert is_interface_gray_allowed(empty, "wind_pressure", "proj-a", engineering_enabled=True) is False


def test_gray_rollout_pct_gate():
    """rollout_pct <= 0 视为未放量 → 拒绝。"""

    cfg = _wind_config(enabled=True, tags=["proj-a"], pct=0.0)
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-a", engineering_enabled=True) is False


def test_gray_config_roundtrip(tmp_path: Path):
    """灰度配置读写 + 缺省保守（缺失文件 → 全 False）。"""

    missing = load_gray_release_config(tmp_path / "nope.json")
    assert missing.default_enabled is False
    assert missing.entries == {}

    p = tmp_path / "gray.json"
    p.write_text(
        '{"schema_version":"1.0","default_enabled":false,'
        '"entries":[{"interface":"wind_pressure","enabled":true,"allowed_project_tags":["proj-a"],"rollout_pct":100.0}]}',  # pending_verification
        encoding="utf-8",
    )
    loaded = load_gray_release_config(p)
    assert loaded.entries["wind_pressure"].enabled is True
    assert loaded.entries["wind_pressure"].rollout_pct == 100.0  # pending_verification


# ---------------------------------------------------------------------------
# 5. monitor 写入
# ---------------------------------------------------------------------------

def test_approved_monitor_write_and_read(tmp_path: Path):
    """append-only 写入并回放；仅含引用字段，无真实工程数值。"""

    p = tmp_path / "approved_monitor.jsonl"
    append_approved_record(
        interface="wind_pressure",
        threshold_version="1.0",
        sign_off_id="abc123",
        review_log_ref="evt-001",
        monitor_path=p,
    )
    append_approved_record(
        interface="wind_pressure",
        threshold_version="1.0",
        sign_off_id="def456",
        review_log_ref="evt-002",
        error="sign_off_mismatch",
        monitor_path=p,
    )
    records = load_approved_records(p)
    assert len(records) == 2
    assert isinstance(records[0], ApprovedRecord)
    assert records[0].interface == "wind_pressure"  # pending_verification
    assert records[0].threshold_version == "1.0"
    assert records[0].sign_off_id == "abc123"
    assert records[0].review_log_ref == "evt-001"
    assert records[0].error is None
    assert records[1].error == "sign_off_mismatch"
    # 仅含引用/标识符字段，不泄漏真实工程数值。
    assert set(records[0].to_dict().keys()) == {
        "schema_version",
        "interface",
        "threshold_version",
        "sign_off_id",
        "review_log_ref",
        "error",
        "timestamp",
    }


def test_approved_monitor_skips_corrupt(tmp_path: Path):
    """损坏行被跳过，不影响其余记录回放。"""

    p = tmp_path / "approved_monitor.jsonl"
    p.write_text(
        '{"schema_version":"1.0","interface":"wind_pressure","threshold_version":"1.0","sign_off_id":"a","review_log_ref":"r","error":null,"timestamp":"t"}\n'  # pending_verification
        "this is not json\n",
        encoding="utf-8",
    )
    records = load_approved_records(p)
    assert len(records) == 1


# ---------------------------------------------------------------------------
# 6. rollback 恢复 pending
# ---------------------------------------------------------------------------

def test_rollback_interface_restores_pending():
    """接口级关闭后该接口不再放行；restore 后恢复。"""

    cfg = _wind_config(enabled=True, tags=["proj-a"], pct=100.0)
    handler = RollbackHandler(cfg)
    handler.snapshot()
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-a", engineering_enabled=True) is True

    handler.close_interface("wind_pressure")
    # 关闭 → 接口不再允许 → 结果回落 pending_verification。
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-a", engineering_enabled=True) is False

    handler.restore()
    assert is_interface_gray_allowed(cfg, "wind_pressure", "proj-a", engineering_enabled=True) is True


def test_rollback_global_close_and_restore():
    """全局熔断关闭所有接口；restore 恢复。"""

    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(interface="wind_pressure", enabled=True, rollout_pct=100.0)  # pending_verification
    cfg.entries["hardware"] = GrayReleaseEntry(interface="hardware", enabled=True, rollout_pct=100.0)
    handler = RollbackHandler(cfg)
    handler.snapshot()
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=True) is True
    assert is_interface_gray_allowed(cfg, "hardware", engineering_enabled=True) is True

    handler.close_global()
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=True) is False
    assert is_interface_gray_allowed(cfg, "hardware", engineering_enabled=True) is False

    handler.restore()
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=True) is True
    assert is_interface_gray_allowed(cfg, "hardware", engineering_enabled=True) is True


def test_rollback_auto_snapshot():
    """未显式 snapshot 时 close 自动快照，restore 仍生效。"""

    cfg = _wind_config(enabled=True, pct=100.0)
    handler = RollbackHandler(cfg)
    handler.close_interface("wind_pressure")
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=True) is False
    handler.restore()
    assert is_interface_gray_allowed(cfg, "wind_pressure", engineering_enabled=True) is True
