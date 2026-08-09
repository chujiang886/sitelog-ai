"""玻璃安全计算规则层（Sprint E 任务2）。

职责：保存玻璃安全计算的**公式结构**（符号级）、**变量关系**、**数据来源映射**；
不保存任何真实工程常数（玻璃厚度 / 安全系数 / 允许应力数值 / 规范条款号）。

红线（Sprint E）：本模块零真实参数、零规范条款号；所有取值 pending_verification。
设计阶段：Sprint D 玻璃安全设计文档已确立符号级公式，本文件仅落地其结构描述。
"""

from __future__ import annotations

from typing import Any, Mapping

# 主公式体系（符号级，无数值；系数选取规则 pending_verification）。
# sigma_g：玻璃弯曲应力；sigma_allow：玻璃允许应力（含安全系数 K）；
# w_k：风荷载标准值（来自 wind_pressure）；t：玻璃厚度；A：分格面积；
# a/b：短边/长边；support：支承条件；K：安全系数；A_max：最大许用面积。
GLASS_SAFETY_FORMULAS: tuple[str, ...] = (
    "sigma_g = w_k * f(A, t, support)",
    "sigma_allow = g(glass_type, K)",
    "safety_check: sigma_g <= sigma_allow and A <= A_max",
    "K = sigma_allow / sigma_g",
    "A_max = h(w_k, t, support, sigma_allow)",
)

# 变量定义：仅结构描述（含义 / 单位 / 来源 / 依赖），不携带真实取值。
# 每个变量 source 指向 Design 阈值 D-TH-02 或上游 wind_pressure；数值 pending_verification。
GLASS_VARIABLES: tuple[dict[str, Any], ...] = (
    {
        "symbol": "w_k",
        "name": "风荷载标准值",
        "unit": "Pa",
        "source": "wind_pressure 上游产出（内部依赖 E-TH-01~03，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "t",
        "name": "玻璃厚度",
        "unit": "mm",
        "source": "D-TH-02（工程阈值库，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "A",
        "name": "玻璃分格面积",
        "unit": "m^2",
        "source": "project geometry / design_candidate.dimensions_hint（inferred，pending_verification）",
        "depends_on": ("a", "b"),
    },
    {
        "symbol": "a",
        "name": "玻璃短边长度",
        "unit": "m",
        "source": "project geometry（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "b",
        "name": "玻璃长边长度",
        "unit": "m",
        "source": "project geometry（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "support",
        "name": "玻璃支承条件（四边支承/对边支承）",
        "unit": "category",
        "source": "project geometry（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "sigma_g",
        "name": "玻璃弯曲应力（目标量）",
        "unit": "Pa",
        "source": "derived from w_k * A * t * support（pending_verification）",
        "depends_on": ("w_k", "A", "t", "support"),
    },
    {
        "symbol": "sigma_allow",
        "name": "玻璃允许应力（含安全系数）",
        "unit": "Pa",
        "source": "D-TH-02（含 K，pending_verification）",
        "depends_on": ("glass_type", "K"),
    },
    {
        "symbol": "K",
        "name": "安全系数 / 安全裕度",
        "unit": "dimensionless",
        "source": "D-TH-02（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "A_max",
        "name": "最大许用面积",
        "unit": "m^2",
        "source": "derived from w_k * t * support * sigma_allow（pending_verification）",
        "depends_on": ("w_k", "t", "support", "sigma_allow"),
    },
)

# 变量 → 绑定工程阈值 ID（供 calculator 引用；数值 pending_verification）。
# 注意：w_k 来自上游 wind_pressure，本模块不直接绑定工程阈值；t / sigma_allow /
# K 三者均来自 D-TH-02（玻璃配置）。
VARIABLE_THRESHOLD_MAP: Mapping[str, str] = {
    "t": "D-TH-02",
    "sigma_allow": "D-TH-02",
    "K": "D-TH-02",
}


def describe_formulas() -> tuple[str, ...]:
    """返回主公式体系字符串（符号级，无数值）。"""

    return GLASS_SAFETY_FORMULAS


def variable_relations() -> tuple[dict[str, Any], ...]:
    """返回变量关系结构（因果依赖描述，无数值）。"""

    return GLASS_VARIABLES


def threshold_for_variable(symbol: str) -> str | None:
    """返回某变量绑定的工程阈值 ID（无绑定返回 None）。"""

    return VARIABLE_THRESHOLD_MAP.get(symbol)


__all__ = [
    "GLASS_SAFETY_FORMULAS",
    "GLASS_VARIABLES",
    "VARIABLE_THRESHOLD_MAP",
    "describe_formulas",
    "variable_relations",
    "threshold_for_variable",
]
