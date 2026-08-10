"""阈值治理迁移基础设施测试（Phase 3.2 Sprint 3.2.4-E）。

覆盖：
1. v1 读取：自由文本 source_ref、无 threshold_status / version → schema v1；
2. v2 读取：结构化 source_ref（含 hash）+ threshold_status + version → schema v2；
3. migration 成功：v1 → v2，生成快照、原文件不变、D-TH 决策 A 补专家签位（null）；
4. migration 失败 rollback：输入损坏 → 输出不生成、快照保留、status=rolled_back；
5. source_ref 缺失：缺 standard / clause → 明确 reason；
6. hash 失败：内容不一致 / 格式非法 → 明确 reason；
7. D-TH 双签字段兼容：真实 D-TH 缺专家签位 → schema 解析为 None + 迁移补齐 null；
8. engineering_enabled=false 保护：迁移后全 draft/value=null，门禁与校验恒 pending。

红线：本测试**不写入**任何 verified=true、不填真实 value、不开启 engineering_enabled、
不输出真实 approved；仅用临时文件与内存夹具、纯标识符（principal-001 / expert-001）。
全部保持 pending_verification。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.engineering.thresholds.schema import (
    SCHEMA_VERSION_V1,
    SCHEMA_VERSION_V2,
    ThresholdGovernanceView,
    ThresholdSourceRef,
    ThresholdStatus,
    entry_schema_version,
    ensure_d_th_expert_sign_fields,
)
from agents.engineering.thresholds.source_ref_validator import (
    SOURCE_REF_CLAUSE_MISSING,
    SOURCE_REF_HASH_FORMAT_INVALID,
    SOURCE_REF_HASH_MISSING,
    SOURCE_REF_HASH_MISMATCH,
    SOURCE_REF_STANDARD_MISSING,
    compute_content_hash,
    validate_source_ref,
)
from agents.engineering.threshold_loader import (
    DEFAULT_VERIFIED_PATH as _E_PATH,
    governance_status,
    load_verified_thresholds,
)
from agents.engineering.threshold_migration import (
    MIGRATION_STATUS_ROLLED_BACK,
    MIGRATION_STATUS_SUCCESS,
    DTH_DECISION_A,
    MigrationReport,
    migrate_thresholds,
)
from agents.engineering.gate.enable_gate import can_enable_engineering
from agents.design.threshold_loader import DEFAULT_VERIFIED_PATH as _D_PATH


# ---------------------------------------------------------------------------
# 临时文件工具（不触碰仓库真实 verified.json）
# ---------------------------------------------------------------------------

def _write_tmp(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _sha256_of(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v1_document(entries: dict[str, Any]) -> dict[str, Any]:
    """构造一个最小 v1 阈值库（schema_version=1，自由文本 source_ref）。"""
    return {
        "schema_version": 1,
        "note": "test fixture pending_verification",
        "thresholds": entries,
    }


def _base_v1_entry(tid: str) -> dict[str, Any]:
    """v1 占位条目：无 threshold_status / version，自由文本 source_ref。"""
    return {
        "param": f"{tid} 占位参数",
        "value": None,
        "unit": "pending_verification",
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "source_ref": "待行业专家签字填入规范/标准号 pending_verification",
        "applies_to": ["iface_a"],
    }


# ---------------------------------------------------------------------------
# 1. v1 读取
# ---------------------------------------------------------------------------

def test_v1_read_detects_version(tmp_path: Path) -> None:
    """场景1：v1 条目（自由文本 source_ref、无治理字段）→ entry_schema_version=v1。"""

    v1_entry = _base_v1_entry("E-TH-01")
    assert entry_schema_version(v1_entry) == SCHEMA_VERSION_V1

    # 自由文本 source_ref 解析为 standard，hash 留空，is_complete=False（缺 clause）。
    sr = ThresholdSourceRef.from_raw(v1_entry["source_ref"])
    assert sr.standard.endswith("pending_verification")
    assert sr.hash == ""
    assert sr.is_complete() is False

    # 通过真实文件加载路径验证 v1 解析（写入临时 v1 文件）。
    tmp = tmp_path / "_tmp_v1_in.json"
    try:
        _write_tmp(tmp, _v1_document({"E-TH-01": _base_v1_entry("E-TH-01")}))
        loaded = load_verified_thresholds(tmp)
        assert "E-TH-01" in loaded
        assert entry_schema_version(loaded["E-TH-01"]) == SCHEMA_VERSION_V1
        view = ThresholdGovernanceView.from_entry("E-TH-01", loaded["E-TH-01"])
        assert view.status is ThresholdStatus.DRAFT
    finally:
        if tmp.is_file():
            tmp.unlink()


# ---------------------------------------------------------------------------
# 2. v2 读取
# ---------------------------------------------------------------------------

def test_v2_read_detects_version() -> None:
    """场景2：v2 条目（结构化 source_ref 含 hash + threshold_status + version）→ v2。"""

    v2_entry: dict[str, Any] = {
        "param": "E-TH-01 参数",
        "value": None,
        "unit": "pending_verification",
        "threshold_status": ThresholdStatus.VERIFIED.value,
        "version": "1.0.0",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-30T00:00:00+00:00",
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-30T01:00:00+00:00",
        "source_ref": {
            "standard": "GB 50009",
            "clause": "8.1.1",
            "edition": "2012",
            "url": "https://example.org/gb50009",
            "retrieved_at": "2026-07-30T00:00:00+00:00",
            "hash": "0" * 64,
        },
        "applies_to": ["iface_a"],
    }
    assert entry_schema_version(v2_entry) == SCHEMA_VERSION_V2

    view = ThresholdGovernanceView.from_entry("E-TH-01", v2_entry)
    assert view.status is ThresholdStatus.VERIFIED
    assert view.version == "1.0.0"
    # v2 结构化 source_ref 含 hash，且 standard+clause 齐全 → 完整。
    assert view.source_ref.hash == "0" * 64
    assert view.source_ref.is_complete() is True


# ---------------------------------------------------------------------------
# 3. migration 成功
# ---------------------------------------------------------------------------

def test_migration_success_keeps_original_and_adds_fields(tmp_path: Path) -> None:
    """场景3：v1 → v2 迁移成功；生成快照、原文件不变、D-TH 决策 A 补专家签位 null。"""

    # 构造混合 v1 输入：一条"类 E-TH"（已带 expert 字段位）、一条"类 D-TH"（缺 expert 字段）。
    dth_like = _base_v1_entry("D-TH-01")  # 缺 expert_verified_by/at
    eth_like = _base_v1_entry("E-TH-01")
    eth_like["expert_verified_by"] = None
    eth_like["expert_verified_at"] = None

    in_tmp = tmp_path / "_tmp_mig_in.json"
    out_tmp = tmp_path / "_tmp_mig_out.json"
    snap_dir = tmp_path / "_tmp_snapshots"
    try:
        _write_tmp(in_tmp, _v1_document({"E-TH-01": eth_like, "D-TH-01": dth_like}))
        original_hash = _sha256_of(in_tmp)

        report = migrate_thresholds(
            in_tmp, out_tmp, snapshot_dir=snap_dir, dth_decision=DTH_DECISION_A
        )
        assert isinstance(report, MigrationReport)
        assert report.status == MIGRATION_STATUS_SUCCESS
        assert report.thresholds_total == 2
        assert report.thresholds_migrated == 2
        assert report.schema_version_before == SCHEMA_VERSION_V1
        assert report.schema_version_after == SCHEMA_VERSION_V2
        assert report.rollback_available is True
        assert report.snapshot_path is not None

        # 原文件未被修改（哈希一致）。
        assert _sha256_of(in_tmp) == original_hash

        # 快照存在。
        assert Path(report.snapshot_path).is_file()

        # 输出为合法 v2。
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        assert out_data["schema_version"] == SCHEMA_VERSION_V2
        migrated = out_data["thresholds"]
        for tid, e in migrated.items():
            # M3/M4 补齐治理字段。
            assert e["threshold_status"] == "draft"
            assert e["version"] == "1.0.0"
            # M5 结构化 source_ref（含 hash 空串）。
            assert isinstance(e["source_ref"], dict)
            assert "hash" in e["source_ref"]
            # 红线：迁移不转正、不填真实值。
            assert e["verified"] is False
            assert e["value"] is None
            # M6 D-TH 决策 A：专家签位补 null（禁止自动填充）。
            assert "expert_verified_by" in e
            assert "expert_verified_at" in e
            assert e["expert_verified_by"] is None
            assert e["expert_verified_at"] is None
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


# ---------------------------------------------------------------------------
# 4. migration 失败 rollback
# ---------------------------------------------------------------------------

def test_migration_failure_rolls_back(tmp_path: Path) -> None:
    """场景4：输入损坏（非法 JSON）→ 自动回滚：输出不生成、快照保留、status=rolled_back。"""

    in_tmp = tmp_path / "_tmp_mig_bad_in.json"
    out_tmp = tmp_path / "_tmp_mig_bad_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_bad"
    try:
        # 写入非法 JSON（损坏输入）。
        in_tmp.write_text("{ this is not valid json", encoding="utf-8")

        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir)
        assert report.status == MIGRATION_STATUS_ROLLED_BACK
        assert report.errors  # 记录了 migration_failed
        # 输出未生成（回滚清理）。
        assert not out_tmp.exists()
        # 快照已生成并保留（M1 先于解析，只读输入）。
        assert report.snapshot_path is not None
        assert Path(report.snapshot_path).is_file()
        assert report.rollback_available is True
    finally:
        if in_tmp.is_file():
            in_tmp.unlink()
        if out_tmp.is_file():
            out_tmp.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


# ---------------------------------------------------------------------------
# 5. source_ref 缺失
# ---------------------------------------------------------------------------

def test_source_ref_missing_fields() -> None:
    """场景5：source_ref 缺 standard / clause → 明确 reason（C1 / C2）。"""

    # 缺 standard（仅 clause）。
    ok, reason = validate_source_ref(
        {"clause": "8.1.1", "edition": "2012", "url": "https://x.org", "hash": "0" * 64}
    )
    assert ok is False
    assert reason == SOURCE_REF_STANDARD_MISSING

    # 缺 clause（仅 standard）。
    ok, reason = validate_source_ref(
        {"standard": "GB 50009", "edition": "2012", "url": "https://x.org", "hash": "0" * 64}
    )
    assert ok is False
    assert reason == SOURCE_REF_CLAUSE_MISSING


# ---------------------------------------------------------------------------
# 6. hash 失败
# ---------------------------------------------------------------------------

def test_source_ref_hash_failures() -> None:
    """场景6：hash 内容不一致 / 格式非法 → 明确 reason（C5）。"""

    good = {
        "standard": "GB 50009",
        "clause": "8.1.1",
        "edition": "2012",
        "url": "https://x.org/doc",
        "hash": "0" * 64,
    }

    # 内容不一致：提供 content，其摘要与声明的 hash 不同 → HASH_MISMATCH。
    ok, reason = validate_source_ref(dict(good), content="real document body")
    assert ok is False
    assert reason == SOURCE_REF_HASH_MISMATCH

    # 格式非法：hash 非 64 位十六进制 → HASH_FORMAT_INVALID。
    bad = dict(good)
    bad["hash"] = "not-a-valid-hash"
    ok, reason = validate_source_ref(bad)
    assert ok is False
    assert reason == SOURCE_REF_HASH_FORMAT_INVALID

    # 缺 hash → HASH_MISSING。
    no_hash = dict(good)
    no_hash.pop("hash")
    ok, reason = validate_source_ref(no_hash)
    assert ok is False
    assert reason == SOURCE_REF_HASH_MISSING

    # 正向：content 摘要一致 → ok。
    content = "canonical reference text"
    good_ok = dict(good)
    good_ok["hash"] = compute_content_hash(content)
    ok, reason = validate_source_ref(good_ok, content=content)
    assert ok is True
    assert reason == "source_ref_ok"


# ---------------------------------------------------------------------------
# 7. D-TH 双签字段兼容
# ---------------------------------------------------------------------------

def test_d_th_double_sign_field_compatible(tmp_path: Path) -> None:
    """场景7：真实 D-TH（设计侧）缺专家签位 → schema 解析为 None + ensure 补齐 null。"""

    design_thresholds = load_verified_thresholds(_D_PATH)
    assert "D-TH-01" in design_thresholds
    d01 = design_thresholds["D-TH-01"]

    # 真实 D-TH 现状：无 expert_verified_by / expert_verified_at。
    view = ThresholdGovernanceView.from_entry("D-TH-01", d01)
    assert view.expert_verified_by is None
    assert view.expert_verified_at is None

    # ensure_d_th_expert_sign_fields 补齐 null（禁止自动填充）。
    padded = ensure_d_th_expert_sign_fields(d01)
    assert padded["expert_verified_by"] is None
    assert padded["expert_verified_at"] is None
    # E-TH 已带该字段则保留原值（此处为 None，验证不覆盖）。
    assert "expert_verified_by" in padded

    # 经由迁移（决策 A）后，D-TH 输出条目仍带 null 专家签位，且治理态为 DRAFT。
    in_tmp = tmp_path / "_tmp_dth_in.json"
    out_tmp = tmp_path / "_tmp_dth_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_dth"
    try:
        _write_tmp(in_tmp, _v1_document({"D-TH-01": d01}))
        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir, dth_decision=DTH_DECISION_A)
        assert report.status == MIGRATION_STATUS_SUCCESS
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        migrated_d01 = out_data["thresholds"]["D-TH-01"]
        assert migrated_d01["expert_verified_by"] is None
        assert migrated_d01["expert_verified_at"] is None
        # 治理态：draft → 不通过（缺双签/引用不完整），无自动转正。
        ok, _ = governance_status(migrated_d01)
        assert ok is False
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


# ---------------------------------------------------------------------------
# 8. engineering_enabled=false 保护（迁移后）
# ---------------------------------------------------------------------------

def test_engineering_enabled_false_after_migration(tmp_path: Path) -> None:
    """场景8：迁移真实 E-TH（v1→v2，全 draft/value=null）后，门禁与校验恒 pending。

    通过 can_enable_engineering 默认拒绝 + ExpertBackedEngineeringValidation
    在 enabled=False 下永不为 approved 双重验证红线闸门。
    """

    from agents.engineering.validation import ExpertBackedEngineeringValidation

    in_tmp = tmp_path / "_tmp_real_mig_in.json"
    out_tmp = tmp_path / "_tmp_real_mig_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_real"
    try:
        # 复制真实工程侧 v1 库为临时输入（不触碰仓库真实文件）。
        in_tmp.write_text(_E_PATH.read_text(encoding="utf-8"), encoding="utf-8")
        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir, dth_decision=DTH_DECISION_A)
        assert report.status == MIGRATION_STATUS_SUCCESS

        # 迁移后加载：仅读迁移输出本身（避免与 design D-TH 合并混淆）。
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        migrated = out_data["thresholds"]
        assert set(migrated.keys()) >= {"E-TH-01", "E-TH-06"}
        for tid, e in migrated.items():
            assert e["threshold_status"] == "draft"
            assert e["value"] is None
            assert e["verified"] is False
            # 治理态不通过（draft）。
            ok, _ = governance_status(e)
            assert ok is False

        # 门禁：默认（无 ci/rollback/authorization、阈值未治理）→ 拒绝。
        allowed, reasons = can_enable_engineering(thresholds=migrated.values())
        assert allowed is False
        assert reasons  # 含 G1/G2/G3/G5/G6 等

        # 即便强行构造治理完备阈值，enabled=False 仍保持 pending（回归守门）。
        assert load_engineering_enabled() is False
        validator = ExpertBackedEngineeringValidation(
            engineering_enabled=False, thresholds=migrated
        )
        record = validator.validate(
            interface="iface_a",
            payload={
                "result": "",
                "confidence": 0.0,
                "evidence": "",
                "verification_status": "pending_verification",
            },
        )
        assert record["verification_status"] == "pending_verification"
        assert record["sign_off_id"] is None
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


# ---------------------------------------------------------------------------
# 附加：noop（输入已是 v2）/ source_ref dict 分支 / 非 Mapping 条目 / 决策 B
# ---------------------------------------------------------------------------

def test_migration_noop_when_already_v2(tmp_path: Path) -> None:
    """已为 v2 的输入 → status=noop，不写输出、保留快照。"""

    # 构造一个最小 v2 文档（schema_version=2，已含治理字段）。
    v2_doc = {
        "schema_version": 2,
        "thresholds": {
            "E-TH-01": {
                "param": "E-TH-01",
                "value": None,
                "unit": "pending_verification",
                "threshold_status": "draft",
                "version": "1.0.0",
                "verified": False,
                "source_ref": {
                    "standard": "GB 50009",
                    "clause": "",
                    "edition": "",
                    "url": "",
                    "retrieved_at": "",
                    "hash": "",
                },
            }
        },
    }
    in_tmp = tmp_path / "_tmp_noop_in.json"
    out_tmp = tmp_path / "_tmp_noop_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_noop"
    try:
        _write_tmp(in_tmp, v2_doc)
        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir)
        assert report.status == "noop"
        assert report.schema_version_before == SCHEMA_VERSION_V2
        assert report.rollback_available is True
        # noop 不写输出（仅保留快照）。
        assert not out_tmp.exists()
        assert report.snapshot_path is not None
        assert Path(report.snapshot_path).is_file()
        # 报告可序列化。
        d = report.as_dict()
        assert d["status"] == "noop"
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


def test_migration_source_ref_dict_branch(tmp_path: Path) -> None:
    """v1 条目若 source_ref 已是字典（但缺 hash）→ 走 Mapping 分支补齐 hash。"""

    eth = _base_v1_entry("E-TH-02")
    eth["source_ref"] = {"standard": "GB 50009", "clause": "8.1.1"}  # 字典、缺 hash
    in_tmp = tmp_path / "_tmp_sr_in.json"
    out_tmp = tmp_path / "_tmp_sr_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_sr"
    try:
        _write_tmp(in_tmp, _v1_document({"E-TH-02": eth}))
        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir)
        assert report.status == MIGRATION_STATUS_SUCCESS
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        sr = out_data["thresholds"]["E-TH-02"]["source_ref"]
        assert isinstance(sr, dict)
        assert sr["standard"] == "GB 50009"
        assert sr["clause"] == "8.1.1"
        assert sr["hash"] == ""  # 补齐空 hash（不填真实值）
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


def test_migration_skips_non_mapping_entry(tmp_path: Path) -> None:
    """thresholds 中混入非 Mapping 条目 → 跳过（continue），不计入迁移。"""

    doc = _v1_document(
        {
            "E-TH-01": _base_v1_entry("E-TH-01"),
            "BAD-ENTRY": ["not", "a", "dict"],  # 非 Mapping，应被跳过
        }
    )
    in_tmp = tmp_path / "_tmp_badentry_in.json"
    out_tmp = tmp_path / "_tmp_badentry_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_badentry"
    try:
        _write_tmp(in_tmp, doc)
        report = migrate_thresholds(in_tmp, out_tmp, snapshot_dir=snap_dir)
        assert report.status == MIGRATION_STATUS_SUCCESS
        assert report.thresholds_total == 2
        assert report.thresholds_migrated == 1  # 仅 E-TH-01 被迁移
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        assert "E-TH-01" in out_data["thresholds"]
        assert "BAD-ENTRY" not in out_data["thresholds"]
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


def test_migration_dth_decision_b_keeps_structure(tmp_path: Path) -> None:
    """决策 B（保持单签）→ 不补 expert_verified_* 字段，D-TH 结构不动。"""

    dth_like = _base_v1_entry("D-TH-01")  # 缺 expert 字段
    in_tmp = tmp_path / "_tmp_dthb_in.json"
    out_tmp = tmp_path / "_tmp_dthb_out.json"
    snap_dir = tmp_path / "_tmp_snapshots_dthb"
    try:
        from agents.engineering.threshold_migration import DTH_DECISION_B

        _write_tmp(in_tmp, _v1_document({"D-TH-01": dth_like}))
        report = migrate_thresholds(
            in_tmp, out_tmp, snapshot_dir=snap_dir, dth_decision=DTH_DECISION_B
        )
        assert report.status == MIGRATION_STATUS_SUCCESS
        out_data = json.loads(out_tmp.read_text(encoding="utf-8"))
        migrated = out_data["thresholds"]["D-TH-01"]
        # 决策 B：不补专家签位（仍为 v1 结构，无 expert_verified_by/at）。
        assert "expert_verified_by" not in migrated
        assert "expert_verified_at" not in migrated
        # 其余 v2 字段仍补齐。
        assert migrated["threshold_status"] == "draft"
        assert migrated["version"] == "1.0.0"
    finally:
        for p in (in_tmp, out_tmp):
            if p.is_file():
                p.unlink()
        if snap_dir.is_dir():
            for f in snap_dir.iterdir():
                f.unlink()
            snap_dir.rmdir()


def test_migration_rollback_with_default_snapshot_dir(tmp_path: Path) -> None:
    """snapshot_dir=None（取输出同级）→ 损坏输入触发回滚，覆盖默认目录分支。"""

    in_tmp = tmp_path / "_tmp_def_in.json"
    out_tmp = tmp_path / "_tmp_def_out.json"  # 同级目录即快照目录
    try:
        in_tmp.write_text("{ broken json", encoding="utf-8")
        report = migrate_thresholds(in_tmp, out_tmp)  # snapshot_dir=None
        assert report.status == MIGRATION_STATUS_ROLLED_BACK
        assert not out_tmp.exists()
        assert report.snapshot_path is not None
        assert Path(report.snapshot_path).is_file()
    finally:
        if in_tmp.is_file():
            in_tmp.unlink()
        if out_tmp.is_file():
            out_tmp.unlink()
        # 同级快照目录里的 verified.*.v1.json。
        # Phase 3.8.31 T7：历史实现在此硬编码扫描 `Path("tests")`，即便本用例的
        # 输入/输出已迁出仓库，该清理块仍会连带删除 `tests/` 下同名快照残留。
        # 现随 out_tmp 定位到真实快照目录（tmp_path），确保清理范围与产出范围一致。
        for f in out_tmp.parent.glob("verified.*.v1.json"):
            f.unlink()
