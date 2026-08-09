"""Production Readiness 核验测试（Phase 3.2 Sprint 3.2.5-G2）。

覆盖：
- Task1 ``check_e_th_realization``：draft 态报告未真实化；真实化条目报告 realized；
- Task2 ``check_review_log_chain``：空链 / 完整链 / 断裂链 / 缺类 四场景；
- Task3 ``validate_release_approval``：七字段齐全 / 缺字段 / SoD 冲突；
- Task4 G4 增强：空 review_log 现在阻断 G4；完整必需事件 + 链式完好则 G4 通过；
- Task5 复合 ``production_readiness``：真实生产态下 gate 恒拒绝。

全部仅读不写，不触碰生产 verified.json / review_log / 授权库。
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.gate.enable_gate import (
    GATE_G4_AUDIT_CHAIN,
    can_enable_engineering,
    required_audit_events,
)
from agents.engineering.release import (
    EngineeringReleaseApproval,
    ProductionReadinessChecker,
    ProductionReadinessReport,
    check_e_th_realization,
    check_review_log_chain,
    check_verified_integrity,
    manual_modified_thresholds,
    production_readiness,
    release_precheck,
    validate_release_approval,
)


def _write_review_log(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for ev in events:
            handle.write(json.dumps(ev, ensure_ascii=False) + "\n")


def _intake_chain() -> list[dict]:
    """构造含四类必需事件的完整链式 review_log。"""

    return [
        {
            "event_id": "e1",
            "threshold_id": "E-TH-01",
            "action": "submit",
            "signer_role": "submitter",
            "signer": "s1",
            "timestamp": "t1",
            "source_ref": "x",
            "prev_event_id": None,
        },
        {
            "event_id": "e2",
            "threshold_id": "E-TH-01",
            "action": "review",
            "signer_role": "principal",
            "signer": "p1",
            "timestamp": "t2",
            "source_ref": "x",
            "prev_event_id": "e1",
        },
        {
            "event_id": "e3",
            "threshold_id": "E-TH-01",
            "action": "expert_recheck",
            "signer_role": "expert",
            "signer": "e1",
            "timestamp": "t3",
            "source_ref": "x",
            "prev_event_id": "e2",
        },
        {
            "event_id": "e4",
            "threshold_id": "E-TH-01",
            "action": "verified",
            "signer_role": "principal",
            "signer": "p1",
            "timestamp": "t4",
            "source_ref": "x",
            "prev_event_id": "e3",
        },
    ]


def _write_verified(path: Path, entries: dict[str, dict]) -> None:
    """写入最小化 verified.json（schema_version + thresholds 段）。"""

    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {"schema_version": 1, "thresholds": entries}
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")


def test_check_e_th_realization_draft() -> None:
    """Task1：真实生产 E-TH-01/02/03 仍 draft/pending → all_realized=False。"""

    report = check_e_th_realization("wind_pressure")
    assert report["required_threshold_ids"] == ["E-TH-01", "E-TH-02", "E-TH-03"]
    assert report["all_realized"] is False
    for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
        entry = report["per_threshold"][tid]
        assert entry["present"] is True
        assert entry["realized"] is False
        # 当前真实态缺 value / source_ref / version / dual_sign。
        assert "value" in entry["missing"]
        assert "dual_sign" in entry["missing"]


def test_check_e_th_realization_realized() -> None:
    """Task1：构造一条已真实化 + 双签的条目 → realized=True。"""

    realized = {
        "value": 0.5,
        "unit": "Pa",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-31T00:00:00+00:00",
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-31T00:00:00+00:00",
        "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
        "version": "1.0",
    }
    report = check_e_th_realization(
        "wind_pressure", thresholds={"E-TH-01": realized}
    )
    entry = report["per_threshold"]["E-TH-01"]
    assert entry["realized"] is True
    assert entry["value_real"] is True
    assert entry["unit_real"] is True
    assert entry["source_ref_complete"] is True
    assert entry["version_present"] is True
    assert entry["dual_signed"] is True


def test_check_review_log_chain_empty(tmp_path: Path) -> None:
    """Task2：空链（文件不存在 / 空）→ ok=False、empty=True、缺全部四类。"""

    empty = tmp_path / "empty.jsonl"
    result = check_review_log_chain(review_log_path=empty)
    assert result["ok"] is False
    assert result["empty"] is True
    assert set(result["missing_actions"]) == {
        "submit",
        "review",
        "expert_recheck",
        "verified",
    }


def test_check_review_log_chain_complete(tmp_path: Path) -> None:
    """Task2：四类必需事件 + 链式完好 → ok=True。"""

    p = tmp_path / "log.jsonl"
    _write_review_log(p, _intake_chain())
    result = check_review_log_chain(review_log_path=p)
    assert result["ok"] is True
    assert result["broken"] is False
    assert result["missing_actions"] == []
    assert result["event_count"] == 4


def test_check_review_log_chain_broken(tmp_path: Path) -> None:
    """Task2：链式断裂 → ok=False、broken=True。"""

    events = _intake_chain()
    events[2]["prev_event_id"] = "WRONG"  # 破坏链
    p = tmp_path / "broken.jsonl"
    _write_review_log(p, events)
    result = check_review_log_chain(review_log_path=p)
    assert result["ok"] is False
    assert result["broken"] is True


def test_check_review_log_chain_missing_action(tmp_path: Path) -> None:
    """Task2：缺一类必需事件（verified）→ ok=False、缺失该类。"""

    events = _intake_chain()[:-1]  # 去掉 verified
    p = tmp_path / "missing.jsonl"
    _write_review_log(p, events)
    result = check_review_log_chain(review_log_path=p)
    assert result["ok"] is False
    assert result["missing_actions"] == ["verified"]


def test_validate_release_approval_ok() -> None:
    """Task3：七字段齐全 → (True, [])。"""

    approval = EngineeringReleaseApproval(
        approval_id="AP-001",
        interface="wind_pressure",
        scope="proj-a",
        authorized_by="governance-lead",
        effective_time="2026-08-01T00:00:00+00:00",
        rollback_owner="ops-lead",
        approval_document_ref="doc://approval/AP-001",
    )
    ok, errors = validate_release_approval(approval)
    assert ok is True
    assert errors == []


def test_validate_release_approval_missing_field() -> None:
    """Task3：缺失 effective_time → (False, 含错误)。"""

    ok, errors = validate_release_approval(
        {
            "approval_id": "AP-001",
            "interface": "wind_pressure",
            "scope": "proj-a",
            "authorized_by": "governance-lead",
            "effective_time": "",  # 缺失
            "rollback_owner": "ops-lead",
            "approval_document_ref": "doc://approval/AP-001",
        }
    )
    assert ok is False
    assert any("effective_time" in e for e in errors)


def test_validate_release_approval_sod_conflict() -> None:
    """Task3：authorized_by == rollback_owner 违反 SoD 软约束 → 报错。"""

    ok, errors = validate_release_approval(
        {
            "approval_id": "AP-001",
            "interface": "wind_pressure",
            "scope": "proj-a",
            "authorized_by": "same-person",
            "effective_time": "2026-08-01T00:00:00+00:00",
            "rollback_owner": "same-person",
            "approval_document_ref": "doc://approval/AP-001",
        }
    )
    assert ok is False
    assert any("SoD" in e for e in errors)


def test_g4_empty_review_log_blocked(tmp_path: Path) -> None:
    """Task4：空 review_log 现在阻断 G4（修复真空通过）。"""

    empty = tmp_path / "empty.jsonl"
    allowed, reasons = can_enable_engineering(
        thresholds=[],
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        review_log_path=empty,
        require_audit_chain=True,
    )
    assert allowed is False
    assert GATE_G4_AUDIT_CHAIN in reasons


def test_g4_required_events_satisfied_passes(tmp_path: Path) -> None:
    """Task4：完整必需事件 + 链式完好 → G4 通过（不误伤正常链）。"""

    p = tmp_path / "log.jsonl"
    _write_review_log(p, _intake_chain())
    allowed, reasons = can_enable_engineering(
        thresholds=[],  # 空阈值表 → G1/G2 自然不触发
        ci_green=True,
        rollback_ready=True,
        authorization_present=True,
        review_log_path=p,
        require_audit_chain=True,
    )
    assert GATE_G4_AUDIT_CHAIN not in reasons
    assert allowed is True  # 其余门禁均满足


def test_production_readiness_real_state(tmp_path: Path) -> None:
    """Task5：真实生产态下复合就绪核验 gate 恒拒绝。"""

    empty = tmp_path / "empty.jsonl"
    status = production_readiness(
        "wind_pressure",
        review_log_path=empty,
        ci_green=False,
        rollback_ready=False,
    )
    assert status["e_th_realization"]["all_realized"] is False
    assert status["review_log_chain"]["ok"] is False
    assert status["approval_present"] is False
    assert status["approval_effective"] is False
    assert status["gate"]["allowed"] is False
    reasons = status["gate"]["reasons"]
    # G1/G2/G3/G4/G5/G6 均应在阻断原因中（真实态全不满足）。
    assert any(r.startswith("G1") for r in reasons)
    assert any(r.startswith("G2") for r in reasons)
    assert any(r.startswith("G4") for r in reasons)
    assert any(r.startswith("G6") for r in reasons)


def test_check_verified_integrity_clean(tmp_path: Path) -> None:
    """Task3：真实生产态（E-TH-01 draft / value=null）无绕过 → ok、bypassed 空。"""

    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": None,
                "unit": "",
                "verified": False,
                "verified_by": None,
                "expert_verified_by": None,
                "source_ref": "待专家签字填入… pending_verification",
                "version": "",
            }
        },
    )
    empty = tmp_path / "empty.jsonl"
    result = check_verified_integrity(
        verified_path=verified, review_log_path=empty
    )
    assert result["ok"] is True
    assert result["bypassed_ids"] == []
    assert result["checked_count"] == 0  # 无填实条目


def test_check_verified_integrity_detects_bypass(tmp_path: Path) -> None:
    """Task3：绕过工作流直接置 verified=true + value，却无 intake 链 → 判绕过。"""

    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": 0.5,
                "unit": "Pa",
                "verified": True,  # 手工直改，无审核链
                "verified_by": "x",
                "expert_verified_by": "y",
                "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
                "version": "1.0",
            }
        },
    )
    empty = tmp_path / "empty.jsonl"  # 无审核链
    result = check_verified_integrity(
        verified_path=verified, review_log_path=empty
    )
    assert result["ok"] is False
    assert result["bypassed_ids"] == ["E-TH-01"]
    assert result["checked_count"] == 1


def test_check_verified_integrity_chain_present_ok(tmp_path: Path) -> None:
    """Task3：填实条目 + 完整 intake 链在 review_log → 不误判绕过。"""

    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": 0.5,
                "unit": "Pa",
                "verified": True,
                "verified_by": "x",
                "expert_verified_by": "y",
                "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
                "version": "1.0",
            }
        },
    )
    p = tmp_path / "log.jsonl"
    _write_review_log(p, _intake_chain())
    result = check_verified_integrity(verified_path=verified, review_log_path=p)
    assert result["ok"] is True
    assert result["bypassed_ids"] == []


def test_production_readiness_report_shape(tmp_path: Path) -> None:
    """Task2/Task3：复合报告含 passed/failed/blocking_reasons 且真实态绕过为 False。"""

    empty = tmp_path / "empty.jsonl"
    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": None,
                "verified": False,
                "source_ref": "pending_verification",
            }
        },
    )
    status = production_readiness(
        "wind_pressure",
        review_log_path=empty,
        verified_path=verified,
        ci_green=False,
        rollback_ready=False,
    )
    # 报告形状：passed/failed/blocking_reasons。
    assert isinstance(status["passed"], list)
    assert isinstance(status["failed"], list)
    assert isinstance(status["blocking_reasons"], list)
    # 真实态：verified_integrity 通过，但 G1-G6 全失败。
    assert "verified_integrity" in status["passed"]
    assert "G1_threshold_governance" in status["failed"]
    assert "G6_authorization" in status["failed"]
    # 无绕过标记。
    assert not any(r.startswith("VERIFIED_BYPASS") for r in status["blocking_reasons"])


def test_required_audit_events_for_wind_pressure() -> None:
    """Task1：required_audit_events(wind_pressure) 返回四类必需 intake 事件。"""

    events = required_audit_events("wind_pressure")
    assert events == [
        "submit",
        "review",
        "expert_recheck",
        "verified",
    ]


def test_production_readiness_checker_real_state(tmp_path: Path) -> None:
    """Task2/Task3：ProductionReadinessChecker 在真实态下输出 unified 报告。

    覆盖：G1-G6 状态报告（#4）、ProductionChecker 输出字段（#3）。
    """

    empty = tmp_path / "empty.jsonl"
    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": None,
                "verified": False,
                "source_ref": "pending_verification",
            }
        },
    )
    checker = ProductionReadinessChecker(
        interface="wind_pressure",
        ci_green=False,
        rollback_ready=False,
        review_log_path=empty,
        verified_path=verified,
    )
    report = checker.run()
    # 类型与字段。
    assert isinstance(report, ProductionReadinessReport)
    assert isinstance(report.passed, list)
    assert isinstance(report.failed, list)
    assert isinstance(report.blocking_reasons, list)
    assert isinstance(report.gate_status, dict)
    assert isinstance(report.to_dict(), dict)
    # 真实态：verified_integrity 通过，但 G1-G6 全部失败。
    assert "verified_integrity" in report.passed
    assert "G1_threshold_governance" in report.failed
    assert "G4_audit_chain" in report.failed
    assert "G6_authorization" in report.failed
    assert report.allowed is False
    # gate_status 含 G1-G6 + verified_integrity 七项。
    for key in (
        "G1_threshold_governance",
        "G2_dual_sign",
        "G3_ci",
        "G4_audit_chain",
        "G5_rollback",
        "G6_authorization",
        "verified_integrity",
    ):
        assert key in report.gate_status
    # details 暴露本接口 G4 必需事件。
    assert report.details["required_audit_events"] == [
        "submit",
        "review",
        "expert_recheck",
        "verified",
    ]


def test_release_precheck_returns_report() -> None:
    """Task3：release_precheck(return_report=True) 返回 ProductionReadinessReport。"""

    import tempfile

    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "empty.jsonl"
        report = release_precheck(
            interface="wind_pressure",
            review_log_path=log,
            return_report=True,
        )
    assert isinstance(report, ProductionReadinessReport)
    assert report.allowed is False
    # to_dict 可序列化。
    d = report.to_dict()
    assert d["interface"] == "wind_pressure"
    assert "gate_status" in d


def test_manual_modified_thresholds_detects_bypass(tmp_path: Path) -> None:
    """Task4/Task5：manual_modified_thresholds 检测绕过工作流直改 verified.json。"""

    verified = tmp_path / "verified.json"
    _write_verified(
        verified,
        {
            "E-TH-01": {
                "value": 0.5,
                "unit": "Pa",
                "verified": True,  # 手工直改，无审核链
                "verified_by": "x",
                "expert_verified_by": "y",
                "source_ref": {"standard": "GB 50009", "clause": "8.1.1"},
                "version": "1.0",
            }
        },
    )
    empty = tmp_path / "empty.jsonl"  # 无审核链
    result = manual_modified_thresholds(
        verified_path=verified, review_log_path=empty
    )
    assert result["ok"] is False
    assert result["bypassed_ids"] == ["E-TH-01"]


def test_engineering_enabled_false_protection() -> None:
    """Task5 #6：核验过程绝不翻转 engineering_enabled（仍 False）。"""

    import tempfile

    before = load_engineering_enabled()
    assert before is False
    with tempfile.TemporaryDirectory() as d:
        log = Path(d) / "empty.jsonl"
        # 两种调用形态均不得改变全局门。
        report = release_precheck(
            interface="wind_pressure",
            review_log_path=log,
            return_report=True,
        )
        allowed, reasons = release_precheck(
            interface="wind_pressure",
            review_log_path=log,
        )
    assert report.allowed is False
    assert allowed is False
    assert before is False
    # 核验后全局门仍为 False（红线守约）。
    assert load_engineering_enabled() is False
