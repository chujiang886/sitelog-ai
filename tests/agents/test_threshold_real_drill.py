"""首批真实阈值录入演练测试（Phase 3.2 Sprint 3.2.4-G）。

覆盖（任务5，六要点）：
1. 真实资料录入流程：run_intake_drill 对 E-TH-01 全四步执行，verified=true、步骤链完整；
2. source_ref 验证：build_source_verification_report 对合法占位通过、对缺字段逐项不通过；
3. 双签：主理人核准 + 专家复核两套签字位齐全方可转正；
4. review_log 链：演练四步事件有序、prev_event_id 链式衔接；
5. SoD：专家复核人与主理人核准人同一身份 → 演练中止于 expert_recheck；
6. enabled 保护：演练后 evaluate_gates 恒 (False, reasons)，ExpertBackedEngineeringValidation
   (enabled=False) 仍 pending_verification，engineering_enabled 恒 False。

附加：授权越界拒绝（D-TH / E-TH-04）、最终转正拒绝分支（通过 fixture 触发防御分支）。

红线：本测试**不写入真实工程数值**——value 一律传 None（AI 不提供真实值）；
source_ref 为结构合法的合成占位（example.org + 计算哈希），signer 仅标识符
（principal-001 / expert-001）。全程不开启 engineering_enabled、不输出
engineering_approved。全部保持 pending_verification。
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.thresholds.schema import ThresholdStatus
from agents.engineering.thresholds.source_ref_validator import compute_content_hash
from agents.engineering.threshold_intake import (
    IntakeOutcome,
    IntakeRequest,
    ThresholdIntakeWorkflow,
    build_source_verification_report,
    run_intake_drill,
)
from agents.engineering.validation import ExpertBackedEngineeringValidation


# ---------------------------------------------------------------------------
# 合成夹具（不含真实工程数值；value=None 占位，source_ref 为结构合法占位）
# ---------------------------------------------------------------------------

def _valid_source_ref() -> dict[str, str]:
    """结构合法的合成 source_ref（非真实规范，仅满足 C1-C6 格式/哈希约束）。"""

    content = "canonical reference text for test fixture pending_verification"
    return {
        "standard": "GB 50009",
        "clause": "8.1.1",
        "edition": "2012",
        "url": "https://example.org/canonical-reference",
        "retrieved_at": "2026-07-31T00:00:00+00:00",
        "hash": compute_content_hash(content),
    }


def _request(tid: str, *, source_ref: dict[str, str] | None = None) -> IntakeRequest:
    """构造一条提交请求（value=None：AI 不提供真实工程数值，红线占位）。"""

    return IntakeRequest(
        threshold_id=tid,
        value=None,
        unit="pending_verification",
        source_ref=source_ref if source_ref is not None else _valid_source_ref(),
        version="1.0.0",
        submitted_by="submitter-001",
    )


def _uniq() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


# Phase 3.8.31 T7（threshold hygiene 技术债根因修复）：
# 历史实现把演练临时件写在 `tests/` 源码目录（`tests/_tmp_drill_*.json` 等），
# 造成两个后果：(1) 仓库工作树被测试产物污染、残留文件跨轮次堆积；
# (2) 清理阶段对 `tests/` 目录批量 unlink 会触发执行环境的批量删除护栏而中断。
# 修复方式为根因隔离——所有临时件迁出仓库，落到进程级系统临时根目录。
# `ThresholdIntakeWorkflow` 的默认 snapshot_dir 取 `verified_path.parent /
# "intake_snapshots"`，因此 verified/review 路径迁移后，快照目录自动跟随迁出。
# 不使用 skip/xfail，不改动被测业务逻辑，断言强度保持不变。
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="boip_threshold_drill_"))


def _paths() -> tuple[Path, Path]:
    return (
        _TMP_ROOT / f"_tmp_drill_{_uniq()}.json",
        _TMP_ROOT / f"_tmp_drill_log_{_uniq()}.jsonl",
    )


def _cleanup(*paths: Path) -> None:
    for p in paths:
        if p.is_file():
            p.unlink()
    snap = _TMP_ROOT / "intake_snapshots"
    if snap.is_dir():
        for f in snap.iterdir():
            f.unlink()
        snap.rmdir()


def _drill(tid: str, *, source_ref: dict[str, str] | None = None) -> tuple:
    """运行一次演练并返回 (result, verified_path, review_log_path)。"""

    verified, review = _paths()
    result = run_intake_drill(
        verified_path=verified,
        review_log_path=review,
        request=_request(tid, source_ref=source_ref),
        verified_by="principal-001",
        verified_at="2026-07-31T00:00:00+00:00",
        expert_verified_by="expert-001",
        expert_verified_at="2026-07-31T01:00:00+00:00",
    )
    return result, verified, review


# ---------------------------------------------------------------------------
# 1. 真实资料录入流程（合法演练）
# ---------------------------------------------------------------------------

def test_drill_valid_flow_verified() -> None:
    """场景1：E-TH-01 演练全四步执行，verified=true、步骤链完整、门禁拒绝。"""

    result, verified, review = _drill("E-TH-01")
    try:
        assert result.authorized is True
        assert result.source_report is not None and result.source_report.passed is True
        assert result.steps == [
            "submit",
            "review_approve",
            "expert_recheck",
            "threshold_verified",
        ]
        assert result.verified is True
        assert result.review_event_id is not None
        # 红线：engineering_enabled 恒 False，verification_status 恒 pending。
        assert result.engineering_enabled is False
        assert result.verification_status == "pending_verification"
        assert result.gate_allowed is False
        assert result.gate_reasons  # G3/G5/G6 等仍阻塞

        # 落库校验：转正态、双签位齐全、value 原样（None 占位，AI 未编造）。
        written = json.loads(verified.read_text(encoding="utf-8"))
        e = written["thresholds"]["E-TH-01"]
        assert e["verified"] is True
        assert e["threshold_status"] == ThresholdStatus.VERIFIED.value
        assert e["verified_by"] == "principal-001"
        assert e["expert_verified_by"] == "expert-001"
        assert e["value"] is None
        # 序列化自洽。
        assert result.as_dict()["threshold_id"] == "E-TH-01"
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 2. source_ref 验证
# ---------------------------------------------------------------------------

def test_source_verification_report_valid() -> None:
    """场景2a：合法 source_ref → 报告 passed，全部 C 通过。"""

    rep = build_source_verification_report(_valid_source_ref())
    assert rep.passed is True
    assert rep.overall == "通过"
    for c in ("C1", "C2", "C3", "C4", "C5", "C6"):
        assert rep.checks[c]["ok"] is True
    assert rep.as_dict()["passed"] is True


def test_source_verification_report_each_c_failure() -> None:
    """场景2b：逐项破坏 source_ref，对应 C 不通过、报告整体不通过。"""

    # C1 缺 standard。
    bad = _valid_source_ref()
    bad.pop("standard")
    rep = build_source_verification_report(bad)
    assert rep.passed is False
    assert rep.checks["C1"]["ok"] is False
    assert rep.checks["C6"]["ok"] is False  # C6 依赖 C1

    # C2 缺 clause。
    bad = _valid_source_ref()
    bad.pop("clause")
    rep = build_source_verification_report(bad)
    assert rep.checks["C2"]["ok"] is False

    # C3 edition 非法。
    bad = _valid_source_ref()
    bad["edition"] = "not-a-year"
    rep = build_source_verification_report(bad)
    assert rep.checks["C3"]["ok"] is False

    # C4 url 非法。
    bad = _valid_source_ref()
    bad["url"] = "ftp://example.org/x"
    rep = build_source_verification_report(bad)
    assert rep.checks["C4"]["ok"] is False

    # C5 hash 非法。
    bad = _valid_source_ref()
    bad["hash"] = "deadbeef"
    rep = build_source_verification_report(bad)
    assert rep.checks["C5"]["ok"] is False


def test_drill_rejects_invalid_source_ref() -> None:
    """场景2c：source_ref 不通过 → 演练不进入步骤、不入库。"""

    bad = _valid_source_ref()
    bad.pop("clause")
    result, verified, review = _drill("E-TH-01", source_ref=bad)
    try:
        assert result.authorized is True
        assert result.source_report is not None and result.source_report.passed is False
        assert result.steps == []
        assert result.verified is False
        # 未提交即无库（或库中无 E-TH-01）。
        if verified.is_file():
            written = json.loads(verified.read_text(encoding="utf-8"))
            assert "E-TH-01" not in written.get("thresholds", {})
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 3. 双签 + 4. review_log 链
# ---------------------------------------------------------------------------

def test_drill_review_log_chain_intact() -> None:
    """场景4：演练四步事件有序、prev_event_id 链式衔接、event_id 确定性。"""

    from agents.engineering.review_log import (
        compute_event_id,
        read_log,
    )

    result, verified, review = _drill("E-TH-02")
    try:
        assert result.verified is True
        events = read_log(review)
        actions = [e["action"] for e in events]
        assert actions == [
            "submit",
            "review",
            "expert_recheck",
            "verified",
        ]
        prev: str | None = None
        for e in events:
            assert e["prev_event_id"] == prev
            prev = e["event_id"]
        # event_id 确定性重算一致。
        first = events[0]
        assert compute_event_id(
            threshold_id=first["threshold_id"],
            action=first["action"],
            signer_role=first["signer_role"],
            signer=first["signer"],
            timestamp=first["timestamp"],
            source_ref=first["source_ref"],
            prev_event_id=first["prev_event_id"],
        ) == first["event_id"]
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 5. SoD 冲突
# ---------------------------------------------------------------------------

def test_drill_sod_conflict_blocked() -> None:
    """场景5：专家复核人与主理人核准人同一身份 → 演练中止于 expert_recheck。"""

    verified, review = _paths()
    try:
        result = run_intake_drill(
            verified_path=verified,
            review_log_path=review,
            request=_request("E-TH-01"),
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
            expert_verified_by="principal-001",  # 与核准人同一身份
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        assert result.authorized is True
        assert result.steps == ["submit", "review_approve"]
        assert result.verified is False
        assert "SoD" in result.message
        assert result.gate_allowed is False
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 6. enabled 保护
# ---------------------------------------------------------------------------

def test_drill_enabled_false_protection() -> None:
    """场景6：演练后工程验证仍 pending_verification；engineering_enabled 恒 False。"""

    # 对授权集合三条全部演练。
    paths: list[Path] = []
    try:
        for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
            verified, review = _paths()
            paths.extend([verified, review])
            result = run_intake_drill(
                verified_path=verified,
                review_log_path=review,
                request=_request(tid),
                verified_by="principal-001",
                verified_at="2026-07-31T00:00:00+00:00",
                expert_verified_by="expert-001",
                expert_verified_at="2026-07-31T01:00:00+00:00",
            )
            assert result.verified is True
            assert result.gate_allowed is False

        # 即便全部双签转真，开关仍关。
        assert load_engineering_enabled() is False
        from agents.engineering.threshold_loader import load_verified_thresholds

        loaded = load_verified_thresholds(paths[0])
        validator = ExpertBackedEngineeringValidation(
            engineering_enabled=False, thresholds=loaded
        )
        record = validator.validate(
            interface="wind_pressure",
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
        _cleanup(*paths)


# ---------------------------------------------------------------------------
# 附加：授权越界 + 最终转正拒绝防御分支（fixture）
# ---------------------------------------------------------------------------

def test_drill_unauthorized_rejected() -> None:
    """授权越界：D-TH-01 / E-TH-04 不在本阶段范围 → 拒绝、不进入步骤。"""

    for tid in ("D-TH-01", "E-TH-04"):
        result, verified, review = _drill(tid)
        try:
            assert result.authorized is False
            assert result.steps == []
            assert result.verified is False
            assert "授权" in result.message
        finally:
            _cleanup(verified, review)


def test_drill_finalize_rejected_branch(monkeypatch) -> None:
    """最终转正拒绝分支：即使前序步骤通过，finalize 拒绝即演练中止不转正。"""

    from agents.engineering.threshold_intake import IntakeResult

    verified, review = _paths()
    try:
        # 让 finalize_verified 返回拒绝（模拟双签判定失败等防御场景）。
        def _fake_finalize(self, threshold_id):  # noqa: ANN001
            return IntakeResult(
                outcome=IntakeOutcome.REJECTED,
                threshold_id=threshold_id,
                state="rejected",
                message="双签不完整（防御分支）",
            )

        monkeypatch.setattr(
            ThresholdIntakeWorkflow, "finalize_verified", _fake_finalize
        )
        result = run_intake_drill(
            verified_path=verified,
            review_log_path=review,
            request=_request("E-TH-01"),
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        assert result.steps == ["submit", "review_approve", "expert_recheck"]
        assert result.verified is False
        assert result.gate_allowed is False
    finally:
        _cleanup(verified, review)
