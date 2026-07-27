"""2.2.3 PDF 方案书增强测试：结构 / 关键章节 / pending 标识 / provenance / 防编造。

依赖 ``pypdf`` 做文本提取以断言徽标与章节锚点；若未安装则降级为「合法 PDF + 不抛」，
并在报告中标注（见 2.2.3 设计文档 §八）。
"""

from __future__ import annotations

import io

from agents.report.generator import (
    BADGE_PENDING,
    BADGE_VERIFIED,
    generate_project_report,
)

try:
    from pypdf import PdfReader

    _HAVE_PYPDF = True
except Exception:  # noqa: BLE001 - 依赖缺失时降级
    _HAVE_PYPDF = False


def _extract_pdf_text(pdf: bytes) -> str:
    """用 pypdf 提取 PDF 全文（用于断言徽标 / 章节锚点）。"""

    if not _HAVE_PYPDF:
        return ""
    reader = PdfReader(io.BytesIO(pdf))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _base_dossier() -> dict:
    """构造与三个 Agent 真实 data 字段形态一致的 mock dossier（全 pending 态）。"""

    return {
        "project": {
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "request_id": "REQ-20250721-0001",
            "consultation": {
                "budget_tier": "标准",
                "style_preference": "现代简约",
                "constraints": "临街需隔音",
            },
        },
        "vision": {
            "scene_type": "开放阳台",
            "obstructions": ["空调外机", "晾衣架"],
            "orientation_hint": "东南",
            "quality": "high",
            "recommendations": ["建议封装以提升保温性能"],
            "pending_verification": True,
            "gaps": ["vision_model: pending_verification"],
        },
        "environment": {
            "climate_zone": "夏热冬暖地区",
            "prevailing_wind": "东南",
            "solar_exposure": "西晒明显",
            "noise_level_hint": "中",
            "regional_material_preference": "断桥铝为主",
            "summary": "华南沿海高温高湿、台风频发，需重视隔热。",
            "field_provenance": {
                "climate_zone": "inferred",
                "prevailing_wind": "inferred",
                "solar_exposure": "inferred",
                "noise_level_hint": "inferred",
            },
            "data_providers": [
                {
                    "name": "geo-mock",
                    "type": "mock",
                    "real_data": False,
                    "source": "mock:geo:v1:__mock__",
                    "fetched_at": "pending_verification",
                }
            ],
            "pending_verification": True,
            "gaps": ["weather_data: pending_verification"],
        },
        "design": {
            "candidates": [
                {
                    "id": "D1",
                    "title": "断桥铝平开窗方案",
                    "opening_type": "平开窗",
                    "frame_material": "断桥铝合金",
                    "glass_type": "中空 Low-E 玻璃",
                    "dimensions_hint": "主窗 1.8m×2.1m，分 2 扇",
                    "estimated_cost_tier": "标准",
                    "pros": ["密封性好", "保温隔热佳"],
                    "cons": ["开启占用室内空间"],
                    "rationale": "结合西晒与台风区，断桥铝 + Low-E 兼顾隔热与气密。",
                    "threshold_refs": {
                        "frame_material": "D-TH-01",
                        "glass_type": "D-TH-02",
                    },
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
                    "cons": ["密封性弱于平开"],
                    "rationale": "预算敏感场景下以推拉降低综合造价。",
                    "threshold_refs": {
                        "frame_material": "D-TH-01",
                        "glass_type": "D-TH-02",
                    },
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
                    "cons": ["造价高"],
                    "rationale": "面向高预算、重景观需求。",
                    "threshold_refs": {
                        "frame_material": "D-TH-01",
                        "glass_type": "D-TH-02",
                    },
                },
            ],
            "pending_verification": True,
            "field_provenance": {
                "frame_material": "inferred",
                "glass_type": "inferred",
            },
            "threshold_refs": {
                "frame_material": "D-TH-01",
                "glass_type": "D-TH-02",
            },
            "verified": {},
            "gaps": [
                "design_threshold:D-TH-01: pending_verification",
                "design_threshold:D-TH-02: pending_verification",
            ],
        },
    }


