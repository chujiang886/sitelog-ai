"""Engineering 工程计算单元包（Phase 3.1 Sprint C + Sprint E + Sprint G + Sprint I + Sprint K）。

承载各分析接口的真实计算结构（wind_pressure + glass_safety + profile +
hardware + installation_risk）。红线：
- 不产出真实工程数值，所有取值 pending_verification；
- engineering_enabled 保持 false；
- 不填真实系数、不写规范条款号、不写死工程常数。
"""

from __future__ import annotations

from agents.engineering.calc.glass_safety import (
    GLASS_SAFETY_INTERFACE,
    GlassSafetyCalculator,
    GlassSafetyResult,
)
from agents.engineering.calc.hardware import (
    HARDWARE_INTERFACE,
    HardwareCalculator,
    HardwareResult,
)
from agents.engineering.calc.installation_risk import (
    INSTALLATION_RISK_INTERFACE,
    InstallationRiskCalculator,
    InstallationRiskResult,
)
from agents.engineering.calc.profile import (
    PROFILE_INTERFACE,
    ProfileCalculator,
    ProfileResult,
)
from agents.engineering.calc.wind_pressure import (
    WIND_PRESSURE_INTERFACE,
    WindPressureCalculator,
    WindPressureResult,
)

__all__ = [
    "GLASS_SAFETY_INTERFACE",
    "GlassSafetyCalculator",
    "GlassSafetyResult",
    "HARDWARE_INTERFACE",
    "HardwareCalculator",
    "HardwareResult",
    "INSTALLATION_RISK_INTERFACE",
    "InstallationRiskCalculator",
    "InstallationRiskResult",
    "PROFILE_INTERFACE",
    "ProfileCalculator",
    "ProfileResult",
    "WIND_PRESSURE_INTERFACE",
    "WindPressureCalculator",
    "WindPressureResult",
]
