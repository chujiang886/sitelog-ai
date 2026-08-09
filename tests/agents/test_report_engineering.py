"""Phase 3.2.2 ReportGenerator 工程章节接线测试。

验证：
1. 五模块展示（风压/玻璃/型材/五金/安装风险锚点）
2. pending badge（工程章节省略 [已验证]，含 [待确认]）
3. engineering 章节生成（五、工程智能分析 + 五子节锚点）
4. gaps 展示（upstream_pending / E-TH-0x 透出）
5. provenance 展示（wind_pressure.w_k 溯源键）
6. 无 engineering 结果时兼容（dossier 无键 / None → 合法 PDF 不抛）

红线：所有工程结果全 pending_verification，绝不渲染 [已验证] 工程结论。
"""

from __future__ import annotations

import io

from agents.engineering.calc import (
    GlassSafetyResult,
    HardwareResult,
    InstallationRiskResult,
    ProfileResult,
    WindPressureResult,
)
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


def _assert_valid_pdf(pdf: bytes) -> None:
    assert isinstance(pdf, bytes), "应返回 bytes"
    assert pdf.startswith(b"%PDF"), "PDF 字节应以 %PDF 开头"
    assert len(pdf) > 200, "PDF 字节长度应大于 200"


def _build_all_pending_engineering() -> dict[str, dict]:
    """构造五模块 as_full() 字典（全 pending 态，含溯源 / gaps）。"""

    wind = WindPressureResult()
    wind.provenance = {"wind_pressure.w_k": "pending"}
    wind.threshold_refs = ["E-TH-01"]

    glass = GlassSafetyResult()
    glass.gaps = ["profile_result: upstream_pending"]
    glass.threshold_refs = ["E-TH-02"]

    profile = ProfileResult()
    profile.threshold_refs = ["E-TH-03"]

    hardware = HardwareResult()
    hardware.threshold_refs = ["E-TH-04"]

    install = InstallationRiskResult()
    install.gaps = ["hardware_result: upstream_pending", "glass_safety_result: upstream_pending"]
    install.threshold_refs = ["E-TH-05"]

    return {
        "wind_pressure": wind.as_full(),
        "glass_safety": glass.as_full(),
        "profile": profile.as_full(),
        "hardware": hardware.as_full(),
        "installation_risk": install.as_full(),
    }


def _base_dossier() -> dict:
    """含五模块工程结果（全 pending）的最小 dossier。"""

    return {
        "project": {
            "address": "广东省汕头市龙湖区测试小区 1 栋 101",
            "request_id": "REQ-20250730-0001",
        },
        "vision": None,
        "environment": None,
        "design": None,
        "engineering": _build_all_pending_engineering(),
    }


# --------------------------------------------------------------------------- #
# 1. 五模块展示                                                                  #
# --------------------------------------------------------------------------- #


def test_five_modules_render() -> None:
    """五接口 as_full() → PDF 含五个 h2 锚点（风压/玻璃/型材/五金/安装风险）。"""

    pdf = generate_project_report(_base_dossier())
    _assert_valid_pdf(pdf)
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        for anchor in ("风压分析", "玻璃安全分析", "型材分析", "五金分析", "安装风险分析"):
            assert anchor in text, f"缺少模块锚点: {anchor}"


# --------------------------------------------------------------------------- #
# 2. pending badge                                                              #
# --------------------------------------------------------------------------- #


def test_engineering_section_no_verified_badge() -> None:
    """工程全 pending → PDF 不含 [已验证] 绿标，且含 [待确认]。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert BADGE_VERIFIED not in text, "工程章节不应出现 [已验证]"
        assert BADGE_PENDING in text, "工程章节应含 [待确认]"


# --------------------------------------------------------------------------- #
# 3. engineering 章节生成                                                        #
# --------------------------------------------------------------------------- #


def test_engineering_section_and_subsections_present() -> None:
    """PDF 含「五、工程智能分析」章节 + 五个子节锚点。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "工程智能分析" in text, "缺少工程章节锚点"
        for sub in ("工程模块状态总览", "五模块详情", "可信等级", "审核链状态", "待确认事项"):
            assert sub in text, f"缺少工程子节: {sub}"


# --------------------------------------------------------------------------- #
# 4. gaps 展示                                                                  #
# --------------------------------------------------------------------------- #


def test_gaps_rendered() -> None:
    """gaps 中 upstream_pending / E-TH-0x 透出到待确认事项。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "upstream_pending" in text, "gaps 的 upstream_pending 应透出"
        assert "E-TH-01" in text, "阈值引用 E-TH-01 应透出"


# --------------------------------------------------------------------------- #
# 5. provenance 展示                                                            #
# --------------------------------------------------------------------------- #


def test_provenance_rendered() -> None:
    """模块 provenance（wind_pressure.w_k）出现在章节。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "wind_pressure.w_k" in text, "provenance 溯源键应透出"


# --------------------------------------------------------------------------- #
# 6. 无 engineering 结果时兼容                                                   #
# --------------------------------------------------------------------------- #


def test_no_engineering_key_compatible() -> None:
    """dossier 无 engineering 键 → PDF 合法、不抛、章节显示暂无数据。"""

    d = {"project": {"address": "x", "request_id": "y"}, "vision": None, "environment": None, "design": None}
    pdf = generate_project_report(d)
    _assert_valid_pdf(pdf)
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        assert "工程智能分析" in text
        assert "暂无数据/待补充" in text


def test_engineering_none_compatible() -> None:
    """engineering 显式 None → PDF 合法、不抛。"""

    d = {
        "project": {"address": "x", "request_id": "y"},
        "vision": None,
        "environment": None,
        "design": None,
        "engineering": None,
    }
    pdf = generate_project_report(d)
    _assert_valid_pdf(pdf)


# --------------------------------------------------------------------------- #
# 7. 防回归：既有三 Agent 章节锚点仍存在                                          #
# --------------------------------------------------------------------------- #


def test_existing_sections_still_present() -> None:
    """含 engineering 的 dossier 仍渲染既有章节（一/二/三/四/六）。"""

    pdf = generate_project_report(_base_dossier())
    text = _extract_pdf_text(pdf)
    if _HAVE_PYPDF:
        for anchor in ("视觉分析", "环境分析", "数据可信等级说明", "设计方案对比", "免责与待确认声明"):
            assert anchor in text, f"既有章节锚点被破坏: {anchor}"


__all__: list[str] = []
