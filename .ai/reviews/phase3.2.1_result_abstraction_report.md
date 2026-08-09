# BOIP Phase 3.2.1 — EngineeringCalculationResult 抽象与红线集中（完成报告）

> **身份**：BOIP AI 架构工程师
> **Sprint**：Phase 3.2 Sprint 3.2.1（产品化第一阶段：结果统一抽象）
> **阶段定位**：重构（抽象基类，消除重复），**非新增工程能力、非新增计算逻辑**。
> **状态**：✅ DONE（待主理人验收）
> **红线守约**：① 未改工程计算逻辑；② 未改五模块输入输出语义；③ 未填真实工程参数；④ 未改 `verified.json`；⑤ 未开 `engineering_enabled`；⑥ 未输出 `engineering_approved`；全程 `pending_verification`。

---

## 1. 修改文件

### 新增
- `agents/engineering/calc/base.py` — `EngineeringCalculationResult` 基类（9 字段 + `as_interface()` + `as_full()` + `enforce_redline()` 红线闸门；`INTERFACE: ClassVar[str]` 接口标识）。

### 迁移（五子类继承基类，删重复）
- `agents/engineering/calc/wind_pressure.py` — `WindPressureResult(EngineeringCalculationResult)`，删重复字段与方法，仅留 `INTERFACE = WIND_PRESSURE_INTERFACE`。
- `agents/engineering/calc/glass_safety.py` — `GlassSafetyResult(EngineeringCalculationResult)`，同上。
- `agents/engineering/calc/profile.py` — `ProfileResult(EngineeringCalculationResult)`，同上。
- `agents/engineering/calc/hardware.py` — `HardwareResult(EngineeringCalculationResult)`，同上。
- `agents/engineering/calc/installation_risk.py` — `InstallationRiskResult(EngineeringCalculationResult)`，同上。
- `agents/engineering/calc/__init__.py` — **未改动**（类名 / 导出不变，调用方零改动）。

### 测试
- `tests/agents/test_result_base.py` — 新增（21 用例）：基类字段 / `as_interface` 四键 / `as_full` 结构 / `enforce_redline` 四类 / 五模块兼容（继承 + interface + `calculate()` 返回类型）+ 上游闸门白盒分支（profile/glass 非 Mapping 守卫 + approved 上游 provenance 分支）+ `PendingEngineeringValidation` 空 interface 校验。

---

## 2. 架构影响

- **职责下沉**：五 Result 共享的 9 字段 + 两方法集中到 `EngineeringCalculationResult`；子类仅声明接口标识 `INTERFACE`。消除约 200 行重复（5 × 40 行）。
- **红线集中**：`enforce_redline()` 闸门固化「pending 态 result 必须为空串 + verification_status 必须 pending」不变量；未来误填真实数值或误置 approved 将被断言拦截。
- **字节兼容**：`as_interface()` 输出四键、`as_full()` 输出八字段 + `interface` 标识，与重构前**逐字一致**（已用既有 5 单测 + 新增兼容测试验证）。
- **零破坏性**：`agent.py` / `validation.py` / `report/generator.py` / `calc/__init__.py` 均未改动；Agent 五接口契约、validator 双签流程、ReportGenerator 徽标逻辑不受影响。
- **继承安全**：`INTERFACE` 用 `ClassVar` 防止成为 dataclass 字段，避免污染 `as_interface()` 四键；`type(self).INTERFACE` 取值，子类覆盖正确。

---

## 3. 测试结果

`bash scripts/ci/local_ci.sh` → **8/8 全绿**：

| 口径 | 结果 |
|---|---|
| Backend pytest | **354 passed**，coverage **88.38%**（≥88.34% 达标，较 Final Integration 333→354 净增 21） |
| Frontend Jest | **29 passed**@93.15% |
| Ruff | 0 违规 |
| ESLint | 0 error |
| Alembic | 双向通过 |
| Seed | 通过 |
| 防编造扫描 | 0 命中 |
| 硬编码扫描 | 0 命中 |

> 覆盖率注：重构初期因删除重复方法净语句略减，覆盖率短暂降至 88.26%；通过补充上游闸门白盒分支测试（不产真实数值、不触 config）恢复至 **88.38%**，稳定超过 Final Integration 基线 88.34%。

---

## 4. 风险

| 编号 | 风险 | 处置 / 现状 |
|---|---|---|
| R-321-1 | `@dataclass` 子类继承字段语义 | 子类仅声明 `INTERFACE` 常量，继承基类字段；`calculate()` 9 关键字构造已验证 OK |
| R-321-2 | `type(self).INTERFACE` 取值遗漏 | 子类显式 `INTERFACE = Xxx_INTERFACE`；新增测试断言 `as_full()["interface"]` |
| R-321-3 | Ruff F401（删除字段后 `field` unused） | 子类删除未用 `field` 导入，提交前 Ruff 校验 0 违规 |
| R-321-4 | 既有断言因字节差异破坏 | `as_interface()`/`as_full()` 输出键集合一致；既有 5 单测全过 |
| R-321-5 | 红线漂移（基类默认值被误改） | `enforce_redline()` 闸门 + 新增测试固化默认值与 pending 空 result 约束 |
| R-321-6 | 误触 enabled / 填真实参数 | 本 Sprint 未碰 `config`/`verified.json`/计算逻辑；上游闸门白盒测试仅注入 `verification_status` 标识符，不产真实数值、结果仍 pending |

---

## 5. 兼容性验证

- ✅ 五 Result `isinstance(res, EngineeringCalculationResult)` 成立。
- ✅ 五 Result `as_interface()` 输出 == `{result:"", confidence:"pending_verification", evidence:"", verification_status:"pending_verification"}`（与重构前一致）。
- ✅ 五 Result `as_full()["interface"]` == 各自接口常量（`wind_pressure`/`glass_safety`/`profile`/`hardware`/`installation_risk`）。
- ✅ 五计算器 `calculate({})` 返回对应子类实例，`verification_status` 恒 pending。
- ✅ `calc/__init__.py` 导出与所有调用方（agent / 既有测试）零改动。
- ✅ 既有各模块单测（风压 / 玻璃 / 型材 / 五金 / 安装风险）**全过**，断言未改。

---

## 6. 红线自检（实施阶段）
- ✅ 未修改工程计算逻辑（`calculate()` 结构装配未动）。
- ✅ 未修改五模块输入输出语义（字段 / 方法 / 构造参数一致）。
- ✅ 未填写真实工程参数（`E-TH-01~06` 仍 `value=null`；上游闸门白盒测试仅注入标识符，不产数值）。
- ✅ 未修改 `verified.json`。
- ✅ 未开启 `engineering_enabled`（仍 false）。
- ✅ 未输出 `engineering_approved`（计算器结果恒 pending）。
- ✅ 全 `pending_verification`；防编造 / 硬编码扫描 0 命中。

**下一步**：等待主理人验收；验收通过 + 授权后进入 Sprint 3.2.2（ReportGenerator 工程章节接线）。本 Sprint 不进入 ReportGenerator。
