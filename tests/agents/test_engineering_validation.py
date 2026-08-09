"""ExpertBackedEngineeringValidation + 阈值治理 + 审核日志 测试（Phase 3.1 Sprint A）。

覆盖任务 5 的六类场景：
1. 阈值缺失：接口所需的签字阈值不在已加载表中 → 恒 pending_verification；
2. 双签失败：仅主理人核准 或 仅专家签字 → 任一缺失即 pending_verification；
3. 双签成功模拟：五字段俱全；真实 flag=false → 仍 pending（红线），
   flag 注入 true（仅逻辑分支测试）→ 派生 engineering_approved + sign_off_id；
4. 日志链：append-only、prev_event_id 链式链接、event_id 确定性；
5. engineering_enabled 保持 false：真实配置 + Agent 注入验证器均不输出 approved；
6. 防编造扫描：verified.json / 新增 .py / review_log.jsonl 均零命中，
   且能正确捕获一条伪造业务数字。

红线断言：Sprint A 真实系统绝不输出 engineering_approved、绝不填真实参数、
绝不设 verified=true。测试中的"双签成功"仅在内存 fixture 中模拟，不写入
任何真实 verified.json，也不改动 config.yaml 的 engineering_enabled。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from agents.config_loader import load_engineering_enabled
from agents.engineering import review_log
from agents.engineering.agent import ANALYSIS_INTERFACES, EngineeringAgent
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
    ExpertBackedEngineeringValidation,
)
from agents.engineering.threshold_loader import (
    DEFAULT_VERIFIED_PATH,
    build_threshold_refs,
    get_interface_thresholds,
    is_fully_verified,
    expert_signed,
    mgmt_signed,
)
from agents.loader import AgentLoader, DEFAULT_CONFIG_PATH
from scripts.lint.check_fabrication import scan_file

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# 辅助 fixture 构造（全部内存态，绝不写入真实 verified.json）                        #
# --------------------------------------------------------------------------- #


def _dual_signed_entry(thr_id: str) -> dict:
    """构造一条五字段俱全的双签阈值（仅用于测试逻辑，不落盘）。"""

    return {
        "param": f"测试参数 {thr_id}",
        "value": None,
        "unit": "pending_verification",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-28",
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-28",
        "source_ref": "test fixture pending_verification",
        "applies_to": [],
    }


def _mgmt_only_entry(thr_id: str) -> dict:
    """仅主理人核准、缺专家签字。"""

    return {
        "param": f"测试参数 {thr_id}",
        "value": None,
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-28",
        "expert_verified_by": None,
        "expert_verified_at": None,
        "source_ref": "test fixture pending_verification",
        "applies_to": [],
    }


def _expert_only_entry(thr_id: str) -> dict:
    """仅专家签字、缺主理人核准。"""

    return {
        "param": f"测试参数 {thr_id}",
        "value": None,
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-28",
        "source_ref": "test fixture pending_verification",
        "applies_to": [],
    }


def _full_wind_thresholds() -> dict:
    """wind_pressure 所需的 E-TH-01~03 全部双签齐全（测试 fixture pending_verification）。"""

    return {
        "E-TH-01": _dual_signed_entry("E-TH-01"),
        "E-TH-02": _dual_signed_entry("E-TH-02"),
        "E-TH-03": _dual_signed_entry("E-TH-03"),
    }


# --------------------------------------------------------------------------- #
# 1. 阈值缺失                                                                   #
# --------------------------------------------------------------------------- #


def test_interface_threshold_map_resolves_all_five() -> None:
    """build_threshold_refs 必须覆盖五个分析接口。"""

    refs = build_threshold_refs()
    for iface in ANALYSIS_INTERFACES:
        assert iface in refs
        assert refs[iface]


def test_missing_threshold_yields_pending() -> None:
    """所需阈值不在已加载表 → threshold_verified/expert_signed 均 False。"""

    # 空表：wind_pressure 需要 E-TH-01~03，但表为空 → 缺失（fixture pending_verification）。
    validator = ExpertBackedEngineeringValidation(thresholds={})
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["structure_valid"] is True
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_partial_threshold_missing_yields_pending() -> None:
    """部分阈值缺失（仅 E-TH-01 在表，02/03 缺失）→ 仍 pending。"""

    validator = ExpertBackedEngineeringValidation(thresholds={"E-TH-01": _dual_signed_entry("E-TH-01")})
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["threshold_verified"] is False
    assert record["verification_status"] == PENDING_VERIFICATION


# --------------------------------------------------------------------------- #
# 2. 双签失败                                                                   #
# --------------------------------------------------------------------------- #


def test_dual_sign_failure_mgmt_only() -> None:
    """仅主理人核准（缺专家签字）→ threshold_verified True / expert_signed False → pending。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_mgmt_only_wind())
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is False
    assert record["verification_status"] == PENDING_VERIFICATION


