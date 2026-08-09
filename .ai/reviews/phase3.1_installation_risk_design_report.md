# Phase 3.1 Sprint J — Installation Risk（安装施工风险）工程设计评审报告（phase3.1_installation_risk_design_report.md，pending_verification）

- **生成**：2026-07-30（Phase 3.1 Sprint J 设计阶段 · 收口）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，**未编码**；等待主理人审核）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 E-TH-05/E-TH-06 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B/C wind_pressure 设计与编码（上游 w_k 供给方就绪，pending_verification）；Sprint D/E glass_safety 设计与编码（玻璃重量/玻璃安全并列，pending_verification）；Sprint F/G profile 设计与编码（型材条件上游，pending_verification）；Sprint H/I hardware 设计与编码（五金条件上游，pending_verification）
- **红线守约**：✅ 零真实风险分数 / ✅ 零真实承载参数 / ✅ 零真实施工安全距离 / ✅ 零规范条款编号 / ✅ `engineering_enabled=false` / ✅ 全参数 `pending_verification` / ✅ 不编码。

---

## 1. 设计交付汇总

| # | 设计项 | 交付文件 | 状态 |
|---|---|---|---|
| 1 | installation_risk 接口分析（骨架 + 与 Glass/Profile/Hardware 末端聚合关系） | `.ai/tasks/phase3.1_installation_risk_design.md` §1 | ✅ (pending_verification) |
| 2 | 输入参数设计（项目/Environment+四上游/Design/Engineering阈值 E-TH-05~06 四层；含 provenance） | §2 | ✅ (pending_verification) |
| 3 | 输出结构设计（四字段 + 扩展 intermediate/provenance/threshold_refs/gaps/sign_off_id + 七字段审核链） | §3 | ✅ |
| 4 | 规则体系设计（installation_rules：风险模型/变量关系/数据来源，仅符号级） | §4 | ✅ |
| 5 | 阈值设计（E-TH-05 腐蚀等级 + E-TH-06 安装风险矩阵，含 施工风险等级/吊装条件/人员操作风险/环境风险 四子维度审核占位） | §5 | ✅ (pending_verification) |
| 6 | 与其他模块关系（玻璃重量来自 Design/Glass、型材条件来自 Profile、五金条件来自 Hardware、降级传导） | §6 | ✅ (pending_verification) |
| 7 | Expert 审核点设计（10 个审核点：施工环境/吊装方案/人员风险/设备条件/工艺流程/环境风险/安全距离/上游可信/溯源/量纲） | §7 | ✅ |
| 8 | PDF 展示方案（三态徽标 + review_chain 透出 + 防误显） | §8 | ✅ |
| 9 | 测试方案（单元/集成/安全/防编造/覆盖率） | §9 | ✅ |
| 10 | 风险分析（R-IR-1~R-IR-8，pending_verification） | §10 | ✅ |

---

## 2. 设计达成度自评

| 设计目标 | 达成 | 证据 |
|---|---|---|
| 不破坏既有契约 | ✅ | installation_risk 仅新增独立计算单元，Agent 调度/四字段/审核链零改动（§1.2，pending_verification） |
| 防编造红线锁死 | ✅ | §4 仅符号级变量关系，无数值；§5 E-TH-05/E-TH-06 value=null；本评审报告经 check_fabrication 扫描 0 命中 |
| 专家双签可落地 | ✅ | §5/§7 明确 E-TH-05/E-TH-06 角色绑定（四子维度）与 10 个审核点，复用 Sprint A `is_fully_verified` |
| enabled 误开防护 | ✅ | 设计态闸门恒 pending（§3.3）；编码前 enabled=false，六门槛未全满足 |
| 跨 Agent 数据契约 | ✅ | 复用 Design `field_provenance`/`threshold_refs` + 四上游 result 产出（§2，pending_verification） |
| 上游耦合正确 | ✅ | installation_risk 末端聚合消费 glass_safety/profile/hardware 三上游，降级传导（§6，pending_verification） |
| PDF 审核透明 | ✅ | 三态徽标 + review_chain 逐接口透出 + 防误显（§8） |

---

## 3. 红灯守约确认（强制自检）

| 红线 | 是否违反 | 说明 |
|---|---|---|
| 写真实风险分数 | ❌ 未违反 | 全文档综合风险评级 `Risk_total` 均为 `<取自 E-TH-06，pending_verification>` 或符号占位 |
| 写真实承载参数 | ❌ 未违反 | 承载参数只来自上游 glass_safety/profile/hardware，installation_risk 仅消费，不写真实值 |
| 写真实施工安全距离 | ❌ 未违反 | 安全距离 `D_safe` 仅符号化，明确标注"数值 pending，禁止真实距离" |
| 写规范条款编号 | ❌ 未违反 | 仅写"相关标准（标准号与条款号 pending_verification）"，无 GB/条款号 |
| 开启 engineering_enabled | ❌ 未违反 | 全程 `engineering_enabled=false`；设计态审核链恒 pending，绝不 engineering_approved |
| 编写实现代码 | ❌ 未违反 | 本文件纯设计，无任何 .py/.ts 实现，未改 `agent.py`/`validation.py` |
| 设 verified=true | ❌ 未违反 | 未触碰 `verified.json`，E-TH-05/E-TH-06 维持 value=null/verified=false |

