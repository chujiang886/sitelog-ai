"""首批真实工程阈值录入流程测试（Phase 3.2 Sprint 3.2.4-F）。

覆盖：
1. 合法录入流程：提交 → 主理人审核 → 专家复核 → 转正，双签齐全、verified=true；
2. source_ref 失败：缺 clause / 缺 hash → 拒绝进入审核，不入库；
3. 缺专家签：未专家复核即转正 → 拒绝；
4. SoD 冲突：专家复核人与主理人核准人同一身份 → 拒绝；
5. review_log 链：四步事件有序、prev_event_id 链式衔接、event_id 确定性；
6. migration 兼容：录入产物为 schema v2，可被 load_verified_thresholds 读取、
   且可喂入 migrate_thresholds 判为 noop（已 v2）；
7. enabled=false 保护：evaluate_gates 恒 (False, reasons)；即便 E-TH-01~03 全双签
   转正，ExpertBackedEngineeringValidation(enabled=False) 仍 pending_verification。

附加：授权越界拒绝（D-TH / E-TH-04 不在本阶段范围）、已转正重复提交拒绝、
未提交即审核拒绝、缺主理人核准即专家复核拒绝。

红线：本测试**不写入真实工程数值**——value 一律传 None（AI 不提供真实值），
source_ref 为结构合法的合成占位（example.org + 计算哈希），signer 仅标识符
（principal-001 / expert-001）；全程不开启 engineering_enabled、不输出
engineering_approved。全部保持 pending_verification。
"""

from __future__ import annotations

