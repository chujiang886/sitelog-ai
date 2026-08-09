"""Sprint 3.2.5-F 灰度发布执行基础设施测试。

覆盖任务要求的 7 点：
1. 无 approval 拒绝 enable
2. G1 失败拒绝
3. G6 失败拒绝（授权未生效 / 门禁层）
4. snapshot 缺失拒绝
5. rollback 恢复
6. audit 写入
7. engineering_enabled=false 保护

以及 approval 追加/查找、audit 追加/读取、gate 正向、CLI 退出码、快照边界等。

红线守约：全部 pending_verification，不读真实参数、不写 verified.json、不开启
engineering_enabled、不输出真实 approved；所有写盘路径均为临时路径，不污染仓库。
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.gray_release import (
    GrayReleaseConfig,
    GrayReleaseEntry,
    is_interface_gray_allowed,
    load_gray_release_config,
)
from agents.engineering.release import (
    EngineeringReleaseApproval,
    ReleaseAuditRecord,
    ReleaseOutcome,
    append_approval_record,
    append_audit_record,
    enable_release,
    find_approval_record,
    is_approval_effective,
    load_audit_records,
    load_approval_records,
    release_precheck,
    restore_release,
    rollback_release,
    disable_release,
)
from agents.engineering.release import controller as release_controller
from agents.engineering.gate.enable_gate import GATE_G1_GOVERNANCE, GATE_G2_DUAL_SIGN


# ---------------------------------------------------------------------------
# 共享助手
# ---------------------------------------------------------------------------


def _wind_config(enabled: bool = True, pct: float = 100.0) -> GrayReleaseConfig:  # pending_verification
    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(
        interface="wind_pressure", enabled=enabled, rollout_pct=pct  # pending_verification
    )
    return cfg


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
        "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},  # pending_verification
    }


def _write_thresholds_file(tmp_path: Path, entries: list[dict]) -> Path:
    p = tmp_path / "thresholds.json"
    p.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")
    return p


def _write_empty_review_log(tmp_path: Path) -> Path:
    p = tmp_path / "review_log.jsonl"
    p.write_text("", encoding="utf-8")
    return p


def _write_valid_review_log(tmp_path: Path) -> Path:
    """写入含四类必需事件且链式完好的真实审核链（模拟 intake 流程已完成的态）。

    3.2.5-G2 G4 增强后，enable / precheck 成功路径必须提供真实审核链；
    本助手构造与 ``check_review_log_chain`` 一致的合法链，供 happy-path / 快照
    失败路径测试使用（不写真实工程数值，仅标识符事件）。
    """

    p = tmp_path / "review_log.jsonl"
    events = [
        {"event_id": "e1", "threshold_id": "E-TH-01", "action": "submit",
         "signer_role": "submitter", "signer": "s1", "timestamp": "t1",
         "source_ref": "x", "prev_event_id": None},
        {"event_id": "e2", "threshold_id": "E-TH-01", "action": "review",
         "signer_role": "principal", "signer": "p1", "timestamp": "t2",
         "source_ref": "x", "prev_event_id": "e1"},
        {"event_id": "e3", "threshold_id": "E-TH-01", "action": "expert_recheck",
         "signer_role": "expert", "signer": "e1", "timestamp": "t3",
         "source_ref": "x", "prev_event_id": "e2"},
        {"event_id": "e4", "threshold_id": "E-TH-01", "action": "verified",
         "signer_role": "principal", "signer": "p1", "timestamp": "t4",
         "source_ref": "x", "prev_event_id": "e3"},
    ]
    p.write_text(
        "\n".join(json.dumps(ev, ensure_ascii=False) for ev in events) + "\n",
        encoding="utf-8",
    )
    return p


def _make_approval(
    tmp_path: Path,
    *,
    approval_id: str = "APR-001",
    interface: str = "wind_pressure",
    effective_time: str = "2026-07-31T00:00:00+00:00",
) -> Path:
    p = tmp_path / "release_approvals.jsonl"
    append_approval_record(
        approval_id=approval_id,
        interface=interface,
        scope="proj-a",
        authorized_by="principal-release",
        effective_time=effective_time,
        rollback_owner="sre-owner",
        approval_document_ref="doc-001",
        approval_path=p,
    )
    return p


def _load_cli():
    """从 scripts/release/gray_release_ctl.py 动态加载 CLI 模块（非包结构）。"""

    import importlib.util

    path = Path(__file__).resolve().parents[2] / "scripts" / "release" / "gray_release_ctl.py"
    spec = importlib.util.spec_from_file_location("gray_release_ctl", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# Approval：追加 / 查找 / append-only
# ---------------------------------------------------------------------------


def test_approval_append_and_find(tmp_path: Path):
    """append-only：追加两条，回放 2 条，按 id 查找，缺失返回 None。"""

    p = tmp_path / "release_approvals.jsonl"
    append_approval_record(
        approval_id="APR-001", interface="wind_pressure", scope="proj-a",
        authorized_by="principal-release", effective_time="2026-07-31T00:00:00+00:00",
        rollback_owner="sre-owner", approval_document_ref="doc-001", approval_path=p,
    )
    append_approval_record(
        approval_id="APR-002", interface="glass_safety", scope="proj-b",
        authorized_by="principal-release", effective_time="2026-07-31T00:00:00+00:00",
        rollback_owner="sre-owner", approval_document_ref="doc-002", approval_path=p,
    )
    records = load_approval_records(p)
    assert len(records) == 2
    assert isinstance(records[0], EngineeringReleaseApproval)
    assert records[0].approval_id == "APR-001"
    assert find_approval_record("APR-002", p).interface == "glass_safety"
    assert find_approval_record("APR-999", p) is None
    # 仅含引用字段，无真实工程数值。
    assert set(records[0].to_dict().keys()) == {
        "schema_version", "approval_id", "interface", "scope", "authorized_by",
        "effective_time", "rollback_owner", "approval_document_ref", "created_at",
    }


def test_approval_fields_only_identifiers(tmp_path: Path):
    """授权记录字段均为标识符/引用，绝不出现真实工程数值。"""

    rec = EngineeringReleaseApproval(
        approval_id="APR-X", interface="wind_pressure", scope="proj-a",
        authorized_by="principal-release", effective_time="2026-07-31T00:00:00+00:00",
        rollback_owner="sre-owner", approval_document_ref="doc-x",
    )
    for value in rec.to_dict().values():
        assert not isinstance(value, (int, float))


# ---------------------------------------------------------------------------
# Gate：默认拒绝 / 正向 / G6 失败
# ---------------------------------------------------------------------------


def test_release_precheck_default_denies():
    """无任何注入时，门禁默认拒绝（G1/G2/G3/G5/G6 均不满足）。"""

    allowed, reasons = release_precheck(interface="wind_pressure")
    assert allowed is False
    assert reasons  # 非空阻塞原因


def test_release_precheck_all_green():
    """六项门禁全部满足（内存注入，非真实激活）→ allowed=True 且无阻塞原因。"""

    allowed, reasons = release_precheck(
        interface="wind_pressure",
        thresholds=[_fully_verified_entry("E-TH-01")],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        require_audit_chain=False,
    )
    assert allowed is True
    assert reasons == []


def test_release_precheck_g6_fails():
    """G6 缺失（authorization_present=False）→ 拒绝且含 G6 原因。"""

    allowed, reasons = release_precheck(
        interface="wind_pressure",
        thresholds=[_fully_verified_entry("E-TH-01")],
        ci_green=True,
        rollback_ready=True,
        authorization_present=False,
        require_audit_chain=False,
    )
    assert allowed is False
    assert any(r.startswith("G6_") for r in reasons)


# ---------------------------------------------------------------------------
# 1. 无 approval 拒绝 enable
# ---------------------------------------------------------------------------


def test_enable_no_approval_rejected(tmp_path: Path):
    """无授权记录 → enable 拒绝（REJECTED_NO_APPROVAL），且不翻转开关。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    _wind_config(enabled=False).to_dict()  # 无文件落盘，仅构造

    result = enable_release(
        interface="wind_pressure",
        approval_id="APR-MISSING",
        config_path=cfg_path,
        audit_path=audit_path,
        snapshot_dir=snap_dir,
    )
    assert result.success is False
    assert result.message == release_controller.REASON_NO_APPROVAL
    # 拒绝时不应创建/改写灰度配置。
    assert not cfg_path.is_file()
    # 审计记录已写入（rejected）。
    audits = load_audit_records(audit_path)
    assert len(audits) == 1
    assert audits[0].result == ReleaseOutcome.REJECTED_NO_APPROVAL.value


