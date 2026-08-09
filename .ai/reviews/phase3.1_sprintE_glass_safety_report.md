# Glass Safety 工程模块编码完成报告（Sprint E）

- **生成**：2026-07-30（Phase 3.1 Sprint E 编码实施）
- **身份**：BOIP AI 工程计算负责人
- **状态**：🟡 CODING_DONE（结构化装配完成，不产真实数值；**等待主理人验收，未进入 Profile**）
- **依赖**：Sprint A 可信基础设施 + Sprint B wind_pressure 设计 + Sprint C wind_pressure 编码（上游 w_k 供给方）+ Sprint D glass_safety 设计（本模块设计基线，pending_verification）
- **红线守约**：`engineering_enabled=false`；零真实玻璃厚度 / 零真实安全系数 / 零真实允许应力 / 零规范条款编号 / 未改 `verified.json` 为 true / 未输出 `engineering_approved`；全参数 `pending_verification`。

---

## 1. 修改文件清单

### 1.1 新增文件

| 文件 | 职责 |
|---|---|
| `agents/engineering/calc/glass_safety.py` | `GlassSafetyCalculator` + `GlassSafetyResult`（glass_safety 结构化装配；消费 wind_pressure 上游 w_k；跨模块降级） |
| `agents/engineering/rules/glass_rules.py` | 符号级公式体系 / 变量关系 / 数据来源映射（零真实常数） |
| `tests/agents/test_glass_safety.py` | 13 个新用例（见 §3） |

### 1.2 修改文件

| 文件 | 改动 |
|---|---|
| `agents/engineering/calc/__init__.py` | 导出 `GLASS_SAFETY_INTERFACE` / `GlassSafetyCalculator` / `GlassSafetyResult` |
| `agents/engineering/rules/__init__.py` | 导出 `glass_rules` |
| `agents/engineering/agent.py` | `analyze_glass_safety()` 由 skeleton 升级为调用 `GlassSafetyCalculator`；模块 docstring 补 Sprint E 说明 |
| `.ai/project_status.json` | `phase_3_1 → SPRINT_E_CODING_DONE` + 新增 `3.1.9` 条目；summary/blocking 同步（pending_verification） |
| `.ai/roadmap_v2.md` | 状态表补 Sprint E CODING_DONE（pending_verification） |

> 未触碰 `validation.py` / `threshold_loader.py` / `verified.json` / `config.yaml`；EngineeringAgent 四字段契约与 validator 调度流程零改动。

---

## 2. 架构影响

### 2.1 计算单元同构

`GlassSafetyResult` 与 `WindPressureResult` 完全同构（result / confidence / evidence / verification_status + 扩展 intermediate / provenance / threshold_refs / gaps / sign_off_id），`as_interface()` 精确四键、`as_full()` 八字段 + interface 标识。Agent 接口契约（`tests/agents/test_engineering.py::test_unified_output_structure_for_each_interface`）继续成立。

### 2.2 规则层同构

`glass_rules` 与 `wind_rules` 同构：`*_FORMULAS` / `*_VARIABLES` / `VARIABLE_THRESHOLD_MAP` + 三个描述函数。公式仅符号级（荷载—应力—校核结构），无真实系数 / 厚度 / 应力数值。

### 2.3 跨模块链路（任务4）

`GlassSafetyCalculator.calculate()` 读取 `context_data["wind_pressure_result"]`：
- 上游 `verification_status == engineering_approved` 且 `intermediate["w_k"].value` 非 None → 标记 w_k 可信（仍不填数值）；
- 否则 → 结论强制 `pending_verification` 并登记 `gaps: ["w_k: upstream_pending"]`。

该逻辑独立于 validator 单接口判定，实现"上游风压不可信 → 玻璃不得达标"的降级传导（§7.3 设计，pending_verification）。

### 2.4 validator 流程不变

`analyze_glass_safety()` 仍经 `invoke()` → `self._validator.validate(interface="glass_safety", payload=output)` 产出七字段审核链记录；validator 仍由 `ExpertBackedEngineeringValidation` 闸门叠加（结构合法 + 双签 + enabled=true 才 approved）。Agent 调度代码零改动。

---

## 3. 测试结果

`bash scripts/ci/local_ci.sh` → **8/8 PASS**（pending_verification）：

| Step | 结果 |
|---|---|
| 1 Ruff | ✅ |
| 2 Backend pytest | ✅ **285 passed @ 87.76%**（≥87.61% 达标，较 Sprint C 272→285 +13 用例，覆盖率 87.61%→87.76% 不降反升） |
| 3 ESLint | ✅ |
| 4 Jest | ✅ 29 passed @ 93.15% |
| 5 Alembic | ✅ |
| 6 Seed | ✅ |
| 7 防编造扫描 | ✅ 全仓 0 命中（新源码 + 文档 + SSOT） |
| 8 硬编码扫描 | ✅ 0 命中 |

### 3.1 新测试覆盖（13 用例，对应任务5 八类）

