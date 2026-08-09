# Phase 3.1 Sprint G — Profile（型材）工程模块编码完成报告

- **生成**：2026-07-30（Phase 3.1 Sprint G 实现阶段）
- **身份**：BOIP AI 工程计算负责人
- **状态**：✅ CODING_DONE（结构化装配，不产真实数值；等待主理人验收）
- **依赖**：Sprint A 可信审核基础设施 + Sprint C 风压编码（上游 w_k 供给方）+ Sprint E 玻璃编码（并列模块）+ Sprint F 型材设计（本阶段落地依据）
- **红线守约**：`engineering_enabled=false`、零真实壁厚/截面惯性矩/截面模量/强度设计值/弹性模量/挠度、零规范条款号、未改 `verified.json`、未输出 `engineering_approved`、全 `pending_verification`

---

## 1. 修改文件

| 文件 | 操作 | 说明 |
|---|---|---|
| `agents/engineering/calc/profile.py` | 新增 | `ProfileCalculator` + `ProfileResult`（结构同构 `WindPressureResult`/`GlassSafetyResult`：四字段 + intermediate/provenance/threshold_refs/gaps/sign_off_id）；不产真实数值；含 wind_pressure 上游 w_k 跨模块降级（任务4） |
| `agents/engineering/rules/profile_rules.py` | 新增 | 符号级公式体系（`q=p(w_k,geometry)` / `M,N=r(q,L,support)` / `σ=M/W+N/A` / `σ≤f` / `δ=s(q,L,E,I,support)` / `δ≤δ_lim`）+ 变量关系 + 数据来源映射；**零真实工程常数**（任务2） |
| `agents/engineering/calc/__init__.py` | 修改 | 导出 `PROFILE_INTERFACE` / `ProfileCalculator` / `ProfileResult` |
| `agents/engineering/rules/__init__.py` | 修改 | 导出 `profile_rules` |
| `agents/engineering/agent.py` | 修改 | `analyze_profile()` 由 skeleton 升级为调用 `ProfileCalculator`；import 新增 `ProfileCalculator`；模块 docstring 补 Sprint G 说明；**四字段契约与 validator 流程零改动** |
| `tests/agents/test_profile.py` | 新增 | 13 个新用例（见第 3 节） |
| `.ai/reviews/phase3.1_sprintG_profile_report.md` | 新增 | 本报告 |
| `.ai/project_status.json` / `.ai/roadmap_v2.md` | 修改 | SSOT 同步（phase_3_1 → SPRINT_G_CODING_DONE + 3.1.11） |

---

## 2. 架构影响

### 2.1 计算单元同构
Profile 计算单元与 Wind Pressure（Sprint C）、Glass Safety（Sprint E）完全同构：
- 统一 `ProfileResult`（`result`/`confidence`/`evidence`/`verification_status` 四字段 + `intermediate`/`provenance`/`threshold_refs`/`gaps`/`sign_off_id` 扩展字段）；
- `as_interface()` 返回精确四键（兼容 `EngineeringAgent` 接口契约与既有 `test_engineering.py::test_unified_output_structure_for_each_interface` 断言）；
- `as_full()` 返回八扩展字段 + `interface="profile"` 标识。

### 2.2 Agent 接入零契约改动
`analyze_profile()` 内部仅从 `build_skeleton_output()` 切换为 `ProfileCalculator().calculate(context_data).as_interface()`；`invoke()` 调度表、`ANALYSIS_INTERFACES`、validator 流程**完全不变**。

### 2.3 跨模块链路（任务4，降级传导）
`ProfileCalculator.calculate` 读取 `context_data["wind_pressure_result"]`，复用与 Glass 相同的 `_is_wind_pressure_approved()` 闸门：
- 上游 `verification_status == engineering_approved` **且** `w_k.value` 非 None → 标记 `provenance["wind_pressure.w_k"]="verified"`（仍不填数值）；
- 否则 → 强制 `pending_verification` 并登记 `gaps: ["w_k: upstream_pending"]`（与 glass_safety 一致的降级逻辑）。

### 2.4 阈值绑定
`get_interface_thresholds("profile")` → `("D-TH-01",)`；`profile_rules.VARIABLE_THRESHOLD_MAP` 将 `series/t/I/W/A/f/E` 七变量绑定 D-TH-01（型材配置/截面属性/强度/弹性模量）。

### 2.5 下游消费
Profile 产出（pending 态）经 `as_full()` 可被未来编排 / PDF 消费；当前未强制下游读取（玻璃/五金/安装风险接口仍为骨架）。

---

## 3. 测试结果