# ---------------------------------------------------------------------------
# 2. G1 失败拒绝
# ---------------------------------------------------------------------------


def test_enable_g1_fails_rejected(tmp_path: Path):
    """授权有效但阈值未治理（G1/G2 失败）→ enable 拒绝，reasons 含 G1。"""

    cfg_path = tmp_path / "gray_release.json"
    approval_path = _make_approval(tmp_path)
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    review_log = _write_empty_review_log(tmp_path)

    # thresholds=None → 加载真实签字库（全 draft）→ G1/G2 失败。
    result = enable_release(
        interface="wind_pressure",
        approval_id="APR-001",
        config_path=cfg_path,
        approval_path=approval_path,
        audit_path=audit_path,
        snapshot_dir=snap_dir,
        ci_green=True,
        rollback_ready=True,
        review_log_path=review_log,
    )
    assert result.success is False
    assert result.message == release_controller.REASON_GATE_BLOCKED
    assert any(r.startswith(GATE_G1_GOVERNANCE) for r in (result.reasons or []))
    assert any(r.startswith(GATE_G2_DUAL_SIGN) for r in (result.reasons or []))


# ---------------------------------------------------------------------------
# 3. G6 失败拒绝（授权未生效）
# ---------------------------------------------------------------------------


def test_enable_g6_not_effective_rejected(tmp_path: Path):
    """授权存在但 effective_time 在未来 → 视为尚未授权（G6 失败）→ 拒绝。"""

    cfg_path = tmp_path / "gray_release.json"
    future = "2099-01-01T00:00:00+00:00"
    approval_path = _make_approval(tmp_path, effective_time=future)
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    review_log = _write_empty_review_log(tmp_path)
    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])

    result = enable_release(
        interface="wind_pressure",
        approval_id="APR-001",
        config_path=cfg_path,
        approval_path=approval_path,
        audit_path=audit_path,
        snapshot_dir=snap_dir,
        thresholds_path=thresholds,
        ci_green=True,
        rollback_ready=True,
        review_log_path=review_log,
    )
    assert result.success is False
    assert result.message == release_controller.REASON_NOT_EFFECTIVE
    assert result.approval_id == "APR-001"


