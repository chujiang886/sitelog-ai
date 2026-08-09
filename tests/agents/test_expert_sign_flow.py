"""ExpertBackedEngineeringValidation 四签流程演练测试（Phase 3.2 Sprint 3.2.3）。

本文件为**演练（Drill）**性质，覆盖四签状态机矩阵、review_log 事件-签名链路、
sign_off_id 确定性、engineering_enabled 关闭保护、pending 保持五点。

红线（Sprint 3.2.3，强制）：
- 不写入任何真实 verified.json（所有阈值夹具均在**内存**构造，value=None）；
- 不修改 config.yaml 的 engineering_enabled（真实态恒 false）；
- 不输出任何可用于生产的交付物（approved 仅内存注入逻辑分支验证）；
- 不填写真实专家身份（signer 仅填 principal-001 / expert-001 之类纯标识符）；
- 全部 verification_status 在真实系统视角恒 pending_verification。

既有 test_engineering_validation.py（Sprint A）不被改动；本文件从"状态机矩阵 +
模拟签署动作链路"视角补充演练覆盖。
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
    get_interface_thresholds,
    expert_signed,
    mgmt_signed,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# --------------------------------------------------------------------------- #
# 内存阈值夹具（全部 value=None，绝不落盘）                                       #
# --------------------------------------------------------------------------- #


def _dual_signed_entry(thr_id: str) -> dict:
    """构造一条五字段俱全的双签阈值（仅测试逻辑，不写入 verified.json）。"""

    return {
        "param": f"测试参数 {thr_id}",
        "value": None,
        "unit": "pending_verification",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-30",
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-30",
        "source_ref": "test fixture pending_verification",
        "applies_to": [],
    }


def _mgmt_only_entry(thr_id: str) -> dict:
    """仅主理人核准、缺专家签字。"""

    return {
        "param": f"测试参数 {thr_id}",
        "value": None,
        "unit": "pending_verification",
        "verified": True,
        "verified_by": "principal-001",
        "verified_at": "2026-07-30",
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
        "unit": "pending_verification",
        "verified": False,
        "verified_by": None,
        "verified_at": None,
        "expert_verified_by": "expert-001",
        "expert_verified_at": "2026-07-30",
        "source_ref": "test fixture pending_verification",
        "applies_to": [],
    }


def _full_wind_thresholds() -> dict:
    """wind_pressure 所需 E-TH-01、E-TH-02、E-TH-03 全部双签齐全（测试夹具 pending_verification）。"""

    return {
        "E-TH-01": _dual_signed_entry("E-TH-01"),
        "E-TH-02": _dual_signed_entry("E-TH-02"),
        "E-TH-03": _dual_signed_entry("E-TH-03"),
    }


def _mgmt_only_wind() -> dict:
    """wind_pressure 所需阈值仅主理人核准（缺专家签字）。"""

    return {
        "E-TH-01": _mgmt_only_entry("E-TH-01"),
        "E-TH-02": _mgmt_only_entry("E-TH-02"),
        "E-TH-03": _mgmt_only_entry("E-TH-03"),
    }


def _expert_only_wind() -> dict:
    """wind_pressure 所需阈值仅专家签字（缺主理人核准）。"""

    return {
        "E-TH-01": _expert_only_entry("E-TH-01"),
        "E-TH-02": _expert_only_entry("E-TH-02"),
        "E-TH-03": _expert_only_entry("E-TH-03"),
    }


def _valid_payload() -> dict:
    """结构齐备的四字段 payload（演练恒携带 pending_verification 语义）。"""

    return {
        "result": "",
        "confidence": "",
        "evidence": "",
        "verification_status": PENDING_VERIFICATION,
    }


# --------------------------------------------------------------------------- #
# 1. 四签状态机矩阵                                                              #
# --------------------------------------------------------------------------- #


def test_scenario_1_missing_structure_invalid() -> None:
    """场景1：四字段不齐备 → structure_valid=False，短路 invalid_structure。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    record = validator.validate(interface="wind_pressure", payload={"result": ""})
    assert record["structure_valid"] is False
    assert record["verification_status"] == "invalid_structure"
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is False
    assert record["sign_off_id"] is None


