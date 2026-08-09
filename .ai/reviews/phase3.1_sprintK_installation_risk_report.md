# Phase 3.1 Sprint K — Installation Risk（安装施工风险）工程模块编码完成报告

- **生成**：2026-07-30（Phase 3.1 Sprint K 实现阶段）
- **身份**：BOIP AI 工程计算负责人
- **状态**：✅ CODING_DONE（结构化装配，不产真实数值；等待主理人验收）
- **依赖**：Sprint A 可信审核基础设施 + Sprint E 玻璃安全编码（上游玻璃重量供给方）+ Sprint G 型材编码（上游型材条件供给方）+ Sprint I 五金编码（上游五金条件供给方）+ Sprint J 安装风险设计（本阶段落地依据）
- **红线守约**：`engineering_enabled=false`、零真实风险分数/承载参数/施工安全距离/施工等级、零规范条款号、未改 `verified.json`、未输出 `engineering_approved`、全 `pending_verification`

---

## 1. 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `agents/engineering/calc/installation_risk.py` | 新增 | `InstallationRiskCalculator` + `InstallationRiskResult`（结构同构 `WindPressureResult`/`GlassSafetyResult`/`ProfileResult`/`HardwareResult`：四字段 + intermediate/provenance/threshold_refs/gaps/sign_off_id）；不产真实数值；含 glass_safety/profile/hardware 三上游审核态跨模块降级（任务4，禁止重算玻璃重量/型材受力/五金承载） |
| `agents/engineering/rules/installation_rules.py` | 新增 | 符号级公式体系（`Risk_total=r(...)` / `lift_check` / `safety_check` / `env_check` / `personnel_check` / `process_check`）+ 变量关系 + 数据来源映射；**零真实工程常数**（任务2） |
| `agents/engineering/calc/__init__.py` | 修改 | 导出 `INSTALLATION_RISK_INTERFACE` / `InstallationRiskCalculator` / `InstallationRiskResult` |
| `agents/engineering/rules/__init__.py` | 修改 | 导出 `installation_rules` |
| `agents/engineering/agent.py` | 修改 | `analyze_installation_risk()` 由 skeleton 升级为调用 `InstallationRiskCalculator`；import 新增 `InstallationRiskCalculator`；模块 docstring 补 Sprint K 说明；**四字段契约与 validator 流程零改动** |
| `tests/agents/test_installation_risk.py` | 新增 | 16 个新用例（见第 3 节） |
| `.ai/reviews/phase3.1_sprintK_installation_risk_report.md` | 新增 | 本报告 |
| `.ai/project_status.json` / `.ai/roadmap_v2.md` | 修改 | SSOT 同步（phase_3_1 → SPRINT_K_CODING_DONE + 3.1.15） |

---

## 2. 架构影响

### 2.1 计算单元同构
Installation Risk 计算单元与 Wind Pressure（Sprint C）、Glass Safety（Sprint E）、Profile（Sprint G）、Hardware（Sprint I）完全同构：
- 统一 `InstallationRiskResult`（`result`/`confidence`/`evidence`/`verification_status` 四字段 + `intermediate`/`provenance`/`threshold_refs`/`gaps`/`sign_off_id` 扩展字段）；
- `as_interface()` 返回精确四键（兼容 `EngineeringAgent` 接口契约与既有 `test_engineering.py::test_unified_output_structure_for_each_interface` 断言）；
- `as_full()` 返回八扩展字段 + `interface="installation_risk"` 标识。

### 2.2 Agent 接入零契约改动
`analyze_installation_risk()` 内部仅从 `build_skeleton_output()` 切换为 `InstallationRiskCalculator().calculate(context_data).as_interface()`；`invoke()` 调度表、`ANALYSIS_INTERFACES`、validator 流程**完全不变**。

