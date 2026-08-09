"""五金（Hardware）计算单元（Sprint I 任务1 + 任务4）。

设计依据：Sprint H 五金设计文档（已审核）。本文件承载 hardware 接口
的计算结构装配，并定义结果模型 ``HardwareResult``。

红线（Sprint I，强制）：
- 本模块**不计算**任何真实五金数值；E-TH-04 在 verified.json 中仍为
  value=null、verified=false，故 intermediate 各量为**符号占位**，目标量
  F_demand / F_hardware / load_check 不可得；
- engineering_enabled 保持 false，verification_status 恒 pending_verification；
- 不填真实五金承载值（F_hardware）、真实锁点数量（lock_system）、
  真实寿命次数（cycle_life）、真实型号规格（hardware_config 仅作标识符）；
- 不写规范条款号，不写死工程常数；
- 所有未知一律 pending_verification。

跨模块链路（任务4）：消费上游 profile 的型材结果；若 profile 的
verification_status 不等于 engineering_approved，hardware 结论强制
pending_verification 并登记 gaps: ["profile_result: upstream_pending"]；
**禁止**在本模块自行计算型材受力（型材受力归属 profile 模块）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents.engineering.calc.base import EngineeringCalculationResult
from agents.engineering.rules import hardware_rules
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    load_verified_thresholds,
)
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
)


# 五金接口标识（与 INTERFACE_THRESHOLD_MAP 对齐；阈值数值 pending_verification）。
HARDWARE_INTERFACE: str = "hardware"


@dataclass
class HardwareResult(EngineeringCalculationResult):
    """hardware 计算单元的统一结果模型（Sprint 3.2.1 继承自基类）。

    九字段与 as_interface() / as_full() 由 ``EngineeringCalculationResult``
    统一提供；本类仅声明接口标识 INTERFACE。

    红线：result 在 pending 态为空串（不产出真实五金选型/承载结论）；
    verification_status 恒 pending_verification。
    """

    INTERFACE = HARDWARE_INTERFACE


class HardwareCalculator:
    """五金计算单元（Sprint I 任务1）。

    输入 ``context_data``（Mapping）应透传：
    - ``project``：项目几何 / 门窗开启形式 / 承载条件（多为 inferred）；
    - ``design_candidate``：Design Agent 候选（opening_type / hardware_config /
      dimensions_hint / field_provenance）；
    - ``profile_result``：ProfileResult 产出（上游型材结果供给方，用于判定
      型材是否可信，但**不**在本模块重算型材受力）；
    - ``wind_pressure_result``（可选）：仅作 w_k 溯源参考，不重算；
    - ``threshold_refs``（可选）：外部传入引用，缺省从阈值库加载。

    红线：本计算器**不产出**任何真实五金数值，所有数值位保持 pending 占位；
    结论恒 pending_verification（数据饥饿 + enabled=false 闸门由 validator 叠加
    + 上游 profile 不可信三重保险）。
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
        # 设计候选关键字段溯源（开启形式 / 五金配置，pending_verification）。
        for key in ("opening_type", "hardware_config"):
            provenance[f"design.{key}"] = str(des_prov.get(key, "inferred"))
        # 项目几何字段（承载条件 / 使用场景）来自 Vision/Design 候选 → inferred。
        for key in ("load_condition", "usage_scenario"):
            provenance[f"project.{key}"] = (
                "inferred" if proj.get(key) is not None else "unavailable"
            )
        return provenance

    @staticmethod
    def _is_profile_approved(
        profile_result: Mapping[str, Any] | None,
    ) -> bool:
        """判断上游 profile 是否 engineering_approved（型材结果可信）。

        任务4 跨模块闸门：仅当上游状态为 engineering_approved 才视为型材可信；
        否则 hardware 必须 pending（不依赖未验证型材结论做五金选型判断）。
        注意：本模块**不**消费 profile 的 intermediate 数值重算受力，
        仅依其审核态做可信性判定。
        """

        if not isinstance(profile_result, Mapping):
            return False
        status: Any = profile_result.get("verification_status")
        return status == ENGINEERING_APPROVED

    # -- 主装配 --------------------------------------------------------- #

    def calculate(self, context_data: Mapping[str, Any]) -> HardwareResult:
        """执行 hardware 计算结构的装配（不产出真实数值）。

        返回 ``HardwareResult``：``verification_status`` 恒
        pending_verification（阈值未双签 + engineering_enabled=false +
        上游 profile 不可信三重保险）。
        """

        ctx: Mapping[str, Any] = (
            context_data if isinstance(context_data, Mapping) else {}
        )
        project: Mapping[str, Any] | None = ctx.get("project")
        design_candidate: Mapping[str, Any] | None = ctx.get("design_candidate")
        profile_result: Mapping[str, Any] | None = ctx.get("profile_result")

        # 1) 接口所需阈值引用（E-TH-04：五金承载力）。
        threshold_ids: tuple[str, ...] = get_interface_thresholds(
            HARDWARE_INTERFACE
        )
        threshold_refs: list[str] = list(threshold_ids)

        # 2) 中间变量符号占位（全部 pending_verification，无真实取值）。
        #    声明：F_hardware（五金承载力）来自 E-TH-04；F_demand（需求承载力）
        #    为派生量；lock_system（锁点体系）仅作类别标识（不写真实数量）；
        #    cycle_life（使用寿命次数）仅占位，不填真实循环次数。
        intermediate: dict[str, Any] = {
            "w_k": {
                "value": None,
                "unit": "Pa",
                "source": "wind_pressure / profile 上游（E-TH-01~03，pending_verification）",
                "verified": False,
            },
            "opening_type": {
                "value": None,
                "unit": "category",
                "source": "design_candidate / project（inferred）",
                "verified": False,
            },
            "load_condition": {
                "value": None,
                "unit": "category",
                "source": "project geometry（inferred）",
                "verified": False,
            },
            "hardware_config": {
                "value": None,
                "unit": "identifier",
                "source": "design_candidate（inferred，pending_verification）",
                "verified": False,
            },
            "F_demand": {
                "value": None,
                "unit": "N",
                "source": "derived (w_k, opening_type, geometry)",
                "verified": False,
            },
            "F_hardware": {
                "value": None,
                "unit": "N",
                "source": "E-TH-04",
                "verified": False,
            },
            "load_class": {
                "value": None,
                "unit": "category",
                "source": "derived (F_demand vs F_hardware)",
                "verified": False,
            },
            "lock_system": {
                "value": None,
                "unit": "category",
                "source": "design_candidate + norm（pending_verification）",
                "verified": False,
            },
            "connection_req": {
                "value": None,
                "unit": "category",
                "source": "derived (opening_type, load_class)",
                "verified": False,
            },
            "usage_scenario": {
                "value": None,
                "unit": "category",
                "source": "project（inferred）",
                "verified": False,
            },
            "cycle_life": {
                "value": None,
                "unit": "cycles",
                "source": "E-TH-04 / product spec（pending_verification）",
                "verified": False,
            },
            "load_check": {
                "value": None,
                "unit": "boolean",
                "source": "derived (F_demand <= F_hardware)",
                "verified": False,
            },
        }

        # 3) 溯源标签（measured / inferred / verified / unavailable）。
        provenance: dict[str, str] = self._read_provenance(
            design_candidate, project
        )

        # 4) 跨模块链路（任务4）：上游 profile 可信性判定。
        upstream_approved: bool = self._is_profile_approved(profile_result)
        if upstream_approved:
            # 仅标记来源可信态（仍不填数值；value 保持 None，强约束红线）。
            provenance["profile_result"] = "verified"
        else:
            provenance["profile_result"] = "upstream_pending"

        # 5) gaps：未双签阈值 + 上游 pending + 非 verified/measured 关键输入。
        gaps: list[str] = []
        for tid in threshold_ids:
            entry: Mapping[str, Any] | None = self._thresholds.get(tid)
            verified: bool = bool(entry and entry.get("verified"))
            if not verified:
                gaps.append(f"{tid}: pending_verification")
        if not upstream_approved:
            gaps.append("profile_result: upstream_pending")
        for key, tag in provenance.items():
            if tag not in ("verified", "measured"):
                gaps.append(f"{key}: pending_verification")

        # 6) 证据（来源说明 + 公式 + 阈值引用 + pending 标注，无真实数值）。
        formula: str = "; ".join(hardware_rules.HARDWARE_FORMULAS)
        evidence: str = (
            f"公式来源：五金采用荷载需求—承载校核结构 {formula}"
            "（系数选取规则 pending_verification）。"
            "变量来源：五金承载力 F_hardware、使用寿命次数 cycle_life 来自工程阈值库 E-TH-04；"
            "需求承载力 F_demand 由上游风荷载 w_k 与门窗开启形式派生；"
            "锁点体系 lock_system、连接要求 connection_req 源自设计方案与规范占位；"
            "上述阈值均未双签，取值 pending_verification。"
            "上游型材（profile）不可信时不得基于未验证型材结论做五金选型/承载判定"
            "（跨模块降级，禁止在本模块重算型材受力）。"
            "E-TH-04 未双签前不得产出具体五金承载值/锁点数量/寿命次数/型号规格（红线）。"
        )

        # 7) 结论：恒 pending（数据饥饿 + enabled=false + 上游闸门三重保险）。
        verification_status: str = PENDING_VERIFICATION

        return HardwareResult(
            result="",  # 红线：不产出真实五金选型/承载结论
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
    "HARDWARE_INTERFACE",
    "HardwareCalculator",
    "HardwareResult",
]
