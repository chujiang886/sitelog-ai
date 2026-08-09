"""安装施工风险（Installation Risk）计算规则层（Sprint K 任务2）。

职责：保存安装风险计算的**公式结构**（符号级）、**变量关系**、**数据来源映射**；
不保存任何真实工程常数（风险分数 / 承载参数 / 施工安全距离 / 规范条款号）。

红线（Sprint K）：本模块零真实参数、零规范条款号；所有取值 pending_verification。
设计阶段：Sprint J 安装风险设计文档已确立符号级公式，本文件仅落地其结构描述。
"""

from __future__ import annotations

from typing import Any, Mapping

# 主公式体系（符号级，无数值；系数与评级矩阵选取规则 pending_verification）。
# Risk_total：综合安装风险评级（多因素聚合）；
# lift_condition：吊装条件校核（吊运工况匹配）；
# D_safe：施工安全距离校核（禁止真实距离）；
# env_risk：环境风险判定（含 E-TH-05 腐蚀等级）；
# personnel_risk：人员操作风险判定；
# process_risk：安装工艺风险判定。
INSTALLATION_FORMULAS: tuple[str, ...] = (
    "Risk_total = r(G_weight, H_floor, lift_condition, env_risk, weather_impact, process_risk, profile_cond, hardware_cond)",
    "lift_check: lift_condition >= lift_required(H_floor, G_weight)",
    "safety_check: D_safe >= D_required(installation_scenario, H_floor)",
    "env_check: env_risk <= env_threshold(E-TH-05)",
    "personnel_check: personnel_risk <= personnel_threshold(E-TH-06)",
    "process_check: process_risk <= process_threshold(E-TH-06)",
)

# 变量定义：仅结构描述（含义 / 单位 / 来源 / 依赖），不携带真实取值。
# 每个变量 source 指向 Design/Engineering 阈值 E-TH-05/E-TH-06 或上游
# glass_safety/profile/hardware 或项目几何；数值 pending_verification。
INSTALLATION_VARIABLES: tuple[dict[str, Any], ...] = (
    {
        "symbol": "G_weight",
        "name": "玻璃面板重量",
        "unit": "kg",
        "source": "glass_safety_result / design_candidate.glass_config（D-TH-02，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "H_floor",
        "name": "楼层高度（类别）",
        "unit": "category",
        "source": "project geometry（楼层高度数值 pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "w_k",
        "name": "风荷载标准值",
        "unit": "Pa",
        "source": "wind_pressure 上游产出（E-TH-01~03，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "profile_cond",
        "name": "型材条件（来自 Profile）",
        "unit": "category",
        "source": "profile_result（D-TH-01，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "hardware_cond",
        "name": "五金条件（来自 Hardware）",
        "unit": "category",
        "source": "hardware_result（E-TH-04，pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "lift_condition",
        "name": "吊装条件指标",
        "unit": "category",
        "source": "E-TH-06（pending_verification）",
        "depends_on": ("H_floor", "G_weight"),
    },
    {
        "symbol": "personnel_risk",
        "name": "人员操作风险",
        "unit": "category",
        "source": "E-TH-06（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "env_risk",
        "name": "环境风险（含腐蚀）",
        "unit": "category",
        "source": "E-TH-05 + E-TH-06（腐蚀等级 pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "weather_impact",
        "name": "天气影响（类别）",
        "unit": "category",
        "source": "project / environment（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "process_risk",
        "name": "安装工艺风险",
        "unit": "category",
        "source": "E-TH-06（pending_verification）",
        "depends_on": (),
    },
    {
        "symbol": "Risk_total",
        "name": "综合安装风险评级（禁止真实分数）",
        "unit": "category",
        "source": "E-TH-06（pending_verification）",
        "depends_on": (
            "G_weight",
            "H_floor",
            "lift_condition",
            "env_risk",
            "weather_impact",
            "process_risk",
            "profile_cond",
            "hardware_cond",
        ),
    },
    {
        "symbol": "D_safe",
        "name": "施工安全距离（禁止真实距离）",
        "unit": "m",
        "source": "E-TH-06（pending_verification）",
        "depends_on": ("installation_scenario", "H_floor"),
    },
)

# 变量 → 绑定工程阈值 ID（供 calculator 引用；数值 pending_verification）。
# Risk_total / lift_condition / personnel_risk / env_risk / process_risk / D_safe
# 均来自 E-TH-05/E-TH-06（安装风险矩阵 + 腐蚀等级）；env_risk 另依赖 E-TH-05。
VARIABLE_THRESHOLD_MAP: Mapping[str, str] = {
    "env_risk": "E-TH-05",
    "Risk_total": "E-TH-06",
    "lift_condition": "E-TH-06",
    "personnel_risk": "E-TH-06",
    "process_risk": "E-TH-06",
    "D_safe": "E-TH-06",
}


def describe_formulas() -> tuple[str, ...]:
    """返回主公式体系字符串（符号级，无数值）。"""

    return INSTALLATION_FORMULAS


def variable_relations() -> tuple[dict[str, Any], ...]:
    """返回变量关系结构（因果依赖描述，无数值）。"""

    return INSTALLATION_VARIABLES


def threshold_for_variable(symbol: str) -> str | None:
    """返回某变量绑定的工程阈值 ID（无绑定返回 None）。"""

    return VARIABLE_THRESHOLD_MAP.get(symbol)


__all__ = [
    "INSTALLATION_FORMULAS",
    "INSTALLATION_VARIABLES",
    "VARIABLE_THRESHOLD_MAP",
    "describe_formulas",
    "variable_relations",
    "threshold_for_variable",
]
