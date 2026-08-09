"""五金（Hardware）计算规则层（Sprint I 任务2）。

职责：保存五金计算的**公式结构**（符号级）、**变量关系**、**数据来源映射**；
不保存任何真实工程常数（五金承载值 / 锁点数量 / 寿命次数 / 型号规格 / 规范条款号）。

红线（Sprint I）：本模块零真实参数、零规范条款号；所有取值 pending_verification。
设计阶段：Sprint H 五金设计文档已确立符号级公式，本文件仅落地其结构描述。
"""

from __future__ import annotations

from typing import Any, Mapping

# 主公式体系（符号级，无数值；系数选取规则 pending_verification）。
# F_demand：五金需求承载力（由风荷载 w_k 与门窗开启形式、几何派生）；
# F_hardware：五金件承载力基准（E-TH-04）；
# load_check：承载校核（需求 ≤ 基准）；
# lock_system / connection_req：锁点体系与连接可靠性（类别判定，非数量）；
# cycle_life：使用寿命次数（仅占位，不填真实循环次数）。
HARDWARE_FORMULAS: tuple[str, ...] = (
    "F_demand = h(w_k, opening_type, geometry)",
    "load_check: F_demand <= F_hardware",
    "lock_system_adequate: lock_system matches load_class",
    "connection_reliable: connection_req satisfied by profile + hardware",
    "cycle_check: cycle_life meets usage_scenario",
)

# 变量定义：仅结构描述（含义 / 单位 / 来源 / 依赖），不携带真实取值。
# 每个变量 source 指向 Design/Engineering 阈值 E-TH-04 或上游 profile/wind_pressure
# 或项目几何；数值 pending_verification。
HARDWARE_VARIABLES: tuple[dict[str, Any], ...] = (
    {
        "symbol": "w_k",
        "name": "风荷载标准值",
        "unit": "Pa",
        "source": "wind_pressure / profile 上游产出（内部依赖 E-TH-01~03，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "opening_type",
        "name": "门窗开启形式",
        "unit": "category",
        "source": "design_candidate / project（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "load_condition",
        "name": "承载条件",
        "unit": "category",
        "source": "project geometry（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "hardware_config",
        "name": "五金配置（型号标识）",
        "unit": "identifier",
        "source": "design_candidate（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "F_demand",
        "name": "五金需求承载力（目标内力）",
        "unit": "N",
        "source": "derived from w_k * opening_type * geometry（pending_verification）",
        "depends_on": ("w_k", "opening_type"),
    },
    {
        "symbol": "F_hardware",
        "name": "五金件承载力基准",
        "unit": "N",
        "source": "E-TH-04（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "load_class",
        "name": "承载等级",
        "unit": "category",
        "source": "derived from F_demand vs F_hardware（pending_verification）",
        "depends_on": ("F_demand", "F_hardware"),
    },
    {
        "symbol": "lock_system",
        "name": "锁点体系（类别判定）",
        "unit": "category",
        "source": "design_candidate + norm（pending_verification，非数量）",
        "depends_on": ("opening_type", "load_class"),
    },
    {
        "symbol": "connection_req",
        "name": "连接要求",
        "unit": "category",
        "source": "derived from opening_type, load_class（pending_verification）",
        "depends_on": ("opening_type", "load_class"),
    },
    {
        "symbol": "usage_scenario",
        "name": "使用场景",
        "unit": "category",
        "source": "project（inferred，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "cycle_life",
        "name": "使用寿命次数（占位）",
        "unit": "cycles",
        "source": "E-TH-04 / product spec（pending_verification，不填真实次数）",
        "depends_on": (),
    },
    {
        "symbol": "load_check",
        "name": "承载校核（目标判定）",
        "unit": "boolean",
        "source": "derived from F_demand <= F_hardware（pending_verification）",
        "depends_on": ("F_demand", "F_hardware"),
    },
)

# 变量 → 绑定工程阈值 ID（供 calculator 引用；数值 pending_verification）。
# F_hardware 与 cycle_life 均来自 E-TH-04（五金承载力/产品规格）。
VARIABLE_THRESHOLD_MAP: Mapping[str, str] = {
    "F_hardware": "E-TH-04",
    "cycle_life": "E-TH-04",
}


def describe_formulas() -> tuple[str, ...]:
    """返回主公式体系字符串（符号级，无数值）。"""

    return HARDWARE_FORMULAS


def variable_relations() -> tuple[dict[str, Any], ...]:
    """返回变量关系结构（因果依赖描述，无数值）。"""

    return HARDWARE_VARIABLES


def threshold_for_variable(symbol: str) -> str | None:
    """返回某变量绑定的工程阈值 ID（无绑定返回 None）。"""

    return VARIABLE_THRESHOLD_MAP.get(symbol)


__all__ = [
    "HARDWARE_FORMULAS",
    "HARDWARE_VARIABLES",
    "VARIABLE_THRESHOLD_MAP",
    "describe_formulas",
    "variable_relations",
    "threshold_for_variable",
]
