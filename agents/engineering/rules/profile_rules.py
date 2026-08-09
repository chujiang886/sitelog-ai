"""型材（Profile）计算规则层（Sprint G 任务2）。

职责：保存型材计算的**公式结构**（符号级）、**变量关系**、**数据来源映射**；
不保存任何真实工程常数（壁厚 / 截面惯性矩 / 截面模量 / 强度设计值 / 弹性模量 / 挠度限值 / 规范条款号）。

红线（Sprint G）：本模块零真实参数、零规范条款号；所有取值 pending_verification。
设计阶段：Sprint F 型材设计文档已确立符号级公式，本文件仅落地其结构描述。
"""

from __future__ import annotations

from typing import Any, Mapping

# 主公式体系（符号级，无数值；系数选取规则 pending_verification）。
# q：杆件线荷载（由 w_k 与分格几何导出）；M / N：弯矩 / 轴力（内力）；
# sigma：型材弯曲/组合应力；f：强度设计值（D-TH-01）；delta：挠度；
# delta_lim：挠度限值；E：弹性模量；I：截面惯性矩；W：截面模量；A：截面积。
PROFILE_FORMULAS: tuple[str, ...] = (
    "q = p(w_k, geometry)",
    "M, N = r(q, L, support)",
    "sigma = M / W + N / A",
    "strength_check: sigma <= f",
    "delta = s(q, L, E, I, support)",
    "deflection_check: delta <= delta_lim",
)

# 变量定义：仅结构描述（含义 / 单位 / 来源 / 依赖），不携带真实取值。
# 每个变量 source 指向 Design 阈值 D-TH-01 或上游 wind_pressure 或项目几何；
# 数值 pending_verification。
PROFILE_VARIABLES: tuple[dict[str, Any], ...] = (
    {
        "symbol": "w_k",
        "name": "风荷载标准值",
        "unit": "Pa",
        "source": "wind_pressure 上游产出（内部依赖 E-TH-01~03，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "series",
        "name": "型材系列",
        "unit": "identifier",
        "source": "D-TH-01（工程阈值库，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "t",
        "name": "壁厚",
        "unit": "mm",
        "source": "D-TH-01（型材配置，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "I",
        "name": "截面惯性矩",
        "unit": "mm^4",
        "source": "D-TH-01（截面属性，pending_verification）",
        "depends_on": ("series",),
    },
    {
        "symbol": "W",
        "name": "截面模量",
        "unit": "mm^3",
        "source": "D-TH-01（截面属性，pending_verification）",
        "depends_on": ("series", "I"),
    },
    {
        "symbol": "A",
        "name": "截面积",
        "unit": "mm^2",
        "source": "D-TH-01（截面积，pending_verification）",
        "depends_on": ("series",),
    },
    {
        "symbol": "f",
        "name": "强度设计值",
        "unit": "MPa",
        "source": "D-TH-01（pending_verification）",
        "depends_on": ("series",),
    },
    {
        "symbol": "E",
        "name": "弹性模量",
        "unit": "MPa",
        "source": "D-TH-01（pending_verification）",
        "depends_on": ("series",),
    },
    {
        "symbol": "L",
        "name": "杆件跨度 / 受力长度",
        "unit": "m",
        "source": "project geometry / design_candidate.dimensions_hint（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "support",
        "name": "杆件支承条件（简支/连续/悬臂）",
        "unit": "category",
        "source": "project geometry（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "q",
        "name": "杆件线荷载",
        "unit": "N/mm",
        "source": "derived from w_k * geometry（pending_verification）",
        "depends_on": ("w_k", "L"),
    },
    {
        "symbol": "M",
        "name": "杆件弯矩（目标内力）",
        "unit": "N·mm",
        "source": "derived from q * L * support（pending_verification）",
        "depends_on": ("q", "L", "support"),
    },
    {
        "symbol": "N",
        "name": "杆件轴力（目标内力）",
        "unit": "N",
        "source": "derived from q * L * support（pending_verification）",
        "depends_on": ("q", "L", "support"),
    },
    {
        "symbol": "sigma",
        "name": "型材弯曲/组合应力（目标量）",
        "unit": "MPa",
        "source": "derived from M / W + N / A（pending_verification）",
        "depends_on": ("M", "N", "W", "A"),
    },
    {
        "symbol": "delta",
        "name": "挠度（目标量）",
        "unit": "mm",
        "source": "derived from q * L * E * I * support（pending_verification）",
        "depends_on": ("q", "L", "E", "I", "support"),
    },
    {
        "symbol": "delta_lim",
        "name": "挠度限值",
        "unit": "mm",
        "source": "project requirement / norm（pending_verification）",
        "depends_on": (),
    },
)

# 变量 → 绑定工程阈值 ID（供 calculator 引用；数值 pending_verification）。
# series / t / I / W / A / f / E 七者均来自 D-TH-01（型材配置/截面属性/强度/弹性模量）。
VARIABLE_THRESHOLD_MAP: Mapping[str, str] = {
    "series": "D-TH-01",
    "t": "D-TH-01",
    "I": "D-TH-01",
    "W": "D-TH-01",
    "A": "D-TH-01",
    "f": "D-TH-01",
    "E": "D-TH-01",
}


def describe_formulas() -> tuple[str, ...]:
    """返回主公式体系字符串（符号级，无数值）。"""

    return PROFILE_FORMULAS


def variable_relations() -> tuple[dict[str, Any], ...]:
    """返回变量关系结构（因果依赖描述，无数值）。"""

    return PROFILE_VARIABLES


def threshold_for_variable(symbol: str) -> str | None:
    """返回某变量绑定的工程阈值 ID（无绑定返回 None）。"""

    return VARIABLE_THRESHOLD_MAP.get(symbol)


__all__ = [
    "PROFILE_FORMULAS",
    "PROFILE_VARIABLES",
    "VARIABLE_THRESHOLD_MAP",
    "describe_formulas",
    "variable_relations",
    "threshold_for_variable",
]
