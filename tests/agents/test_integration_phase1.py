"""Phase 1 集成测试：三 Agent（Vision / Environment / Design）真实输出 → PDF 报告端到端打通。

目标：验证 Phase 1 三块实现与 PDF 报告模块之间的「数据契约」成立，且端到端不崩溃。

手法：
- 通过 monkeypatch ``DualTrackRouter`` 注入确定性的合法 JSON 响应（不真正调用 LLM），
  让三 Agent 走真实 LLM 成功路径，产出与运行时一致的 ``.data`` dict；
- 把三段 ``.data`` 组装成 dossier，调用 ``generate_project_report``，断言返回合法 PDF 字节流；
- 同时验证降级（llm disabled → 全部占位 envelope）路径下报告仍生成合法 PDF。

不依赖 PDF 文本可搜索（reportlab 默认压缩流），仅校验字节流合法性 + 数据契约字段。
"""

from __future__ import annotations

import asyncio
import io
import json
from types import SimpleNamespace

import pytest

from agents.base import AgentContext
from agents.design.agent import DesignAgent
from agents.environment.agent import EnvironmentAgent
from agents.report.generator import generate_project_report
from agents.vision.agent import VisionAgent


# --------------------------------------------------------------------------- #
# 注入用的确定性 payload（与三 Agent system prompt 的 schema 对应）              #
# --------------------------------------------------------------------------- #

_VISION_PAYLOAD: dict = {
    "scene_type": "开放阳台",
    "obstructions": ["空调外机", "晾衣架", "护栏"],
    "orientation_hint": "东南",
    "quality": "high",
    "recommendations": ["建议封装以提升保温性能", "注意晾衣架对开启路径的影响"],
}

_ENV_PAYLOAD: dict = {
    "climate_zone": "夏热冬暖地区",
    "prevailing_wind": "东南",
    "solar_exposure": "西晒明显",
    "noise_level_hint": "中",
    "regulatory_hints": ["阳台封装需符合地方管理条例", "外立面改动需物业备案"],
    "regional_material_preference": "断桥铝为主",
    "summary": "华南沿海高温高湿、台风频发，需重视隔热与抗风压。",
}

_DESIGN_PAYLOAD: dict = {
    "candidates": [
        {
            "id": "D1",
            "title": "断桥铝平开窗方案",
            "opening_type": "平开窗",
            "frame_material": "断桥铝合金",
            "glass_type": "中空 Low-E 玻璃",
            "dimensions_hint": "主窗 1.8m×2.1m，分 2 扇",
            "estimated_cost_tier": "标准",
            "pros": ["密封性好", "保温隔热佳", "抗风压能力强"],
            "cons": ["开启占用室内空间", "五金成本略高"],
            "rationale": "结合西晒与台风区，断桥铝 + Low-E 兼顾隔热与气密。",
        },
        {
            "id": "D2",
            "title": "塑钢推拉窗方案",
            "opening_type": "推拉窗",
            "frame_material": "塑钢",
            "glass_type": "中空玻璃",
            "dimensions_hint": "主窗 2.0m×2.1m，推拉扇",
            "estimated_cost_tier": "经济",
            "pros": ["性价比高", "不占室内空间"],
            "cons": ["密封性弱于平开", "抗风压一般"],
            "rationale": "预算敏感场景下以推拉降低综合造价，适合低楼层。",
        },
        {
            "id": "D3",
            "title": "木铝复合落地窗方案",
            "opening_type": "上悬 + 平开复合",
            "frame_material": "木铝复合",
            "glass_type": "夹胶 Low-E 中空玻璃",
            "dimensions_hint": "整面 3.0m×2.4m 分段",
            "estimated_cost_tier": "高端",
            "pros": ["观景效果佳", "隔热隔音优"],
            "cons": ["造价高", "维护要求高"],
            "rationale": "面向高预算、重景观需求，强调舒适与美观统一。",
        },
    ]
}


# --------------------------------------------------------------------------- #
# helpers                                                                       #
# --------------------------------------------------------------------------- #


def _assert_valid_pdf(pdf: bytes) -> None:
    """一组稳健的 PDF 合法性断言（不依赖文本可搜索）。"""

    assert isinstance(pdf, bytes), "应返回 bytes"
    assert pdf.startswith(b"%PDF"), "PDF 字节应以 %PDF 开头"
    assert len(pdf) > 200, "PDF 字节长度应大于 200"
    reused = io.BytesIO(pdf)
    reused.seek(0)
    assert reused.read(4) == b"%PDF"


def _make_dispatcher_router() -> SimpleNamespace:
    """返回单一假 router：按 user prompt 关键字分发到三 Agent 各自 payload。

    三个 Agent 都 import 同一个 ``agents.llm.router.build_router_from_config``，
    因此只需 patch 一次；router 根据请求内容区分 Vision / Environment / Design。
    """

    async def _route(request):
        # LLMRequest.messages 为 (system, user) 元组，末位即 user 消息。
        # 注意：Design 的 prompt 里也出现「环境事实（Environment Agent）」，
        # 因此必须用更具体的子串（含「JSON」）区分，避免误匹配。
        user_msg = request.messages[-1]
        content = getattr(user_msg, "content", str(user_msg))
        if "环境事实 JSON" in content:
            payload = _ENV_PAYLOAD
        elif "设计候选 JSON" in content:
            payload = _DESIGN_PAYLOAD
        else:
            payload = _VISION_PAYLOAD
        response = SimpleNamespace(content=json.dumps(payload), model="qwen-test")
        return response, [
            SimpleNamespace(
                provider_name="track_a",
                track="track_a",
                response=response,
                error=None,
                latency_ms=1,
                pending_verification=False,
            )
        ]

    return SimpleNamespace(route=_route, aclose=lambda: asyncio.sleep(0))


