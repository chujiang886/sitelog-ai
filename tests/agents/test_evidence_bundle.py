"""Tests for ReleaseEvidenceBundle (3.2.5-H3-B).

红线约束验证：
- collect 仅只读哈希，不修改/创建任何生产证据文件
- 证据缺失时如实记录（hash=None / present=False / notes）
- 不承载任何真实工程参数
"""
from pathlib import Path

from agents.engineering.release.evidence_bundle import (
    collect_release_evidence_bundle,
    REQUIRED_INTAKE_EVENTS,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

COMMIT = "543c3c7a651b158b6c8f76ad99666aef058a1502"
CI_EVIDENCE = {
    "commit": COMMIT,
    "timestamp": "2026-08-01T19:31:00+08:00",
    "test_result": "481 passed (baseline from H3-A green local_ci)",
    "coverage": "90% (baseline)",
}


def test_bundle_id_deterministic():
    a = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    assert a.bundle_id == b.bundle_id
    assert a.bundle_id.startswith("BOIP-EB-")


def test_threshold_evidence_hash_matches_real_file():
    import hashlib

    real = (REPO_ROOT / "agents/engineering/thresholds/verified.json").read_bytes()
    expected = hashlib.sha256(real).hexdigest()
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    assert b.threshold_evidence_hash == expected
    assert b.threshold_evidence_present is True


def test_review_evidence_incomplete_missing_intake_events():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    # 真实 review_log 仅含 schema_established，缺四类 intake 事件
    assert b.review_evidence_present is False
    assert any("review_evidence_incomplete" in n for n in b.notes)
    # 四类事件常量正确定义
    assert set(REQUIRED_INTAKE_EVENTS) == {
        "submit",
        "review",
        "expert_recheck",
        "verified",
    }


def test_authorization_missing():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    # 真实授权库不存在
    assert b.authorization_hash is None
    assert b.authorization_present is False
    assert any("authorization_missing" in n for n in b.notes)


def test_rollback_evidence_references_script():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    assert b.rollback_evidence_hash is not None  # gray_release_ctl.py 存在


def test_ci_evidence_hash_is_reference_only():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    # ci_evidence_hash 是对事实字典的哈希引用，不承载真实参数
    assert b.ci_evidence_hash is not None
    # 修改 ci_evidence 任意字段会改变哈希（证明仅引用事实）
    other = dict(CI_EVIDENCE)
    other["coverage"] = "91%"
    b2 = collect_release_evidence_bundle("wind_pressure", COMMIT, other)
    assert b2.ci_evidence_hash != b.ci_evidence_hash


def test_complete_false_when_evidence_missing():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    # 当前真实态：阈值/审核/授权证据均缺失 -> 不完整
    assert b.complete is False


def test_collect_is_readonly_no_file_write(tmp_path: Path):
    # 将真实证据文件软链/复制到临时仓库结构，验证 collect 不创建/修改任何文件
    import shutil

    root = tmp_path / "repo"
    (root / "agents" / "engineering" / "thresholds").mkdir(parents=True, exist_ok=True)
    (root / "agents" / "engineering" / "release").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "release").mkdir(parents=True, exist_ok=True)
    shutil.copy(
        REPO_ROOT / "agents/engineering/thresholds/verified.json",
        root / "agents" / "engineering" / "thresholds" / "verified.json",
    )
    shutil.copy(
        REPO_ROOT / "scripts/release/gray_release_ctl.py",
        root / "scripts" / "release" / "gray_release_ctl.py",
    )
    # 缺 review_log 与 approval（模拟缺失）
    before_files = set(p.name for p in root.rglob("*") if p.is_file())
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE, repo_root=root)
    after_files = set(p.name for p in root.rglob("*") if p.is_file())
    # collect 不创建任何新文件
    assert after_files == before_files
    # 缺失证据如实记录
    assert b.review_log_hash is None
    assert b.authorization_hash is None


def test_to_dict_roundtrip():
    b = collect_release_evidence_bundle("wind_pressure", COMMIT, CI_EVIDENCE)
    d = b.to_dict()
    assert d["bundle_id"] == b.bundle_id
    assert d["interface"] == "wind_pressure"
    assert set(d.keys()) >= {
        "bundle_id",
        "interface",
        "threshold_evidence_hash",
        "review_log_hash",
        "authorization_hash",
        "ci_evidence_hash",
        "rollback_evidence_hash",
        "commit_hash",
        "created_at",
    }