def test_is_approval_effective_variants():
    """is_approval_effective：空/不可解析/过去→生效；未来→未生效。"""

    from agents.engineering.release.approval import EngineeringReleaseApproval

    empty = EngineeringReleaseApproval(
        approval_id="A", interface="i", scope="s", authorized_by="u",
        effective_time="", rollback_owner="r", approval_document_ref="d",
    )
    bad = EngineeringReleaseApproval(
        approval_id="A", interface="i", scope="s", authorized_by="u",
        effective_time="not-a-date", rollback_owner="r", approval_document_ref="d",
    )
    future = EngineeringReleaseApproval(
        approval_id="A", interface="i", scope="s", authorized_by="u",
        effective_time="2099-01-01T00:00:00+00:00", rollback_owner="r", approval_document_ref="d",
    )
    assert is_approval_effective(empty) is True
    assert is_approval_effective(bad) is True
    assert is_approval_effective(future) is False


# ---------------------------------------------------------------------------
# 4. snapshot 缺失拒绝
# ---------------------------------------------------------------------------


def test_enable_snapshot_missing_rejected(tmp_path: Path):
    """启用前快照失败（snapshot_dir 为已存在文件）→ 拒绝（REJECTED_SNAPSHOT_FAILED）。"""

    cfg_path = tmp_path / "gray_release.json"
    approval_path = _make_approval(tmp_path)
    audit_path = tmp_path / "release_audit.jsonl"
    # 用一个已存在的文件充当 snapshot_dir，使 mkdir 失败 → 快照缺失。
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    review_log = _write_valid_review_log(tmp_path)  # G4 需真实审核链
    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])

    result = enable_release(
        interface="wind_pressure",
        approval_id="APR-001",
        config_path=cfg_path,
        approval_path=approval_path,
        audit_path=audit_path,
        snapshot_dir=str(blocker),
        thresholds_path=thresholds,
        ci_green=True,
        rollback_ready=True,
        review_log_path=review_log,
    )
    assert result.success is False
    assert result.message == release_controller.REASON_SNAPSHOT_FAILED
    assert result.reasons is not None


