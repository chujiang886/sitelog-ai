# BOIP Phase 3.2 执行计划（Execution Plan）

> **身份**：BOIP AI CTO
> **阶段**：Phase 3.2 Planning（产品化路线制定，**仅规划、不编码**）
> **前置**：Phase 3.1 已完成（五工程模块 CODING_DONE + Final Integration FINAL_INTEGRATION_DONE），见 `.ai/reviews/phase3.1_final_integration_report.md`。
> **红线（本计划阶段强制）**：① 不编码；② 不修改工程模块（`calc/*.py` / `agent.py` / `validation.py`）；③ 不填写真实工程参数；④ 不开启 `engineering_enabled`；⑤ 不进入编码实施。
> **状态**：`pending_verification`（所有规划未主理人授权实施）。
> **定位**：制定本阶段产品化路线，输出执行计划 + 就绪报告，待主理人审核后进入实施 Sprint。

---

## 1. Phase 3.1 成果总结

Phase 3.1 完成了 Engineering Intelligence Framework（工程智能框架）的结构化装配与最终联调，建立了一条**可信、可审计、防编造**的工程审核链路，但全程未产出真实工程数值。

### 1.1 五工程模块（结构化装配，不产真实数值）
| 模块 | 计算类 | 上游信号 | 末端消费 | 当前状态 |
|---|---|---|---|---|
| Wind Pressure（风压） | `WindPressureCalculator` | Environment / Design | w_k → Glass / Profile | `pending_verification` |
| Glass Safety（玻璃安全） | `GlassSafetyCalculator` | w_k (Wind) | profile_result → Hardware | `pending_verification` |
| Profile（型材） | `ProfileCalculator` | w_k (Wind) | profile_result → Hardware | `pending_verification` |
| Hardware（五金） | `HardwareCalculator` | profile_result (Profile) | hardware_result → Installation Risk | `pending_verification` |
| Installation Risk（安装风险） | `InstallationRiskCalculator` | glass/profile/hardware_result（三上游） | 末端聚合 | `pending_verification` |

- 五模块均实现 `@dataclass` 形态的 Result 模型（`calculate()` 返回 Result，`as_full()` 为跨模块消费形态，`as_interface()` 为 Agent 契约形态）。
- 全链路降级：任一上游未 `approved` → 下游强制 `pending` 并登记 `xxx: upstream_pending`。
- 红线守约：`engineering_enabled=false`、零真实参数、未输出 `engineering_approved`。

### 1.2 Result 体系（五同构 Result）
- 五 Result 为**高度同构** `@dataclass`：9 字段完全一致（result / confidence / verification_status / evidence / intermediate / provenance / threshold_refs / gaps / sign_off_id）+ 2 方法一致（`as_interface()` 四键、`as_full()` 八字段+interface 常量）。
- 唯一差异：`as_full()` 中 `"interface"` 值取自各模块常量。
- 重复约 200 行（40 行 × 5），属「浅重复」，Phase 3.1 收口期**未抽象**（见 `.ai/tasks/phase3.1_result_abstraction_analysis.md`）。

### 1.3 Validator（双签审核链）
- `PendingEngineeringValidation`：结构校验 → `pending`（默认路径）。
- `ExpertBackedEngineeringValidation`：需 `structure_valid + threshold_verified + expert_signed + engineering_enabled` **四者全满足**才输出 `engineering_approved`。
- `engineering_enabled=false` 下恒返回 `pending`，**永不通过**。

### 1.4 Pending 机制（pending_verification 传导）
- 所有 Result 默认 `verification_status = PENDING_VERIFICATION`，`result=""`，`sign_off_id=None`。
- 跨模块降级：Wind↓(w_k)↓Glass/Profile↓(profile_result)↓Hardware↓(glass/profile/hardware_result)↓Installation Risk，任一非 approved → 下游强制 pending + 登记 `xxx: upstream_pending`。
- ReportGenerator `_badge_for()` 对 `pending_verification` 一律 `[待确认]`，无误显为 `[已验证]`。

**Phase 3.1 验收结论**：五模块同构契约一致、跨模块 pending 传导正确、Agent 五接口四字段统一、validator 流程与 ReportGenerator 徽标无误显已验证；CI 8/8 全绿（333 passed@88.34%，≥88.29%）。

---

## 2. Phase 3.2 目标

