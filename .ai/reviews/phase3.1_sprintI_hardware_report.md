# Phase 3.1 Sprint I — Hardware（五金）工程模块编码完成报告

- **生成**：2026-07-30（Phase 3.1 Sprint I 实现阶段）
- **身份**：BOIP AI 工程计算负责人
- **状态**：✅ CODING_DONE（结构化装配，不产真实数值；等待主理人验收）
- **依赖**：Sprint A 可信审核基础设施 + Sprint G 型材编码（上游 profile 可信态供给方）+ Sprint H 五金设计（本阶段落地依据）
- **红线守约**：`engineering_enabled=false`、零真实五金承载值/锁点数量/寿命次数/型号规格、零规范条款号、未改 `verified.json`、未输出 `engineering_approved`、全 `pending_verification`

---

## 1. 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `agents/engineering/calc/hardware.py` | 新增 | `HardwareCalculator` + `HardwareResult`（结构同构 `WindPressureResult`/`GlassSafetyResult`/`ProfileResult`：四字段 + intermediate/provenance/threshold_refs/gaps/sign_off_id）；不产真实数值；含 profile 上游审核态跨模块降级（任务4，禁止重算型材受力） |
| `agents/engineering/rules/hardware_rules.py` | 新增 | 符号级公式体系（`F_demand=h(...)` / `F_demand<=F_hardware` / `lock_system_adequate` / `connection_reliable` / `cycle_check`）+ 变量关系 + 数据来源映射；**零真实工程常数**（任务2） |
| `agents/engineering/calc/__init__.py` | 修改 | 导出 `HARDWARE_INTERFACE` / `HardwareCalculator` / `HardwareResult` |
| `agents/engineering/rules/__init__.py` | 修改 | 导出 `hardware_rules` |
| `agents/engineering/agent.py` | 修改 | `analyze_hardware()` 由 skeleton 升级为调用 `HardwareCalculator`；import 新增 `HardwareCalculator`；模块 docstring 补 Sprint I 说明；**四字段契约与 validator 流程零改动** |
| `tests/agents/test_hardware.py` | 新增 | 13 个新用例（见第 3 节） |
| `.ai/reviews/phase3.1_sprintI_hardware_report.md` | 新增 | 本报告 |
| `.ai/project_status.json` / `.ai/roadmap_v2.md` | 修改 | SSOT 同步（phase_3_1 → SPRINT_I_CODING_DONE + 3.1.13） |

---

## 2. 架构影响

### 2.1 计算单元同构
Hardware 计算单元与 Wind Pressure（Sprint C）、Glass Safety（Sprint E）、Profile（Sprint G）完全同构：
- 统一 `HardwareResult`（`result`/`confidence`/`evidence`/`verification_status` 四字段 + `intermediate`/`provenance`/`threshold_refs`/`gaps`/`sign_off_id` 扩展字段）；
- `as_interface()` 返回精确四键（兼容 `EngineeringAgent` 接口契约与既有 `test_engineering.py::test_unified_output_structure_for_each_interface` 断言）；
- `as_full()` 返回八扩展字段 + `interface="hardware"` 标识。

### 2.2 Agent 接入零契约改动
`analyze_hardware()` 内部仅从 `build_skeleton_output()` 切换为 `HardwareCalculator().calculate(context_data).as_interface()`；`invoke()` 调度表、`ANALYSIS_INTERFACES`、validator 流程**完全不变**。

### 2.3 跨模块链路（任务4，降级传导，与 Glass/Profile 同构但上游不同）
`HardwareCalculator.calculate` 读取 `context_data["profile_result"]`，新增 `_is_profile_approved()` 闸门（**不同于** Glass/Profile 读 wind_pressure）：
- 上游 `profile.verification_status == engineering_approved` → 标记 `provenance["profile_result"]="verified"`（仍不填数值）；
- 否则 → 强制 `pending_verification` 并登记 `gaps: ["profile_result: upstream_pending"]`。
- **红线硬约束**：本模块**禁止**自行计算型材受力——型材受力归属 Profile 模块，Hardware 仅依 profile 审核态做可信性判定，绝不消费 profile 的 intermediate 数值重算。

### 2.4 阈值绑定
`get_interface_thresholds("hardware")` → `("E-TH-04",)`（五金承载力，`applies_to:["hardware"]` 已占位）；`hardware_rules.VARIABLE_THRESHOLD_MAP` 将 `F_hardware`/`cycle_life` 两变量绑定 E-TH-04。

### 2.5 工程链路位置
本模块在链路 **Wind → Profile → Hardware** 末端（Glass 独立并列）；消费 profile 审核态，是除 glass/profile 外第三个落地结构化装配的模块。

---

## 3. 测试结果

