# Phase 3.2.1 — EngineeringCalculationResult 抽象与红线集中（设计确认）

> **身份**：BOIP AI 架构工程师
> **Sprint**：Phase 3.2 Sprint 3.2.1（产品化第一阶段：结果统一抽象）
> **阶段定位**：重构（抽象基类，消除重复），**非新增工程能力、非新增计算逻辑**。
> **红线（强制）**：① 不修改工程计算逻辑；② 不修改五模块输入输出语义；③ 不填真实工程参数；④ 不修改 `verified.json`；⑤ 不开启 `engineering_enabled`；⑥ 不输出 `engineering_approved`；全程保持 `pending_verification`。
> **状态**：`pending_verification`（设计确认阶段，未实施编码）。
> **关联**：Phase 3.1 Final Integration 同构分析（`.ai/tasks/phase3.1_result_abstraction_analysis.md` §4 迁移方案草案）。

---

## 1. 当前五 Result 结构分析

实读五文件（`agents/engineering/calc/{wind_pressure,glass_safety,profile,hardware,installation_risk}.py`），确认 `WindPressureResult` / `GlassSafetyResult` / `ProfileResult` / `HardwareResult` / `InstallationRiskResult` 为**逐字同构**的 `@dataclass`，差异仅一处——`as_full()` 中 `"interface"` 取值来自各模块常量（`WIND_PRESSURE_INTERFACE` / `GLASS_SAFETY_INTERFACE` / `PROFILE_INTERFACE` / `HARDWARE_INTERFACE` / `INSTALLATION_RISK_INTERFACE`）。

**九字段完全一致**：
```text
result: str = ""
confidence: str = PENDING_VERIFICATION
evidence: str = ""
verification_status: str = PENDING_VERIFICATION
intermediate: dict[str, Any] = field(default_factory=dict)
provenance: dict[str, str] = field(default_factory=dict)
threshold_refs: list[str] = field(default_factory=list)
gaps: list[str] = field(default_factory=list)
sign_off_id: str | None = None
```

**两方法完全一致**：
- `as_interface()` → 精确四键 `{result, confidence, evidence, verification_status}`。
- `as_full()` → 八字段 + `"interface"` 标识（`interface` 值 = 模块常量）。

**构造调用一致**：五计算器 `calculate()` 均以相同数量的关键字参数返回 `XxxResult(...)`（见 `wind_pressure.py` 的 `calculate()` 返回处等），无位置参数、无额外字段。

**既有测试断言**（如 `tests/agents/test_wind_pressure.py` 的四字段 / 八字段断言段）：
- `as_interface()` 断言恰好 4 键（`result/confidence/evidence/verification_status`）。
- `as_full()` 断言含 8 扩展字段 + `sign_off_id is None` + `threshold_refs` 对应接口阈值。
- 直接 `XxxResult(...)` 构造后序列化正确。

→ 基类重构**必须**保证：九字段、两方法字节结构不变；否则破坏上述断言与 Agent 契约。

---

## 2. 基类设计（`agents/engineering/calc/base.py`）

新增 `EngineeringCalculationResult` 基类（`@dataclass`），承载九字段 + 两方法 + 红线闸门：

```python
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from agents.engineering.validation import PENDING_VERIFICATION


@dataclass
class EngineeringCalculationResult:
    """工程计算统一结果基类（Sprint 3.2.1）。

    五模块 Result 共享的九字段 + as_interface() + as_full() 下沉于此，
    消除约 200 行重复；红线不变量集中于本类。

    子类须覆盖类级常量 INTERFACE（接口标识）。
    """

    result: str = ""
    confidence: str = PENDING_VERIFICATION
    evidence: str = ""
    verification_status: str = PENDING_VERIFICATION
    intermediate: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    threshold_refs: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    sign_off_id: str | None = None

    # 子类覆盖：接口标识（如 "wind_pressure"）。
    INTERFACE: str = ""

    def as_interface(self) -> dict[str, Any]:
        """返回 EngineeringAgent 接口所需的统一四字段结构（精确四键）。"""
        return {
            "result": self.result,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
        }

    def as_full(self) -> dict[str, Any]:
        """返回含扩展字段的完整结果（八字段 + interface 标识）。"""
        return {
            "interface": type(self).INTERFACE,
            "result": self.result,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
            "intermediate": self.intermediate,
            "provenance": self.provenance,
            "threshold_refs": self.threshold_refs,
            "gaps": self.gaps,
            "sign_off_id": self.sign_off_id,
        }

    def enforce_redline(self) -> None:
        """红线闸门：pending 态下 result 必须为空、verification_status 必须 pending。

        用于 AgentResult 装配前调用，防未来误填真实数值或误置 approved。
        """
        if self.verification_status == PENDING_VERIFICATION:
            assert self.result == "", (
                "红线违规：pending 态 result 必须为空串（不得产出真实工程数值）"
            )
        assert self.verification_status in (
            PENDING_VERIFICATION,
            "approved",
            "invalid_structure",
        ), f"未知 verification_status: {self.verification_status!r}"
```

**关键决策**：
- `INTERFACE` 用**类级常量**（`type(self).INTERFACE` 取值），避免实例字段污染 `as_interface()` 四键与 `as_full()` 结构。
- `enforce_redline()` 仅校验 pending 态红线（result 空 + status pending），不限制未来 `approved` 态（那由 validator 双签链控制，本 Sprint 不触达）。
- 基类**不**改变任何默认值，确保子类构造零差异。

---

## 3. 继承方案（五模块改造）

