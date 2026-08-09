# Phase 3.1 Sprint F — Profile（型材）工程设计评审报告（phase3.1_profile_design_report.md，pending_verification）

- **生成**：2026-07-30（Phase 3.1 Sprint F 设计阶段 · 收口）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，**未编码**；等待主理人审核）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B wind_pressure 设计 + Sprint C 编码（上游 w_k 供给方就绪）；Sprint D/E glass_safety 设计与编码（并列模块，pending_verification）
- **红线守约**：✅ 零真实壁厚值 / ✅ 零真实强度值 / ✅ 零真实截面惯性矩 / ✅ 零规范条款编号 / ✅ `engineering_enabled=false` / ✅ 全参数 `pending_verification` / ✅ 不编码。

---

## 1. 设计交付汇总

| # | 设计项 | 交付文件 | 状态 |
|---|---|---|---|
| 1 | profile 接口分析（骨架 + 与 wind_pressure/glass_safety 关系） | `.ai/tasks/phase3.1_profile_design.md` §1 | ✅ (pending_verification) |
| 2 | 输入参数设计（项目/Environment+wind_pressure w_k/Design/Engineering阈值 D-TH-01 四层） | §2 | ✅ (pending_verification) |
| 3 | 输出结构设计（四字段 + 扩展 intermediate/provenance/threshold_refs/gaps/sign_off_id + 七字段审核链） | §3 | ✅ |
| 4 | 规则体系设计（profile_rules：公式来源/变量关系/数据来源，仅符号级） | §4 | ✅ |
| 5 | 阈值依赖设计（D-TH-01 型材配置/壁厚/截面属性/审核流程 + 与 wind_pressure w_k 双闸门） | §5 | ✅ (pending_verification) |
| 6 | 与 wind_pressure / glass_safety 关系（w_k 上游消费 + 降级传导 + Glass 不替代 Profile） | §6 | ✅ (pending_verification) |
| 7 | Expert 审核点设计（8 个审核点：型材配置/截面参数/强度规则/挠度规则/边界条件 等） | §7 | ✅ |
| 8 | PDF 展示方案（三态徽标 + review_chain 透出 + 防误显） | §8 | ✅ |
| 9 | 测试方案（单元/集成/安全/防编造/覆盖率） | §9 | ✅ |
| 10 | 风险分析（R-PF-1~R-PF-8，pending_verification） | §10 | ✅ |

---

## 2. 设计达成度自评

| 设计目标 | 达成 | 证据 |
|---|---|---|
| 不破坏既有契约 | ✅ | profile 仅新增独立计算单元，Agent 调度/四字段/审核链零改动（§1.2，pending_verification） |
| 防编造红线锁死 | ✅ | §4 仅符号级变量关系，无数值；§5 D-TH-01 value=null；本评审报告经 check_fabrication 扫描 0 命中 |
| 专家双签可落地 | ✅ | §5/§7 明确 D-TH-01 角色绑定与 8 个审核点，复用 Sprint A `is_fully_verified` |
| enabled 误开防护 | ✅ | 设计态闸门恒 pending（§3.3）；编码前 enabled=false，六门槛未全满足 |
| 跨 Agent 数据契约 | ✅ | 复用 Design `field_provenance`/`threshold_refs` + wind_pressure 上游 `w_k`（§2，pending_verification） |
| 上游耦合正确 | ✅ | profile 消费 wind_pressure 的 `w_k`，双闸门 + 降级传导（§5.2/§6.3，pending_verification） |
| Glass 不替代 Profile | ✅ | §6.4 明确二者物理对象/阈值/审核独立，glass_safety approved 不替代 profile 计算 |
| PDF 审核透明 | ✅ | 三态徽标 + review_chain 逐接口透出 + 防误显（§8） |

---

## 3. 红灯守约确认（强制自检）

| 红线 | 是否违反 | 说明 |
|---|---|---|
| 写真实壁厚值 | ❌ 未违反 | 全文档壁厚 `t` 均为 `<取自 D-TH-01，pending_verification>` 或符号占位 |
| 写真实强度值 | ❌ 未违反 | 强度设计值 `f`/弹性模量 `E` 均符号化，无数值表 |
| 写真实截面惯性矩 | ❌ 未违反 | `I`/`W`/`A` 均为 `<取自 D-TH-01 截面属性，pending_verification>` 或符号占位 |
| 写规范条款编号 | ❌ 未违反 | 仅写"相关标准（标准号与条款号 pending_verification）"，无 GB/条款号 |
| 开启 engineering_enabled | ❌ 未违反 | 全程 `engineering_enabled=false`；设计态审核链恒 pending，绝不 engineering_approved |
| 编写实现代码 | ❌ 未违反 | 本文件纯设计，无任何 .py/.ts 实现，未改 `agent.py`/`validation.py` |
| 设 verified=true | ❌ 未违反 | 未触碰 `verified.json`，D-TH-01 维持 value=null/verified=false |