Phase 3.2 = **Engineering 产品化**——在 Phase 3.1 可信框架基础上，完成「结果抽象统一 → 报告呈现 → 真实审核闭环 → 平台产品化」四步走，使工程智能从「结构化骨架」走向「可交付产品」，但仍须按六门槛与主理人授权分步解锁真实数值。

### 2.A Engineering 结果抽象（建议优先，低风险高收益）
- **A-1 `EngineeringCalculationResult` 基类抽象**
  - 引入 `agents/engineering/calc/base.py`，定义 `EngineeringCalculationResult` 基类（9 字段 + `as_interface()` + `as_full()` + `INTERFACE` 类常量）。
  - 五子类改为继承 + 删重复方法，保留 `INTERFACE`。
  - 新增 `enforce_redline()` 闸门：断言 `verification_status == PENDING_VERIFICATION` 且 pending 态 `result==""`，防未来误填。
  - 迁移 6 步（见 phase3.1_result_abstraction_analysis.md §4）：新增基类 → 子类改造 → 更新 `__init__.py` 导出（类名不变，调用方零改动）→ 既有 5 单测不改断言 + 新增 `test_result_base.py` → 跑 CI 8/8 → 确认 `as_interface()` 字节结构不变则 `agent.py`/`validation.py`/ReportGenerator 零改动。
- **A-2 红线集中管理**
  - 红线不变量（默认值、pending 强制、零真实参数）集中到基类与方法闸门，消除五文件分散风险。
  - 可选：`validate_contract()` 在构造/导出时断言 `as_interface()` 恰好四键。

### 2.B ReportGenerator 工程章节（用户可见价值）
- **B-1 五模块结果展示**
  - 新增 Engineering 章节消费五 Result 的 `as_full()`，按 interface 分栏渲染（风压 / 玻璃 / 型材 / 五金 / 安装风险）。
  - 复用现有报告模板与 `_badge_for()` 徽标逻辑。
- **B-2 可信等级（credibility level）**
  - 渲染每个模块的 `confidence` / `verification_status` / `threshold_refs` / `sign_off_id`。
  - credibility 表升级：Level 3 工程批准在 `enabled=false` 时仍标「系统未启用」，approved 后显示签署人/时间。
- **B-3 pending 展示**
  - pending 模块显示 `[待确认]` 徽标 + `gaps` 列表（如 `w_k: upstream_pending`） + `provenance` 来源说明。
  - 严禁将 pending 渲染为已验证（已由 `_badge_for()` 保证，本 Sprint 仅接线不新增逻辑风险）。

### 2.C 真实审核闭环（高风险，须主理人授权 + 六门槛）
- **C-1 `verified.json` 真实化**
  - 由权威来源（国标/规范/专家）填充 `E-TH-01~06` 的 `value` 与 `verified=true`，并填 `verified_by` / `verified_at` 双签。
  - 严禁 AI 自推数值；所有来源须带 `source_ref` + `pending_verification` 标记直至双签齐备。
- **C-2 专家签署流程**
  - 落地 `ExpertBackedEngineeringValidation` 四签：`structure_valid + threshold_verified + expert_signed + engineering_enabled`。
  - `review_log.jsonl` append-only 链式记录每次签署事件（event_id / sign_off_id / prev_event_id）。
- **C-3 `engineering_enabled` 开启条件**
  - 仅在以下**全满足**时开启：① `verified.json` 六阈值全 `verified=true` 且双签齐备；② 专家签署流程演练通过；③ CI 8/8 + 防编造扫描 0 命中持续；④ 主理人书面授权。
  - 开启后首次真实计算须灰度（单模块试点），观察 `engineering_approved` 输出与日志链。

### 2.D 平台产品化（企业 SaaS 能力）
- **D-1 项目管理**
  - 工程 dossier 与项目生命周期绑定（创建/版本/归档），支持多项目并行与历史对比。
- **D-2 RBAC 增强**
  - 在 Phase 2.2 RBAC 基础上，新增工程角色（工程审核员 / 专家签署人 / 项目管理员），细化 `engineering_approved` 权限边界。
- **D-3 RAG 连接**
  - 将规范库 / 专家知识接入 Phase 2.2 RAG，支撑 `source_ref` 检索与阈值溯源，降低编造风险。
- **D-4 企业流程**
  - 销售 AI / CRM（Phase 3.2 原 T13–T17 范围）与工程审核链打通，形成「设计 → 工程审核 → 报价 → 签单」闭环。

---

## 3. 技术债排序