# ---------------------------------------------------------------------------
# enable 成功路径 + 7. engineering_enabled=false 保护
# ---------------------------------------------------------------------------


def test_enable_success_flips_switch_only(tmp_path: Path):
    """授权+G1-G6 全过 → enable 成功，仅翻转灰度开关；engineering_enabled 不变。"""

    cfg_path = tmp_path / "gray_release.json"
    approval_path = _make_approval(tmp_path)
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    review_log = _write_valid_review_log(tmp_path)  # G4 需真实审核链
    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])

    # 预置 wind_pressure 条目为关闭态。
    _wind_config(enabled=False).to_dict()
    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(
        interface="wind_pressure", enabled=False, rollout_pct=0.0  # pending_verification
    )
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    result = enable_release(
        interface="wind_pressure",
        approval_id="APR-001",
        config_path=cfg_path,
        approval_path=approval_path,
        audit_path=audit_path,
        snapshot_dir=snap_dir,
        thresholds_path=thresholds,
        ci_green=True,
        rollback_ready=True,
        review_log_path=review_log,
    )
    assert result.success is True
    assert result.approval_id == "APR-001"
    assert result.snapshot_path

    # 灰度开关被翻转。
    loaded = load_gray_release_config(cfg_path)
    assert loaded.entries["wind_pressure"].enabled is True
    assert loaded.entries["wind_pressure"].rollout_pct == 100.0  # pending_verification

    # 红线保护：engineering_enabled 仍为 False，全局闸门未变。
    assert load_engineering_enabled() is False
    assert is_interface_gray_allowed(loaded, "wind_pressure", engineering_enabled=False) is False
    # 即便全局 true，本动作也未触碰 engineering_enabled（仅灰度条目）。
    assert is_interface_gray_allowed(loaded, "wind_pressure", engineering_enabled=True) is True


# ---------------------------------------------------------------------------
# 5. rollback 恢复
# ---------------------------------------------------------------------------


