"""2.2.2 Design 三方案专业化测试（机制先行，零工程数值）。

覆盖（用户指令 Step 4）：
- 三方案数量（T1）
- pending 语义修正（T2）
- field_provenance 溯源（T3）
- verified 机制（T4 已签字标 verified / T5 一票否决维持 pending）
- 防编造（T6 降级零杜撰 / T7 loader 全 pending / T8 threshold_refs 仅引用无数值）

全部阈值在默认 verified.json 中 verified=false；本测试**不写入**任何
verified=true、不构造任何真实工程数值，仅校验机制语义。
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.design.agent import (
    DesignAgent,
)
from agents.design.threshold_loader import (
    KEY_FIELDS,
    build_threshold_refs,
    is_fully_verified,
    load_verified_thresholds,
)


# --------------------------------------------------------------------------- #
# 工具                                                                         #
# --------------------------------------------------------------------------- #

_THREE_CANDIDATES_PAYLOAD: dict = {
    "candidates": [
        {
            "id": "D1",
            "title": "断桥铝平开窗方案",
            "opening_type": "平开窗",
            "frame_material": "断桥铝合金",
            "glass_type": "中空玻璃",
            "dimensions_hint": "宽 1.8m × 高 2.1m，左右等分",
            "estimated_cost_tier": "标准",
            "pros": ["密封性好", "隔音佳"],
            "cons": ["造价略高"],
            "rationale": "通用推荐。",
        },
        {
            "id": "D2",
            "title": "塑钢推拉窗方案",
            "opening_type": "推拉窗",
            "frame_material": "塑钢",
            "glass_type": "单片钢化",
            "dimensions_hint": "宽 1.8m × 高 2.1m，推拉扇",
            "estimated_cost_tier": "经济",
            "pros": ["性价比高"],
            "cons": ["密封性一般"],
            "rationale": "预算优先。",
        },
        {
            "id": "D3",
            "title": "木铝复合落地窗方案",
            "opening_type": "落地窗",
            "frame_material": "木铝复合",
            "glass_type": "低辐射 Low-E",
            "dimensions_hint": "宽 2.4m × 高 2.6m，整面采光",
            "estimated_cost_tier": "高端",
            "pros": ["保温优"],
            "cons": ["成本高"],
            "rationale": "采光与保温高要求时考虑。",
        },
    ]
}


def _fake_llm_router(payload: dict):
    """构造返回 3 候选合法 JSON 的假 router（禁用真实 LLM）。"""

    fake_response = SimpleNamespace(content=json.dumps(payload), model="qwen-test")

    async def _route(_request):
        return fake_response, [
            SimpleNamespace(
                provider_name="track_a",
                track="track_a",
                response=fake_response,
                error=None,
                latency_ms=1,
                pending_verification=False,
            )
        ]

    return SimpleNamespace(route=_route, aclose=lambda: asyncio.sleep(0))


def _enable_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    """把 load_llm_config 与 router 工厂替换为 fake，使 invoke 走 LLM 成功路径。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {
            "enabled": True,
            "track_a": {"provider": "openai_compat", "api_key": "k"},
            "track_b": {},
        },
    )
    monkeypatch.setattr(
        "agents.llm.router.build_router_from_config",
        lambda _cfg, **_kw: _fake_llm_router(_THREE_CANDIDATES_PAYLOAD),
    )


# --------------------------------------------------------------------------- #
# T1 三方案数量                                                                #
# --------------------------------------------------------------------------- #


def test_design_produces_exactly_three_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 成功仍返回恰好 3 个候选（契约保持，无回归）。"""

    _enable_llm(monkeypatch)
    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-1",
        input_data={
            "vision_result": {"scene_type": "落地窗", "orientation_hint": "南"},
            "environment_result": {
                "climate_zone": "夏热冬暖地区",
                "prevailing_wind": "东南",
                "solar_exposure": "西晒明显",
            },
            "consultation": {"budget_tier": "标准", "style_preference": "现代简约"},
            "address": "广东省汕头市",
            "region_hint": "华南/汕头",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert isinstance(result.data["candidates"], list)
    assert len(result.data["candidates"]) == 3
    assert [c["id"] for c in result.data["candidates"]] == ["D1", "D2", "D3"]


# --------------------------------------------------------------------------- #
# T2 pending 语义修正                                                          #
# --------------------------------------------------------------------------- #


def test_design_pending_true_after_llm_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 成功时 pending_verification 仍为 True（修正 P1，ADR §7 对齐）。"""

    _enable_llm(monkeypatch)
    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-2",
        input_data={
            "consultation": {"budget_tier": "标准"},
            "address": "广东省汕头市",
            "region_hint": "华南/汕头",
        },
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True


# --------------------------------------------------------------------------- #
# T3 field_provenance 溯源                                                    #
# --------------------------------------------------------------------------- #