1. `test_d_th_missing_yields_pending` — D-TH-02 缺失 → pending + gap 登记；
2. `test_wind_pressure_pending_propagation` — 上游未 approved → pending + `w_k: upstream_pending`；
3. `test_wind_pressure_approved_but_unavailable_wk_still_pending` — 上游 approved 但 w_k 无取值 → 仍 pending（不伪造数值）；
4. `test_inferred_input_stays_pending` — inferred 输入 → 不伪造 sigma_g / sigma_allow / A_max；
5. `test_output_structure_four_fields` + `test_glass_safety_result_serializers` — 四字段 / 八字段序列化；
6. `test_threshold_refs_align_with_interface_map` — threshold_refs == `["D-TH-02"]`；
7. `test_evidence_carries_formula_and_pending` — evidence 含公式 + pending + D-TH-02，无具体数值；
8. `test_fabrication_scan_clean_on_glass_sources` + `test_fabrication_scan_catches_fabricated_number` — 防编造扫描（含扫描有效性反例）；
9. `test_pending_propagation_through_validator` + `test_pending_propagation_through_agent_invoke` + `test_unified_interface_keys_for_glass_safety` — `engineering_enabled=false` 闸门不可绕过（注入 True 仍 pending，无 approved）。

---

## 4. 技术债变化

| 项 | 状态 |
|---|---|
| 计算单元机制（calc/ 包） | 新增 glass 同构实现，与 wind 共用模式，未引入新债 |
| 规则层（rules/ 包） | 新增 glass_rules，符号级，零常数，未引入新债 |
| 防编造扫描覆盖 | 新源码 0 命中；跨模块降级逻辑增加显式 gaps 登记，可追溯性提升 |
| Agent 接口 | 零改动，契约稳定 |
| 测试覆盖 | +13 用例，backend 覆盖率 87.61%→87.76% |
| 遗留债 | 五大模块仍余 Profile / Hardware / Installation Risk 三接口为骨架；D-TH-02 / E-TH-01~06 仍 value=null（待双签） |

---

## 5. 风险分析（对照 Sprint D R-GS-1~R-GS-8）

| ID | 风险 | 本 Sprint 缓解 |
|---|---|---|
| R-GS-1 | D-TH-02 长期未双签 | 计算单元恒 pending；CI 防编造闸门持续锁死 |
| R-GS-2 | 误用 Environment 实时气象作玻璃荷载 | 荷载仅来自 wind_pressure 的 w_k；代码不读 Environment 实时气象 |
| R-GS-3 | 上游 w_k 不可信却当确定输入 | `_is_wind_pressure_approved` 显式检查 + `w_k: upstream_pending` 登记 |
| R-GS-4 | inferred 直接驱动确定性结论 | provenance 判定 inferred → pending（ADR-2.2.1 §7） |
| R-GS-5 | 跨模块错误传导 | 下游独立审核 + 降级传导，未依赖 validator 单接口判定 |
| R-GS-6 | PDF 误显"已验证"/数值 | 状态 != approved 仅显 pending 占位（设计态，编码未触碰 PDF） |
| R-GS-7 | engineering_enabled 误开 | Sprint A 闸门 + 测试不得置 true + 本 Sprint 三重保险（enabled=false + 数据饥饿 + 上游不可信） |
| R-GS-8 | 公式系数体系选择不当 | 系数规则全 pending_verification，设计态不固化，待专家双签 |

---

## 6. 红线守约自检

| 红线项 | 自检结果 |
|---|---|
| 保持 `engineering_enabled=false` | ✅ config.yaml 未改；校验器闸门恒 pending |
| 不填真实玻璃厚度 | ✅ `intermediate["t"].value is None` |
| 不填真实安全系数 | ✅ `intermediate["K"].value is None` |
| 不填真实允许应力 | ✅ `intermediate["sigma_allow"].value is None` |
| 不写规范条款号 | ✅ 仅引用 D-TH-02（value=null），无条款号 |
| 不改 `verified.json` 为 true | ✅ 文件未触碰，D-TH-02 仍 value=null/verified=false |
| 不输出 `engineering_approved` | ✅ 注入 enabled=True + 缺双签仍 pending；零 approved 落盘 |
| 全参数 pending_verification | ✅ result 空、gaps 全登记、evidence 标注 pending |

---

## 7. 阶段门 / 下一步

- **当前门**：Sprint E CODING_DONE，等待主理人验收；所有改动**未 commit**。
- **下一步**：验收通过后进入 **Profile（五大模块之三）** 真实编码，仍须六门槛全满足 + `engineering_enabled=false` 守约。
- **不进入**：Profile 之前不启动；本 Sprint 未触碰 PDF 渲染、未触碰其余三接口。

> 本文件不含任何真实玻璃厚度 / 安全系数 / 允许应力数值，未开启 `engineering_enabled`，全参数 `pending_verification`。

**END**（CODING_DONE，等待主理人验收；未进入 Profile 模块）