def test_dual_sign_failure_expert_only() -> None:
    """仅专家签字（缺主理人核准）→ threshold_verified False / expert_signed True → pending。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_expert_only_wind())
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is True
    assert record["verification_status"] == PENDING_VERIFICATION


def test_is_fully_verified_requires_both_signs() -> None:
    """is_fully_verified 五字段缺一即 False。"""

    assert is_fully_verified(_dual_signed_entry("E-TH-01")) is True
    assert is_fully_verified(_mgmt_only_entry("E-TH-01")) is False
    assert is_fully_verified(_expert_only_entry("E-TH-01")) is False
    assert is_fully_verified(None) is False
    assert mgmt_signed(_dual_signed_entry("E-TH-01")) is True
    assert expert_signed(_dual_signed_entry("E-TH-01")) is True
    assert mgmt_signed(_expert_only_entry("E-TH-01")) is False


# --------------------------------------------------------------------------- #
# 3. 双签成功模拟                                                               #
# --------------------------------------------------------------------------- #


def test_dual_sign_success_real_flag_false_stays_pending() -> None:
    """双签齐全 + 真实 engineering_enabled=false → 仍 pending_verification（红线）。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    # 真实 flag：读取 config.yaml（false），不注入。
    assert validator.engineering_enabled is False
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is True
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_dual_sign_success_injected_flag_true_approves() -> None:
    """仅逻辑分支测试：注入 engineering_enabled=true 验证闸门能产出 approved。

    注意：这是对代码闸门的逻辑验证，绝不改动真实 config.yaml；
    真实系统因 flag=false 永不触发本分支。
    """

    validator = ExpertBackedEngineeringValidation(
        thresholds=_full_wind_thresholds(), engineering_enabled=True
    )
    assert validator.engineering_enabled is True
    record = validator.validate(
        interface="wind_pressure",
        payload={"result": "", "confidence": "", "evidence": "", "verification_status": PENDING_VERIFICATION},
    )
    assert record["verification_status"] == ENGINEERING_APPROVED
    assert isinstance(record["sign_off_id"], str) and len(record["sign_off_id"]) == 16
    # sign_off_id 必须由同一签名元数据确定性派生（可复核）。
    expected = review_log.compute_sign_off_id(
        interface="wind_pressure",
        threshold_ids=get_interface_thresholds("wind_pressure"),
        signs=[
            ("E-TH-01", _dual_signed_entry("E-TH-01")),
            ("E-TH-02", _dual_signed_entry("E-TH-02")),
            ("E-TH-03", _dual_signed_entry("E-TH-03")),
        ],
    )
    assert record["sign_off_id"] == expected


