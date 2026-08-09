# BOIP Phase 3.1 Final Integration 收口报告

> **阶段定位**：Final Integration（最终联调）——集成 / 验证 / 统一 / 收口。
> **红线守约**：① `engineering_enabled=false` 全程未开启；② 零真实工程参数填写；③ `verified.json` 未修改；④ 未输出 `engineering_approved`；⑤ 未进入 Phase 3.2；全部保持 `pending_verification`。
> **状态**：✅ FINAL_INTEGRATION_DONE，待主理人验收。不进入 Phase 3.2。
> **日期**：2026-07-30
> **CI 结果**：`local_ci.sh` 8/8 全绿（backend pytest 333 passed@88.34%、Jest 29 passed@93.15%、编造/硬编码扫描 0 命中，coverage ≥88.29% 达标）。

---

## 1. 五模块状态

五大工程模块（wind_pressure / glass_safety / profile / hardware / installation_risk）均已完成结构化装配编码，计算结构 `COING_DONE`，统一为 `@dataclass` 形态的工程计算结果模型。

| 模块 | 计算类 | 上游信号 | 下游消费 | 当前 verification_status | 真实数值 |
|---|---|---|---|---|---|
| wind_pressure | `WindPressureCalculator` | Environment / Design | w_k → Glass / Profile | `pending_verification` | 无 |
| glass_safety | `GlassSafetyCalculator` | w_k (Wind) | profile_result → Hardware | `pending_verification` | 无 |
| profile | `ProfileCalculator` | w_k (Wind) | profile_result → Hardware | `pending_verification` | 无 |
| hardware | `HardwareCalculator` | profile_result (Profile) | hardware_result → Installation Risk | `pending_verification` | 无 |
| installation_risk | `InstallationRiskCalculator` | glass/profile/hardware_result (三上游) | 末端聚合 | `pending_verification` | 无 |

**关键事实**：
- 五模块 `calculate()` 返回 Result，`as_full()` 为跨模块消费形态，`as_interface()` 为 Agent 级契约输出形态（四字段）。
- 任一上游未 `approved` 时，下游强制 `pending` 并登记 `xxx: upstream_pending`（如 `w_k: upstream_pending`、`profile_result: upstream_pending`、`glass_safety_result: upstream_pending`、`hardware_result: upstream_pending`、`installation_risk` 三上游 gap）。
- 全程 `engineering_enabled=false`，所有 Result 的 `result` 字段为空、`verification_status` 恒为 `pending_verification`，无 `sign_off_id`。

---

## 2. 架构一致性

### 2.1 五 Result 模型同构性

五 Result 模型为**高度同构** `@dataclass`：
- **9 字段完全一致**：`result=""`、`confidence`/`verification_status` 默认 `PENDING_VERIFICATION`、`evidence=""`、`intermediate`/`provenance`/`threshold_refs`/`gaps` 默认空容器、`sign_off_id=None`。
- **2 方法一致**：`as_interface()` 输出四键（`result/confidence/evidence/verification_status`）、`as_full()` 输出八字段（`intermediate/provenance/threshold_refs/gaps/sign_off_id` + interface 常量）。
- **唯一差异**：`as_full()` 中 `"interface"` 值取自各模块常量（`WIND_PRESSURE` / `GLASS_SAFETY` / `PROFILE` / `HARDWARE` / `INSTALLATION_RISK`）。

### 2.2 跨模块降级链路

```
Environment → Design → Wind Pressure ──w_k──┬→ Glass Safety
                                             └→ Profile ──profile_result──→ Hardware
                                                                              └── hardware_result ─┐
Glass/Profile ── glass_safety_result/profile_result ───────────────────────────────────────┤
                                                                                              ↓
                                                              Installation Risk（末端聚合，三上游全 approved 才评估）
```

- Wind 产 `w_k` → Glass/Profile 消费；Profile 产 `profile_result` → Hardware 消费；Glass/Profile/Hardware 产三 Result → Installation Risk 消费。
- 任一上游非 `approved` → 下游强制 `pending` + 登记 `xxx: upstream_pending`。

### 2.3 Engineering Agent 五接口统一契约

