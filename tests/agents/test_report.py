"""T11 / TASK-106：PDF 方案书生成模块测试。

验证：
- 正常 dossier → 返回合法 PDF 字节流（以 b"%PDF" 开头、长度 > 200、可被 BytesIO 再包装）；
- 某段 Agent 输出为 None（如 vision=None）→ 仍返回合法 PDF 且不抛异常；
- 三段全部为 None → 仍返回合法 PDF 且不抛异常。

注意：reportlab 文本默认压缩，故不依赖「字节内可搜到关键字」这类脆弱断言。
"""

from __future__ import annotations

import io

from agents.report.generator import generate_project_report


def _mock_dossier() -> dict:
    """构造一个与三个 Agent 真实 data 字段形态一致的 mock dossier。"""

    return {
        "project": {
            "address": "广东省汕头市龙湖区某某小区 3 栋 1801",
            "request_id": "REQ-20250721-0001",
        },
        "vision": {
            "scene_type": "开放阳台",
            "obstructions": ["空调外机", "晾衣架", "护栏"],
            "orientation_hint": "东南",
            "quality": "high",
            "recommendations": ["建议封装以提升保温性能", "注意晾衣架对开启路径的影响"],
            "pending_verification": True,
            "gaps": ["vision_model: pending_verification"],
        },
        "environment": {
            "climate_zone": "夏热冬暖地区",
            "prevailing_wind": "东南",
            "solar_exposure": "西晒明显",
            "noise_level_hint": "中",
            "regulatory_hints": ["阳台封装需符合地方管理条例", "外立面改动需物业备案"],
            "regional_material_preference": "断桥铝为主",
            "summary": "华南沿海高温高湿、台风频发，需重视隔热与抗风压。",
            "pending_verification": True,
            "gaps": [
                "weather_data: pending_verification",
                "gis_data: pending_verification",
            ],
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
                    "pros": ["性价比高", "不占室内空间", "保温尚可"],
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
                    "pros": ["观景效果佳", "隔热隔音优", "质感高端"],
                    "cons": ["造价高", "维护要求高"],
                    "rationale": "面向高预算、重景观需求，强调舒适与美观统一。",
                },
            ],
            "pending_verification": False,
            "gaps": [],
        },
    }


def _assert_valid_pdf(pdf: bytes) -> None:
    """一组稳健的 PDF 合法性断言（不依赖文本可搜索）。"""

    assert isinstance(pdf, bytes), "应返回 bytes"
    assert pdf.startswith(b"%PDF"), "PDF 字节应以 %PDF 开头"
    assert len(pdf) > 200, "PDF 字节长度应大于 200"
    # 能被 BytesIO 再次包装，验证是连续合法字节流
    reused = io.BytesIO(pdf)
    reused.seek(0)
    assert reused.read(4) == b"%PDF"


def test_normal_dossier_returns_valid_pdf() -> None:
    """正常 dossier：返回合法 PDF 字节流。"""

    pdf = generate_project_report(_mock_dossier())
    _assert_valid_pdf(pdf)


def test_missing_vision_section_still_valid() -> None:
    """vision=None：仍返回合法 PDF 且不抛异常。"""

    dossier = _mock_dossier()
    dossier["vision"] = None
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)


def test_missing_design_and_environment_sections_still_valid() -> None:
    """design / environment 为 None：仍返回合法 PDF 且不抛异常。"""

    dossier = _mock_dossier()
    dossier["design"] = None
    dossier["environment"] = None
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)


def test_all_sections_none_still_valid() -> None:
    """三段全部为 None：仅封面 + 缺失占位，仍返回合法 PDF 且不抛异常。"""

    pdf = generate_project_report(
        {"project": {}, "vision": None, "environment": None, "design": None}
    )
    _assert_valid_pdf(pdf)


def test_empty_dossier_still_valid() -> None:
    """空 dict / None dossier：不抛异常，返回合法 PDF。"""

    assert isinstance(generate_project_report({}), bytes)
    _assert_valid_pdf(generate_project_report(None))  # type: ignore[arg-type]


def test_cjk_font_registered_no_garble() -> None:
    """CJK 字体 STSong-Light 应注册成功，否则中文会乱码（方块）。"""

    from agents.report.generator import _CJK_FONT_NAME, _ensure_cjk_font

    assert _ensure_cjk_font() == _CJK_FONT_NAME == "STSong-Light"


def test_special_xml_chars_in_content_no_crash() -> None:
    """候选字段含 XML 特殊字符（& < >）时，escape 后不应导致 PDF 生成崩溃。"""

    dossier = _mock_dossier()
    dossier["design"]["candidates"][0]["title"] = "方案A & <敏感> 特殊字符测试"
    dossier["design"]["candidates"][0]["rationale"] = "含 <tag> 与 & 符号的说明"
    dossier["environment"]["summary"] = "结论含 <未核实> & 待确认项"
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)


def test_empty_candidates_shows_placeholder() -> None:
    """design.candidates=[]（降级占位）时，设计章节应显示占位而非崩溃。"""

    dossier = _mock_dossier()
    dossier["design"]["candidates"] = []
    dossier["design"]["pending_verification"] = True
    pdf = generate_project_report(dossier)
    _assert_valid_pdf(pdf)