def _patch_llm_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """llm.enabled=True 且 router 按 prompt 分发三 Agent 的确定性响应。"""

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
        lambda _cfg, **_kw: _make_dispatcher_router(),
    )


def _patch_llm_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """llm.enabled=False → 三 Agent 全部走占位降级路径（不构建 router）。"""

    monkeypatch.setattr(
        "agents.config_loader.load_llm_config",
        lambda: {"enabled": False, "track_a": {}, "track_b": {}},
    )


# --------------------------------------------------------------------------- #
# 集成测试                                                                       #
# --------------------------------------------------------------------------- #


def test_integration_phase1_full_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实调用三 Agent（LLM 成功路径）→ 组装 dossier → 生成合法 PDF。

    验证数据契约：报告模块消费的字段（scene_type / climate_zone / candidates 等）
    在真实 Agent 输出中均存在，且端到端 PDF 生成不崩溃。
    """

    _patch_llm_enabled(monkeypatch)

    vision_agent = VisionAgent()
    env_agent = EnvironmentAgent()
    design_agent = DesignAgent()

    vision_res = asyncio.run(
        vision_agent.invoke(
            AgentContext(
                request_id="int-vision",
                input_data={
                    "image_id": "img-001",
                    "image_b64": "ZHVtbXliYXNlNjQ=",
                    "mime_type": "image/jpeg",
                },
            )
        )
    )
    env_res = asyncio.run(
        env_agent.invoke(
            AgentContext(
                request_id="int-env",
                input_data={"address": "广东省汕头市", "region_hint": "华南/汕头"},
            )
        )
    )
    design_res = asyncio.run(
        design_agent.invoke(
            AgentContext(
                request_id="int-design",
                input_data={
                    "vision_result": dict(vision_res.data),
                    "environment_result": dict(env_res.data),
                    "consultation": {"budget_tier": "标准", "style_preference": "现代简约"},
                    "address": "广东省汕头市",
                    "region_hint": "华南/汕头",
                },
            )
        )
    )

    # 三 Agent 在 LLM 成功路径下均为 success、且非占位。
    assert vision_res.success is True
    assert env_res.success is True
    assert design_res.success is True
    # 2.2.2 语义修正（ADR-2.2.1 §7 对齐）：Design 候选属 LLM 推理（Level 0
    # inferred），即使 LLM 成功也永远 pending_verification=True；实测/签字字段
    # 才会回落。此处无签字阈值 → 恒 True。
    assert design_res.data["pending_verification"] is True

    # 数据契约：报告模块读取的字段在真实输出中均存在。
    v = vision_res.data
    e = env_res.data
    d = design_res.data
    assert v["scene_type"] == "开放阳台"
    assert v["orientation_hint"] == "东南"
    assert e["climate_zone"] == "夏热冬暖地区"
    assert e["prevailing_wind"] == "东南"
    assert len(d["candidates"]) == 3
    assert d["candidates"][0]["id"] == "D1"

    # 端到端：组装 dossier 并生成 PDF。
    dossier = {
        "project": {
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "request_id": "REQ-INT-001",
        },
        "vision": dict(v),
        "environment": dict(e),
        "design": dict(d),
    }
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)


def test_integration_phase1_placeholder_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """llm 关闭 → 三 Agent 全为占位 envelope → 报告仍生成合法 PDF（降级不崩溃）。"""

    _patch_llm_disabled(monkeypatch)

    vision_agent = VisionAgent()
    env_agent = EnvironmentAgent()
    design_agent = DesignAgent()

    vision_res = asyncio.run(
        vision_agent.invoke(
            AgentContext(
                request_id="int-vision-ph",
                input_data={
                    "image_id": "img-002",
                    "image_b64": "ZHVtbXk=",
                    "mime_type": "image/jpeg",
                },
            )
        )
    )
    env_res = asyncio.run(
        env_agent.invoke(
            AgentContext(
                request_id="int-env-ph",
                input_data={"address": "广东省汕头市"},
            )
        )
    )
    design_res = asyncio.run(
        design_agent.invoke(
            AgentContext(
                request_id="int-design-ph",
                input_data={"consultation": {"budget_tier": "标准"}},
            )
        )
    )

    # 占位路径：均为 pending_verification=True，不杜撰。
    assert vision_res.data["pending_verification"] is True
    assert env_res.data["pending_verification"] is True
    assert design_res.data["pending_verification"] is True
    assert design_res.data["candidates"] == []

    dossier = {
        "project": {"address": "广东省汕头市", "request_id": "REQ-INT-002"},
        "vision": dict(vision_res.data),
        "environment": dict(env_res.data),
        "design": dict(design_res.data),
    }
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)


def test_integration_phase1_report_rejects_no_crash_on_partial_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实 Design（3 候选）+ 其他段为 None → 报告仍合法，验证健壮组装。"""

    _patch_llm_enabled(monkeypatch)

    design_agent = DesignAgent()
    # 仅提供 consultation，让 Design 走 LLM 成功路径产出 3 候选。
    design_res = asyncio.run(
        design_agent.invoke(
            AgentContext(
                request_id="int-design-partial",
                input_data={"consultation": {"budget_tier": "高端"}},
            )
        )
    )
    assert len(design_res.data["candidates"]) == 3

    # environment / vision 故意置 None，仅 design 有真实数据。
    dossier = {
        "project": {"address": "广东省汕头市", "request_id": "REQ-INT-003"},
        "vision": None,
        "environment": None,
        "design": dict(design_res.data),
    }
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)
