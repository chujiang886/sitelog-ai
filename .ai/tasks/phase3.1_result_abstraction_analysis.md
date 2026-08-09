# Phase 3.1 Final Integration — 五 Result 模型抽象分析（Task 1）

> 身份：BOIP AI 工程总架构负责人
> 阶段：Phase 3.1 Final Integration（集成 / 验证 / 统一 / 收口，非新增能力）
> 红线：本分析**不重构**代码，仅评估抽象 `EngineeringCalculationResult` 的收益 / 风险 / 迁移方案。
> 状态：`pending_verification`（所有工程结论未双签、engineering_enabled=false）。

---

## 0. 分析范围与依据

实读五个计算单元的结果模型：

| 模块 | 文件 | Result 类 | interface 常量 |
|------|------|-----------|----------------|
| 风压 | `agents/engineering/calc/wind_pressure.py` | `WindPressureResult` | `WIND_PRESSURE_INTERFACE = "wind_pressure"` |
| 玻璃安全 | `agents/engineering/calc/glass_safety.py` | `GlassSafetyResult` | `GLASS_SAFETY_INTERFACE = "glass_safety"` |
| 型材 | `agents/engineering/calc/profile.py` | `ProfileResult` | `PROFILE_INTERFACE = "profile"` |
| 五金 | `agents/engineering/calc/hardware.py` | `HardwareResult` | `HARDWARE_INTERFACE = "hardware"` |
| 安装风险 | `agents/engineering/calc/installation_risk.py` | `InstallationRiskResult` | `INSTALLATION_RISK_INTERFACE = "installation_risk"` |

---

## 1. 现状：五个 Result 模型的结构同构性

逐字段比对五个 `@dataclass`，确认**高度同构**：

```text
字段（9 个，完全一致）：
  result: str = ""
  confidence: str = PENDING_VERIFICATION
  evidence: str = ""
  verification_status: str = PENDING_VERIFICATION
  intermediate: dict = field(default_factory=dict)
  provenance: dict = field(default_factory=dict)
  threshold_refs: list = field(default_factory=list)
  gaps: list = field(default_factory=list)
  sign_off_id: str | None = None

方法（2 个，完全一致）：
  as_interface() -> dict   # 精确四键 {result, confidence, evidence, verification_status}
  as_full() -> dict        # 八字段 + interface 标识（interface 值取各自模块常量）
```

**差异仅一处**：`as_full()` 中 `"interface"` 字段的值来自各模块的接口常量（wind_pressure / glass_safety / profile / hardware / installation_risk）。其余字段、默认值、方法实现逐字相同。

结论：**五个 Result 是「同一结构 + 仅 interface 标签不同」的近似克隆**，存在约 40 行 × 5 = 200 行的重复。

---

## 2. 抽象收益（Benefits）

### B-1. 消除重复、集中契约
引入基类 `EngineeringCalculationResult` 后，`as_interface()`（四键契约）与九个共享字段下沉到基类，五个子类只需声明 `interface` 常量 + `as_full()` 的 interface 注入。新增第六个模块时，只需 `class XxxResult(EngineeringCalculationResult): INTERFACE = "xxx"`。

### B-2. 红线不变量单一化
当前红线不变量（`result=""`、`verification_status=PENDING_VERIFICATION` 默认、`sign_off_id=None`）分散在五个文件。抽象后集中到基类，**一处定义、五处继承**，降低「某模块误改默认值导致输出 approved 数值」的风险。

### B-3. 契约校验可统一
可对基类增加 `@property` 或 `validate_contract()`，在构造/导出时断言 `as_interface()` 恰好四键；未来 Phase 3.2 真实数值接入时，可在基类层统一拦截「未双签却非空 result」的违规输出。

### B-4. 利于编排层（Orchestrator）类型化
Phase 3.2 若引入跨模块编排（把 `as_full()` 结果线程给下游），基类可作为统一的 `Sequence[EngineeringCalculationResult]` 类型提示，下游消费代码更清晰。

---

## 3. 抽象风险（Risks）

### R-1. 破坏性迁移（高）
五个 `calc` 模块、均引用各自 `XxxResult`；`agent.py` 的 `analyze_*` 调用 `.as_interface()` / `.as_full()`；既有单测（`test_wind_pressure.py` / `test_glass_safety.py` / `test_profile.py` / `test_hardware.py` / `test_installation_risk.py`）直接 import 这些类并断言字段。任何基类改动都需同步 五 个模块 + 五 个单测 + `calc/__init__.py` 导出，回归面大。