`agent.py` 暴露五接口（`ANALYSIS_INTERFACES`）：`wind_pressure` / `glass_safety` / `profile` / `hardware` / `installation_risk`。
- 每个 `analyze_*` 调用对应 Calculator 的 `as_interface()`，统一输出四字段。
- `invoke()` 对每个接口调 `self._validator.validate()`（双签机制）。
- `review_chain` / `gaps` 字段按上游审核态装配。

### 2.4 Validator 双签流程

`ExpertBackedEngineeringValidation`：需 `structure_valid + threshold_verified + expert_signed + engineering_enabled` **四者全满足**才输出 `engineering_approved`。
- 当前 `engineering_enabled=false` → `validate()` 恒返回 `pending`，**永不输出 `engineering_approved`**。
- `PendingEngineeringValidation`（结构校验 → pending）作为默认路径。

### 2.5 PDF / ReportGenerator 链路

`ReportGenerator.generate_project_report(dossier)` 当前仅消费 vision / environment / design，**尚无 engineering 章节**（属 Phase 3.2 接线项，本阶段未新增）。
- `_badge_for(level)` 对 `pending_verification` 一律返回 `(BADGE_PENDING, "badge_pending")` 即 `[待确认]`，**不会误显为 `[已验证]`**。
- credibility 表已注明 "Level 3 工程批准：当前系统未启用"。

**结论**：PDF 链路对工程 pending 结果无误显风险，但"工程结果入报告"需 Phase 3.2 接线。

---

## 3. 测试结果

### 3.1 新增集成测试 `tests/agents/test_phase3_1_integration.py`（六用例，全过）

1. `test_cross_module_pipeline_all_pending_with_upstream_gaps`：全链路计算器级 `as_full()` 线程，断言各模块 pending + 正确 `upstream_pending` gap（w_k / glass_safety_result / profile_result / hardware_result）。
2. `test_upstream_fake_approved_consumes_signal_but_stays_pending`：伪造 wind_pressure approved（w_k.value 设为非 None 占位值，仅作信号）→ 下游 provenance 翻 verified、gap 移除，但自身仍 pending。
3. `test_agent_invoke_installation_risk_pending_when_no_upstream_approved`：Agent invoke 默认空上游 → installation_risk pending 且 result 空。
4. `test_agent_invoke_five_interfaces_uniform_four_field_contract`：五接口统一四键 + 全 pending + review_chain 结构合法。
5. `test_validator_flow_pending_and_expert_backed_still_pending`：默认 + 专家双签（enabled=false）均不输出 `engineering_approved`。
6. `test_report_generator_handles_engineering_pending_as_unverified`：ReportGenerator `_badge_for` 对 pending 必为 BADGE_PENDING 非 BADGE_VERIFIED。

### 3.2 全量 CI（`bash scripts/ci/local_ci.sh`）

| 口径 | 结果 |
|---|---|
| backend pytest | **333 passed@88.34%** |
| Jest (frontend) | **29 passed@93.15%** |
| 编造扫描 `check_fabrication.py` | **0 命中** |
| 硬编码扫描 | **0 命中** |
| coverage 门槛 | **≥88.29% 达标**（实际 88.34%） |
| 总评 | **8/8 PASS** |

> 注：Sprint K 基线为 327 passed@88.29%；Final Integration 新增 6 集成用例，达 333 passed@88.34%，覆盖率不降反升。

---

## 4. 技术债变化

| 项 | 变化 | 说明 |
|---|---|---|
| Result 模型重复 | 同构但**未抽象** | 五 Result 9 字段 + 2 方法逐字相同，仅 interface 常量差。Phase 3.1 收口期**不重构**，抽象建议延至 Phase 3.2（见 `.ai/tasks/phase3.1_result_abstraction_analysis.md`）。 |
| 红线不变量分散 | 现状 | 守约逻辑分散在各 `as_full()` / validator，无集中闸门；抽象基类可在 Phase 3.2 引入 `enforce_redline()`。 |
| ReportGenerator 无 engineering 章节 | 新增识别（Phase 3.2 项） | 当前报告不消费工程结果；需 Phase 3.2 接线，本阶段未做。 |
| 跨模块降级链路 | 已验证一致 | 计算器级 `as_full()` 线程传导正确，Agent 级 invoke 不自动线程上游（设计如此）。 |
| 测试覆盖 | +6 用例 | 新增集成测试补齐跨模块契约与 validator 流程验证。 |

