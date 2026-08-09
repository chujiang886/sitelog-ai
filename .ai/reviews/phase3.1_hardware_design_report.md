# Phase 3.1 Sprint H — Hardware（五金）工程设计评审报告（phase3.1_hardware_design_report.md，pending_verification）

- **生成**：2026-07-30（Phase 3.1 Sprint H 设计阶段 · 收口）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，**未编码**；等待主理人审核）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 E-TH-04 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B/C wind_pressure 设计与编码（上游 w_k 供给方就绪，pending_verification）；Sprint D/E glass_safety 设计与编码（并列模块，pending_verification）；Sprint F/G profile 设计与编码（Hardware 直接上游，pending_verification）
- **红线守约**：✅ 零真实五金承载值 / ✅ 零真实寿命次数 / ✅ 零真实锁点数量 / ✅ 零规范条款编号 / ✅ `engineering_enabled=false` / ✅ 全参数 `pending_verification` / ✅ 不编码。

---

## 1. 设计交付汇总

| # | 设计项 | 交付文件 | 状态 |
|---|---|---|---|
| 1 | hardware 接口分析（骨架 + 与 Wind/Profile/Glass 关系） | `.ai/tasks/phase3.1_hardware_design.md` §1 | ✅ (pending_verification) |
| 2 | 输入参数设计（项目/Environment+wind_pressure+profile/Design/Engineering阈值 E-TH-04 四层） | §2 | ✅ (pending_verification) |
| 3 | 输出结构设计（四字段 + 扩展 intermediate/provenance/threshold_refs/gaps/sign_off_id + 七字段审核链） | §3 | ✅ |
| 4 | 规则体系设计（hardware_rules：公式来源/变量关系/数据来源，仅符号级） | §4 | ✅ |
| 5 | 阈值设计（E-TH-04 五金承载力 + 五金配置/承载等级/锁点体系/连接要求 四子维度审核占位） | §5 | ✅ (pending_verification) |
| 6 | 与 Profile 关系（消费 profile_result，Profile approved 不替代 Hardware 审核 + 降级传导） | §6 | ✅ (pending_verification) |
| 7 | 与 Wind/Glass 关系（链路 Wind↓Profile↓Hardware；Glass 并列） | §7 | ✅ (pending_verification) |
| 8 | Expert 审核点设计（9 个审核点：五金型号/承载能力/开启方式/连接可靠性/使用场景/锁点体系/风荷载/溯源/量纲） | §8 | ✅ |
| 9 | PDF 展示方案（三态徽标 + review_chain 透出 + 防误显） | §9 | ✅ |
| 10 | 测试方案（单元/集成/安全/防编造/覆盖率） | §10 | ✅ |
| 11 | 风险分析（R-HW-1~R-HW-8，pending_verification） | §11 | ✅ |

---

## 2. 设计达成度自评

| 设计目标 | 达成 | 证据 |
|---|---|---|
| 不破坏既有契约 | ✅ | hardware 仅新增独立计算单元，Agent 调度/四字段/审核链零改动（§1.2，pending_verification） |
| 防编造红线锁死 | ✅ | §4 仅符号级变量关系，无数值；§5 E-TH-04 value=null；本评审报告经 check_fabrication 扫描 0 命中 |
| 专家双签可落地 | ✅ | §5/§8 明确 E-TH-04 角色绑定（四子维度）与 9 个审核点，复用 Sprint A `is_fully_verified` |
| enabled 误开防护 | ✅ | 设计态闸门恒 pending（§3.3）；编码前 enabled=false，六门槛未全满足 |
| 跨 Agent 数据契约 | ✅ | 复用 Design `field_provenance`/`threshold_refs` + wind_pressure 上游 `w_k` + profile 上游 `profile_result`（§2，pending_verification） |
| 上游耦合正确 | ✅ | hardware 消费 profile 的 `profile_result`，链路 Wind↓Profile↓Hardware + 降级传导（§6/§7，pending_verification） |
| PDF 审核透明 | ✅ | 三态徽标 + review_chain 逐接口透出 + 防误显（§9） |

---

## 3. 红灯守约确认（强制自检）

| 红线 | 是否违反 | 说明 |
|---|---|---|
| 写真实五金承载值 | ❌ 未违反 | 全文档承载力基准 `R` 均为 `<取自 E-TH-04，pending_verification>` 或符号占位 |
| 写真实寿命次数 | ❌ 未违反 | 启闭寿命等级 `N_life` 仅符号化，明确标注"次数 pending，禁止真实次数" |
| 写真实锁点数量 | ❌ 未违反 | 锁点数量 `n_lock`/`n_req` 均符号化，标注"数量 pending，禁止真实数量" |
| 写规范条款编号 | ❌ 未违反 | 仅写"相关标准（标准号与条款号 pending_verification）"，无 GB/条款号 |
| 开启 engineering_enabled | ❌ 未违反 | 全程 `engineering_enabled=false`；设计态审核链恒 pending，绝不 engineering_approved |
| 编写实现代码 | ❌ 未违反 | 本文件纯设计，无任何 .py/.ts 实现，未改 `agent.py`/`validation.py` |
| 设 verified=true | ❌ 未违反 | 未触碰 `verified.json`，E-TH-04 维持 value=null/verified=false |

