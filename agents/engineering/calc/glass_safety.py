"""玻璃安全计算单元（Sprint E 任务1 + 任务4）。

设计依据：Sprint D 玻璃安全设计文档（已审核）。本文件承载 glass_safety 接口
的计算结构装配，并定义结果模型 ``GlassSafetyResult``。

红线（Sprint E，强制）：
- 本模块**不计算**任何真实玻璃安全数值；D-TH-02 在 verified.json 中仍为
  value=null、verified=false，故 intermediate 各量为**符号占位**，目标量
  sigma_g / sigma_allow / A_max / K 不可得；
- engineering_enabled 保持 false，verification_status 恒 pending_verification；
- 不填真实玻璃厚度（t）、安全系数（K）、允许应力（sigma_allow）；
- 不写规范条款号，不写死工程常数；
- 所有未知一律 pending_verification。

跨模块链路（任务4）：消费上游 wind_pressure 的 w_k；若 wind_pressure 的
verification_status 不等于 engineering_approved（或 w_k 不可得），glass_safety
结论强制 pending_verification 并登记 gaps: ["w_k: upstream_pending"]。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents.engineering.calc.base import EngineeringCalculationResult
from agents.engineering.rules import glass_rules
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    load_verified_thresholds,
)
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
)


# 玻璃安全接口标识（与 INTERFACE_THRESHOLD_MAP 对齐；阈值数值 pending_verification）。
GLASS_SAFETY_INTERFACE: str = "glass_safety"


@dataclass
class GlassSafetyResult(EngineeringCalculationResult):
    """glass_safety 计算单元的统一结果模型（Sprint 3.2.1 继承自基类）。

    九字段与 as_interface() / as_full() 由 ``EngineeringCalculationResult``
    统一提供；本类仅声明接口标识 INTERFACE。

    红线：result 在 pending 态为空串（不产出真实玻璃安全数值）；
    verification_status 恒 pending_verification。
    """

    INTERFACE = GLASS_SAFETY_INTERFACE


class GlassSafetyCalculator:
    """玻璃安全计算单元（Sprint E 任务1）。

    输入 ``context_data``（Mapping）应透传：
    - ``project``：项目几何 / 支承条件 / 玻璃面积（多为 inferred）；
    - ``design_candidate``：Design Agent 候选（glass_type / dimensions_hint / field_provenance）；
    - ``wind_pressure_result``：WindPressureResult 产出（上游 w_k 供给方）；
    - ``threshold_refs``（可选）：外部传入引用，缺省从阈值库加载。

    红线：本计算器**不产出**任何真实玻璃安全数值，所有数值位保持 pending 占位；
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
        design_candidate: Mapping[str, Any] | None,
        project: Mapping[str, Any] | None,
    ) -> dict[str, str]:
        """合并 Design / Project 的溯源标签（缺省 inferred / unavailable）。"""

        provenance: dict[str, str] = {}
        proj: Mapping[str, Any] = project if isinstance(project, Mapping) else {}
        des: Mapping[str, Any] = (
            design_candidate if isinstance(design_candidate, Mapping) else {}
        )
        des_prov_raw: Any = des.get("field_provenance")
        des_prov: Mapping[str, Any] = (
            des_prov_raw if isinstance(des_prov_raw, Mapping) else {}
        )
        # 设计候选关键字段溯源（玻璃类型 / 尺寸建议，pending_verification）。
        for key in ("glass_type", "dimensions_hint"):
            provenance[f"design.{key}"] = str(des_prov.get(key, "inferred"))
        # 项目几何字段（面积 / 支承条件 / 建筑高度）来自 Vision/Design 候选 → inferred。
        for key in ("glass_area", "support_condition", "building_height"):
            provenance[f"project.{key}"] = (
                "inferred" if proj.get(key) is not None else "unavailable"
            )
        return provenance

    @staticmethod
    def _is_wind_pressure_approved(
        wind_pressure_result: Mapping[str, Any] | None,
    ) -> bool:
        """判断上游 wind_pressure 是否 engineering_approved 且 w_k 真实可得。

        任务4 跨模块闸门：仅当上游状态为 engineering_approved 且 intermediate
        中 w_k.value 非 None 才视为可信；否则 glass_safety 必须 pending。
        """

        if not isinstance(wind_pressure_result, Mapping):
            return False
        status: Any = wind_pressure_result.get("verification_status")
        if status != ENGINEERING_APPROVED:
            return False
        wk_raw: Any = wind_pressure_result.get("intermediate", {})
        wk: Mapping[str, Any] = wk_raw if isinstance(wk_raw, Mapping) else {}
        wk_entry: Any = wk.get("w_k", {})
        if not isinstance(wk_entry, Mapping):
            return False
        return wk_entry.get("value") is not None

    # -- 主装配 --------------------------------------------------------- #

    def calculate(self, context_data: Mapping[str, Any]) -> GlassSafetyResult:
        """执行 glass_safety 计算结构的装配（不产出真实数值）。

        返回 ``GlassSafetyResult``：``verification_status`` 恒
        pending_verification（阈值未双签 + engineering_enabled=false +
        上游 w_k 不可信三重保险）。
        """

        ctx: Mapping[str, Any] = (
            context_data if isinstance(context_data, Mapping) else {}
        )
        project: Mapping[str, Any] | None = ctx.get("project")
        design_candidate: Mapping[str, Any] | None = ctx.get("design_candidate")
        wind_pressure_result: Mapping[str, Any] | None = ctx.get(
            "wind_pressure_result"
        )

        # 1) 接口所需阈值引用（D-TH-02）。
        threshold_ids: tuple[str, ...] = get_interface_thresholds(
            GLASS_SAFETY_INTERFACE
        )
        threshold_refs: list[str] = list(threshold_ids)

        # 2) 中间变量符号占位（全部 pending_verification，无真实取值）。
        intermediate: dict[str, Any] = {
            "w_k": {
                "value": None,
                "unit": "Pa",
                "source": "wind_pressure upstream (E-TH-01~03)",
                "verified": False,
            },
            "t": {
                "value": None,
                "unit": "mm",
                "source": "D-TH-02",
                "verified": False,
            },
            "A": {
                "value": None,
                "unit": "m^2",
                "source": "project geometry (inferred)",
                "verified": False,
            },
            "support": {
                "value": None,
                "unit": "category",
                "source": "project geometry (inferred)",
                "verified": False,
            },
            "sigma_g": {
                "value": None,
                "unit": "Pa",
                "source": "derived (w_k * A * t * support)",
                "verified": False,
            },
            "sigma_allow": {
                "value": None,
                "unit": "Pa",
                "source": "D-TH-02 (with K)",
                "verified": False,
            },
            "K": {
                "value": None,
                "unit": "dimensionless",
                "source": "D-TH-02",
                "verified": False,
            },
            "A_max": {
                "value": None,
                "unit": "m^2",
                "source": "derived (w_k * t * support * sigma_allow)",
                "verified": False,
            },
        }

        # 3) 溯源标签（measured / inferred / verified / unavailable）。
        provenance: dict[str, str] = self._read_provenance(
            design_candidate, project
        )

        # 4) 跨模块链路（任务4）：上游 wind_pressure w_k 可信性判定。
        upstream_approved: bool = self._is_wind_pressure_approved(
            wind_pressure_result
        )
        if upstream_approved:
            # 仅标记来源可信态（仍不填数值；value 保持 None，强约束红线）。
            intermediate["w_k"]["verified"] = True
            provenance["wind_pressure.w_k"] = "verified"
        else:
            provenance["wind_pressure.w_k"] = "upstream_pending"

        # 5) gaps：未双签阈值 + 上游 pending + 非 verified/measured 关键输入。
        gaps: list[str] = []
        for tid in threshold_ids:
            entry: Mapping[str, Any] | None = self._thresholds.get(tid)
            verified: bool = bool(entry and entry.get("verified"))
            if not verified:
                gaps.append(f"{tid}: pending_verification")
        if not upstream_approved:
            gaps.append("w_k: upstream_pending")
        for key, tag in provenance.items():
            if tag not in ("verified", "measured"):
                gaps.append(f"{key}: pending_verification")

        # 6) 证据（来源说明 + 公式 + 阈值引用 + pending 标注，无真实数值）。
        formula: str = "; ".join(glass_rules.GLASS_SAFETY_FORMULAS)
        evidence: str = (
            f"公式来源：玻璃安全采用荷载—应力—校核结构 {formula}"
            "（系数选取规则 pending_verification）。"
            "变量来源：玻璃厚度 t、允许应力 sigma_allow、安全系数 K 来自工程阈值库 D-TH-02；"
            "风荷载标准值 w_k 来自上游 wind_pressure；上述阈值均未双签，"
            "取值 pending_verification。"
            "上游 w_k 不可信时不得基于未验证风压推出玻璃达标结论（跨模块降级）。"
            "D-TH-02 未双签前不得产出具体玻璃厚度/安全系数/许用应力数值（红线）。"
        )

        # 7) 结论：恒 pending（数据饥饿 + enabled=false + 上游闸门三重保险）。
        verification_status: str = PENDING_VERIFICATION

        return GlassSafetyResult(
            result="",  # 红线：不产出真实玻璃安全数值
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
    "GLASS_SAFETY_INTERFACE",
    "GlassSafetyCalculator",
    "GlassSafetyResult",
]