def test_rollback_and_restore_roundtrip(tmp_path: Path):
    """接口级回滚关闭 → 恢复快照后重新放行；全局熔断同理。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"

    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    # 接口级回滚。
    r1 = rollback_release(interface="wind_pressure", config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert r1.success is True
    assert load_gray_release_config(cfg_path).entries["wind_pressure"].enabled is False

    # 从快照恢复。
    r2 = restore_release(config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert r2.success is True
    assert load_gray_release_config(cfg_path).entries["wind_pressure"].enabled is True

    # 全局熔断。
    r3 = rollback_release(global_=True, config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert r3.success is True
    restored = load_gray_release_config(cfg_path)
    assert restored.default_enabled is False
    assert restored.entries["wind_pressure"].enabled is False

    # 恢复全局。
    r4 = restore_release(config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert r4.success is True
    assert load_gray_release_config(cfg_path).entries["wind_pressure"].enabled is True


def test_restore_without_snapshot_rejected(tmp_path: Path):
    """无快照时 restore → 拒绝（REJECTED_NO_SNAPSHOT）。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"  # 不存在
    result = restore_release(config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert result.success is False
    assert result.message == release_controller.REASON_NO_SNAPSHOT


def test_disable_closes_interface(tmp_path: Path):
    """disable 关闭接口灰度（恢复 pending_verification）。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    result = disable_release(interface="wind_pressure", config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    assert result.success is True
    assert load_gray_release_config(cfg_path).entries["wind_pressure"].enabled is False


# ---------------------------------------------------------------------------
# 6. audit 写入
# ---------------------------------------------------------------------------


def test_audit_records_written(tmp_path: Path):
    """操作后审计记录含 6 字段（仅引用），append-only 计数递增。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    disable_release(interface="wind_pressure", config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)
    rollback_release(global_=True, config_path=cfg_path, audit_path=audit_path, snapshot_dir=snap_dir)

    records = load_audit_records(audit_path)
    assert len(records) == 2
    for rec in records:
        assert isinstance(rec, ReleaseAuditRecord)
        assert set(rec.to_dict().keys()) == {
            "schema_version", "approval_id", "interface", "operator",
            "action", "timestamp", "result",
        }
        # 无真实工程数值：result/action 均为语义标记字符串。
        assert rec.action in {"disable", "rollback", "enable", "restore", "precheck"}
        assert not isinstance(rec.timestamp, (int, float))


def test_audit_append_only_increments(tmp_path: Path):
    """多次追加，记录数递增，不覆盖历史。"""

    p = tmp_path / "release_audit.jsonl"
    append_audit_record(approval_id="A1", interface="wind_pressure", operator="op", action="enable", result="success", audit_path=p)
    append_audit_record(approval_id="A2", interface="glass_safety", operator="op", action="disable", result="success", audit_path=p)
    records = load_audit_records(p)
    assert len(records) == 2
    assert records[0].approval_id == "A1"
    assert records[1].approval_id == "A2"


# ---------------------------------------------------------------------------
# 7. engineering_enabled=false 保护（综合）
# ---------------------------------------------------------------------------


def test_engineering_enabled_never_flipped_by_controller(tmp_path: Path):
    """任何 controller 操作都不翻转 engineering_enabled、不输出 approved。"""

    cfg_path = tmp_path / "gray_release.json"
    approval_path = _make_approval(tmp_path)
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    review_log = _write_empty_review_log(tmp_path)
    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])

    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(
        interface="wind_pressure", enabled=False, rollout_pct=0.0  # pending_verification
    )
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    # 即便授权+G1-G6 全过，enable 也只翻灰度开关。
    enable_release(
        interface="wind_pressure", approval_id="APR-001", config_path=cfg_path,
        approval_path=approval_path, audit_path=audit_path, snapshot_dir=snap_dir,
        thresholds_path=thresholds, ci_green=True, rollback_ready=True, review_log_path=review_log,
    )
    assert load_engineering_enabled() is False
    # 审计结果仅为 success / rejected 标记，不含 engineering_approved 真值。
    for rec in load_audit_records(audit_path):
        assert "approved" not in rec.result


# ---------------------------------------------------------------------------
# 快照边界（disable/rollback 快照失败分支）
# ---------------------------------------------------------------------------