### 3.1 新增单元测试（`tests/agents/test_hardware.py`，13 passed）
覆盖用户要求的 8 类场景 + 序列化：
1. **E-TH-04 缺失** → `test_e_th_missing_yields_pending`（阈值库空 → 恒 pending，gaps 登记 E-TH-04 pending）
2. **profile pending 传导** → `test_profile_pending_propagation` + `test_profile_approved_but_forbids_self_force_calc`（上游未 approved → 强制 pending + `profile_result: upstream_pending`；上游 approved 时仍不重算型材受力、不填数值）
3. **inferred 输入** → `test_inferred_input_stays_pending`（全 inferred → pending，且不伪造 F_hardware/F_demand/lock_system/cycle_life/load_check 数值）
4. **输出结构** → `test_output_structure_four_fields` + `test_hardware_result_serializers`（四字段 + 八扩展字段 + interface 标识）
5. **threshold_refs** → `test_threshold_refs_align_with_interface_map`（与 `get_interface_thresholds` 一致）
6. **evidence** → `test_evidence_carries_formula_and_pending`（含公式来源 + E-TH-04 + pending 标注，无真实数值）
7. **防编造扫描** → `test_fabrication_scan_clean_on_hardware_sources`（源码 hardware.py/hardware_rules.py/本测试零命中）+ `test_fabrication_scan_catches_fabricated_number`（临时文件伪造防腐等级数值触发，验证扫描有效）
8. **engineering_enabled=false** → `test_pending_propagation_through_validator`（注入 enabled=True + 缺双签仍 pending）+ `test_pending_propagation_through_agent_invoke` + `test_unified_interface_keys_for_hardware`（Agent 接口恒四字段）

### 3.2 全量 CI（`bash scripts/ci/local_ci.sh` → 8/8 PASS）
| Step | 结果 |
|---|---|
| 1 Ruff | ✅ |
| 2 Backend pytest | ✅ **311 passed @ 88.09%**（≥87.90% 达标，298→311 +13 用例，覆盖率反升） |
| 3 ESLint | ✅ |
| 4 Jest | ✅ 29 passed @ 93.15% |
| 5 Alembic | ✅ |
| 6 Seed | ✅ |
| 7 防编造扫描 | ✅ **全仓 0 命中**（含新增 hardware.py/hardware_rules.py/test_hardware.py） |
| 8 硬编码扫描 | ✅ 0 命中 |

---

## 4. 技术债变化

### 4.1 清偿
- 五大工程模块之四（wind_pressure / glass_safety / profile / hardware）均已落地结构化装配，统一四字段 + 扩展字段契约在四个模块间完全对齐，可复制模式成熟。
- 跨模块降级传导逻辑在 glass（读 wind）、profile（读 wind）、hardware（读 profile）三处落地，验证通过，模式一致但上游各异。

### 4.2 新增 / 存续
- **存续债**：`hardware` 仍 `pending_verification`——真实数值依赖 E-TH-04 双签 + `engineering_enabled=true` + 可信 profile，三者未满足前不得 approved（符合红线）。
- **存续债**：下游 `installation_risk` 仍为骨架（五大模块之五），待各自 Sprint 实施。
- **无新增代码债**：无临时 hack、无 TODO 遗留、无重复实现。

---

## 5. 风险

| ID | 风险 | 影响 | 缓解（已落地） |
|---|---|---|---|
| R-HW-1 | E-TH-04 长期未双签 | hardware 永久 pending | 专家双签流程 + review_log 追踪；CI 防编造闸门 |
| R-HW-2 | 误将型材受力在本模块重算 | 越权编造型材结论 | 红线硬约束：仅依 profile 审核态判定，绝不消费其数值重算（已测试） |
| R-HW-3 | 上游 profile 不可信被当确定输入 | 编造五金选型/承载结论 | 降级传导；calculator 显式检查 profile 审核态（已测试 `profile_result: upstream_pending`） |
| R-HW-4 | inferred 输入直接驱动确定性结论 | 编造工程判断 | field_provenance 判定：inferred → pending（已测试） |
| R-HW-5 | 写死真实锁点数量/寿命次数/型号规格 | 违反红线第 2/3/4 项 | 规则层/计算层全符号占位，零实数；防编造 + 硬编码双扫描门禁 |
| R-HW-7 | engineering_enabled 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |

---

## 6. 红线自检（全程强制）

- ✅ `engineering_enabled=false` 未开启；
- ✅ `result` 恒空串；`intermediate` 各量（`F_hardware`/`F_demand`/`lock_system`/`cycle_life`/`load_check` 等）`value=null`；
- ✅ **未改 `verified.json`**（E-TH-04 仍 `value=null/verified=false`）；
- ✅ **未输出 `engineering_approved`**（注入 `enabled=true` + 缺双签仍 pending，三重保险：enabled=false + 数据饥饿 + 上游 profile 不可信）；
- ✅ 全参数 `pending_verification`；
- ✅ **未编写任何真实五金承载值/锁点数量/寿命次数/型号规格/规范条款号**（规则层仅符号级）。

---

## 7. 阶段门（Gate）

- **当前**：`phase_3_1 = SPRINT_I_CODING_DONE`，所有改动**未 commit**，等主理人验收。
- **下一步**：进入 Installation Risk 模块（五大模块之五）前，须主理人授权 + 六门槛全满足（阈值双签 / Vision 调优 / 测试通过 / 审核链跑通 / CI 8-8 / 主理人授权）+ 继续守 `engineering_enabled=false`。
- **严禁**：未验收即进入 Installation Risk，或任何绕过红线（填真实值 / 开 enabled / 改 verified=true / 输出 approved）的动作。