每个子类改为：
```python
from agents.engineering.calc.base import EngineeringCalculationResult

@dataclass
class WindPressureResult(EngineeringCalculationResult):
    INTERFACE: str = WIND_PRESSURE_INTERFACE
```
并**删除**子类内重复的九字段声明、重复的 `as_interface()` / `as_full()` 方法体。

**保留项**：
- 类名不变（`WindPressureResult` 等）→ `calc/__init__.py` 导出与所有调用方零改动。
- `WIND_PRESSURE_INTERFACE` 等模块级常量保留（供 `INTERFACE` 赋值 + 既有代码引用）。
- `calculate()` 返回 `XxxResult(...)` 的 9 关键字参数**不变**（基类已提供同名字段）。

**导入调整**：子类文件顶部新增 `from agents.engineering.calc.base import EngineeringCalculationResult`；`from agents.engineering.validation import PENDING_VERIFICATION` 仍可保留或改由基类提供（保留无害，避免不必要扩散改动）。本次选择**保留** `validation` 导入与 `field`/`dataclass` 导入（若子类不再定义字段，`dataclass`/`field` 导入可能 unused → 需 Ruff 检查；为稳妥，子类仍保留 `@dataclass` 装饰器，删除字段后 `field` 在子类不再使用 → 删除 `field` 导入，`dataclass` 装饰子类仍需保留）。

> 注意：子类用 `@dataclass` + 继承 + 仅声明 `INTERFACE` 常量。`@dataclass` 作用于子类时，若无字段则生成空 `__init__` 继承基类字段 —— 验证：Python `@dataclass` 子类继承父类字段正常，构造传 9 关键字参数有效。

---

## 4. 兼容策略

| 关注点 | 策略 | 验证 |
|---|---|---|
| 类名 / 导入 | 不变 | `calc/__init__.py` 不改 |
| `as_interface()` 四键 | 基类实现，逐字等同 | 既有 5 单测断言不改即过 |
| `as_full()` 八字段 + interface | 基类实现，`interface=type(self).INTERFACE` | 既有断言 `as_full()["interface"]==Xxx_INTERFACE` 仍成立 |
| `calculate()` 构造 | 9 关键字参数不变 | 计算器无改动 |
| Agent 契约 | `agent.py` 调 `.as_interface()` → 不变 | `test_engineering.py` 不改 |
| validator | `validation.py` 不依赖 Result 内部结构 | 不改动 |
| ReportGenerator | Phase 3.2.2 才接线，本 Sprint 不触 | N/A |

**零破坏性判据**：若 `as_interface()` 与 `as_full()` 的**输出字节结构**与重构前完全一致，则 `agent.py` / `validation.py` / ReportGenerator 无需改动 —— 本设计保证成立。

---

## 5. 测试迁移方案

- **既有各模块单测**（风压 / 玻璃 / 型材 / 五金 / 安装风险）：**不改断言**，仅验证继承后字段/方法仍可用（类名不变 → import 不变）。
- **新增 `tests/agents/test_result_base.py`**（五类断言）：
  1. 基类字段：直接构造 `EngineeringCalculationResult()` 九字段默认值正确。
  2. `as_interface()` 四字段：恰好 `result/confidence/evidence/verification_status`，无多余键。
  3. `as_full()` 结构：含 8 扩展字段 + `interface==""`（基类默认）。
  4. `enforce_redline()`：pending 态 result 空 → 通过；result 非空 → 抛 AssertionError；非 pending 合法 status → 通过。
  5. 五模块兼容：以各 `XxxResult` 构造并断言 `isinstance(res, EngineeringCalculationResult)` + `as_interface()` 四键 + `as_full()["interface"]==Xxx_INTERFACE` + `calculate()` 返回实例类型正确。
- **CI 门禁**：`bash scripts/ci/local_ci.sh` → 8/8 PASS；coverage ≥88.34%。

---

## 6. 风险分析

| 编号 | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R-321-1 | `@dataclass` 子类继承字段语义（default_factory 复用语义） | 低 | 子类仅声明 `INTERFACE` 常量不重定义字段，继承基类字段；`calculate()` 9 关键字构造已验证 |
| R-321-2 | `type(self).INTERFACE` 取值遗漏子类覆盖 | 低 | 子类显式 `INTERFACE: str = Xxx_INTERFACE`；新增测试断言 `as_full()["interface"]` |
| R-321-3 | Ruff F401（子类删除字段后 `field`/`dataclass` unused） | 中 | 子类保留 `@dataclass`，删除 unused `field` 导入；提交前 Ruff 校验 |
| R-321-4 | 既有断言因字段顺序/字节差异破坏 | 低 | 输出为 dict，键集合一致即等价；既有测试断言键名非顺序 |
| R-321-5 | 红线漂移（基类被误改默认值） | 低 | `enforce_redline()` 闸门 + 新增测试固化默认值 |
| R-321-6 | 误触 `engineering_enabled` / 填真实参数 | 极低 | 本 Sprint 不碰 `config`/`verified.json`/计算逻辑；`enforce_redline` 仅校验 pending 红线 |

---

## 7. 红线自检（设计阶段）
- 未编码（本文件为设计确认）；未修改 `calc/*.py` / `agent.py` / `validation.py` / `verified.json`。
- 未填写真实工程参数；未开启 `engineering_enabled`；未输出 `engineering_approved`。
- 全文 `pending_verification`；防编造扫描预期 0 命中（业务词不携带未验证真实数字）。

**下一步**：主理人确认本设计后，进入实现（新增 `base.py` + 五子类改造 + 新增测试 + 跑 CI）。本设计阶段已停止。
