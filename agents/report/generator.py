"""PDF 方案书生成模块（T11 / TASK-106 + Phase 2.2 / 2.2.3 客户可交付增强）。

核心导出
--------
``generate_project_report(dossier: dict) -> bytes``

``dossier`` 形态
----------------
{
    "project":    {address, request_id, consultation?},
    "vision":     <Vision AgentResult.data dict 或 None>,
    "environment":<Environment AgentResult.data dict 或 None>,
    "design":     <Design AgentResult.data dict 或 None>,
}

设计原则（2.2.3 增强）
---------------------
- 使用 reportlab Platypus（SimpleDocTemplate / Paragraph / Spacer / Table）；
- 中文字体使用 reportlab 内置 CJK 字体 ``STSong-Light``，避免乱码/方块；
- 消费 2.2.1 的 Environment evidence（field_provenance / data_providers /
  real_data）与 2.2.2 的 Design provenance（field_provenance /
  threshold_refs / verified），在方案书中**显式展示数据可信等级**；
- 严守「不把 AI 推理包装成工程确认」：凡非 verified 字段，统一标
  ``[AI推理·待确认]`` / ``[待确认]``，绝不渲染为确定性工程结论；
- 任一 Agent 输出为 ``None`` 或字段缺失时，对应章节显示「暂无数据/待补充」，
  **绝不抛未捕获异常**；
- 所有动态文本在写入 ``Paragraph`` 前经过 XML 转义，防止特殊字符导致排版崩溃。
"""

from __future__ import annotations

import io
from typing import Any, Mapping, Sequence

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    HRFlowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


# --------------------------------------------------------------------------- #
# 常量 / 字体注册                                                              #
# --------------------------------------------------------------------------- #

_CJK_FONT_NAME: str = "STSong-Light"
_FALLBACK_FONT_NAME: str = "Helvetica"
_FONT_REGISTERED: bool = False

# 可信等级徽标文案（无色盲依赖的 emoji，用方括号 + 颜色区分）。
BADGE_VERIFIED: str = "[已验证]"
BADGE_INFERRED: str = "[AI推理·待确认]"
BADGE_PENDING: str = "[待确认]"
BADGE_MOCK: str = "[模拟数据·待确认]"

# 设计方案三原型（与 Design Agent SCHEME_ARCHETYPES 对齐）。
_COST_TIER_TO_ARCHETYPE: Mapping[str, str] = {
    "经济": "经济型方案",
    "经济型": "经济型方案",
    "标准": "舒适型方案",
    "舒适": "舒适型方案",
    "舒适型": "舒适型方案",
    "高端": "高性能型方案",
    "高性能": "高性能型方案",
    "性能型": "高性能型方案",
}


def _ensure_cjk_font() -> str:
    """注册并返回可用的 CJK 字体名；失败则回退到默认字体（不阻断生成）。"""

    global _FONT_REGISTERED
    if _FONT_REGISTERED:
        return _CJK_FONT_NAME
    try:
        pdfmetrics.registerFont(UnicodeCIDFont(_CJK_FONT_NAME))
        _FONT_REGISTERED = True
        return _CJK_FONT_NAME
    except Exception:  # noqa: BLE001 - 字体不可用时不阻断 PDF 生成
        return _FALLBACK_FONT_NAME


# --------------------------------------------------------------------------- #
# 样式构造                                                                      #
# --------------------------------------------------------------------------- #