### 3.1 新增单元测试（`tests/agents/test_profile.py`，13 passed）
覆盖用户要求的 8 类场景 + 序列化：
1. **D-TH-01 缺失** → `test_d_th_missing_yields_pending`（阈值库空 → 恒 pending，gaps 登记 D-TH-01 pending）
2. **wind_pressure pending 传导** → `test_wind_pressure_pending_propagation` + `test_wind_pressure_approved_but_unavailable_wk_still_pending`（上游未 approved 或 w_k 无值 → 强制 pending + `w_k: upstream_pending`）
3. **inferred 输入** → `test_inferred_input_stays_pending`（全 inferred → pending，且不伪造 σ/δ/I/W/f/E/t 数值）
4. **输出结构** → `test_output_structure_four_fields` + `test_profile_result_serializers`（四字段 + 八扩展字段 + interface 标识）
5. **threshold_refs** → `test_threshold_refs_align_with_interface_map`（与 `get_interface_thresholds` 一致）
6. **evidence** → `test_evidence_carries_formula_and_pending`（含公式来源 + D-TH-01 + pending 标注，无真实数值）
7. **防编造扫描** → `test_fabrication_scan_clean_on_profile_sources`（源码 profile.py/profile_rules.py/本测试零命中）+ `test_fabrication_scan_catches_fabricated_number`（临时文件伪造型材壁厚数值触发，验证扫描有效）
8. **engineering_enabled=false** → `test_pending_propagation_through_validator`（注入 enabled=True + 缺双签仍 pending）+ `test_pending_propagation_through_agent_invoke` + `test_unified_interface_keys_for_profile`（Agent 接口恒四字段）

### 3.2 全量 CI（`bash scripts/ci/local_ci.sh` → 8/8 PASS）
| Step | 结果 |
|---|---|
| 1 Ruff | ✅ |
| 2 Backend pytest | ✅ **298 passed @ 87.90%**（≥87.76% 达标，285→298 +13 用例，覆盖率反升） |
| 3 ESLint | ✅ |
| 4 Jest | ✅ 29 passed @ 93.15% |
| 5 Alembic | ✅ |
| 6 Seed | ✅ |
| 7 防编造扫描 | ✅ **全仓 0 命中**（含新增 profile.py/profile_rules.py/test_profile.py） |
| 8 硬编码扫描 | ✅ 0 命中 |

---

## 4. 技术债变化

### 4.1 清偿
- 五大工程模块之三（wind_pressure / glass_safety / profile）均已落地结构化装配，统一四字段 + 扩展字段契约在三个模块间完全对齐，可复制模式成熟。
- 跨模块降级传导逻辑（wind pending → 下游 pending）在 glass 与 profile 间复用，验证通过。

### 4.2 新增 / 存续
- **存续债**：`profile` 仍 `pending_verification`——真实数值依赖 D-TH-01 双签 + `engineering_enabled=true` + 可信 w_k，三者未满足前不得 approved（符合红线）。
- **存续债**：下游 `hardware` / `installation_risk` 仍为骨架（五大模块之四、之五），待各自 Sprint 实施。
- **无新增代码债**：无临时 hack、无 TODO 遗留、无重复实现。

---

## 5. 风险

| ID | 风险 | 影响 | 缓解（已落地） |
|---|---|---|---|
| R-PF-1 | D-TH-01 长期未双签 | profile 永久 pending | 专家双签流程 + review_log 追踪；CI 防编造闸门 |
| R-PF-2 | 误将 Environment 实时气象当杆件荷载 | 来源错误 | 荷载只来自 wind_pressure 的 w_k；代码中 w_k 仅消费不重算 |
| R-PF-3 | 上游 w_k 不可信被当确定输入 | 编造型材达标结论 | 降级传导；calculator 显式检查 w_k 可信态（已测试） |
| R-PF-4 | inferred 输入直接驱动确定性结论 | 编造工程判断 | field_provenance 判定：inferred → pending（已测试） |
| R-PF-7 | engineering_enabled 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |

---

## 6. 红线自检（全程强制）

- ✅ `engineering_enabled=false` 未开启；
- ✅ `result` 恒空串；`intermediate` 各量（`t`/`I`/`W`/`A`/`f`/`E`/`σ`/`δ` 等）`value=null`；
- ✅ **未改 `verified.json`**（D-TH-01 仍 `value=null/verified=false`）；
- ✅ **未输出 `engineering_approved`**（注入 `enabled=true` + 缺双签仍 pending，三重保险：enabled=false + 数据饥饿 + 上游 w_k 不可信）；
- ✅ 全参数 `pending_verification`；
- ✅ **未编写任何真实型材数值 / 规范条款号**（规则层仅符号级）。

---

## 7. 阶段门（Gate）

- **当前**：`phase_3_1 = SPRINT_G_CODING_DONE`，所有改动**未 commit**，等主理人验收。
- **下一步**：进入 Hardware 模块（五大模块之四）前，须主理人授权 + 六门槛全满足（阈值双签 / Vision 调优 / 测试通过 / 审核链跑通 / CI 8-8 / 主理人授权）+ 继续守 `engineering_enabled=false`。
- **严禁**：未验收即进入 Hardware，或任何绕过红线（填真实值 / 开 enabled / 改 verified=true / 输出 approved）的动作。