### P0（须在本阶段早期清理，阻塞真实闭环）
| 编号 | 债项 | 影响 | 处置 |
|---|---|---|---|
| P0-1 | 五 Result 同构重复（约 200 行） | 红线不变量分散，未来易漂移 | A-1 基类抽象（低风险，建议 Sprint 3.2.1 优先） |
| P0-2 | `verified.json` 六阈值全 `value=null` | 真实计算无法闭环 | C-1 权威填充（须主理人授权 + 双签） |
| P0-3 | ReportGenerator 无 engineering 章节 | 工程结果不可见，阻塞用户价值 | B 系列接线（Sprint 3.2.2） |

### P1（重要，不阻塞但建议本阶段完成）
| 编号 | 债项 | 影响 | 处置 |
|---|---|---|---|
| P1-1 | 红线闸门无集中方法 | 仅靠 review 维持，易漏 | A-2 `enforce_redline()`（随 A-1 落地） |
| P1-2 | 专家签署演练未执行 | 真实闭环缺流程验证 | C-2 签署流程 + `review_log` 演练 |
| P1-3 | `engineering_enabled` 开启条件未文档化 | 易误开 | C-3 开启条件清单（本计划已列） |
| P1-4 | RBAC 工程角色缺失 | 权限边界模糊 | D-2 角色扩展 |

### P2（增强项，可延后或并行走）
| 编号 | 债项 | 影响 | 处置 |
|---|---|---|---|
| P2-1 | RAG 规范库接入 | 溯源效率 | D-3 |
| P2-2 | 项目管理生命周期 | 多项目运维 | D-1 |
| P2-3 | 企业流程（CRM/销售 AI）打通 | 商业闭环 | D-4 |
| P2-4 | 跨模块编排层类型化 | 代码清晰度 | A-1 后可选增强 |

---

## 4. Phase 3.2 Sprint 拆分

> 每个 Sprint 均须：开启前确认前置门禁；完成后跑 `local_ci.sh` 8/8 + 防编造扫描 0 命中；全程 `engineering_enabled=false`（除明确授权的 C 系列灰度 Sprint）；不填写真实参数（除 C-1 经主理人授权的 `verified.json` 填充）。

### Sprint 3.2.1 — Result 抽象与红线集中（P0-1 / P1-1）
- **目标**：引入 `EngineeringCalculationResult` 基类，消除五 Result 重复，集中红线闸门。
- **输入**：`phase3.1_result_abstraction_analysis.md` 迁移方案；五 `calc/*.py` 现有 Result。
- **输出**：`agents/engineering/calc/base.py` + 五子类改造 + `test_result_base.py`；`as_interface()` 字节结构不变。
- **验收标准**：① 五子类继承且 `INTERFACE` 正确；② 既有 5 单测全过（断言不改）；③ `enforce_redline()` 在 pending 态拦截误填；④ CI 8/8、coverage ≥88.34%；⑤ 防编造扫描 0 命中；⑥ `agent.py`/`validation.py`/ReportGenerator 零改动（字节兼容）。

### Sprint 3.2.2 — ReportGenerator 工程章节（P0-3 / B 系列）
- **目标**：报告新增 Engineering 章节，五模块结果 + 可信等级 + pending 展示。
- **输入**：五 Result 的 `as_full()`；现有 `_badge_for()` 与报告模板。
- **输出**：ReportGenerator 工程章节渲染 + 单测（含 pending 展示断言）。
- **验收标准**：① 五模块分栏渲染；② pending 一律 `[待确认]` 无误显；③ `gaps`/`provenance` 可见；④ CI 8/8；⑤ 不引入 engineering_approved 真实输出。

### Sprint 3.2.3 — 专家签署流程演练（P1-2 / C-2）
- **目标**：落地 `ExpertBackedEngineeringValidation` 四签流程，`review_log.jsonl` 链式演练。
- **输入**：`validation.py` 现有双签链；`review_log.py`。
- **输出**：签署流程演练报告 + 流程单测（模拟四签齐备 → approved 逻辑分支，不落盘真实 enabled）。
- **验收标准**：① 四签缺一则 pending；② 日志链 event_id/sign_off_id/prev_event_id 正确；③ `enabled=false` 下仍不输出 approved；④ 防编造扫描 0 命中。

