# Phase 3.1 工程智能闭环 — 设计就绪报告（phase3.1_design_readiness_report.md）

- **生成**：2026-07-28（Phase 3.1 设计阶段 · 收口）
- **身份**：BOIP AI 首席工程架构师
- **状态**：✅ DESIGN_READY（设计完成，待主理人审核；**未进入编码**）
- **红线守约**：四份设计物零真实工程参数、未开启 `engineering_enabled`、未编写任何业务代码。
- **依据收口**：任务1 架构设计 / 任务2 ADR / 任务3 专家流程 / 任务4 测试方案，全部生成。

---

## 1. 四任务交付汇总

| # | 任务 | 交付文件 | 状态 |
|---|---|---|---|
| 1 | Engineering 整体架构分析 | `.ai/tasks/phase3.1_engineering_architecture_design.md` | ✅ |
| 2 | 工程计算 ADR 体系 | `.ai/decisions/ADR-phase3.1-engineering-calculation.md` | ✅ |
| 3 | 专家审核流程 | `.ai/tasks/phase3.1_expert_review_process.md` | ✅ |
| 4 | 测试方案 | `.ai/tasks/phase3.1_test_plan.md` | ✅ |

### 1.1 任务1 — 架构设计要点
- 现状锁定：骨架五接口契约 + 四字段 + 审核链骨架 + pending 默认，3.1 只需"替换 validator + 补阈值库 + 接 Rules"，**EngineeringAgent 侧零改动**。
- 五大模块（wind_pressure/glass_safety/profile/hardware/installation_risk）均定义输入/输出/证据/验证等级/pending 规则。
- `ExpertBackedEngineeringValidation.validate()` 返回七字段记录（interface/structure_valid/threshold_verified/expert_signed/verification_status/sign_off_id/validator）；`threshold_verified && expert_signed` → `engineering_approved`（Level 3）。
- engineering_enabled 开启**六门槛**（阈值双签/Vision 调优/测试通过/审核链跑通/CI 8-8/主理人授权）。
- 与 Design（field_provenance + threshold_refs 对齐）、PDF（三态徽标 + review_chain 透出）连接方案明确。
- 风险 R-E1~R-E7 全列出并配缓解。

### 1.2 任务2 — ADR 要点
- 全局三原则：参数唯一事实源=verified.json、公式唯一事实源=规范、验证状态二分。
- 五模块逐一定义数据来源/公式来源/规范依据（条款号 pending_verification）/专家审核点/禁止 AI 自推范围（不得补风压常数、不得自造壁厚、不得未签字断言安全等）。
- §6 实施约束：AI 代码零硬编码工程常数、未双签不得标 engineering_approved、防编造测试锁死。

### 1.3 任务3 — 专家流程要点
- 四步流程：起草 → 行业专家评审 → 主理人核准 → 入库（每步写审核日志）。
- Engineering 侧 `verified.json` 扩展：E-TH-01~06（基本风压/体型系数/粗糙度/五金/腐蚀等级/安装风险矩阵），全 `value=null`（pending_verification）。
- 双签机制：`is_fully_verified()` 升级需 `verified+verified_by+verified_at + expert_verified_by+expert_verified_at` 全齐。
- `review_log.jsonl` append-only 审计 + 哈希链防篡改。

### 1.4 任务4 — 测试方案要点
- 四类别：单元（五接口+审核链+加载器）/ 集成（invoke 全链路+Design/Environment/PDF 契约）/ 安全（未签字降级+enabled 误开+日志防篡改）/ 防编造（未签参数不进 approved+零硬编码常数+check_fabrication 联动）。
- 运行方式 + 覆盖率基线（backend≥60%、前端≥50%）+ 六门槛门禁映射。
- 红线：测试零真实数值、不触发 enabled。

---

## 2. 设计达成度自评

| 设计目标 | 达成 | 证据 |
|---|---|---|
| 不破坏既有契约 | ✅ | 仅替换 validator 注入，EngineeringAgent 零改动（§1.2 架构设计）|
| 防编造红线锁死 | ✅ | ADR §6 + 测试 §4 双重锁死 + check_fabrication 联动 |
| 专家双签可落地 | ✅ | 专家流程 §6 `is_fully_verified` 升级 + 审核日志 |
| enabled 误开防护 | ✅ | 六门槛 + 配置缺省 false + 安全测试 §3.2 |
| 跨 Agent 数据契约 | ✅ | field_provenance + threshold_refs 对齐（架构 §5）|
| PDF 审核透明 | ✅ | review_chain 逐接口透出 + 三态徽标（架构 §6）|

---

## 3. 待主理人审核项（须解决后授权编码）

### 3.1 ✅ 已闭合：阈值 ID 命名不一致
- **原现象**：ADR 初稿用 `E-TH-wp-01`（风压基准），专家流程用 `E-TH-01~06` 扁平命名，存在引用冲突（pending_verification）。
- **已修复（本收口轮）**：已将 ADR 中 `E-TH-wp-01` 统一修订为 `E-TH-01`（基本风压），并补 `E-TH-02`（体型系数）/`E-TH-03`（粗糙度）引用，与专家流程 `E-TH-01~06` 完全对齐；两文档现一致（pending_verification）。
- **结论**：契约级缺陷已消除，编码可直接复用 `E-TH-01~06`，无需主理人额外裁决。

### 3.2 🟡 建议确认
1. **Vision 调优（门槛2）归属**：Vision prompt 调优属 Vision 范畴，本设计未覆盖其测试，列为"外部观察项"，请主理人确认是否纳入 3.1 同一里程碑。
2. **五金参数库（E-TH-04）建设范围**：hardware 模块强依赖"五金参数库"，3.1 实施须明确建库子项；未建前该模块显式 pending（R-E7）。
3. **防编造扫描范围**：建议将 `agents/engineering/` 纳入 `check_fabrication.py` 强制扫描（当前扫描已覆盖 `.ai/`）。
4. **CI 门禁自动化**：门槛6（主理人授权）纯人工；门槛2（Vision）是否需额外 CI 钩子，请指示。

### 3.3 🟢 已知限制（设计态，非阻塞）
- 所有工程参数 `value=null`、规范条款号 `pending_verification`——这是设计态正确表现，非缺陷。
- 真实规范条款号与参数值由专家双签阶段填入（TD-002 偿还路径）。

---

## 4. 阶段门状态

| 门 | 状态 |
|---|---|
| 架构设计完成 | ✅ |
| ADR 生效 | ✅ |
| 专家流程设计完成 | ✅ |
| 测试方案完成 | ✅ |
| 阈值 ID 一致性修复 | 🔴 待主理人授权后编码前闭合 |
| engineering_enabled | ⛔ 保持 `false`，六门槛未全满足 |
| 编码启动 | ⛔ 等待主理人最终授权 |

---

## 5. 下一步建议（授权后）

1. **闭合 ID 不一致**（3.1 必做首项）。
2. 实施顺序建议：阈值库+双签加载器 → ExpertBackedEngineeringValidation → 五接口真实计算（接 Rules/参数库）→ 集成测试 → 防编造闸门 → CI 8/8 → 申请六门槛验收 → 主理人授权开 enabled。
3. 编码全程保持 `engineering_enabled=false` 直至六门槛全绿。

---

**END**（DESIGN_READY，等待主理人审核；本文件不含代码实现）
