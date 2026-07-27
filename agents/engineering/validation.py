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
from typing import Any, Mapping


# Engineering Agent 统一输出结构的必备字段（接口契约，勿随意增删）。
REQUIRED_OUTPUT_KEYS: tuple[str, ...] = (
    "result",
    "confidence",
    "evidence",
    "verification_status",
)

# 骨架阶段唯一合法的验证状态：一切工程结论均未经真实验证。
PENDING_VERIFICATION: str = "pending_verification"


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


__all__ = [
    "PENDING_VERIFICATION",
    "REQUIRED_OUTPUT_KEYS",
    "EngineeringValidation",
    "PendingEngineeringValidation",
]
