"""Wind Pressure 计算单元（Sprint C 任务1 + 任务2）。

设计依据：Sprint B 风压设计文档（已审核）。本文件承载 wind_pressure 接口
的计算结构装配，并定义结果模型 ``WindPressureResult``。

红线（Sprint C，强制）：
- 本模块**不计算**任何真实风压数值；E-TH-01、E-TH-02、E-TH-03 在
  verified.json 中全为 value=null、verified=false，故 ``intermediate``
  各量为**符号占位**，目标量 w_k 不可得；
- ``engineering_enabled`` 保持 false，``verification_status`` 恒
  pending_verification；
- 不填真实系数（mu_s/mu_z/beta 全符号化），不写规范条款号，不写死工程常数；
- 所有未知一律 pending_verification。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents.engineering.calc.base import EngineeringCalculationResult
from agents.engineering.rules import wind_rules
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    load_verified_thresholds,
)
from agents.engineering.validation import PENDING_VERIFICATION


# 风压接口标识（与 INTERFACE_THRESHOLD_MAP 对齐；阈值数值 pending_verification）。
WIND_PRESSURE_INTERFACE: str = "wind_pressure"


@dataclass
class WindPressureResult(EngineeringCalculationResult):
    """wind_pressure 计算单元的统一结果模型（继承 EngineeringCalculationResult 基类）。

    九字段与 as_interface() / as_full() 由 ``EngineeringCalculationResult``
    统一提供；本类仅声明接口标识 INTERFACE。

    红线：result 在 pending 态为空串（不产出真实风压数值）；
    verification_status 恒 pending_verification。
    """

    INTERFACE = WIND_PRESSURE_INTERFACE


class WindPressureCalculator:
    """wind_pressure 风荷载标准值计算单元（Sprint C 任务1）。

    输入 ``context_data``（Mapping）应透传：
    - ``project``：项目几何 / 重要性 / 场地类别（多为 inferred）；
    - ``environment_result``：Environment Agent 输出（facts + field_provenance）；
    - ``design_candidate``：Design Agent 候选（dimensions_hint / field_provenance）；
    - ``threshold_refs``（可选）：外部传入引用，缺省从阈值库加载。

    红线：本计算器**不产出**任何真实风压数值，所有数值位保持 pending 占位；
    结论恒 pending_verification（数据饥饿 + enabled=false 闸门由 validator 叠加）。
    """

    def __init__(
        self,
        *,
        thresholds: Mapping[str, Any] | None = None,
        thresholds_path: Any | None = None,
    ) -> None:
        # thresholds=None → 运行时从 Engineering 阈值库加载（默认全 pending）。
        if thresholds is not None:
            self._thresholds: dict[str, Any] = dict(thresholds)
        else:
            self._thresholds = load_verified_thresholds(thresholds_path)

    # -- 内部：输入读取（带溯源标签） ------------------------------------ #

    @staticmethod
    def _read_provenance(
        environment_result: Mapping[str, Any] | None,
        design_candidate: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        """合并 Environment / Design 的 field_provenance（缺省 unavailable）。"""

        provenance: dict[str, str] = {}
        env: Mapping[str, Any] = (
            environment_result if isinstance(environment_result, Mapping) else {}
        )
        des: Mapping[str, Any] = (
            design_candidate if isinstance(design_candidate, Mapping) else {}
        )
        env_prov_raw: Any = env.get("field_provenance")
        env_prov: Mapping[str, Any] = (
            env_prov_raw if isinstance(env_prov_raw, Mapping) else {}
        )
        des_prov_raw: Any = des.get("field_provenance")
        des_prov: Mapping[str, Any] = (
            des_prov_raw if isinstance(des_prov_raw, Mapping) else {}
        )
        # 关键环境字段溯源（ADR-2.2.1 §7：measured / mock / inferred / unavailable）。
        for key in ("climate_zone", "prevailing_wind", "solar_exposure"):
            provenance[f"env.{key}"] = str(env_prov.get(key, "unavailable"))
        # 设计候选关键字段溯源（inferred 等，pending_verification）。
        for key in ("dimensions_hint", "frame_material", "glass_type"):
            provenance[f"design.{key}"] = str(des_prov.get(key, "unavailable"))
        return provenance

    @staticmethod
    def _read_height_provenance(project: Mapping[str, Any] | None) -> str:
        """读取项目离地高度溯源标签：有值 → inferred（Vision/用户推理），否则 unavailable。"""

        proj: Mapping[str, Any] = project if isinstance(project, Mapping) else {}
        return "inferred" if proj.get("building_height") is not None else "unavailable"

    # -- 主装配 --------------------------------------------------------- #

    def calculate(self, context_data: Mapping[str, Any]) -> WindPressureResult:
        """执行 wind_pressure 计算结构的装配（不产出真实数值）。

        返回 ``WindPressureResult``：``verification_status`` 恒
        pending_verification（阈值未双签 + engineering_enabled=false）。
        """

        ctx: Mapping[str, Any] = (
            context_data if isinstance(context_data, Mapping) else {}
        )
        project: Mapping[str, Any] | None = ctx.get("project")
        environment_result: Mapping[str, Any] | None = ctx.get("environment_result")
        design_candidate: Mapping[str, Any] | None = ctx.get("design_candidate")

        # 1) 接口所需阈值引用（E-TH-01、E-TH-02、E-TH-03）。
        threshold_ids: tuple[str, ...] = get_interface_thresholds(
            WIND_PRESSURE_INTERFACE
        )
        threshold_refs: list[str] = list(threshold_ids)

        # 2) 中间变量符号占位（全部 pending_verification，无真实取值）。
        intermediate: dict[str, Any] = {
            "w_0": {
                "value": None,
                "unit": "Pa",
                "source": "E-TH-01",
                "verified": False,
            },
            "mu_s": {
                "value": None,
                "unit": "dimensionless",
                "source": "E-TH-02",
                "verified": False,
            },
            "mu_z": {
                "value": None,
                "unit": "dimensionless",
                "source": "E-TH-03 + project.building_height",
                "verified": False,
            },
            "beta": {
                "value": None,
                "unit": "dimensionless",
                "source": "derived from E-TH-03 + project geometry",
                "verified": False,
            },
            "w_k": {
                "value": None,
                "unit": "Pa",
                "source": "product of w_0 * mu_s * mu_z * beta",
                "verified": False,
            },
        }

        # 3) 溯源标签（measured / mock / inferred / unavailable）。
        provenance: dict[str, str] = self._read_provenance(
            environment_result, design_candidate
        )
        provenance["project.building_height"] = self._read_height_provenance(project)
        provenance["project.site_category"] = "inferred"  # 来自 E-TH-03 或 inferred

        # 4) 公式来源（符号级，无数值；来自规则层 wind_rules）。
        formula: str = wind_rules.WIND_PRESSURE_FORMULA

        # 5) gaps：未双签阈值 + 非 verified/measured 的关键输入。
        gaps: list[str] = []
        for tid in threshold_ids:
            entry: Mapping[str, Any] | None = self._thresholds.get(tid)
            verified: bool = bool(entry and entry.get("verified"))
            if not verified:
                gaps.append(f"{tid}: pending_verification")
        for key, tag in provenance.items():
            if tag not in ("verified", "measured"):
                gaps.append(f"{key}: pending_verification")

        # 6) 证据（来源说明 + 公式 + 阈值引用 + pending 标注，无真实数值）。
        evidence: str = (
            f"公式来源：风荷载标准值采用乘积结构 {formula}（系数选取规则 pending_verification）。"
            "变量来源：w_0 来自工程阈值库 E-TH-01，mu_s 来自 E-TH-02，"
            "mu_z 与 beta 取决于 E-TH-03 加项目几何；上述阈值均未双签，"
            "取值 pending_verification。"
            "基本风压不取自 Environment 实时气象，仅来自工程阈值库；"
            "风压基数未双签前不得产出具体数值（红线）。"
        )

        # 7) 结论：恒 pending（数据饥饿 + enabled=false 闸门由 validator 叠加）。
        verification_status: str = PENDING_VERIFICATION

        return WindPressureResult(
            result="",  # 红线：不产出真实风压数值
            confidence=PENDING_VERIFICATION,
            evidence=evidence,
            verification_status=verification_status,
            intermediate=intermediate,
            provenance=provenance,
            threshold_refs=threshold_refs,
            gaps=gaps,
            sign_off_id=None,
        )


__all__ = [
    "WIND_PRESSURE_INTERFACE",
    "WindPressureCalculator",
    "WindPressureResult",
]