def _build_styles(font_name: str) -> dict[str, ParagraphStyle]:
    """构建方案书所需的全部 ParagraphStyle（均使用 CJK 字体）。"""

    base = getSampleStyleSheet()
    styles: dict[str, ParagraphStyle] = {}

    styles["title"] = ParagraphStyle(
        "boip_title",
        parent=base["Title"],
        fontName=font_name,
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#1F3864"),
        spaceAfter=6,
    )
    styles["subtitle"] = ParagraphStyle(
        "boip_subtitle",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=11,
        leading=16,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=4,
    )
    styles["h1"] = ParagraphStyle(
        "boip_h1",
        parent=base["Heading1"],
        fontName=font_name,
        fontSize=15,
        leading=20,
        textColor=colors.HexColor("#1F3864"),
        spaceBefore=12,
        spaceAfter=6,
    )
    styles["h2"] = ParagraphStyle(
        "boip_h2",
        parent=base["Heading2"],
        fontName=font_name,
        fontSize=12,
        leading=16,
        textColor=colors.HexColor("#2E5496"),
        spaceBefore=8,
        spaceAfter=4,
    )
    styles["body"] = ParagraphStyle(
        "boip_body",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=15,
        alignment=TA_LEFT,
        spaceAfter=3,
    )
    styles["small"] = ParagraphStyle(
        "boip_small",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#666666"),
    )
    styles["warn"] = ParagraphStyle(
        "boip_warn",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=10,
        leading=15,
        textColor=colors.HexColor("#B00020"),
        spaceAfter=3,
    )
    styles["badge_verified"] = ParagraphStyle(
        "boip_badge_verified",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#1B7F3B"),
        spaceAfter=2,
    )
    styles["badge_inferred"] = ParagraphStyle(
        "boip_badge_inferred",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#B58900"),
        spaceAfter=2,
    )
    styles["badge_pending"] = ParagraphStyle(
        "boip_badge_pending",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#B00020"),
        spaceAfter=2,
    )
    styles["cell"] = ParagraphStyle(
        "boip_cell",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
    )
    styles["cell_header"] = ParagraphStyle(
        "boip_cell_header",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=colors.white,
    )
    styles["cell_badge"] = ParagraphStyle(
        "boip_cell_badge",
        parent=base["Normal"],
        fontName=font_name,
        fontSize=8.5,
        leading=12,
        textColor=colors.white,
    )
    return styles


# --------------------------------------------------------------------------- #
# 安全取值 helper                                                               #
# --------------------------------------------------------------------------- #


def _escape(text: str) -> str:
    """转义 reportlab Paragraph 的 XML 特殊字符，避免排版崩溃。"""

    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _as_str(value: Any, default: str = "未提供") -> str:
    """把任意值安全地转成展示字符串。"""

    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() if value.strip() else default
    if isinstance(value, (list, tuple)):
        if not value:
            return default
        return "、".join(
            _as_str(item, "") for item in value if item not in (None, "")
        )
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value)


def _as_list(value: Any) -> list[Any]:
    """把任意值安全地转成列表（None / 非列表 → 空列表）。"""

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return list(value)
    return [value]


def _section_safe(data: Any) -> dict[str, Any]:
    """把 Agent 输出统一为普通 dict；None / 非 Mapping → 空 dict。"""

    if data is None:
        return {}
    if isinstance(data, Mapping):
        return dict(data)
    return {}


def _list_flowable(items: Sequence[Any], style: ParagraphStyle) -> list[Any]:
    """把字符串列表渲染为「· 」前缀段落列表；空列表 → 占位段落。"""

    cleaned: list[str] = [str(i) for i in items if i not in (None, "")]
    if not cleaned:
        return [Paragraph("暂无数据/待补充。", style)]
    return [Paragraph("· " + _escape(item), style) for item in cleaned]


def _badge_for(provenance_level: str | None) -> tuple[str, str]:
    """把单字段 provenance 等级映射为（徽标文案, 样式键）。

    等级语义（ADR-2.2.1 §7 + 2.2.3）：
    - measured / verified → 已验证
    - inferred / mock      → 推理/模拟，待确认
    - unavailable / 其他   → 待确认
    """

    level = (provenance_level or "").lower()
    if level in ("measured", "verified"):
        return BADGE_VERIFIED, "badge_verified"
    if level == "mock":
        return BADGE_MOCK, "badge_inferred"
    if level == "inferred":
        return BADGE_INFERRED, "badge_inferred"
    return BADGE_PENDING, "badge_pending"