`check_fabrication.py` 对 `.ai/tasks/phase3.1_installation_risk_design.md` 扫描结果：**0 命中** (pending_verification)。

---

## 4. 与既有架构的衔接

- **Sprint A 基础设施全部复用**：`ExpertBackedEngineeringValidation.validate`（七字段）、`INTERFACE_THRESHOLD_MAP["installation_risk"]=("E-TH-05","E-TH-06")`、`review_log` 哈希链。E-TH-05（腐蚀等级）/ E-TH-06（安装风险矩阵）已在 `agents/engineering/thresholds/verified.json` 占位（`applies_to:["installation_risk"]`），无需新建阈值 ID。
- **EngineeringAgent 零改动**：`analyze_installation_risk` 内部替换为调用新计算单元，签名/调度/审核链不变（§1.2，pending_verification）。
- **Design 侧契约复用**：`field_provenance`/`threshold_refs` 直接消费（Design 候选 `glass_config`/`frame_series`），不重定义。
- **上游复用**：消费 Sprint E 的 `glass_safety_result`（玻璃重量）、Sprint G 的 `profile_result`（型材条件）、Sprint I 的 `hardware_result`（五金条件），不直接推算风压/玻璃/型材/五金（红线，§2.2/§5.2，pending_verification）。
- **结果模型同构**：InstallationRiskResult 与 WindPressureResult / GlassSafetyResult / ProfileResult / HardwareResult 字段同构（四字段 + 扩展八字段），降低编码阶段迁移成本。

---

## 5. 待主理人审核项

### 5.1 🟢 已闭合（设计内自查）
- 阈值 ID 命名与 Sprint A `INTERFACE_THRESHOLD_MAP` 一致（installation_risk → E-TH-05/E-TH-06，已存在占位），无需裁决。
- 输入四层边界清晰，与 glass_safety/profile/hardware 的耦合仅限 `xxx_result` 透传，无重叠歧义。

### 5.2 🟡 建议确认
1. **末端聚合抽象层级**：§1.3/§6 采用"installation_risk 末端聚合消费 glass_safety/profile/hardware 三上游"的聚合定位（区别于 Wind↓Profile↓Hardware 串行链路）。请主理人确认 installation_risk 是否应同时消费三上游产出，而非仅消费 hardware 末端。
2. **E-TH-06 四子维度拆分粒度**：§5 将"施工风险等级/吊装条件/人员操作风险/环境风险"定义为 E-TH-06 的四子维度审核占位（单一阈值 ID，内部多字段）。请确认该粒度是否符合预期，或是否需要拆分为独立阈值 ID。
3. **安全距离口径**：§4/§7 的 `D_safe`（施工安全距离）仅以符号/类别抽象，不写真实距离。请确认"以类别替代真实距离"的抽象方式是否符合专家双签预期。

### 5.3 ⛔ 编码启动前置
- `engineering_enabled` 保持 `false`，六门槛（阈值双签/Vision 调优/测试通过/审核链跑通/CI 8-8/主理人授权）未全满足前**禁止编码**。
- 真实规范条款号与参数值（风险分数/承载参数/安全距离）由专家双签阶段填入 `verified.json`（E-TH-05/E-TH-06 偿还路径）。

---

## 6. 阶段门状态

| 门 | 状态 |
|---|---|
| installation_risk 模块设计完成 | ✅ |
| 红线守约 | ✅ |
| fabrication 扫描 0 命中 | ✅ |
| 阈值 ID 一致性 | ✅（对齐 Sprint A，installation_risk→E-TH-05/E-TH-06，已占位） |
| engineering_enabled | ⛔ 保持 `false` |
| 编码启动 | ⛔ 等待主理人审核 + 六门槛全满足 |

---

## 7. 下一步建议（授权后编码阶段）

1. 主理人审核通过 + 六门槛满足后，进入 Sprint K（installation_risk 真实计算编码）。
2. 编码顺序建议：新增 `agents/engineering/calc/installation_risk.py` 计算单元（含 InstallationRiskResult）→ 新增 `agents/engineering/rules/installation_rules.py` 规则层 → 注入 `ExpertBackedEngineeringValidation` → 串联三上游 `glass_safety_result`/`profile_result`/`hardware_result` + Design/Project 输入契约 → 单测/集成/防编造测试 → 保持 `engineering_enabled=false` 直至全绿。
3. 编码全程零硬编码工程常数，所有数值仅来自 `verified.json`（E-TH-05/E-TH-06 pending 态为 null）。

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含代码实现，未开启 `engineering_enabled`，全参数 `pending_verification`）
