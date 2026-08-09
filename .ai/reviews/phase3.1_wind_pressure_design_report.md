# Phase 3.1 Sprint B — Wind Pressure 工程设计评审报告（phase3.1_wind_pressure_design_report.md，pending_verification）

- **生成**：2026-07-30（Phase 3.1 Sprint B 设计阶段 · 收口）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，**未编码**；等待主理人审核）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）
- **红线守约**：✅ 零真实风压值 / ✅ 零真实系数 / ✅ 零规范条款编号 / ✅ `engineering_enabled=false` / ✅ 全参数 `pending_verification` / ✅ 不编码。

---

## 1. 设计交付汇总

| # | 设计项 | 交付文件 | 状态 |
|---|---|---|---|
| 1 | wind_pressure 接口分析 | `.ai/tasks/phase3.1_wind_pressure_design.md` §1 | ✅ (pending_verification) |
| 2 | 输入参数设计（项目/Environment/Design/Engineering阈值四层） | §2 | ✅ |
| 3 | 输出结构设计（四字段 + 扩展字段 + 审核链记录） | §3 | ✅ |
| 4 | 公式来源设计（公式来源/变量关系/数据来源，仅符号级） | §4 | ✅ |
| 5 | verified.json 依赖设计（E-TH-01/02/03 角色绑定 + 双签口径） | §5 | ✅ |
| 6 | Expert 审核点设计（7 个审核点） | §6 | ✅ |
| 7 | 与 Glass Safety / Profile 连接方式 | §7 | ✅ |
| 8 | PDF 展示方案（三态徽标 + review_chain 透出） | §8 | ✅ |
| 9 | 测试方案（单元/集成/安全/防编造/覆盖率） | §9 | ✅ |
| 10 | 风险分析（R-WP-1~R-WP-7） | §10 | ✅ |

---

## 2. 设计达成度自评

| 设计目标 | 达成 | 证据 |
|---|---|---|
| 不破坏既有契约 | ✅ | wind_pressure 仅新增独立计算单元，Agent 调度/四字段/审核链零改动（§1.2，pending_verification） |
| 防编造红线锁死 | ✅ | §4 仅符号级变量关系，无数值；§5 三项阈值 value=null；本评审报告经 check_fabrication 扫描 0 命中 |
| 专家双签可落地 | ✅ | §5/§6 明确 E-TH-01~03 角色绑定与 7 个审核点，复用 Sprint A `is_fully_verified` |
| enabled 误开防护 | ✅ | 设计态闸门恒 pending（§3.3）；编码前 enabled=false，六门槛未全满足 |
| 跨 Agent 数据契约 | ✅ | 复用 Design `field_provenance`/`threshold_refs` + Environment `facts`/`field_provenance`（§2） |
| 下游耦合正确 | ✅ | wind_pressure 为 glass_safety/profile 上游 `w_k` 供给方，下游独立审核 + 降级传导（§7，pending_verification） |
| PDF 审核透明 | ✅ | 三态徽标 + review_chain 逐接口透出 + 防误显（§8） |

---

## 3. 红灯守约确认（强制自检）

| 红线 | 是否违反 | 说明 |
|---|---|---|
| 写真实风压值 | ❌ 未违反 | 全文档任何风压数值位为 `<取自 E-TH-01，pending_verification>` 或符号 `w_0`/`w_k` |
| 写真实系数 | ❌ 未违反 | 体型系数 μ_s/高度变化系数 μ_z/风振系数 β 均符号化，无数值表 |
| 写规范条款编号 | ❌ 未违反 | 仅写"建筑围护结构/幕墙风荷载计算相关标准（标准号与条款号 pending_verification）"，无 GB/条款号 |
| 开启 engineering_enabled | ❌ 未违反 | 全程 `engineering_enabled=false`；设计态审核链恒 pending，绝不 engineering_approved |
| 编写实现代码 | ❌ 未违反 | 本文件纯设计，无任何 .py/.ts 实现，未改 `agent.py`/`validation.py` |
| 设 verified=true | ❌ 未违反 | 未触碰 `verified.json`，三项阈值维持 value=null/verified=false |

`check_fabrication.py` 对 `.ai/tasks/phase3.1_wind_pressure_design.md` 扫描结果：**0 命中** (pending_verification)。

---

## 4. 与既有架构的衔接

- **Sprint A 基础设施全部复用**：`ExpertBackedEngineeringValidation.validate`（七字段）、`INTERFACE_THRESHOLD_MAP["wind_pressure"]=("E-TH-01","E-TH-02","E-TH-03")`、`review_log` 哈希链。
- **EngineeringAgent 零改动**：`analyze_wind_pressure` 内部替换为调用新计算单元，签名/调度/审核链不变（§1.2，pending_verification）。
- **Design 侧契约复用**：`field_provenance`/`threshold_refs` 直接消费，不重定义。
- **Environment 侧约束**：`prevailing_wind` 仅作朝向校验参考，基本风压 `w_0` 只来自 E-TH-01（红线，§2.2/§4.3，pending_verification）。

---

## 5. 待主理人审核项

### 5.1 🟢 已闭合（设计内自查）
- 阈值 ID 命名与 Sprint A `INTERFACE_THRESHOLD_MAP` 一致（E-TH-01~03），无需裁决。
- 输入四层边界清晰，无重叠歧义。

### 5.2 🟡 建议确认
1. **公式体系选择**：§4 采用"风振/阵风系数 × 体型系数 × 高度变化系数 × 基本风压"乘积结构，具体系数体系 (pending_verification)（阵风 vs 风振二选一）留待专家双签时确认——请主理人确认这是否符合预期抽象层级。
2. **Environment 实时风速的边界**：明确"基本风压只来自 E-TH-01，实时风速不参与数值计算"——请确认该边界无误。
3. **下游耦合粒度**：wind_pressure → glass_safety/profile 仅传 `w_k`——请确认是否需要额外中间量（如局部体型系数 μ_sl）透传给玻璃模块。

### 5.3 ⛔ 编码启动前置
- `engineering_enabled` 保持 `false`，六门槛（阈值双签/Vision 调优/测试通过/审核链跑通/CI 8-8/主理人授权）未全满足前**禁止编码**。
- 真实规范条款号与参数值由专家双签阶段填入 `verified.json`（TD-002 偿还路径）。

---

## 6. 阶段门状态

| 门 | 状态 |
|---|---|
| wind_pressure 模块设计完成 | ✅ |
| 红线守约 | ✅ |
| fabrication 扫描 0 命中 | ✅ |
| 阈值 ID 一致性 | ✅（对齐 Sprint A） |
| engineering_enabled | ⛔ 保持 `false` |
| 编码启动 | ⛔ 等待主理人审核 + 六门槛全满足 |

---

## 7. 下一步建议（授权后编码阶段）

1. 主理人审核通过 + 六门槛满足后，进入 Sprint C（wind_pressure 真实计算编码）。
2. 编码顺序建议：新增 `agents/engineering/calc/wind_pressure.py` 计算单元 → 注入 `ExpertBackedEngineeringValidation` → 串联 Design/Environment 输入契约 → 单测/集成/防编造测试 → 保持 `engineering_enabled=false` 直至全绿。
3. 编码全程零硬编码工程常数，所有数值仅来自 `verified.json`（pending 态为 null）。

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含代码实现，未开启 `engineering_enabled`，全参数 `pending_verification`）