def _kv_table_style() -> TableStyle:
    """章节内「键值」表格的统一样式：左侧蓝底白字表头列。"""

    return TableStyle(
        [
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#2E5496")),
            ("TEXTCOLOR", (0, 0), (0, -1), colors.white),
            ("FONTNAME", (0, 0), (-1, -1), _CJK_FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#BBBBBB")),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _badge_table_style() -> TableStyle:
    """含可信徽标的表格样式（右侧徽标列蓝底）。"""

    style = _kv_table_style()
    style.add("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#2E5496"))
    style.add("TEXTCOLOR", (2, 0), (2, -1), colors.white)
    return style


# --------------------------------------------------------------------------- #
# 章节构建                                                                      #
# --------------------------------------------------------------------------- #


def _build_cover(project: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """封面：标题 + 项目基础信息（地址 / request_id / 咨询需求）。"""

    flow: list[Any] = []
    flow.append(Spacer(1, 55))
    flow.append(Paragraph("建筑开口智能设计方案书", styles["title"]))
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("BOIP · 建筑开口智能设计平台", styles["subtitle"]))
    flow.append(Spacer(1, 28))
    flow.append(
        HRFlowable(width="60%", thickness=1, color=colors.HexColor("#1F3864"))
    )
    flow.append(Spacer(1, 16))

    address = _as_str(project.get("address"), "未提供")
    request_id = _as_str(project.get("request_id"), "未提供")
    consultation = _section_safe(project.get("consultation")) if isinstance(
        project.get("consultation"), Mapping
    ) else {}
    budget = _as_str(consultation.get("budget_tier"), "未提供")
    style_pref = _as_str(consultation.get("style_preference"), "未提供")
    constraints = _as_str(consultation.get("constraints"), "未提供")

    meta_rows = [
        [
            Paragraph("项目地址", styles["cell_header"]),
            Paragraph(_escape(address), styles["cell"]),
        ],
        [
            Paragraph("Request ID", styles["cell_header"]),
            Paragraph(_escape(request_id), styles["cell"]),
        ],
        [
            Paragraph("预算档位", styles["cell_header"]),
            Paragraph(_escape(budget), styles["cell"]),
        ],
        [
            Paragraph("风格偏好", styles["cell_header"]),
            Paragraph(_escape(style_pref), styles["cell"]),
        ],
        [
            Paragraph("约束条件", styles["cell_header"]),
            Paragraph(_escape(constraints), styles["cell"]),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[35 * mm, 115 * mm])
    meta_table.setStyle(_kv_table_style())
    flow.append(meta_table)
    flow.append(Spacer(1, 40))
    flow.append(
        Paragraph(
            "本报告由 AI 多 Agent 运行时生成，仅供初步设计参考，须经专业工程师复核。",
            styles["small"],
        )
    )
    flow.append(PageBreak())
    return flow


def _build_vision_section(
    vision: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """一、视觉分析（来自 Vision Agent）。"""

    flow: list[Any] = [Paragraph("一、视觉分析", styles["h1"])]
    if not vision:
        flow.append(
            Paragraph("暂无数据/待补充（Vision Agent 未返回结果）。", styles["body"])
        )
        return flow

    pending = bool(vision.get("pending_verification", True))
    badge_text, badge_style = (
        (BADGE_PENDING, "badge_pending") if pending else (BADGE_VERIFIED, "badge_verified")
    )
    flow.append(Paragraph(f"整体可信状态：{badge_text}", styles[badge_style]))

    scene = _as_str(vision.get("scene_type"))
    orientation = _as_str(vision.get("orientation_hint"))
    quality = _as_str(vision.get("quality"))
    rows = [
        [
            Paragraph("场景类型", styles["cell_header"]),
            Paragraph(_escape(scene), styles["cell"]),
        ],
        [
            Paragraph("朝向线索", styles["cell_header"]),
            Paragraph(_escape(orientation), styles["cell"]),
        ],
        [
            Paragraph("清晰度", styles["cell_header"]),
            Paragraph(_escape(quality), styles["cell"]),
        ],
    ]
    table = Table(rows, colWidths=[35 * mm, 125 * mm])
    table.setStyle(_kv_table_style())
    flow.append(table)
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("障碍物", styles["h2"]))
    flow.extend(_list_flowable(_as_list(vision.get("obstructions")), styles["body"]))
    flow.append(Paragraph("视觉建议", styles["h2"]))
    flow.extend(_list_flowable(_as_list(vision.get("recommendations")), styles["body"]))
    return flow


def _build_environment_section(
    environment: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """二、环境分析（来自 Environment Agent，含可信等级列 + 数据来源溯源）。"""

    flow: list[Any] = [Paragraph("二、环境分析", styles["h1"])]
    if not environment:
        flow.append(
            Paragraph(
                "暂无数据/待补充（Environment Agent 未返回结果）。", styles["body"]
            )
        )
        return flow

    pending = bool(environment.get("pending_verification", True))
    badge_text, badge_style = (
        (BADGE_PENDING, "badge_pending") if pending else (BADGE_VERIFIED, "badge_verified")
    )
    flow.append(Paragraph(f"整体可信状态：{badge_text}", styles[badge_style]))

    provenance: Mapping[str, Any] = environment.get("field_provenance", {}) or {}

    def _row(label: str, value: Any, level: str | None) -> list[Any]:
        b_text, b_style = _badge_for(level)
        return [
            Paragraph(label, styles["cell_header"]),
            Paragraph(_escape(_as_str(value)), styles["cell"]),
            Paragraph(b_text, styles["cell_badge"]),
        ]

    rows = [
        _row("气候区", environment.get("climate_zone"), provenance.get("climate_zone")),
        _row("主导风向", environment.get("prevailing_wind"), provenance.get("prevailing_wind")),
        _row("日照/西晒", environment.get("solar_exposure"), provenance.get("solar_exposure")),
        _row("临街噪音", environment.get("noise_level_hint"), provenance.get("noise_level_hint")),
        _row("地域材料偏好", environment.get("regional_material_preference"), None),
        _row("环境结论", environment.get("summary"), None),
    ]
    table = Table(rows, colWidths=[32 * mm, 98 * mm, 28 * mm])
    table.setStyle(_badge_table_style())
    flow.append(table)
    flow.append(Spacer(1, 6))

    # 环境数据溯源（2.2.1 evidence）：逐 provider 列出来源 / 是否实测 / 获取时间。
    providers = _as_list(environment.get("data_providers"))
    if providers:
        flow.append(Paragraph("环境数据溯源", styles["h2"]))
        prov_rows: list[list[Any]] = [
            [
                Paragraph("来源", styles["cell_header"]),
                Paragraph("类型", styles["cell_header"]),
                Paragraph("是否实测", styles["cell_header"]),
                Paragraph("获取时间", styles["cell_header"]),
            ]
        ]
        for p in providers:
            p = _section_safe(p)
            real = bool(p.get("real_data", False))
            prov_rows.append(
                [
                    Paragraph(_escape(_as_str(p.get("name"))), styles["cell"]),
                    Paragraph(_escape(_as_str(p.get("type", "unknown"))), styles["cell"]),
                    Paragraph("是" if real else "否", styles["cell"]),
                    Paragraph(_escape(_as_str(p.get("fetched_at"))), styles["cell"]),
                ]
            )
        prov_table = Table(prov_rows, colWidths=[45 * mm, 35 * mm, 30 * mm, 48 * mm])
        prov_table.setStyle(_kv_table_style())
        flow.append(prov_table)
        flow.append(Spacer(1, 4))
        flow.append(
            Paragraph(
                "说明：未配置真实数据源时（默认 disabled / mock），以上均非实测，"
                "结论须人工核实。",
                styles["small"],
            )
        )

    flow.append(Paragraph("规范提示", styles["h2"]))
    flow.extend(
        _list_flowable(_as_list(environment.get("regulatory_hints")), styles["body"])
    )
    return flow


def _build_credibility_section(
    dossier: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """三、数据可信等级说明（Level 0~3 模型 + 本方案书如何读 badge）。

    严格区分「AI 推理」与「工程确认」，落实 2.2.3 红线。
    """

    flow: list[Any] = [Paragraph("三、数据可信等级说明", styles["h1"])]
    flow.append(
        Paragraph(
            "本方案书所有结论均标注可信等级，便于客户与工程师识别「AI 推理」与"
            "「工程确认」的区别：",
            styles["body"],
        )
    )
    model_rows = [
        [
            Paragraph("等级", styles["cell_header"]),
            Paragraph("含义", styles["cell_header"]),
            Paragraph("本方案书中的标注", styles["cell_header"]),
        ],
        [
            Paragraph("Level 0", styles["cell"]),
            Paragraph("AI 推理（LLM inferred），未经实测或专家确认", styles["cell"]),
            Paragraph(BADGE_INFERRED, styles["cell_badge"]),
        ],
        [
            Paragraph("Level 1", styles["cell"]),
            Paragraph("实测数据（measured source，real_data=true）", styles["cell"]),
            Paragraph("已验证来源（仍需工程师复核）", styles["cell"]),
        ],
        [
            Paragraph("Level 2", styles["cell"]),
            Paragraph("专家审核确认（expert verified）", styles["cell"]),
            Paragraph("待专家签字（当前系统未启用）", styles["cell"]),
        ],
        [
            Paragraph("Level 3", styles["cell"]),
            Paragraph("工程批准（engineering approved）", styles["cell"]),
            Paragraph("待工程批准（当前系统未启用）", styles["cell"]),
        ],
    ]
    model_table = Table(model_rows, colWidths=[20 * mm, 95 * mm, 43 * mm])
    model_table.setStyle(_badge_table_style())
    flow.append(model_table)
    flow.append(Spacer(1, 6))
    flow.append(
        Paragraph(
            "当前阶段（2.2.3）：环境实测源默认未接入（disabled / mock），设计阈值"
            "尚未经专家签字（verified=false），故全方案书以 Level 0 为主，相关结论"
            "均标注为待确认，不构成施工依据。",
            styles["small"],
        )
    )
    return flow


def _build_design_section(
    design: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """四、设计方案对比（经济型 / 舒适型 / 高性能型三原型，含依据/优势/限制/待验证项）。"""

    flow: list[Any] = [Paragraph("四、设计方案对比", styles["h1"])]
    if not design:
        flow.append(
            Paragraph("暂无数据/待补充（Design Agent 未返回结果）。", styles["body"])
        )
        return flow

    pending = bool(design.get("pending_verification", True))
    badge_text, badge_style = (
        (BADGE_PENDING, "badge_pending") if pending else (BADGE_VERIFIED, "badge_verified")
    )
    flow.append(Paragraph(f"整体可信状态：{badge_text}", styles[badge_style]))

    candidates = _as_list(design.get("candidates"))
    if not candidates:
        flow.append(Paragraph("暂无候选方案/待补充。", styles["body"]))
        return flow

    verified: Mapping[str, Any] = design.get("verified", {}) or {}
    threshold_refs: Mapping[str, Any] = design.get("threshold_refs", {}) or {}

    for cand in candidates:
        c = _section_safe(cand)
        cost_tier = _as_str(c.get("estimated_cost_tier"), "标准")
        archetype = _COST_TIER_TO_ARCHETYPE.get(cost_tier, "舒适型方案")
        title = _as_str(c.get("title"), "待确认方案")
        flow.append(
            Paragraph(f"{archetype}：{_escape(title)}", styles["h2"])
        )

        # 依据说明 / 优势 / 限制 / 待验证项
        flow.append(Paragraph("依据说明", styles["body"]))
        flow.extend(_list_flowable([c.get("rationale")], styles["body"]))
        flow.append(Paragraph("优势", styles["body"]))
        flow.extend(_list_flowable(_as_list(c.get("pros")), styles["body"]))
        flow.append(Paragraph("限制", styles["body"]))
        flow.extend(_list_flowable(_as_list(c.get("cons")), styles["body"]))

        # 待验证项：未签字阈值 + gaps 中 design_threshold 条目
        pending_items: list[str] = []
        cand_thr = _section_safe(c.get("threshold_refs")) or {}
        for field, thr_id in {**dict(threshold_refs), **dict(cand_thr)}.items():
            entry = _section_safe(verified.get(thr_id)) if isinstance(
                verified.get(thr_id), Mapping
            ) else {}
            if not entry.get("verified", False):
                pending_items.append(f"{field}（阈值 {thr_id}）：待专家签字")
        gaps = _as_list(design.get("gaps")) + _as_list(c.get("gaps"))
        for g in gaps:
            gs = str(g)
            if "design_threshold" in gs or "threshold" in gs.lower():
                pending_items.append(gs)
        flow.append(Paragraph("待验证项", styles["warn"]))
        if pending_items:
            for item in pending_items:
                flow.append(Paragraph("· " + _escape(item), styles["warn"]))
        else:
            flow.append(Paragraph("· 暂无显式待验证项（仍须工程师复核）", styles["small"]))

        # provenance 脚注
        provenance: Mapping[str, Any] = design.get("field_provenance", {}) or {}
        if provenance:
            prov_text = "；".join(
                f"{k}={v}" for k, v in provenance.items() if k not in (None, "")
            )
            flow.append(
                Paragraph(f"字段溯源：{_escape(prov_text)}", styles["small"])
            )
        flow.append(Spacer(1, 6))
    return flow


def _build_disclaimer_section(
    dossier: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """五、免责与待确认声明（醒目，标注各 Agent pending_verification 状态）。"""

    flow: list[Any] = [Paragraph("五、免责与待确认声明", styles["h1"])]
    flow.append(
        Paragraph(
            "【重要提示】本报告由 AI 多 Agent 运行时自动生成，结构安全、"
            "规范参数与材料力学结论须经注册专业工程师复核，本方案书不构成施工依据。",
            styles["warn"],
        )
    )

    any_pending = False
    labels = [
        ("vision", "视觉分析（Vision Agent）"),
        ("environment", "环境分析（Environment Agent）"),
        ("design", "设计方案（Design Agent）"),
    ]
    for key, label in labels:
        section = _section_safe(dossier.get(key))
        pending = bool(section.get("pending_verification", True)) if section else True
        if pending:
            any_pending = True
        status_text = (
            "需人工核实（pending_verification=true）"
            if pending
            else "已生成（仍需专业复核）"
        )
        flow.append(Paragraph(f"· {label}：{status_text}", styles["body"]))
        if pending and section:
            gaps = _as_list(section.get("gaps"))
            if gaps:
                gap_text = "；".join(
                    _as_str(g, "") for g in gaps if g not in (None, "")
                )
                if gap_text:
                    flow.append(
                        Paragraph(f"  待确认项：{_escape(gap_text)}", styles["small"])
                    )

    if any_pending:
        flow.append(Spacer(1, 6))
        flow.append(
            Paragraph(
                "结论：由于存在 pending_verification 的 Agent 输出，本方案书相关结论"
                "均需人工核实后方可使用。",
                styles["warn"],
            )
        )
    return flow


# --------------------------------------------------------------------------- #
# 对外主入口                                                                    #
# --------------------------------------------------------------------------- #


def generate_project_report(dossier: dict) -> bytes:
    """聚合 Vision / Environment / Design Agent 输出，生成中文方案书 PDF 字节流。

    参数
    ----
    dossier:
        ``{"project": {...}, "vision": <dict|None>, "environment": <dict|None>,
        "design": <dict|None>}``

    返回
    ----
    bytes:
        合法 PDF 字节流（以 ``b"%PDF"`` 开头），使用 ``io.BytesIO`` 收集。

    健壮性
    ------
    任一 Agent 输出为 ``None`` 或字段缺失时，对应章节显示「暂无数据/待补充」，
    不抛未捕获异常。
    """

    dossier = dossier or {}
    font_name = _ensure_cjk_font()
    styles = _build_styles(font_name)

    project = _section_safe(dossier.get("project"))
    vision = _section_safe(dossier.get("vision"))
    environment = _section_safe(dossier.get("environment"))
    design = _section_safe(dossier.get("design"))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="建筑开口智能设计方案书",
        author="BOIP Multi-Agent Runtime",
    )

    story: list[Any] = []
    story += _build_cover(project, styles)
    story += _build_vision_section(vision, styles)
    story += _build_environment_section(environment, styles)
    story += _build_credibility_section(dossier, styles)
    story += _build_design_section(design, styles)
    story += _build_disclaimer_section(dossier, styles)

    doc.build(story)
    return buffer.getvalue()


__all__ = ["BADGE_PENDING", "BADGE_VERIFIED", "generate_project_report"]
