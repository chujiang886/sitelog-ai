"""Tests for ReleaseCandidateRecord (3.2.5-H4-RC).

红线约束验证：
- collect 仅只读哈希，不修改/创建任何生产证据文件
- 证据缺失时如实记录（hash=None / present=False / decision=NO-GO）
- 不承载任何真实工程参数；Runbook 冻结仅引用其哈希
"""
from pathlib import Path

from agents.engineering.release.candidate import (
    RUNBOOK_VERSION,
    collect_release_candidate,
)

REPO_ROOT = Path(__file__).resolve().parents[2]

COMMIT = "543c3c7a651b158b6c8f76ad99666aef058a1502"
CI_EVIDENCE = {
    "commit": COMMIT,
    "timestamp": "2026-08-01T19:31:00+08:00",
    "test_result": "481 passed (baseline from H3-A green local_ci)",
    "coverage": "90% (baseline)",
}


def test_candidate_id_deterministic():
    a = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    b = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    assert a.candidate_id == b.candidate_id
    assert a.candidate_id.startswith("BOIP-RC-")


def test_core_fields_present():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    d = rc.to_dict()
    for f in (
        "candidate_id",
        "commit_hash",
        "config_hash",
        "evidence_bundle_id",
        "runbook_version",
        "created_at",
    ):
        assert f in d
    assert d["commit_hash"] == COMMIT
    assert d["runbook_version"] == RUNBOOK_VERSION == "3.2.5-H4-A"


def test_evidence_bundle_binding():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    # 绑定证据包 id 须与重新采集的证据包一致（同 interface + commit 确定性）
    from agents.engineering.release.evidence_bundle import (
        collect_release_evidence_bundle,
    )

    assert rc.evidence_bundle_id == collect_release_evidence_bundle(
        "wind_pressure", COMMIT, CI_EVIDENCE
    ).bundle_id
    assert rc.evidence_bundle_id.startswith("BOIP-EB-")
    binding = rc.evidence_binding
    # 五类证据哈希均被绑定（只读引用）
    for k in (
        "threshold_evidence_hash",
        "review_log_hash",
        "authorization_hash",
        "ci_evidence_hash",
        "rollback_evidence_hash",
    ):
        assert k in binding
    # 真实态：阈值存在、审核/授权缺失
    assert binding["threshold_evidence_present"] is True
    assert binding["review_evidence_present"] is False
    assert binding["authorization_present"] is False


def test_runbook_frozen_hash_present():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    # H4-A Runbook 文件存在 -> runbook_hash 非 None（冻结引用）
    assert rc.runbook_hash is not None
    # 与直接对文件做 sha256 一致
    import hashlib

    real = (REPO_ROOT / ".ai/tasks/phase3.2.5H4A_release_runbook.md").read_bytes()
    assert rc.runbook_hash == hashlib.sha256(real).hexdigest()


def test_config_hash_matches_real_file():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    import hashlib

    real = (REPO_ROOT / "agents/config.yaml").read_bytes()
    assert rc.config_hash == hashlib.sha256(real).hexdigest()


def test_decision_no_go_when_incomplete():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    # 当前真实态：审核/授权证据缺失 -> 不完整 -> NO-GO
    assert rc.complete is False
    assert rc.decision == "NO-GO"
    assert any("evidence_incomplete" in n for n in rc.notes)


def test_collect_is_readonly_no_file_write(tmp_path: Path):
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
    # 缺 review_log / approval / H4-A runbook（模拟缺失）
    before_files = set(p.name for p in root.rglob("*") if p.is_file())
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE, repo_root=root)
    after_files = set(p.name for p in root.rglob("*") if p.is_file())
    # collect 不创建任何新文件
    assert after_files == before_files
    # 缺失证据 / runbook 如实记录
    assert rc.evidence_binding["review_log_hash"] is None
    assert rc.evidence_binding["authorization_hash"] is None
    assert rc.runbook_hash is None  # 临时仓库无 H4-A runbook


def test_to_dict_roundtrip():
    rc = collect_release_candidate("wind_pressure", COMMIT, CI_EVIDENCE)
    d = rc.to_dict()
    assert d["candidate_id"] == rc.candidate_id
    assert set(d.keys()) >= {
        "candidate_id",
        "commit_hash",
        "config_hash",
        "evidence_bundle_id",
        "runbook_version",
        "created_at",
        "runbook_hash",
        "evidence_binding",
    }