def test_design_field_provenance_present_and_inferred(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """field_provenance 存在；设计关键字段标 inferred（非 verified）。"""

    _enable_llm(monkeypatch)
    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-3",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    provenance = result.data["field_provenance"]
    for field in KEY_FIELDS:
        assert field in provenance
        assert provenance[field] == "inferred"
    # 未签字 → 顶层 pending 恒 True
    assert result.data["pending_verification"] is True


# --------------------------------------------------------------------------- #
# T4 verified 机制：已完整签字 → 该字段 verified                               #
# --------------------------------------------------------------------------- #


def test_design_verified_threshold_marks_field_verified(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verified=true 且 verified_by/verified_at 俱全 → 对应字段标 verified，
    且不再进入该字段的 pending gap。"""

    _enable_llm(monkeypatch)
    # 仅 D-TH-01（frame_material）完整签字；其余保持未签。
    signed = {
        "D-TH-01": {
            "param": "型材壁厚/系列",
            "value": None,
            "unit": "mm",
            "verified": True,
            "verified_by": "expert-zhang",
            "verified_at": "2026-07-27",
            "source_ref": "GB/T pending_verification",
            "applies_to_scheme": ["economy", "comfort", "performance"],
        }
    }
    monkeypatch.setattr(
        "agents.design.agent.load_verified_thresholds", lambda: signed
    )

    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-4",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    provenance = result.data["field_provenance"]
    assert provenance["frame_material"] == "verified"
    # 该字段不再进入 pending gap（其余字段仍在）。
    gaps = result.data["gaps"]
    assert not any("design_threshold:D-TH-01" in g for g in gaps)
    assert any("design_threshold:D-TH-02" in g for g in gaps)


# --------------------------------------------------------------------------- #
# T5 一票否决：缺签字 → 字段维持 pending                                        #
# --------------------------------------------------------------------------- #


def test_design_unverified_threshold_stays_pending(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """verified=true 但缺 verified_by → 仍视为未签字（一票否决）→ 字段维持
    inferred / 顶层 pending 恒 True。"""

    _enable_llm(monkeypatch)
    # 缺 verified_by（伪造部分签字，必须被拒）。
    partial = {
        "D-TH-01": {
            "param": "型材壁厚/系列",
            "value": None,
            "unit": "mm",
            "verified": True,
            "verified_by": None,
            "verified_at": "2026-07-27",
            "source_ref": "pending_verification",
            "applies_to_scheme": ["economy", "comfort", "performance"],
        }
    }
    monkeypatch.setattr(
        "agents.design.agent.load_verified_thresholds", lambda: partial
    )

    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-5",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    provenance = result.data["field_provenance"]
    assert provenance["frame_material"] == "inferred"
    assert result.data["pending_verification"] is True
    # 仍计入该字段的 pending gap（一票否决生效）。
    assert any("design_threshold:D-TH-01" in g for g in result.data["gaps"])


# --------------------------------------------------------------------------- #
# T6 降级零杜撰                                                                #
# --------------------------------------------------------------------------- #


def test_design_disabled_llm_returns_placeholder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llm.enabled=false → 占位 envelope，不抛错，candidates=[]，pending=True。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )
    agent = DesignAgent()
    ctx = AgentContext(
        request_id="design-prof-6",
        input_data={"consultation": {"budget_tier": "标准"}},
    )
    result = asyncio.run(agent.invoke(ctx))
    assert result.success is True
    assert result.data["pending_verification"] is True
    assert result.data["candidates"] == []
    assert result.data["provider"] == "mock"
    # 溯源在占位态为 unavailable（未产出）。
    assert result.data["field_provenance"]["frame_material"] == "unavailable"


# --------------------------------------------------------------------------- #
# T7 loader 默认全 pending（防编造机制）                                        #
# --------------------------------------------------------------------------- #


def test_threshold_loader_default_all_pending() -> None:
    """默认 verified.json 全部 verified=false，任何字段不得转正。"""

    verified = load_verified_thresholds()
    assert verified, "verified.json 应至少包含 D-TH-01..05"
    for thr_id, entry in verified.items():
        assert is_fully_verified(entry) is False
        assert entry.get("verified") is False
        assert entry.get("verified_by") is None
        assert entry.get("verified_at") is None
        assert entry.get("value") is None


# --------------------------------------------------------------------------- #
# T8 threshold_refs 仅引用 ID，不携带数值（防编造）                             #
# --------------------------------------------------------------------------- #


def test_threshold_refs_only_ids_no_values() -> None:
    """threshold_refs 仅指向阈值 ID，绝不内联任何工程数值。"""

    refs = build_threshold_refs()
    for field, thr_id in refs.items():
        assert isinstance(thr_id, str)
        assert thr_id.startswith("D-TH-")
    # 与 KEY_FIELDS 对齐（外加 scheme_scoring）。
    for field in KEY_FIELDS:
        assert field in refs
    assert refs["scheme_scoring"] == "D-TH-05"