def test_scenario_2_missing_threshold_verified_pending() -> None:
    """场景2：缺主理人核准（仅专家签字）→ threshold_verified=False → pending。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_expert_only_wind())
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["structure_valid"] is True
    assert record["threshold_verified"] is False
    assert record["expert_signed"] is True
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_scenario_3_missing_expert_signed_pending() -> None:
    """场景3：缺专家签字（仅主理人核准）→ expert_signed=False → pending。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_mgmt_only_wind())
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["structure_valid"] is True
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is False
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_scenario_4_all_signed_but_enabled_false_pending() -> None:
    """场景4：四签满足但 engineering_enabled=false（真实态）→ 红线保护 pending。"""

    # engineering_enabled=None 显式读 config.yaml（真实 false），不注入。
    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    assert validator.engineering_enabled is False
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["structure_valid"] is True
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is True
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_scenario_5_all_signed_enabled_true_approves_injected_only() -> None:
    """场景5：仅逻辑分支——注入 engineering_enabled=True 验证闸门派生 approved。

    注意：这是对代码闸门的逻辑验证，绝不改动真实 config.yaml；
    真实系统因 engineering_enabled=false 永不触发本分支。
    """

    validator = ExpertBackedEngineeringValidation(
        thresholds=_full_wind_thresholds(), engineering_enabled=True
    )
    assert validator.engineering_enabled is True
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["verification_status"] == ENGINEERING_APPROVED
    assert isinstance(record["sign_off_id"], str)
    assert len(record["sign_off_id"]) == 16


def test_state_machine_matrix_exhaustive() -> None:
    """四签矩阵全景：枚举 structure/threshold/expert 组合 + enabled 两态，断言输出与不变量。"""

    cases = [
        # (structure_valid 由 payload 决定, threshold_verified, expert_signed, enabled, 期望 status, 期望 sign_off None)
        (False, False, False, False, "invalid_structure", True),
        (True, False, True, False, PENDING_VERIFICATION, True),
        (True, True, False, False, PENDING_VERIFICATION, True),
        (True, True, True, False, PENDING_VERIFICATION, True),   # 红线保护（场景4）
        (True, False, True, True, PENDING_VERIFICATION, True),    # 缺主理人核准，enabled 开也无用
        (True, True, False, True, PENDING_VERIFICATION, True),    # 缺专家签字，enabled 开也无用
        (True, True, True, True, ENGINEERING_APPROVED, False),    # 仅注入分支
    ]
    for structure_ok, thr_ok, exp_ok, enabled, exp_status, exp_none in cases:
        if structure_ok:
            payload = _valid_payload()
            thresholds = _full_wind_thresholds() if (thr_ok and exp_ok) else (
                _mgmt_only_wind() if thr_ok else _expert_only_wind()
            )
        else:
            payload = {"result": ""}
            thresholds = _full_wind_thresholds()
        validator = ExpertBackedEngineeringValidation(
            thresholds=thresholds,
            engineering_enabled=enabled,
        )
        record = validator.validate(interface="wind_pressure", payload=payload)
        assert record["verification_status"] == exp_status, (structure_ok, thr_ok, exp_ok, enabled)
        if exp_none:
            assert record["sign_off_id"] is None
        else:
            assert isinstance(record["sign_off_id"], str) and len(record["sign_off_id"]) == 16


# --------------------------------------------------------------------------- #
# 2. review_log 事件-签名链路                                                   #
# --------------------------------------------------------------------------- #


def test_review_log_chain_principal_then_expert() -> None:
    """模拟签署链：先 principal_approve 后 expert_sign，后者 prev_event_id 指向前者。"""

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "review_log.jsonl"
        principal = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="principal_approve",
            signer_role="principal",
            signer="principal-001",
            source_ref="test fixture pending_verification",
            log_path=log_path,
        )
        expert = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="expert_sign",
            signer_role="expert",
            signer="expert-001",
            source_ref="test fixture pending_verification",
            log_path=log_path,
        )
        # 链接正确：专家签字事件指向下一条的前驱为主理人核准事件。
        assert expert["prev_event_id"] == principal["event_id"]
        # 回放保持写入顺序。
        records = review_log.read_log(log_path)
        assert len(records) == 2
        assert records[0]["event_id"] == principal["event_id"]
        assert records[1]["event_id"] == expert["event_id"]
        # 八字段齐备。
        for field in review_log.REQUIRED_FIELDS:
            assert field in records[0]
            assert field in records[1]


def test_review_log_event_id_deterministic_and_recomputable() -> None:
    """event_id 确定性：相同入参恒得相同哈希；可用 compute_event_id 复算核对。"""

    kw = dict(
        threshold_id="E-TH-04",
        action="expert_sign",
        signer_role="expert",
        signer="expert-001",
        timestamp="2026-07-30T00:00:00+00:00",
        source_ref="test fixture pending_verification",
        prev_event_id=None,
    )
    first = review_log.compute_event_id(**kw)
    second = review_log.compute_event_id(**kw)
    assert first == second
    # 复算一致（可复核性）。
    assert review_log.compute_event_id(**kw) == first


def test_review_log_custom_prev_pointer() -> None:
    """显式传入 prev_event_id 时，记录须保留该指针（演练自定义链）。"""

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "review_log.jsonl"
        e1 = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="principal_approve",
            signer_role="principal",
            signer="principal-001",
            source_ref="test fixture pending_verification",
            log_path=log_path,
        )
        custom_prev = "0" * 64
        e2 = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="expert_sign",
            signer_role="expert",
            signer="expert-001",
            source_ref="test fixture pending_verification",
            prev_event_id=custom_prev,
            log_path=log_path,
        )
        # 显式覆盖默认指针。
        assert e2["prev_event_id"] == custom_prev
        # 首条仍由无历史推导（prev 指向 None）。
        assert e1["prev_event_id"] is None


