"""风压计算规则层（Sprint C 任务3）。

职责：保存风压计算的**公式结构**（符号级）、**变量关系**、**规则接口**；
不保存任何真实工程常数（系数 / 阈值数值 / 规范条款号）。

红线（Sprint C）：本模块零真实系数、零规范条款号；所有取值 pending_verification。
设计阶段：Sprint B 风压设计文档已确立符号级公式，本文件仅落地其结构描述。
"""

from __future__ import annotations

from typing import Any, Mapping

# 主公式（符号级，无数值；系数选取规则 pending_verification）。
# w_k：垂直于幕墙平面的风荷载标准值；beta：风振/阵风系数；
# mu_s：风荷载体型系数；mu_z：风压高度变化系数；w_0：基本风压标准值。
WIND_PRESSURE_FORMULA: str = "w_k = beta * mu_s * mu_z * w_0"

# 变量定义：仅结构描述（含义 / 单位 / 来源 / 依赖），不携带真实取值。
# 每个变量 source 指向工程阈值（E-TH-xx）或项目输入；数值 pending_verification。
WIND_VARIABLES: tuple[dict[str, Any], ...] = (
    {
        "symbol": "w_k",
        "name": "垂直于幕墙平面的风荷载标准值",
        "unit": "Pa",
        "source": "derived (product of factors below)",
        "depends_on": ("w_0", "mu_s", "mu_z", "beta"),
    },
    {
        "symbol": "w_0",
        "name": "基本风压标准值",
        "unit": "Pa",
        "source": "E-TH-01（工程阈值库，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "mu_s",
        "name": "风荷载体型系数（含局部体型系数 mu_sl）",
        "unit": "dimensionless",
        "source": "E-TH-02 + 项目几何（位置/朝向，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "mu_z",
        "name": "风压高度变化系数",
        "unit": "dimensionless",
        "source": "E-TH-03 + project.building_height（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "beta",
        "name": "风振系数 / 阵风系数",
        "unit": "dimensionless",
        "source": "derived from E-TH-03 + 项目几何（pending_verification）",
        "depends_on": (),
    },
)

# 变量 → 绑定工程阈值 ID（供 calculator 引用；数值 pending_verification）。
# 注意：mu_z 与 beta 共享 E-TH-03（粗糙度类别）作为取值依据。
VARIABLE_THRESHOLD_MAP: Mapping[str, str] = {
    "w_0": "E-TH-01",
    "mu_s": "E-TH-02",
    "mu_z": "E-TH-03",
    "beta": "E-TH-03",
}


def describe_formula() -> str:
    """返回主公式字符串（符号级，无数值）。"""

    return WIND_PRESSURE_FORMULA


def variable_relations() -> tuple[dict[str, Any], ...]:
    """返回变量关系结构（因果依赖描述，无数值）。"""

    return WIND_VARIABLES


def threshold_for_variable(symbol: str) -> str | None:
    """返回某变量绑定的工程阈值 ID（无绑定返回 None）。"""

    return VARIABLE_THRESHOLD_MAP.get(symbol)


__all__ = [
    "WIND_PRESSURE_FORMULA",
    "WIND_VARIABLES",
    "VARIABLE_THRESHOLD_MAP",
    "describe_formula",
    "variable_relations",
    "threshold_for_variable",
]