def test_disable_snapshot_failure_rejected(tmp_path: Path):
    """disable 时快照失败（snapshot_dir 为文件）→ 拒绝。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    result = disable_release(interface="wind_pressure", config_path=cfg_path, audit_path=audit_path, snapshot_dir=str(blocker))
    assert result.success is False
    assert result.message == release_controller.REASON_SNAPSHOT_FAILED


def test_rollback_snapshot_failure_rejected(tmp_path: Path):
    """rollback 时快照失败（snapshot_dir 为文件）→ 拒绝。"""

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    result = rollback_release(interface="wind_pressure", config_path=cfg_path, audit_path=audit_path, snapshot_dir=str(blocker))
    assert result.success is False
    assert result.message == release_controller.REASON_SNAPSHOT_FAILED


# ---------------------------------------------------------------------------
# _load_thresholds 分支
# ---------------------------------------------------------------------------


def test_load_thresholds_shapes(tmp_path: Path):
    """_load_thresholds：list / Mapping(thresholds) / None / 损坏 / 缺失文件。"""

    list_p = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])
    assert release_controller._load_thresholds(str(list_p)) == [_fully_verified_entry("E-TH-01")]

    map_p = tmp_path / "map.json"
    map_p.write_text(json.dumps({"thresholds": {"E-TH-01": _fully_verified_entry("E-TH-01")}}), encoding="utf-8")
    assert release_controller._load_thresholds(str(map_p)) == [_fully_verified_entry("E-TH-01")]

    assert release_controller._load_thresholds(None) is None
    missing = tmp_path / "nope.json"
    assert release_controller._load_thresholds(str(missing)) is None
    corrupt = tmp_path / "bad.json"
    corrupt.write_text("not json", encoding="utf-8")
    assert release_controller._load_thresholds(str(corrupt)) is None


# ---------------------------------------------------------------------------
# CLI 退出码
# ---------------------------------------------------------------------------


def test_cli_precheck_blocked_exit_nonzero(tmp_path: Path):
    """precheck（未授权）→ 退出码 1。"""

    ctl = _load_cli()

    code = ctl.main(["precheck", "--interface", "wind_pressure"])
    assert code == 1


def test_cli_precheck_authorized_green_exit_zero(tmp_path: Path):
    """precheck --authorized + 注入全绿阈值 + 空审核链 → 退出码 0。"""

    ctl = _load_cli()

    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])
    review_log = _write_valid_review_log(tmp_path)  # G4 需真实审核链
    code = ctl.main([
        "precheck", "--interface", "wind_pressure",
        "--thresholds", str(thresholds), "--ci-green", "--rollback-ready",
        "--authorized", "--review-log", str(review_log),
    ])
    assert code == 0


def test_cli_enable_rejected_exit_nonzero(tmp_path: Path):
    """enable（无授权）→ 退出码 1。"""

    ctl = _load_cli()

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    code = ctl.main([
        "enable", "--interface", "wind_pressure", "--approval-id", "MISSING",
        "--config", str(cfg_path), "--audit-path", str(audit_path),
        "--snapshot-dir", str(snap_dir),
    ])
    assert code == 1


def test_cli_enable_success_exit_zero(tmp_path: Path):
    """enable（授权+全绿+有效快照）→ 退出码 0。"""

    ctl = _load_cli()

    cfg_path = tmp_path / "gray_release.json"
    approval_path = _make_approval(tmp_path)
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    review_log = _write_valid_review_log(tmp_path)  # G4 需真实审核链
    thresholds = _write_thresholds_file(tmp_path, [_fully_verified_entry("E-TH-01")])

    cfg = GrayReleaseConfig()
    cfg.entries["wind_pressure"] = GrayReleaseEntry(
        interface="wind_pressure", enabled=False, rollout_pct=0.0  # pending_verification
    )
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    code = ctl.main([
        "enable", "--interface", "wind_pressure", "--approval-id", "APR-001",
        "--approval-path", str(approval_path), "--config", str(cfg_path),
        "--audit-path", str(audit_path), "--snapshot-dir", str(snap_dir),
        "--thresholds", str(thresholds), "--ci-green", "--rollback-ready",
        "--review-log", str(review_log),
    ])
    assert code == 0
    assert load_gray_release_config(cfg_path).entries["wind_pressure"].enabled is True


def test_cli_disable_rollback_restore_exit_codes(tmp_path: Path):
    """disable / rollback / restore 退出码 0（restore 依赖前置快照）。"""

    ctl = _load_cli()

    cfg_path = tmp_path / "gray_release.json"
    audit_path = tmp_path / "release_audit.jsonl"
    snap_dir = tmp_path / "snap"
    cfg = _wind_config(enabled=True, pct=100.0)  # pending_verification
    cfg_path.write_text(json.dumps(cfg.to_dict(), ensure_ascii=False), encoding="utf-8")

    assert ctl.main(["disable", "--interface", "wind_pressure", "--config", str(cfg_path),
                     "--audit-path", str(audit_path), "--snapshot-dir", str(snap_dir)]) == 0
    assert ctl.main(["rollback", "--global", "--config", str(cfg_path),
                     "--audit-path", str(audit_path), "--snapshot-dir", str(snap_dir)]) == 0
    # restore 依赖 rollback 写入的快照。
    assert ctl.main(["restore", "--config", str(cfg_path),
                     "--audit-path", str(audit_path), "--snapshot-dir", str(snap_dir)]) == 0