**净债**：Final Integration 阶段未引入新债，识别两项 Phase 3.2 待办（Result 抽象、ReportGenerator 工程章节接线），均不阻塞当前验收。

---

## 5. 风险

| 编号 | 风险 | 等级 | 现状 / 缓解 |
|---|---|---|---|
| R-FI-1 | 红线误操作（误开 enabled / 填真实参数 / 改 verified.json / 输 approved） | 中 | 已全程守约；防编造扫描 0 命中；建议 Phase 3.2 引入 `enforce_redline()` 集中闸门。 |
| R-FI-2 | 五 Result 同构漂移（未来有人局部改某模块字段） | 中 | 当前同构；未抽象，靠 review 维持。Phase 3.2 抽象基类可根治。 |
| R-FI-3 | ReportGenerator 工程章节缺失导致验收后报告无工程结论 | 低 | 当前已验证 pending 不误显；工程入报告属 Phase 3.2 明确待办。 |
| R-FI-4 | 跨模块降级在 Agent 级 invoke 不自动线程上游 | 低 | 设计如此（Agent 接收外部已审核 dossier）；集成测试已直接验证计算器级 full 结果。 |
| R-FI-5 | CI 覆盖率口径误读（`--cov=agents` 根目录 vs `cd backend --cov=app --cov=agents`） | 低 | 已确认以 `local_ci.sh` 为权威口径（88.34%）；避免手动根目录误读。 |

---

## 6. Phase 3.2 建议

**进入 Phase 3.2 前置条件（六门槛，须主理人验收 + 全满足）**：
1. 主理人验收本报告与全部交付物（含 `phase3.1_result_abstraction_analysis.md` / `test_phase3_1_integration.py` / `phase3.1_final_integration_report.md`）。
2. `engineering_enabled` 仍须 `false` 直至真实审核流程与专家签署就绪。
3. 真实工程参数仍禁止填写，直至 `verified.json` 经权威来源填充且 `engineering_approved` 流程闭合。
4. CI 8/8 全绿且 coverage ≥88.29% 持续达标。
5. 防编造 / 硬编码扫描 0 命中持续达标。
6. Result 抽象重构（若采纳本报告建议）须在 Phase 3.2 内完成且零破坏性回归。

**Phase 3.2 建议工作项**：
- **A. Result 抽象（建议）**：引入 `BaseEngineeringResult` 基类（统一 9 字段 + 2 方法 + `enforce_redline()` 闸门），五模块子类化，消除重复并集中红线不变量。迁移 6 步法见分析文档。
- **B. ReportGenerator 工程章节接线（明确待办）**：新增 Engineering 章节消费五 Result 的 `as_full()`，复用 `_badge_for()` 徽标逻辑，确保 pending 显示 `[待确认]`。
- **C. 真实审核闭环**：`verified.json` 填充权威阈值、`engineering_enabled=true` 上线、`ExpertBackedEngineeringValidation` 四签齐备后输出 `engineering_approved`。
- **D. 跨模块编排层**：若引入类型化编排，可利用抽象基类统一处理降级链路。

**本阶段已停止，等待主理人验收。不进入 Phase 3.2。**

---

## 附：交付物清单

- `.ai/tasks/phase3.1_result_abstraction_analysis.md` — 五 Result 同构性分析与重构建议（仅分析不重构）
- `tests/agents/test_phase3_1_integration.py` — 跨模块集成测试（六用例，全过）
- `.ai/reviews/phase3.1_final_integration_report.md` — 本报告
- `.ai/project_status.json` — SSOT 同步（FINAL_INTEGRATION_DONE + 新增 3.1.16 条目）
- `.ai/roadmap_v2.md` — 里程碑同步（Final Integration 叙事段 + 3.1 里程碑刷新）

**红线自检**：✅ `engineering_enabled=false` ✅ 零真实参数 ✅ `verified.json` 未改 ✅ 未输出 `engineering_approved` ✅ 未进入 Phase 3.2 ✅ 全 `pending_verification` ✅ 未重构 Result ✅ 未给 ReportGenerator 加 engineering 章节。
