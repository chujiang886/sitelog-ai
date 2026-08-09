"""安装施工风险（Installation Risk）计算单元（Sprint K 任务1 + 任务4）。

设计依据：Sprint J 安装风险设计文档（已审核）。本文件承载 installation_risk
接口的计算结构装配，并定义结果模型 ``InstallationRiskResult``。

红线（Sprint K，强制）：
- 本模块**不计算**任何真实风险数值；E-TH-05（腐蚀等级）/ E-TH-06（安装风险矩阵）
  在 verified.json 中仍为 value=null、verified=false，故 intermediate 各量
  （Risk_total / lift_condition / D_safe / personnel_risk / env_risk 等）为
  **符号占位**，目标量不可得；
- engineering_enabled 保持 false，verification_status 恒 pending_verification；
- 不填真实风险分数、真实承载参数、真实施工安全距离、真实施工等级、规范条款号；
- 所有未知一律 pending_verification。

跨模块链路（任务4，末端聚合）：消费上游 glass_safety_result（玻璃重量）、
profile_result（型材条件）、hardware_result（五金条件）的审核态；任一上游的
verification_status 不等于 engineering_approved，installation_risk 结论强制
pending_verification 并登记 gaps: ["glass_safety_result: upstream_pending" /
"profile_result: upstream_pending" / "hardware_result: upstream_pending"]；
**禁止**在本模块自行计算玻璃重量 / 型材条件 / 五金条件（三者分别归属
glass_safety / profile / hardware 模块）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from agents.engineering.calc.base import EngineeringCalculationResult
from agents.engineering.rules import installation_rules
from agents.engineering.threshold_loader import (
    get_interface_thresholds,
    load_verified_thresholds,
)
from agents.engineering.validation import (
    ENGINEERING_APPROVED,
    PENDING_VERIFICATION,
)


# 安装风险接口标识（与 INTERFACE_THRESHOLD_MAP 对齐；阈值数值 pending_verification）。
INSTALLATION_RISK_INTERFACE: str = "installation_risk"


@dataclass
class InstallationRiskResult(EngineeringCalculationResult):
    """installation_risk 计算单元的统一结果模型（Sprint 3.2.1 继承自基类）。

    九字段与 as_interface() / as_full() 由 ``EngineeringCalculationResult``
    统一提供；本类仅声明接口标识 INTERFACE。

    红线：result 在 pending 态为空串（不产出真实风险评级/安全距离结论）；
    verification_status 恒 pending_verification。
    """

    INTERFACE = INSTALLATION_RISK_INTERFACE


class InstallationRiskCalculator:
    """安装施工风险计算单元（Sprint K 任务1）。

    输入 ``context_data``（Mapping）应透传：
    - ``project``：项目几何 / 安装场景 / 楼层高度类别 / 吊装风险 / 施工环境 /
      天气影响 / 安装工艺（多为 inferred）；
    - ``design_candidate``：Design Agent 候选（glass_config / opening_form_hint /
      frame_series / field_provenance）；
    - ``glass_safety_result``：玻璃安全上游产出（玻璃重量供给方；仅消费其
      审核态与重量量级，不重算）；
    - ``profile_result``：型材上游产出（型材条件供给方；仅消费审核态，
      不重算型材受力）；
    - ``hardware_result``：五金上游产出（五金条件供给方；仅消费审核态，
      不重算五金承载）；
    - ``wind_pressure_result``（可选）：仅作 w_k 溯源参考，不重算；
    - ``threshold_refs``（可选）：外部传入引用，缺省从阈值库加载。

    红线：本计算器**不产出**任何真实风险评级/承载/距离，所有数值位保持 pending
    占位；结论恒 pending_verification（数据饥饿 + enabled=false 闸门 + 三上游
    不可信三重保险）。
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
        # 设计候选关键字段溯源（玻璃配置 / 开启形式建议，pending_verification）。
        for key in ("glass_config", "opening_form_hint"):
            provenance[f"design.{key}"] = str(des_prov.get(key, "inferred"))
        # 项目几何字段（安装场景 / 楼层高度 / 吊装风险 / 施工环境 / 天气 / 工艺）
        # 来自 Vision/Design/Environment 候选 → inferred（楼层高度数值 pending）。
        for key in (
            "installation_scenario",
            "floor_height",
            "lift_risk",
            "construction_env",
            "weather_impact",
            "install_process",
        ):
            provenance[f"project.{key}"] = (
                "inferred" if proj.get(key) is not None else "unavailable"
            )
        return provenance

    @staticmethod
    def _is_upstream_approved(
        upstream_result: Mapping[str, Any] | None,
    ) -> bool:
        """判断某个上游是否 engineering_approved（其结论可信）。

        任务4 跨模块闸门：仅当上游状态为 engineering_approved 才视为可信；
        否则 installation_risk 必须 pending（不依赖未验证上游结论做风险聚合判断）。
        注意：本模块**不**消费上游的 intermediate 数值重算玻璃重量/型材/五金，
        仅依其审核态做可信性判定。
        """

        if not isinstance(upstream_result, Mapping):
            return False
        status: Any = upstream_result.get("verification_status")
        return status == ENGINEERING_APPROVED

    # -- 主装配 --------------------------------------------------------- #

    def calculate(self, context_data: Mapping[str, Any]) -> InstallationRiskResult:
        """执行 installation_risk 计算结构的装配（不产出真实数值）。

        返回 ``InstallationRiskResult``：``verification_status`` 恒
        pending_verification（阈值未双签 + engineering_enabled=false +
        三上游不可信三重保险）。
        """

        ctx: Mapping[str, Any] = (
            context_data if isinstance(context_data, Mapping) else {}
        )
        project: Mapping[str, Any] | None = ctx.get("project")
        design_candidate: Mapping[str, Any] | None = ctx.get("design_candidate")
        glass_result: Mapping[str, Any] | None = ctx.get("glass_safety_result")
        profile_result: Mapping[str, Any] | None = ctx.get("profile_result")
        hardware_result: Mapping[str, Any] | None = ctx.get("hardware_result")

        # 1) 接口所需阈值引用（E-TH-05 腐蚀等级 + E-TH-06 安装风险矩阵）。
        threshold_ids: tuple[str, ...] = get_interface_thresholds(
            INSTALLATION_RISK_INTERFACE
        )
        threshold_refs: list[str] = list(threshold_ids)

        # 2) 中间变量符号占位（全部 pending_verification，无真实取值）。
        #    声明：G_weight（玻璃重量）来自 Design/Glass（经 glass_safety_result）；
        #    H_floor（楼层高度类别）来自项目几何；w_k 来自 wind_pressure 上游；
        #    P_profile / P_hardware 来自上游型材/五金审核态；
        #    Risk_total / lift_condition / D_safe / personnel_risk / env_risk /
        #    process_risk / weather_impact 来自 E-TH-05/E-TH-06 风险矩阵（评级 pending）。
        intermediate: dict[str, Any] = {
            "G_weight": {
                "value": None,
                "unit": "kg",
                "source": "glass_safety_result / design_candidate（D-TH-02，pending_verification）",
                "verified": False,
            },
            "H_floor": {
                "value": None,
                "unit": "category",
                "source": "project geometry（楼层高度数值 pending_verification）",
                "verified": False,
            },
            "w_k": {
                "value": None,
                "unit": "Pa",
                "source": "wind_pressure 上游（E-TH-01~03，pending_verification）",
                "verified": False,
            },
            "profile_cond": {
                "value": None,
                "unit": "category",
                "source": "profile_result（D-TH-01，pending_verification）",
                "verified": False,
            },
            "hardware_cond": {
                "value": None,
                "unit": "category",
                "source": "hardware_result（E-TH-04，pending_verification）",
                "verified": False,
            },
            "lift_condition": {
                "value": None,
                "unit": "category",
                "source": "E-TH-06（吊装条件，pending_verification）",
                "verified": False,
            },
            "personnel_risk": {
                "value": None,
                "unit": "category",
                "source": "E-TH-06（人员操作风险，pending_verification）",
                "verified": False,
            },
            "env_risk": {
                "value": None,
                "unit": "category",
                "source": "E-TH-05 + E-TH-06（环境风险/腐蚀等级，pending_verification）",
                "verified": False,
            },
            "weather_impact": {
                "value": None,
                "unit": "category",
                "source": "project / environment（天气影响类别，pending_verification）",
                "verified": False,
            },
            "process_risk": {
                "value": None,
                "unit": "category",
                "source": "E-TH-06（安装工艺风险，pending_verification）",
                "verified": False,
            },
            "Risk_total": {
                "value": None,
                "unit": "category",
                "source": "E-TH-06（综合安装风险评级，禁止真实分数，pending_verification）",
                "verified": False,
            },
            "D_safe": {
                "value": None,
                "unit": "m",
                "source": "E-TH-06（施工安全距离，禁止真实距离，pending_verification）",
                "verified": False,
            },
        }

        # 3) 溯源标签（measured / inferred / verified / unavailable）。
        provenance: dict[str, str] = self._read_provenance(
            design_candidate, project
        )

        # 4) 跨模块链路（任务4）：三上游可信性判定（末端聚合）。
        glass_approved: bool = self._is_upstream_approved(glass_result)
        profile_approved: bool = self._is_upstream_approved(profile_result)
        hardware_approved: bool = self._is_upstream_approved(hardware_result)
        provenance["glass_safety_result"] = (
            "verified" if glass_approved else "upstream_pending"
        )
        provenance["profile_result"] = (
            "verified" if profile_approved else "upstream_pending"
        )
        provenance["hardware_result"] = (
            "verified" if hardware_approved else "upstream_pending"
        )

        # 5) gaps：未双签阈值 + 三上游 pending + 非 verified/measured 关键输入。
        gaps: list[str] = []
        for tid in threshold_ids:
            entry: Mapping[str, Any] | None = self._thresholds.get(tid)
            verified: bool = bool(entry and entry.get("verified"))
            if not verified:
                gaps.append(f"{tid}: pending_verification")
        if not glass_approved:
            gaps.append("glass_safety_result: upstream_pending")
        if not profile_approved:
            gaps.append("profile_result: upstream_pending")
        if not hardware_approved:
            gaps.append("hardware_result: upstream_pending")
        for key, tag in provenance.items():
            if tag not in ("verified", "measured"):
                gaps.append(f"{key}: pending_verification")

        # 6) 证据（来源说明 + 公式 + 阈值引用 + pending 标注，无真实数值）。
        formula: str = "; ".join(installation_rules.INSTALLATION_FORMULAS)
        evidence: str = (
            "公式来源：安装施工风险采用多因素风险评级结构 "
            f"{formula}"
            "（系数与评级矩阵选取规则 pending_verification）。"
            "变量来源：综合风险评级 Risk_total、吊装条件 lift_condition、人员操作风险 "
            "personnel_risk、环境风险 env_risk、工艺流程风险 process_risk、施工安全距离 "
            "D_safe 来自工程阈值库 E-TH-05（腐蚀等级）与 E-TH-06（安装风险矩阵）；"
            "玻璃重量 G_weight 来自 Design/Glass（经 glass_safety_result 透传，D-TH-02）；"
            "型材条件 profile_cond 来自 profile_result（D-TH-01）；"
            "五金条件 hardware_cond 来自 hardware_result（E-TH-04）；"
            "楼层高度 H_floor 与天气影响 weather_impact 来自项目几何与施工环境（inferred）；"
            "上述阈值均未双签，取值 pending_verification。"
            "三上游（玻璃安全/型材/五金）不可信时不得基于未验证玻璃重量/型材/五金推出"
            "安装风险可控结论（跨模块降级，禁止在本模块重算玻璃重量/型材受力/五金承载）。"
            "E-TH-05/E-TH-06 未双签前不得产出具体风险分数/承载参数/施工安全距离/施工等级"
            "（红线）。"
        )

        # 7) 结论：恒 pending（数据饥饿 + enabled=false + 三上游闸门三重保险）。
        verification_status: str = PENDING_VERIFICATION

        return InstallationRiskResult(
            result="",  # 红线：不产出真实风险评级/安全距离结论
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
    "INSTALLATION_RISK_INTERFACE",
    "InstallationRiskCalculator",
    "InstallationRiskResult",
]
