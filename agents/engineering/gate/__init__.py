"""Engineering Enable Gate 包（Phase 3.2 Sprint 3.2.5-B）。

落地 Sprint 3.2.5-A 门禁设计：``can_enable_engineering`` 六项门禁
G1 阈值治理 / G2 双签 / G3 CI / G4 审核链 / G5 回滚就绪 / G6 授权。

红线：本包只判定"是否允许开启 engineering_enabled"，**绝不**自行翻转
engineering_enabled、绝不输出 engineering_approved、绝不写入真实参数。
"""

from agents.engineering.gate.enable_gate import (
    GATE_G1_GOVERNANCE,
    GATE_G2_DUAL_SIGN,
    GATE_G3_CI,
    GATE_G4_AUDIT_CHAIN,
    GATE_G5_ROLLBACK,
    GATE_G6_AUTHORIZATION,
    can_enable_engineering,
)

__all__ = [
    "GATE_G1_GOVERNANCE",
    "GATE_G2_DUAL_SIGN",
    "GATE_G3_CI",
    "GATE_G4_AUDIT_CHAIN",
    "GATE_G5_ROLLBACK",
    "GATE_G6_AUTHORIZATION",
    "can_enable_engineering",
]