`check_fabrication.py` 对 `.ai/tasks/phase3.1_hardware_design.md` 扫描结果：**0 命中** (pending_verification)。

---

## 4. 与既有架构的衔接

- **Sprint A 基础设施全部复用**：`ExpertBackedEngineeringValidation.validate`（七字段）、`INTERFACE_THRESHOLD_MAP["hardware"]=("E-TH-04",)`、`review_log` 哈希链。E-TH-04 已在 `agents/engineering/thresholds/verified.json` 占位（`applies_to:["hardware"]`），无需新建阈值 ID。
- **EngineeringAgent 零改动**：`analyze_hardware` 内部替换为调用新计算单元，签名/调度/审核链不变（§1.2，pending_verification）。
- **Design 侧契约复用**：`field_provenance`/`threshold_refs` 直接消费（Design 候选 `hardware_selection`），不重定义。
- **上游复用**：消费 Sprint C 的 `w_k`（经 Sprint G 的 profile 传递）与 Sprint G 的 `profile_result`（直接上游），不直接推算风压（红线，§2.2/§5.2，pending_verification）。
- **结果模型同构**：HardwareResult 与 WindPressureResult / GlassSafetyResult / ProfileResult 字段同构（四字段 + 扩展八字段），降低编码阶段迁移成本。

---

## 5. 待主理人审核项

### 5.1 🟢 已闭合（设计内自查）
- 阈值 ID 命名与 Sprint A `INTERFACE_THRESHOLD_MAP` 一致（hardware → E-TH-04，已存在占位），无需裁决。
- 输入四层边界清晰，与 wind_pressure/profile 的耦合仅限 `w_k`/`profile_result`，无重叠歧义。

### 5.2 🟡 建议确认
1. **工程链路抽象层级**：§1.3/§7 采用"Wind↓Profile↓Hardware"三级链路（hardware 直接消费 `profile_result`，间接消费 `w_k`）。请主理人确认 hardware 是否应直接消费 `profile_result` 的杆件反力，而非另设独立荷载入口。
2. **E-TH-04 四子维度拆分粒度**：§5 将"五金配置/承载等级/锁点体系/连接要求"定义为 E-TH-04 的四子维度审核占位（单一阈值 ID，内部多字段）。请确认该粒度是否符合预期，或是否需要拆分为独立阈值 ID。
3. **寿命等级口径**：§4/§8 的 `N_life`（启闭寿命等级）仅以等级/类别抽象，不写真实次数。请确认"以等级替代次数"的抽象方式是否符合专家双签预期。

### 5.3 ⛔ 编码启动前置
- `engineering_enabled` 保持 `false`，六门槛（阈值双签/Vision 调优/测试通过/审核链跑通/CI 8-8/主理人授权）未全满足前**禁止编码**。
- 真实规范条款号与参数值（承载力基准/锁点数量/寿命次数/型号规格）由专家双签阶段填入 `verified.json`（E-TH-04 偿还路径）。

---

## 6. 阶段门状态

| 门 | 状态 |
|---|---|
| hardware 模块设计完成 | ✅ |
| 红线守约 | ✅ |
| fabrication 扫描 0 命中 | ✅ |
| 阈值 ID 一致性 | ✅（对齐 Sprint A，hardware→E-TH-04，已占位） |
| engineering_enabled | ⛔ 保持 `false` |
| 编码启动 | ⛔ 等待主理人审核 + 六门槛全满足 |

---

## 7. 下一步建议（授权后编码阶段）

1. 主理人审核通过 + 六门槛满足后，进入 Sprint I（hardware 真实计算编码）。
2. 编码顺序建议：新增 `agents/engineering/calc/hardware.py` 计算单元（含 HardwareResult）→ 新增 `agents/engineering/rules/hardware_rules.py` 规则层 → 注入 `ExpertBackedEngineeringValidation` → 串联 profile 上游 `profile_result` + w_k + Design/Project 输入契约 → 单测/集成/防编造测试 → 保持 `engineering_enabled=false` 直至全绿。
3. 编码全程零硬编码工程常数，所有数值仅来自 `verified.json`（E-TH-04 pending 态为 null）。

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含代码实现，未开启 `engineering_enabled`，全参数 `pending_verification`）