### 2.3 跨模块链路（任务4，末端聚合，三上游降级传导）
`InstallationRiskCalculator.calculate` 读取 `context_data["glass_safety_result"]` / `["profile_result"]` / `["hardware_result"]`，新增 `_is_upstream_approved()` 闸门（**区别于** Glass/Profile 读 wind_pressure、Hardware 读 profile——此处聚合三个上游）：
- 上游 `verification_status == engineering_approved` → 标记 `provenance["xxx_result"]="verified"`（仍不填数值）；
- 否则 → 强制 `pending_verification` 并登记 `gaps: ["glass_safety_result: upstream_pending" / "profile_result: upstream_pending" / "hardware_result: upstream_pending"]`。
- **红线硬约束**：本模块**禁止**自行计算玻璃重量/型材受力/五金承载——三者分别归属 glass_safety/profile/hardware 模块，installation_risk 仅依上游审核态做可信性判定，绝不消费其 intermediate 数值重算。

### 2.4 阈值绑定
`get_interface_thresholds("installation_risk")` → `("E-TH-05", "E-TH-06")`（腐蚀等级 + 安装风险矩阵，均 `applies_to:["installation_risk"]` 已占位）；`installation_rules.VARIABLE_THRESHOLD_MAP` 将 `env_risk`→E-TH-05、`Risk_total`/`lift_condition`/`personnel_risk`/`process_risk`/`D_safe`→E-TH-06。

### 2.5 工程链路位置
本模块是**链路末端聚合**：Glass（并列）/ Profile / Hardware 三上游结论汇入安装风险评级；自身仍需 E-TH-05/E-TH-06 双签 + `engineering_enabled=true` + 三上游可信 才转 approved。这是五大工程模块中最后一个完成结构化装配的模块。

---

## 3. 测试结果

### 3.1 新增单元测试（`tests/agents/test_installation_risk.py`，16 passed）
覆盖用户要求的 10 类场景：
1. **E-TH-05/E-TH-06 缺失** → `test_e_th_missing_yields_pending`（阈值库空 → 恒 pending，gaps 登记 E-TH-05/E-TH-06 pending）
2. **glass pending 传导** → `test_glass_pending_propagation`（上游未 approved → 强制 pending + `glass_safety_result: upstream_pending`）
3. **profile pending 传导** → `test_profile_pending_propagation`（上游未 approved → 强制 pending + `profile_result: upstream_pending`）
4. **hardware pending 传导** → `test_hardware_pending_propagation`（上游未 approved → 强制 pending + `hardware_result: upstream_pending`）+ `test_all_upstreams_approved_but_thresholds_pending`（三上游均 approved 时仍不重算/不填数值、E-TH 未签仍 pending）
5. **inferred 输入** → `test_inferred_input_stays_pending`（全 inferred → pending，且不伪造 Risk_total/D_safe/lift_condition/personnel_risk/env_risk/process_risk 数值）
6. **输出结构** → `test_output_structure_four_fields` + `test_installation_risk_result_serializers`（四字段 + 八扩展字段 + interface 标识）
7. **threshold_refs** → `test_threshold_refs_align_with_interface_map`（与 `get_interface_thresholds` 一致）
8. **evidence** → `test_evidence_carries_formula_and_pending`（含公式来源 + E-TH-05/E-TH-06 + pending 标注，无真实数值）
9. **防编造扫描** → `test_fabrication_scan_clean_on_installation_sources`（源码 installation_risk.py/installation_rules.py/本测试零命中）+ `test_fabrication_scan_catches_fabricated_number`（临时文件伪造防腐等级数值触发，验证扫描有效）
10. **engineering_enabled=false** → `test_pending_propagation_through_validator`（注入 enabled=True + 缺双签仍 pending）+ `test_pending_propagation_through_agent_invoke` + `test_unified_interface_keys_for_installation_risk`（Agent 接口恒四字段）+ `test_upstream_propagation_through_agent_invoke_all`（全链路 invoke 仍恒 pending）