def _assert_valid_pdf(pdf: bytes) -> None:
    assert isinstance(pdf, bytes), "应返回 bytes"
    assert pdf.startswith(b"%PDF"), "PDF 字节应以 %PDF 开头"
    assert len(pdf) > 200, "PDF 字节长度应大于 200"
    reused = io.BytesIO(pdf)
    reused.seek(0)
    assert reused.read(4) == b"%PDF"


# --------------------------------------------------------------------------- #
# 1. 三方案数量                                                                  #
# --------------------------------------------------------------------------- #


def test_exactly_three_candidates_render() -> None:
    """恰好 3 候选 → PDF 合法且文本含三原型标题。"""

    pdf = generate_project_report(_base_dossier())
    _assert_valid_pdf(pdf)
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "经济型方案" in text
        assert "舒适型方案" in text
        assert "高性能型方案" in text


def test_two_candidates_still_valid() -> None:
    """候选数 ≠ 3 时仍生成合法 PDF，不崩溃。"""

    d = _base_dossier()
    d["design"]["candidates"] = d["design"]["candidates"][:2]
    pdf = generate_project_report(d)
    _assert_valid_pdf(pdf)


# --------------------------------------------------------------------------- #
# 2. pending 语义                                                                #
# --------------------------------------------------------------------------- #


def test_design_pending_true_shows_inferred_badge() -> None:
    """design pending_verification=True → PDF 文本含 AI推理·待确认 / 待确认。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "AI推理·待确认" in text
        assert BADGE_PENDING in text


# --------------------------------------------------------------------------- #
# 3. provenance                                                                 #
# --------------------------------------------------------------------------- #


def test_environment_provenance_rendered() -> None:
    """environment field_provenance(inferred) → 徽标 + data_providers 来源名渲染。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "AI推理·待确认" in text
        assert "geo-mock" in text  # data_providers 来源名


def test_environment_measured_field_shows_verified_badge() -> None:
    """environment 某字段 measured → 该字段显示已验证来源徽标。"""

    d = _base_dossier()
    d["environment"]["field_provenance"]["climate_zone"] = "measured"
    d["environment"]["pending_verification"] = False
    pdf = generate_project_report(d)
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "已验证来源" in text


# --------------------------------------------------------------------------- #
# 4. verified 机制                                                              #
# --------------------------------------------------------------------------- #


def test_no_verified_badge_when_all_false() -> None:
    """verified 全 false（真实系统现状）→ 全文档不出现 [已验证] 绿标。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert BADGE_VERIFIED not in text


def test_verified_mechanism_wired() -> None:
    """防御性：当数据显式 verified（pending=False + provenance=verified）时，
    PDF 应渲染 [已验证] —— 验证机制连通（非 Agent 逻辑，仅渲染通路）。"""

    d = _base_dossier()
    d["design"]["pending_verification"] = False
    d["design"]["field_provenance"]["frame_material"] = "verified"
    d["design"]["verified"] = {
        "D-TH-01": {
            "verified": True,
            "verified_by": "expert:pending_verification",
            "verified_at": "pending_verification",
        }
    }
    pdf = generate_project_report(d)
    _assert_valid_pdf(pdf)
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert BADGE_VERIFIED in text


# --------------------------------------------------------------------------- #
# 5. 防编造                                                                     #
# --------------------------------------------------------------------------- #


def test_pending_threshold_items_shown() -> None:
    """gaps 中 design_threshold:* 条目出现在待验证项（防编造：不隐藏 pending）。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "D-TH-01" in text  # 待验证阈值 ID 透出


# --------------------------------------------------------------------------- #
# 6. 关键章节锚点                                                              #
# --------------------------------------------------------------------------- #


def test_key_sections_present() -> None:
    """PDF 文本含全部关键章节锚点。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        for anchor in (
            "环境分析",
            "数据可信等级说明",
            "设计方案对比",
            "免责与待确认声明",
        ):
            assert anchor in text, f"缺少章节锚点: {anchor}"


__all__: list[str] = []