import json
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering.thresholds.schema import (
    ThresholdStatus,
    entry_schema_version,
)
from agents.engineering.thresholds.source_ref_validator import compute_content_hash
from agents.engineering.threshold_intake import (
    DEFAULT_ALLOWED_IDS,
    IntakeOutcome,
    IntakeRequest,
    ThresholdIntakeWorkflow,
)
from agents.engineering.threshold_loader import load_verified_thresholds
from agents.engineering.threshold_migration import (
    MIGRATION_STATUS_NOOP,
    migrate_thresholds,
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


def _new_workflow() -> tuple[ThresholdIntakeWorkflow, Path, Path]:
    """返回工作流实例 + 临时 verified 路径 + 临时 review_log 路径。"""

    verified = Path(f"tests/_tmp_intake_{_uniq()}.json")
    review = Path(f"tests/_tmp_intake_log_{_uniq()}.jsonl")
    return (
        ThresholdIntakeWorkflow(
            verified_path=verified,
            review_log_path=review,
            allowed_ids=DEFAULT_ALLOWED_IDS,
        ),
        verified,
        review,
    )


def _uniq() -> str:
    import uuid

    return uuid.uuid4().hex[:8]


def _cleanup(*paths: Path) -> None:
    for p in paths:
        if p.is_file():
            p.unlink()
    snap = Path("tests/intake_snapshots")
    if snap.is_dir():
        for f in snap.iterdir():
            f.unlink()
        snap.rmdir()


# ---------------------------------------------------------------------------
# 1. 合法录入流程
# ---------------------------------------------------------------------------

def test_valid_intake_flow_double_sign_verified() -> None:
    """场景1：E-TH-01 提交→主理人审核→专家复核→转正，双签齐全、verified=true。"""

    wf, verified, review = _new_workflow()
    try:
        r1 = wf.submit(_request("E-TH-01"))
        assert r1.outcome is IntakeOutcome.ACCEPTED
        assert r1.state == ThresholdStatus.REVIEW.value

        # 主理人核准（人工提供 signer，AI 不篡改）。
        r2 = wf.review(
            threshold_id="E-TH-01",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        assert r2.outcome is IntakeOutcome.ACCEPTED

        # 专家复核（异身份，满足 SoD）。
        r3 = wf.expert_recheck(
            threshold_id="E-TH-01",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        assert r3.outcome is IntakeOutcome.ACCEPTED

        # 转正：双签齐全 → verified=true。
        r4 = wf.finalize_verified("E-TH-01")
        assert r4.outcome is IntakeOutcome.ACCEPTED
        assert r4.state == ThresholdStatus.VERIFIED.value

        # 落库校验。
        written = json.loads(verified.read_text(encoding="utf-8"))
        e = written["thresholds"]["E-TH-01"]
        assert e["verified"] is True
        assert e["threshold_status"] == ThresholdStatus.VERIFIED.value
        assert e["verified_by"] == "principal-001"
        assert e["expert_verified_by"] == "expert-001"
        # 红线：value 原样来自人工（本测试 AI 以 None 占位，不编造）。
        assert e["value"] is None
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 2. source_ref 失败
# ---------------------------------------------------------------------------

def test_source_ref_invalid_rejected() -> None:
    """场景2：source_ref 缺 clause / 缺 hash → 拒绝进入审核，不入库。"""

    wf, verified, review = _new_workflow()
    try:
        # 缺 clause（C2 失败）。
        bad = _valid_source_ref()
        bad.pop("clause")
        r = wf.submit(_request("E-TH-01", source_ref=bad))
        assert r.outcome is IntakeOutcome.REJECTED
        assert "source_ref" in r.message.lower()

        # 库中应无任何 E-TH-01（拒绝不入库）。
        if verified.is_file():
            written = json.loads(verified.read_text(encoding="utf-8"))
            assert "E-TH-01" not in written.get("thresholds", {})
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 3. 缺专家签
# ---------------------------------------------------------------------------

def test_finalize_without_expert_sign_rejected() -> None:
    """场景3：主理人核准后未专家复核即转正 → 拒绝（双签不完整）。"""

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-01"))
        wf.review(
            threshold_id="E-TH-01",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        # 跳过 expert_recheck，直接转正 → 应拒绝。
        r = wf.finalize_verified("E-TH-01")
        assert r.outcome is IntakeOutcome.REJECTED
        written = json.loads(verified.read_text(encoding="utf-8"))
        assert written["thresholds"]["E-TH-01"]["verified"] is False
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 4. SoD 冲突
# ---------------------------------------------------------------------------

def test_sod_conflict_rejected() -> None:
    """场景4：专家复核人与主理人核准人同一身份 → 拒绝（SoD 红线）。"""

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-01"))
        wf.review(
            threshold_id="E-TH-01",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        # 专家复核人 == 主理人核准人 → SoD 冲突。
        r = wf.expert_recheck(
            threshold_id="E-TH-01",
            expert_verified_by="principal-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        assert r.outcome is IntakeOutcome.REJECTED
        assert "SoD" in r.message
        written = json.loads(verified.read_text(encoding="utf-8"))
        assert written["thresholds"]["E-TH-01"]["expert_verified_by"] is None
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 5. review_log 链
# ---------------------------------------------------------------------------

def test_review_log_chain_intact() -> None:
    """场景5：四步事件有序、prev_event_id 链式衔接、event_id 确定性。"""

    from agents.engineering.review_log import (
        compute_event_id,
        read_log,
    )

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-02"))
        wf.review(
            threshold_id="E-TH-02",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        wf.expert_recheck(
            threshold_id="E-TH-02",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        wf.finalize_verified("E-TH-02")

        events = read_log(review)
        actions = [e["action"] for e in events]
        assert actions == [
            "submit",
            "review",
            "expert_recheck",
            "verified",
        ]

        # prev_event_id 链式衔接。
        prev: str | None = None
        for e in events:
            assert e["prev_event_id"] == prev
            prev = e["event_id"]

        # event_id 确定性：用首条事件的字段重算应一致。
        first = events[0]
        recomputed = compute_event_id(
            threshold_id=first["threshold_id"],
            action=first["action"],
            signer_role=first["signer_role"],
            signer=first["signer"],
            timestamp=first["timestamp"],
            source_ref=first["source_ref"],
            prev_event_id=first["prev_event_id"],
        )
        assert recomputed == first["event_id"]
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 6. migration 兼容
# ---------------------------------------------------------------------------

def test_intake_output_v2_and_migration_noop() -> None:
    """场景6：录入产物为 schema v2，可被 loader 读取、喂入迁移判为 noop。"""

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-03"))
        wf.review(
            threshold_id="E-TH-03",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        wf.expert_recheck(
            threshold_id="E-TH-03",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        wf.finalize_verified("E-TH-03")

        # 录入产物顶层 schema_version=2。
        written = json.loads(verified.read_text(encoding="utf-8"))
        assert written["schema_version"] == 2
        e = written["thresholds"]["E-TH-03"]
        assert entry_schema_version(e) == 2
        assert isinstance(e["source_ref"], dict)
        assert "hash" in e["source_ref"]

        # 可被 load_verified_thresholds 读取。
        loaded = load_verified_thresholds(verified)
        assert loaded["E-TH-03"]["verified"] is True

        # 喂入迁移工具 → 已 v2 → noop（结构升级能力兼容）。
        out_tmp = Path(f"tests/_tmp_intake_mig_{_uniq()}.json")
        snap_dir = Path(f"tests/_tmp_intake_snap_{_uniq()}")
        try:
            report = migrate_thresholds(verified, out_tmp, snapshot_dir=snap_dir)
            assert report.status == MIGRATION_STATUS_NOOP
        finally:
            if out_tmp.is_file():
                out_tmp.unlink()
            if snap_dir.is_dir():
                for f in snap_dir.iterdir():
                    f.unlink()
                snap_dir.rmdir()
    finally:
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 7. enabled=false 保护
# ---------------------------------------------------------------------------

def test_enabled_false_protection() -> None:
    """场景7：evaluate_gates 恒 (False, reasons)；即便 E-TH-01~03 全双签转正，
    ExpertBackedEngineeringValidation(enabled=False) 仍 pending_verification。"""

    wf, verified, review = _new_workflow()
    try:
        # 对授权集合全部三条执行完整录入流程。
        for tid in ("E-TH-01", "E-TH-02", "E-TH-03"):
            wf.submit(_request(tid))
            wf.review(
                threshold_id=tid,
                verified_by="principal-001",
                verified_at="2026-07-31T00:00:00+00:00",
            )
            wf.expert_recheck(
                threshold_id=tid,
                expert_verified_by="expert-001",
                expert_verified_at="2026-07-31T01:00:00+00:00",
            )
            wf.finalize_verified(tid)

        # 门禁：即便双签齐全，仍传入 ci/rollback/authorization=False 且开关关 → 拒绝。
        allowed, reasons = wf.evaluate_gates()
        assert allowed is False
        assert reasons  # G3/G5/G6 等仍阻塞

        # 即便强行构造 enabled=False 校验器，永不为 approved。
        assert load_engineering_enabled() is False
        loaded = load_verified_thresholds(verified)
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
        _cleanup(verified, review)


# ---------------------------------------------------------------------------
# 附加：授权越界 / 重复提交 / 未提交审核 / 缺主理人即专家复核
# ---------------------------------------------------------------------------

def test_unauthorized_threshold_rejected() -> None:
    """授权越界：D-TH-01 / E-TH-04 不在本阶段范围 → 拒绝。"""

    wf, verified, review = _new_workflow()
    try:
        for tid in ("D-TH-01", "E-TH-04"):
            r = wf.submit(_request(tid))
            assert r.outcome is IntakeOutcome.REJECTED
            assert "授权" in r.message
    finally:
        _cleanup(verified, review)


def test_already_verified_repeat_submit_rejected() -> None:
    """已转正阈值重复提交 → 拒绝。"""

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-01"))
        wf.review(
            threshold_id="E-TH-01",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        wf.expert_recheck(
            threshold_id="E-TH-01",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        wf.finalize_verified("E-TH-01")
        # 重复提交已转正阈值 → 拒绝。
        r = wf.submit(_request("E-TH-01"))
        assert r.outcome is IntakeOutcome.REJECTED
        assert "已转正" in r.message
    finally:
        _cleanup(verified, review)


def test_review_before_submit_rejected() -> None:
    """未提交即审核 → 拒绝。"""

    wf, verified, review = _new_workflow()
    try:
        r = wf.review(
            threshold_id="E-TH-01",
            verified_by="principal-001",
            verified_at="2026-07-31T00:00:00+00:00",
        )
        assert r.outcome is IntakeOutcome.REJECTED
        assert "提交" in r.message
    finally:
        _cleanup(verified, review)


def test_expert_recheck_before_principal_rejected() -> None:
    """缺主理人核准即专家复核 → 拒绝（须先主理人审核）。"""

    wf, verified, review = _new_workflow()
    try:
        wf.submit(_request("E-TH-01"))
        r = wf.expert_recheck(
            threshold_id="E-TH-01",
            expert_verified_by="expert-001",
            expert_verified_at="2026-07-31T01:00:00+00:00",
        )
        assert r.outcome is IntakeOutcome.REJECTED
        assert "主理人" in r.message
    finally:
        _cleanup(verified, review)