`check_fabrication.py` 对 `.ai/tasks/phase3.1_profile_design.md` 扫描结果：**0 命中** (pending_verification)。

---

## 4. 与既有架构的衔接

- **Sprint A 基础设施全部复用**：`ExpertBackedEngineeringValidation.validate`（七字段）、`INTERFACE_THRESHOLD_MAP["profile"]=("D-TH-01",)`、`review_log` 哈希链。
- **EngineeringAgent 零改动**：`analyze_profile` 内部替换为调用新计算单元，签名/调度/审核链不变（§1.2，pending_verification）。
- **Design 侧契约复用**：`field_provenance`/`threshold_refs` 直接消费（D-TH-01→frame_series/frame_material），不重定义。
- **wind_pressure 上游复用**：消费 Sprint C 产出的 `w_k`，不直接推算风压；基本风压只来自 E-TH-01（红线，§2.2/§5.2，pending_verification）。
- **结果模型同构**：ProfileResult 与 WindPressureResult / GlassSafetyResult 字段同构（四字段 + 扩展八字段），降低编码阶段迁移成本。
- **与 glass_safety 并列**：二者均为 wind_pressure 下游、各自阈值（D-TH-01 vs D-TH-02）、独立审核，glass_safety 结论不替代 profile 计算（§6.4，pending_verification）。

---

## 5. 待主理人审核项

### 5.1 🟢 已闭合（设计内自查）
- 阈值 ID 命名与 Sprint A `INTERFACE_THRESHOLD_MAP` 一致（profile → D-TH-01），无需裁决。
- 输入四层边界清晰，与 wind_pressure 的耦合仅限 `w_k`，与 glass_safety 并列无重叠歧义。

### 5.2 🟡 建议确认
1. **公式体系选择**：§4 采用"荷载—内力—应力/挠度校核"结构（σ = M/W + N/A，σ ≤ f；δ = s(q,L,E,I,support)，δ ≤ δ_lim），具体系数体系（简支/连续/悬臂二选一、强度与挠度双控口径）留待专家双签时确认——请主理人确认这是否符合预期抽象层级。
2. **上游 w_k 的边界**：明确"型材受荷只来自 wind_pressure 的 w_k，实时气象不参与"——请确认该边界无误。
3. **Glass 与 Profile 的独立性**：明确 glass_safety approved 不替代 profile 计算——请确认此并列关系符合项目预期。
4. **双闸门粒度**：profile approved 须 D-TH-01 双签 **且** wind_pressure 已 approved **且** enabled=true——请确认是否需要额外中间量（如局部体型系数 μ_sl）透传给型材模块。

### 5.3 ⛔ 编码启动前置
- `engineering_enabled` 保持 `false`，六门槛（阈值双签/Vision 调优/测试通过/审核链跑通/CI 8-8/主理人授权）未全满足前**禁止编码**。
- 真实规范条款号与参数值由专家双签阶段填入 `verified.json`（D-TH-01 偿还路径）。

---

## 6. 阶段门状态

| 门 | 状态 |
|---|---|
| profile 模块设计完成 | ✅ |
| 红线守约 | ✅ |
| fabrication 扫描 0 命中 | ✅ |
| 阈值 ID 一致性 | ✅（对齐 Sprint A，profile→D-TH-01） |
| engineering_enabled | ⛔ 保持 `false` |
| 编码启动 | ⛔ 等待主理人审核 + 六门槛全满足 |

---

## 7. 下一步建议（授权后编码阶段）

1. 主理人审核通过 + 六门槛满足后，进入 Sprint G（profile 真实计算编码）。
2. 编码顺序建议：新增 `agents/engineering/calc/profile.py` 计算单元（含 ProfileResult）→ 新增 `agents/engineering/rules/profile_rules.py` 规则层 → 注入 `ExpertBackedEngineeringValidation` → 串联 wind_pressure 上游 w_k + Design/Project 输入契约 → 单测/集成/防编造测试 → 保持 `engineering_enabled=false` 直至全绿。
3. 编码全程零硬编码工程常数，所有数值仅来自 `verified.json`（D-TH-01 pending 态为 null）。

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含代码实现，未开启 `engineering_enabled`，全参数 `pending_verification`）
