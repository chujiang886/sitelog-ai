"""PDF 方案书生成模块（T11 / TASK-106）。

核心导出
--------
``generate_project_report(dossier: dict) -> bytes``

``dossier`` 形态
----------------
{
    "project":    {... 可选元信息如 address / request_id},
    "vision":     <Vision AgentResult.data dict 或 None>,
    "environment":<Environment AgentResult.data dict 或 None>,
    "design":     <Design AgentResult.data dict 或 None>,
}

设计原则
--------
- 使用 reportlab Platypus（SimpleDocTemplate / Paragraph / Spacer / Table）；
- 中文字体使用 reportlab 内置 CJK 字体 ``STSong-Light``，避免乱码/方块；
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
    """把字符串列表渲染为「· 」前缀段落列表；空列表 → 占位段落。

    使用普通 Paragraph + 「· 」前缀（而非 ListFlowable 的 bullet 字符），
    可确保圆点始终由 CJK 字体渲染，避免方块/缺失字形。
    """

    cleaned: list[str] = [str(i) for i in items if i not in (None, "")]
    if not cleaned:
        return [Paragraph("暂无数据/待补充。", style)]
    return [Paragraph("· " + _escape(item), style) for item in cleaned]


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


# --------------------------------------------------------------------------- #
# 章节构建                                                                      #
# --------------------------------------------------------------------------- #


def _build_cover(project: dict[str, Any], styles: dict[str, ParagraphStyle]) -> list[Any]:
    """封面：标题 + 项目元信息（地址 / request_id）。"""

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
    meta_rows = [
        [
            Paragraph("项目地址", styles["cell_header"]),
            Paragraph(_escape(address), styles["cell"]),
        ],
        [
            Paragraph("Request ID", styles["cell_header"]),
            Paragraph(_escape(request_id), styles["cell"]),
        ],
    ]
    meta_table = Table(meta_rows, colWidths=[40 * mm, 110 * mm])
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
    """二、环境分析（来自 Environment Agent）。"""

    flow: list[Any] = [Paragraph("二、环境分析", styles["h1"])]
    if not environment:
        flow.append(
            Paragraph(
                "暂无数据/待补充（Environment Agent 未返回结果）。", styles["body"]
            )
        )
        return flow

    climate = _as_str(environment.get("climate_zone"))
    wind = _as_str(environment.get("prevailing_wind"))
    solar = _as_str(environment.get("solar_exposure"))
    noise = _as_str(environment.get("noise_level_hint"))
    material = _as_str(environment.get("regional_material_preference"))
    summary = _as_str(environment.get("summary"))
    rows = [
        [
            Paragraph("气候区", styles["cell_header"]),
            Paragraph(_escape(climate), styles["cell"]),
        ],
        [
            Paragraph("主导风向", styles["cell_header"]),
            Paragraph(_escape(wind), styles["cell"]),
        ],
        [
            Paragraph("日照/西晒", styles["cell_header"]),
            Paragraph(_escape(solar), styles["cell"]),
        ],
        [
            Paragraph("临街噪音", styles["cell_header"]),
            Paragraph(_escape(noise), styles["cell"]),
        ],
        [
            Paragraph("地域材料偏好", styles["cell_header"]),
            Paragraph(_escape(material), styles["cell"]),
        ],
        [
            Paragraph("环境结论", styles["cell_header"]),
            Paragraph(_escape(summary), styles["cell"]),
        ],
    ]
    table = Table(rows, colWidths=[35 * mm, 125 * mm])
    table.setStyle(_kv_table_style())
    flow.append(table)
    flow.append(Spacer(1, 6))
    flow.append(Paragraph("规范提示", styles["h2"]))
    flow.extend(
        _list_flowable(_as_list(environment.get("regulatory_hints")), styles["body"])
    )
    return flow


def _build_design_section(
    design: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """三、设计方案（来自 Design Agent，含 3 个候选）。"""

    flow: list[Any] = [Paragraph("三、设计方案", styles["h1"])]
    if not design:
        flow.append(
            Paragraph("暂无数据/待补充（Design Agent 未返回结果）。", styles["body"])
        )
        return flow

    candidates = _as_list(design.get("candidates"))
    if not candidates:
        flow.append(Paragraph("暂无候选方案/待补充。", styles["body"]))
        return flow

    for idx, cand in enumerate(candidates, start=1):
        c = _section_safe(cand)
        title = _as_str(c.get("title"), "待确认方案")
        flow.append(
            Paragraph(f"方案 {idx}：{_escape(title)}", styles["h2"])
        )
        rows = [
            [
                Paragraph("开启方式", styles["cell_header"]),
                Paragraph(_escape(_as_str(c.get("opening_type"))), styles["cell"]),
            ],
            [
                Paragraph("型材", styles["cell_header"]),
                Paragraph(_escape(_as_str(c.get("frame_material"))), styles["cell"]),
            ],
            [
                Paragraph("玻璃", styles["cell_header"]),
                Paragraph(_escape(_as_str(c.get("glass_type"))), styles["cell"]),
            ],
            [
                Paragraph("尺寸建议", styles["cell_header"]),
                Paragraph(_escape(_as_str(c.get("dimensions_hint"))), styles["cell"]),
            ],
            [
                Paragraph("成本档位", styles["cell_header"]),
                Paragraph(
                    _escape(_as_str(c.get("estimated_cost_tier"))), styles["cell"]
                ),
            ],
            [
                Paragraph("推荐理由", styles["cell_header"]),
                Paragraph(_escape(_as_str(c.get("rationale"))), styles["cell"]),
            ],
        ]
        table = Table(rows, colWidths=[35 * mm, 125 * mm])
        table.setStyle(_kv_table_style())
        flow.append(table)
        flow.append(Spacer(1, 4))
        flow.append(Paragraph("优势", styles["body"]))
        flow.extend(_list_flowable(_as_list(c.get("pros")), styles["body"]))
        flow.append(Paragraph("劣势/注意", styles["body"]))
        flow.extend(_list_flowable(_as_list(c.get("cons")), styles["body"]))
        flow.append(Spacer(1, 6))
    return flow


def _build_disclaimer_section(
    dossier: dict[str, Any], styles: dict[str, ParagraphStyle]
) -> list[Any]:
    """四、免责与待确认声明（醒目，标注各 Agent pending_verification 状态）。"""

    flow: list[Any] = [Paragraph("四、免责与待确认声明", styles["h1"])]
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
    story += _build_design_section(design, styles)
    story += _build_disclaimer_section(dossier, styles)

    doc.build(story)
    return buffer.getvalue()


__all__ = ["generate_project_report"]