def test_missing_interface_raises() -> None:
    """空 interface 必须抛 ValueError（与 PendingEngineeringValidation 对齐）。"""

    validator = ExpertBackedEngineeringValidation(thresholds={})
    try:
        validator.validate(interface="", payload={})
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_invalid_structure_returns_invalid_status() -> None:
    """四字段不齐备 → invalid_structure，不进入阈值判定。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    record = validator.validate(interface="wind_pressure", payload={"result": ""})
    assert record["structure_valid"] is False
    assert record["verification_status"] == "invalid_structure"
    assert record["threshold_verified"] is False


# --------------------------------------------------------------------------- #
# 4. 日志链                                                                     #
# --------------------------------------------------------------------------- #


def test_review_log_chain_links_and_append_only() -> None:
    """审核日志 append-only，prev_event_id 链式链接到末条。"""

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "review_log.jsonl"
        e1 = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="expert_sign",
            signer_role="expert",
            signer="expert-001",
            source_ref="test pending_verification",
            log_path=log_path,
        )
        e2 = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="principal_approve",
            signer_role="principal",
            signer="principal-001",
            source_ref="test pending_verification",
            log_path=log_path,
        )
        # e2 必须链接到 e1（链式溯源）。
        assert e2["prev_event_id"] == e1["event_id"]
        # 回放保持写入顺序。
        records = review_log.read_log(log_path)
        assert len(records) == 2
        assert records[0]["event_id"] == e1["event_id"]
        assert records[1]["event_id"] == e2["event_id"]
        # event_id 确定性：相同入参必须得到相同哈希。
        e1b = review_log.compute_event_id(
            threshold_id="E-TH-01",
            action="expert_sign",
            signer_role="expert",
            signer="expert-001",
            timestamp=e1["timestamp"],
            source_ref="test pending_verification",
            prev_event_id=None,
        )
        assert e1b == e1["event_id"]


def test_review_log_event_id_deterministic() -> None:
    """相同输入 → 相同 event_id（内容寻址）。"""

    kw = dict(
        threshold_id="E-TH-04",
        action="expert_sign",
        signer_role="expert",
        signer="expert-002",
        timestamp="2026-07-28T00:00:00+00:00",
        source_ref="x pending_verification",
        prev_event_id=None,
    )
    assert review_log.compute_event_id(**kw) == review_log.compute_event_id(**kw)


# --------------------------------------------------------------------------- #
# 5. engineering_enabled 保持 false                                            #
# --------------------------------------------------------------------------- #


def test_engineering_enabled_false_in_config() -> None:
    """真实配置：orchestrator.engineering_enabled 必须为 false（红线）。"""

    assert load_engineering_enabled() is False
    loader = AgentLoader(config_path=DEFAULT_CONFIG_PATH, registry=None)  # type: ignore[arg-type]
    config = loader.load_config()
    assert config.engineering_enabled is False


def test_agent_with_expert_validator_never_approves() -> None:
    """Agent 注入 ExpertBackedEngineeringValidation（默认读真实 flag=false）
    → invoke 全链路 verification_status 恒 pending_verification，无 approved。"""

    from agents.base import AgentContext
    import asyncio

    agent = EngineeringAgent(validator=ExpertBackedEngineeringValidation())
    context = AgentContext(request_id="eng-sprintA", input_data={})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    for iface in ANALYSIS_INTERFACES:
        rec = next(r for r in result.data["review_chain"] if r["interface"] == iface)
        assert rec["verification_status"] == PENDING_VERIFICATION
        assert rec["sign_off_id"] is None
        assert rec["verification_status"] != ENGINEERING_APPROVED


# --------------------------------------------------------------------------- #
# 6. 防编造扫描                                                                 #
# --------------------------------------------------------------------------- #


def test_fabrication_scan_clean_on_engineering_assets() -> None:
    """verified.json / 新增工程 .py / review_log.jsonl 均零命中（防编造）。"""

    assert scan_file(DEFAULT_VERIFIED_PATH) == []
    assert scan_file(Path(__file__).resolve().parents[2] / "agents" / "engineering" / "validation.py") == []
    assert scan_file(Path(__file__).resolve().parents[2] / "agents" / "engineering" / "threshold_loader.py") == []
    assert scan_file(review_log.DEFAULT_REVIEW_LOG_PATH) == []


def test_fabrication_scan_catches_fabricated_number() -> None:
    """扫描器能正确捕获一条伪造业务数字（验证扫描有效，非空跑）。"""

    with tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8"
    ) as fh:
        # 故意构造含业务词 + 真实数字的行写入临时文件，验证扫描器能捕获；
        # 源文件本身把各部分拆到不同行，避免被当成未验证数值误伤。
        fake_a = "某阈值 "
        fake_b = "风压 "
        fake_c = "1200"
        fake_d = " Pa 直接写死\n"
        fh.write(fake_a + fake_b + fake_c + fake_d)
        tmp_path = Path(fh.name)
    try:
        findings = scan_file(tmp_path)
        assert len(findings) == 1
        first = findings[0]
        assert "风压" in first.line
    finally:
        tmp_path.unlink()


# --------------------------------------------------------------------------- #
# 内部辅助                                                                      #
# --------------------------------------------------------------------------- #


def _mgmt_only_wind() -> dict:
    return {
        "E-TH-01": _mgmt_only_entry("E-TH-01"),
        "E-TH-02": _mgmt_only_entry("E-TH-02"),
        "E-TH-03": _mgmt_only_entry("E-TH-03"),
    }


def _expert_only_wind() -> dict:
    return {
        "E-TH-01": _expert_only_entry("E-TH-01"),
        "E-TH-02": _expert_only_entry("E-TH-02"),
        "E-TH-03": _expert_only_entry("E-TH-03"),
    }