### Sprint 3.2.4 — verified.json 真实化（P0-2 / C-1，须主理人授权）
- **目标**：权威填充 `E-TH-01~06` 的 `value` + 双签 `verified=true`。
- **输入**：国标/规范/专家来源；`verified.json` 占位结构。
- **输出**：真实 `verified.json`（带 `source_ref` + `verified_by/at`）+ 溯源文档。
- **验收标准**：① 六阈值全 `verified=true` 且双签齐备；② 来源可溯、零 AI 自推；③ 防编造扫描对 `verified.json` 0 命中（来源标记合规）；④ `engineering_enabled` 仍 false（本 Sprint 仅填阈值，不开 enabled）。

### Sprint 3.2.5 — engineering_enabled 开启与灰度（P1-3 / C-3，须主理人书面授权）
- **目标**：在满足全部开启条件后开启 `engineering_enabled`，单模块灰度真实计算。
- **输入**：3.2.4 真实 `verified.json` + 3.2.3 签署流程 + 主理人授权书。
- **输出**：`config.yaml` `engineering_enabled=true`（灰度）+ 灰度观察报告 + 真实 `engineering_approved` 首例（带 sign_off_id）。
- **验收标准**：① 四签齐备才 approved；② 灰度仅单模块；③ `review_log` 记录首例；④ CI 8/8；⑤ 可一键回滚 `enabled=false`。

### Sprint 3.2.6 — 平台产品化（P1-4 / P2 / D 系列）
- **目标**：项目管理生命周期 + RBAC 工程角色 + RAG 规范库接入 + 企业流程打通。
- **输入**：Phase 2.2 RBAC/RAG 基座；工程审核链。
- **输出**：工程角色权限 + 项目 dossier 生命周期 + RAG 溯源 + CRM/销售 AI 接口。
- **验收标准**：① 工程角色权限边界清晰；② 多项目 dossier 可管理；③ RAG 支撑 `source_ref` 检索；④ 企业流程链路打通；⑤ 全量 CI 8/8。

---

## 5. 风险分析

| 编号 | 风险 | 等级 | 缓解 |
|---|---|---|---|
| R-32-1 | Result 抽象破坏 `as_interface()` 字节结构 | 中 | 迁移 6 步 + 既有 5 单测不改断言兜底；CI 门禁拦截 |
| R-32-2 | `verified.json` 真实数值来源不可靠/AI 自推 | 高 | 仅权威来源 + 双签 + `source_ref` + 防编造扫描；禁止 AI 自推 |
| R-32-3 | `engineering_enabled` 误开导致未审核 approved | 高 | 四签闸门 + 开启条件清单（C-3）+ 灰度 + 一键回滚 |
| R-32-4 | 报告 pending 误显为已验证 | 低 | `_badge_for()` 已保证；新增章节复用同逻辑 + 单测断言 |
| R-32-5 | 专家签署流程未演练即上线 | 中 | Sprint 3.2.3 先演练；3.2.5 再开启 enabled |
| R-32-6 | 跨模块降级在 Agent 级 invoke 不自动线程上游 | 低 | 设计如此；报告/编排消费 `as_full()` 显式传入 |
| R-32-7 | 平台产品化范围蔓延（D 系列过大） | 中 | Sprint 3.2.6 拆子任务 + 主理人里程碑把控 |
| R-32-8 | 红线漂移（未来有人局部改某模块默认值） | 中 | A-1 基类集中红线 + `enforce_redline()` 闸门根治 |

---

## 6. 进入实施的前置门禁（六门槛，沿用 Phase 3.1）

1. 主理人验收本计划 + 就绪报告。
2. `engineering_enabled` 仍须 `false` 直至 Sprint 3.2.5 明确授权。
3. 真实参数仍禁止填写，直至 Sprint 3.2.4 经主理人授权填充 `verified.json`。
4. CI 8/8 全绿且 coverage ≥88.29% 持续达标。
5. 防编造 / 硬编码扫描 0 命中持续达标。
6. 任一 Sprint 完成后须回归全量测试，零破坏性变更方可进入下一 Sprint。

**本计划阶段已停止，等待主理人审核。不进入编码实施。**

---

## 附：红线自检（Planning 阶段）
- ✅ 未编码（仅产出计划文档）。
- ✅ 未修改 `calc/*.py` / `agent.py` / `validation.py` / `verified.json`。
- ✅ 未填写真实工程参数（含 `E-TH-01~06` 仍 `value=null`）。
- ✅ 未开启 `engineering_enabled`（仍 false）。
- ✅ 未输出 `engineering_approved`。
- ✅ 全 `pending_verification`；未进入编码实施。
