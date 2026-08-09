"""EngineeringValidation 接口（Phase 2.1.5 骨架）。

职责：
- 定义 Engineering Agent 输出的统一审核链（review chain）契约；
- 骨架阶段不做任何真实工程校验，只做**结构校验**：
  确认每个分析输出携带统一四字段
  ``result / confidence / evidence / verification_status``；
- 任何工程数值判定（风压、玻璃安全、型材、五金、安装风险）
  一律保持 ``pending_verification``，绝不在校验器中编造阈值或权重。

演进路径：
- Phase 3+ 可提供接入真实规则引擎 / 规范库的 ``EngineeringValidation``
  实现类，替换 ``PendingEngineeringValidation``，Agent 侧无需改动。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Mapping

from agents.config_loader import load_engineering_enabled
from agents.engineering import review_log
from agents.engineering.threshold_loader import (
    expert_signed,
    get_interface_thresholds,
    load_verified_thresholds,
    mgmt_signed,
)


# Engineering Agent 统一输出结构的必备字段（接口契约，勿随意增删）。
REQUIRED_OUTPUT_KEYS: tuple[str, ...] = (
    "result",
    "confidence",
    "evidence",
    "verification_status",
)

# 骨架阶段唯一合法的验证状态：一切工程结论均未经真实验证。
PENDING_VERIFICATION: str = "pending_verification"

# 双签完整 + engineering_enabled=true 时才允许的工程审核通过态。
ENGINEERING_APPROVED: str = "engineering_approved"


class EngineeringValidation(ABC):
    """Engineering 输出审核链的抽象契约。

    每一个分析接口的输出在写入 ``AgentResult`` 前，必须经过一次
    ``validate`` 调用，产出一条审核链记录（review chain record）。
    """

    @abstractmethod
    def validate(
        self,
        *,
        interface: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """校验单个分析输出并返回审核链记录。

        参数：
        - ``interface``：分析接口标识（如 ``wind_pressure``）；
        - ``payload``：该接口产出的统一输出结构。

        返回的审核链记录至少包含：
        - ``interface``：被审核的接口名；
        - ``structure_valid``：统一结构四字段是否齐备；
        - ``missing_keys``：缺失字段列表（齐备时为空）；
        - ``verification_status``：审核后的验证状态。
        """

        raise NotImplementedError("EngineeringValidation 子类必须实现 validate")


class PendingEngineeringValidation(EngineeringValidation):
    """骨架默认实现：只校验结构，工程结论一律 pending_verification。

    显式不做的事情（防编造红线）：
    - 不校验风压是否达标（无真实规范数据）；
    - 不校验玻璃配置是否安全（无真实厚度/面积规则）；
    - 不校验型材/五金选型（无真实产品库）；
    - 不评估安装风险等级（无真实工况数据）。
    """

    def validate(
        self,
        *,
        interface: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """结构校验：四字段齐备 → 记录 pending_verification 审核链。"""

        normalized_interface: str = interface.strip()
        if not normalized_interface:
            raise ValueError("EngineeringValidation 需要非空 interface 标识")

        missing_keys: list[str] = [
            key for key in REQUIRED_OUTPUT_KEYS if key not in payload
        ]
        structure_valid: bool = not missing_keys

        # 即使结构合法，验证状态也必须保持 pending_verification：
        # 骨架阶段没有任何真实工程验证能力。
        verification_status: str = (
            PENDING_VERIFICATION if structure_valid else "invalid_structure"
        )

        return {
            "interface": normalized_interface,
            "structure_valid": structure_valid,
            "missing_keys": missing_keys,
            "verification_status": verification_status,
            "validator": type(self).__name__,
        }


class ExpertBackedEngineeringValidation(EngineeringValidation):
    """专家双签审核链（Phase 3.1 Sprint A 基础设施）。

    在 ``PendingEngineeringValidation`` 的结构校验之上，叠加**阈值双签**判定：
    - ``structure_valid``：统一四字段是否齐备（结构契约）；
    - ``threshold_verified``：所需阈值是否经**主理人核准**
      （``verified=true`` + ``verified_by`` + ``verified_at`` 俱全）；
    - ``expert_signed``��所需阈值是否经**行业专家签字**
      （``expert_verified_by`` + ``expert_verified_at`` 俱全）；
    - ``verification_status``：仅当 *结构合法 + 双签完整 + engineering_enabled=true*
      三者同时满足才输出 ``engineering_approved``，否则恒 ``pending_verification``。

    红线（Sprint A）：``engineering_enabled`` 在 ``config.yaml`` 中恒为 ``false``，
    因此本验证器在真实系统里**永不输出** ``engineering_approved``；``sign_off_id``
    仅在通过态才派生。阈值数值仍来自 ``verified.json``（全 ``value=null``），
    本类不消费、不编造任何真实工程常数。
    """

    def __init__(
        self,
        *,
        engineering_enabled: bool | None = None,
        thresholds: Mapping[str, Any] | None = None,
        thresholds_path: "Path | str | None" = None,
    ) -> None:
        # engineering_enabled=None → 运行时从 config.yaml 读取（默认 false）。
        self._engineering_enabled_override: bool | None = engineering_enabled
        if thresholds is not None:
            self._thresholds: dict[str, Any] = dict(thresholds)
        else:
            self._thresholds = load_verified_thresholds(thresholds_path)

    @property
    def engineering_enabled(self) -> bool:
        """返回工程审核开关：显式注入优先，否则读 config.yaml（默认 false）。"""

        if self._engineering_enabled_override is not None:
            return bool(self._engineering_enabled_override)
        return bool(load_engineering_enabled())

    def validate(
        self,
        *,
        interface: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        """双签审核：返回七字段审核链记录。"""

        normalized_interface: str = (interface or "").strip()
        if not normalized_interface:
            raise ValueError("EngineeringValidation 需要非空 interface 标识")

        missing_keys: list[str] = [
            key for key in REQUIRED_OUTPUT_KEYS if key not in payload
        ]
        structure_valid: bool = not missing_keys

        if not structure_valid:
            # 结构非法：不进入阈值判定，直接 invalid_structure。
            return {
                "interface": normalized_interface,
                "structure_valid": False,
                "threshold_verified": False,
                "expert_signed": False,
                "verification_status": "invalid_structure",
                "sign_off_id": None,
                "validator": type(self).__name__,
            }

        # 解析该接口所需的签字阈值，并逐项判定双签状态。
        threshold_ids: tuple[str, ...] = get_interface_thresholds(normalized_interface)
        entries: list[tuple[str, Any]] = [
            (tid, self._thresholds.get(tid)) for tid in threshold_ids
        ]
        threshold_verified: bool = bool(threshold_ids) and all(
            mgmt_signed(entry) for _, entry in entries
        )
        expert_signed_flag: bool = bool(threshold_ids) and all(
            expert_signed(entry) for _, entry in entries
        )

        # 红线闸门：三个条件全部满足才允许 engineering_approved。
        approved: bool = (
            structure_valid
            and threshold_verified
            and expert_signed_flag
            and self.engineering_enabled
        )

        if approved:
            verification_status: str = ENGINEERING_APPROVED
            signed_pairs: list[tuple[str, Any]] = [
                (tid, entry)
                for tid, entry in entries
                if entry is not None and mgmt_signed(entry) and expert_signed(entry)
            ]
            sign_off_id: str | None = review_log.compute_sign_off_id(
                interface=normalized_interface,
                threshold_ids=threshold_ids,
                signs=signed_pairs,
            )
        else:
            verification_status = PENDING_VERIFICATION
            sign_off_id = None

        return {
            "interface": normalized_interface,
            "structure_valid": structure_valid,
            "threshold_verified": threshold_verified,
            "expert_signed": expert_signed_flag,
            "verification_status": verification_status,
            "sign_off_id": sign_off_id,
            "validator": type(self).__name__,
        }


__all__ = [
    "PENDING_VERIFICATION",
    "ENGINEERING_APPROVED",
    "REQUIRED_OUTPUT_KEYS",
    "EngineeringValidation",
    "PendingEngineeringValidation",
    "ExpertBackedEngineeringValidation",
]