def test_review_log_skips_corrupted_lines() -> None:
    """损坏行（非 JSON）静默跳过，不影响回放顺序与数量。"""

    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / "review_log.jsonl"
        good = review_log.append_review_event(
            threshold_id="E-TH-01",
            action="principal_approve",
            signer_role="principal",
            signer="principal-001",
            source_ref="test fixture pending_verification",
            log_path=log_path,
        )
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write("this is not valid json\n")
        records = review_log.read_log(log_path)
        assert len(records) == 1
        assert records[0]["event_id"] == good["event_id"]


# --------------------------------------------------------------------------- #
# 3. sign_off_id 确定性                                                         #
# --------------------------------------------------------------------------- #


def test_sign_off_id_deterministic_recompute() -> None:
    """场景5 派生的 sign_off_id 与用同一夹具 compute_sign_off_id 重算完全一致。"""

    validator = ExpertBackedEngineeringValidation(
        thresholds=_full_wind_thresholds(), engineering_enabled=True
    )
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
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
    assert len(record["sign_off_id"]) == 16


def test_sign_off_id_absent_when_pending() -> None:
    """pending 态（含场景4红线）sign_off_id 恒 None；不为空串/占位。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["sign_off_id"] is None


# --------------------------------------------------------------------------- #
# 4. engineering_enabled 关闭保护                                              #
# --------------------------------------------------------------------------- #


def test_enabled_false_in_real_config() -> None:
    """真实配置 engineering_enabled 必须为 false（红线，演练不改动）。"""

    assert load_engineering_enabled() is False


def test_all_five_interfaces_pending_when_enabled_false() -> None:
    """真实 enabled=false 下，五接口全 validate 恒 pending、sign_off_id=None。"""

    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    for iface in ANALYSIS_INTERFACES:
        record = validator.validate(interface=iface, payload=_valid_payload())
        assert record["verification_status"] == PENDING_VERIFICATION
        assert record["sign_off_id"] is None
        assert record["verification_status"] != ENGINEERING_APPROVED


def test_agent_with_expert_validator_never_approves() -> None:
    """EngineeringAgent 注入 ExpertBackedEngineeringValidation（读真实 flag=false）
    全链路 verification_status 恒 pending_verification，无 approved 产出。"""

    import asyncio

    from agents.base import AgentContext

    agent = EngineeringAgent(validator=ExpertBackedEngineeringValidation())
    context = AgentContext(request_id="eng-sign-drill", input_data={})
    result = asyncio.run(agent.invoke(context))
    assert result.success is True
    for iface in ANALYSIS_INTERFACES:
        rec = next(r for r in result.data["review_chain"] if r["interface"] == iface)
        assert rec["verification_status"] == PENDING_VERIFICATION
        assert rec["sign_off_id"] is None
        assert rec["verification_status"] != ENGINEERING_APPROVED


# --------------------------------------------------------------------------- #
# 5. pending 保持                                                              #
# --------------------------------------------------------------------------- #


def test_pending_preserved_across_sign_flow_drill() -> None:
    """演练全流程：无论双签是否"模拟齐全"，只要真实 enabled=false，结论恒 pending。"""

    # 模拟齐全双签 + 真实 enabled=false（场景4）。
    validator = ExpertBackedEngineeringValidation(thresholds=_full_wind_thresholds())
    record = validator.validate(interface="wind_pressure", payload=_valid_payload())
    assert record["threshold_verified"] is True
    assert record["expert_signed"] is True
    # 关键不变量：双签齐全但开关关闭 → 仍 pending，绝不泄漏 approved。
    assert record["verification_status"] == PENDING_VERIFICATION
    assert record["sign_off_id"] is None


def test_signer_identifiers_are_non_real() -> None:
    """演练 signer 仅用纯标识符（非真实姓名/资质编号），不污染真实签署库。"""

    assert mgmt_signed(_dual_signed_entry("E-TH-01")) is True
    assert expert_signed(_dual_signed_entry("E-TH-01")) is True
    # 主理人/专家标识为 principal-001 / expert-001，不含真实身份。
    assert _dual_signed_entry("E-TH-01")["verified_by"] == "principal-001"
    assert _dual_signed_entry("E-TH-01")["expert_verified_by"] == "expert-001"


# --------------------------------------------------------------------------- #
# 内部辅助（防重复）                                                            #
# --------------------------------------------------------------------------- #


def _drill_log_path(tmp_root: str) -> Path:
    """返回演练用临时日志路径（不触碰真实 review_log.jsonl）。"""

    return Path(tmp_root) / "review_log_drill.jsonl"