### 3.2 全量 CI（`bash scripts/ci/local_ci.sh` → 8/8 PASS）
| Step | 结果 |
|---|---|
| 1 Ruff | ✅ |
| 2 Backend pytest | ✅ **327 passed @ 88.29%**（≥88.09% 达标，311→327 +16 用例，覆盖率递增） |
| 3 ESLint | ✅ |
| 4 Jest | ✅ 29 passed @ 93.15% |
| 5 Alembic | ✅ |
| 6 Seed | ✅ |
| 7 防编造扫描 | ✅ **全仓 0 命中**（含新增 installation_risk.py/installation_rules.py/test_installation_risk.py） |
| 8 硬编码扫描 | ✅ 0 命中 |

---

## 4. 技术债变化

### 4.1 清偿
- 五大工程模块（wind_pressure / glass_safety / profile / hardware / installation_risk）**全部**落地结构化装配，统一四字段 + 扩展字段契约在五个模块间完全对齐，可复制模式成熟。
- 跨模块降级传导逻辑在 glass（读 wind）、profile（读 wind）、hardware（读 profile）、installation_risk（读三上游）四处落地，验证通过，模式一致但上游各异。
- Phase 3.1 全部工程模块编制完成，进入最终联调前夜（验收 + 六门槛全满足后启动最终联调）。

### 4.2 存续
- **存续债**：installation_risk 仍 `pending_verification`——真实数值依赖 E-TH-05/E-TH-06 双签 + `engineering_enabled=true` + 三上游可信，四者未满足前不得 approved（符合红线）。
- **无新增代码债**：无临时 hack、无 TODO 遗留、无重复实现。

---

## 5. 风险

| ID | 风险 | 影响 | 缓解（已落地） |
|---|---|---|---|
| R-IR-1 | E-TH-05/E-TH-06 长期未双签 | installation_risk 永久 pending | 专家双签流程 + review_log 追踪；CI 防编造闸门 |
| R-IR-2 | 误将 Environment 实时气象当作风险判定 | 来源错误，结论失真 | 风险只来自上游产出与 E-TH-05/E-TH-06；代码审查锁死 |
| R-IR-3 | 上游 glass/profile/hardware_result 不可信却被当确定输入 | 编造风险可控结论 | 降级传导；calculator 显式检查三上游审核态（已测试 upstream_pending） |
| R-IR-4 | inferred 输入直接驱动确定性结论 | 编造工程判断 | field_provenance 判定：inferred → pending（已测试） |
| R-IR-5 | 跨模块耦合错误传导 | 上游错值污染 installation_risk | 降级传导；下游独立审核 |
| R-IR-6 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | Sprint J 防误显设计；状态 != approved 仅显 pending 占位 |
| R-IR-7 | engineering_enabled 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-IR-8 | 风险评级矩阵口径选择不当 | 适用边界错误 | Sprint J 审核点由专家在双签时确认；设计态不固化 |

---

## 6. 红线自检（全程强制）

- ✅ `engineering_enabled=false` 未开启；
- ✅ `result` 恒空串；`intermediate` 各量（`G_weight`/`H_floor`/`lift_condition`/`personnel_risk`/`env_risk`/`weather_impact`/`process_risk`/`Risk_total`/`D_safe` 等）`value=null`；
- ✅ **未改 `verified.json`**（E-TH-05/E-TH-06 仍 `value=null/verified=false`）；
- ✅ **未输出 `engineering_approved`**（注入 `enabled=true` + 缺双签仍 pending，四重保险：enabled=false + 数据饥饿 + 三上游不可信）；
- ✅ 全参数 `pending_verification`；
- ✅ **未编写任何真实风险分数/承载参数/施工安全距离/施工等级/规范条款号**（规则层仅符号级）。

---

## 7. 阶段门（Gate）

- **当前**：`phase_3_1 = SPRINT_K_CODING_DONE`，所有改动**未 commit**，等主理人验收。
- **下一步**：进入 Phase 3.1 最终联调前，须主理人授权 + 六门槛全满足（阈值双签 / Vision 调优 / 测试通过 / 审核链跑通 / CI 8-8 / 主理人授权）+ 继续守 `engineering_enabled=false`。
- **严禁**：未验收即进入最终联调，或任何绕过红线（填真实值 / 开 enabled / 改 verified=true / 输出 approved）的动作。