### R-2. dataclass 继承 + default_factory 细节
`@dataclass` 子类若重定义字段，需注意 `field(default_factory=dict)` 在继承链上的复用语义；`as_full()` 中 `interface` 为**类级常量**而非实例字段，基类方法需以 `type(self).INTERFACE` 取值，存在拼写/遗漏风险。

### R-3. 跨模块降级逻辑不在基类
各计算器的跨模块闸门（`_is_wind_pressure_approved` / `_is_profile_approved` / `_is_upstream_approved`）是**模块特有**逻辑，不属于 Result 模型；抽象 Result 不会触碰这部分，故抽象对"pending 传导"无正面/负面影响——属于正交关注点。

### R-4. 过度设计（YAGNI）
当前五个 Result 结构稳定、无差异化需求；克隆重复属「浅重复」，抽象收益（B-1~B-4）在 Phase 3.1 收口期并非瓶颈。**Final Integration 阶段定位是集成/验证/收口，禁止新增能力**，抽象重构与定位冲突。

### R-5. 测试/CI 扰动
重构需在 Final Integration 的 CI（8/8、coverage≥88.29%）窗口内完成，且不能引入任何真实参数或改变 `as_interface()` 输出字节结构（否则破坏 Agent 契约与既有单测）。改动成本高、收益递延。

---

## 4. 迁移方案（若 Phase 3.2 采纳）

> 以下为**前瞻性方案草案**，本阶段不执行。

### 4.1 基类定义（置于 `agents/engineering/calc/base.py`）
```python
from dataclasses import dataclass, field
from typing import Any

from agents.engineering.validation import PENDING_VERIFICATION

@dataclass
class EngineeringCalculationResult:
    result: str = ""
    confidence: str = PENDING_VERIFICATION
    evidence: str = ""
    verification_status: str = PENDING_VERIFICATION
    intermediate: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, str] = field(default_factory=dict)
    threshold_refs: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    sign_off_id: str | None = None

    INTERFACE: str = ""  # 子类覆盖

    def as_interface(self) -> dict[str, Any]:
        return {
            "result": self.result,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "verification_status": self.verification_status,
        }

    def as_full(self) -> dict[str, Any]:
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
```

### 4.2 子类改造（以 WindPressure 为例）
```python
@dataclass
class WindPressureResult(EngineeringCalculationResult):
    INTERFACE: str = "wind_pressure"   # 或用类级常量覆盖
```
其余四模块同构改造；删除各自重复的 `as_interface` / `as_full`。

### 4.3 校验闸门（可选增强）
基类可加：
```python
def enforce_redline(self) -> None:
    assert self.verification_status == PENDING_VERIFICATION
    # result 在 pending 态必须为空串（Phase 3.1 红线）
```
在 `AgentResult` 装配前调用，防未来误填。

### 4.4 迁移步骤
1. 新增 `calc/base.py` 基类（不删旧类）。
2. 五个子类改为继承 + 删重复方法，保留 `INTERFACE` 常量。
3. 更新 `calc/__init__.py` 导出（类名不变，调用方零改动）。
4. 既有 5 个单测**不改断言**（仅验证字段/方法仍可用），新增 `test_result_base.py` 验证契约一致性。
5. 跑 `bash scripts/ci/local_ci.sh`，确认 8/8、coverage 不低于迁移前。
6. 若 `as_interface()` 输出字节结构不变，则 `agent.py` / `validation.py` / ReportGenerator 无需改动。

---

## 5. 结论与建议

| 维度 | 评估 |
|------|------|
| 是否必要（Phase 3.1 收口） | **否** — 现状结构稳定、契约一致，重复为浅重复 |
| 是否安全（不破坏红线） | 可行，但需在 CI 窗口内验证 `as_interface()` 字节不变 |
| 推荐时机 | **Phase 3.2**（真实数值接入前，借重构统一契约闸门） |
| 本阶段动作 | **仅记录分析，不重构** |

**建议**：Phase 3.1 Final Integration 不做 Result 抽象重构；将本分析作为 Phase 3.2 技术债清理项（见最终联调报告「技术债变化 / Phase 3.2 建议」）。本阶段继续以「五 Result 同构、契约一致、pending 全传导」作为验收结论。

---

## 6. 红线自检

- 未修改任何 `calc/*.py` / `agent.py` / `validation.py` / `verified.json`。
- 未开启 `engineering_enabled`（仍 false）。
- 未写真实工程参数 / 规范条款号；未输出 `engineering_approved`。
- 全文 `pending_verification`；本分析为设计文档，非实现，不进入 CI 执行路径。
- 防编造扫描：本文件业务词（风压 / 楼层 / 壁厚 / 评分权重 / 使用寿命 / 防腐等级）均不携带未验证真实数字，且全程 `pending_verification` 标注；扫描预期 0 命中。
