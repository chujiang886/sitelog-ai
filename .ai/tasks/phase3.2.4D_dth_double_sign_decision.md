# BOIP Phase 3.2 Sprint 3.2.4-D — D-TH 双签决策方案

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：真实阈值接入前的「D-TH 双签路径决策」设计——**本阶段不填写真实工程参数、不修改 verified.json、不设置 verified=true、不开 engineering_enabled**，全部保持 `pending_verification`。本文档只比较两条路径并给出推荐，最终决策待主理人书面授权。

---

## 0. 问题背景

设计侧阈值库 `agents/design/thresholds/verified.json` 的 D-TH-01~05 当前**仅有主理人单签位**（`verified_by` / `verified_at`），**缺少行业专家签字位**（`expert_verified_by` / `expert_verified_at`）。而工程侧 E-TH-01~06 已具备双签位。

双签语义由 `agents/engineering/threshold_loader.is_fully_verified` 强制：`mgmt_signed`（主理人）**AND** `expert_signed`（专家）缺一不可。因此：
- 对 D-TH：当前 `expert_signed=False` → `is_fully_verified=False` 永远成立。
- 影响接口：`profile → D-TH-01`、`glass_safety → D-TH-02` 永远无法 `engineering_approved`。

这构成 3.2.4 §5、3.2.5-C §7 已识别的高优先级开放项。本 Sprint 给出两条路径的对比与推荐。

---

## 1. 方案 A：D-TH 补专家双签位

为 D-TH-01~05 新增 `expert_verified_by` / `expert_verified_at` 两个字段位，与 E-TH 完全同构。

### 1.1 迁移动作（衔接 3.2.4-D 迁移 M6）
- D-TH 每条补 `expert_verified_by` / `expert_verified_at`（真实化时由专家签署填入，本阶段 null）；
- 复用既有 `threshold_loader.expert_signed` / `is_fully_verified`，零逻辑改动；
- `INTERFACE_THRESHOLD_MAP` 中 `profile` / `glass_safety` 无需改映射。

### 1.2 安全性
- ✅ 全接口统一"主理人 + 行业专家"双签，杜绝单方自批；
- ✅ `review_log` 中 `expert_recheck` 事件对 D-TH 同样可追溯；
- ✅ 满足 3.2.5-C SoD 约束（主理人 ≠ 专家签署人）。

### 1.3 一致性
- ✅ 工程侧 E-TH 与设计侧 D-TH 同构双签，治理语义统一；
- ✅ `governance_status` / `is_fully_verified` 对全部阈值一视同仁，无特例分支；
- ✅ 灰度门禁 G1/G2 对所有接口统一生效，无需为 profile/glass_safety 写例外。

### 1.4 长期影响
- ✅ 型材/玻璃接口具备转正前提，首个灰度接口锁定 wind_pressure 后，profile/glass_safety 可后续独立灰度；
- ✅ 未来新增 Design 侧阈值（如 D-TH-03~05 用于方案选型）天然支持双签；
- ⚠️ 需为 D-TH 补一次专家签字流程（组织成本，一次性）。

---

## 2. 方案 B：D-TH 保持单签

保留 D-TH 仅主理人单签，修改 `validation.py` 对复用 D-TH 的接口（`profile` / `glass_safety`）**放宽双签要求**（仅校验 `mgmt_signed`）。

### 2.1 迁移动作
- D-TH 结构不动；
- `ExpertBackedEngineeringValidation` 增加接口级豁免：对 `profile` / `glass_safety` 跳过 `expert_signed` 校验；
- 需新增豁免白名单配置，且须与 `INTERFACE_THRESHOLD_MAP` 联动维护。

### 2.2 安全性
- ❌ 型材/玻璃阈值无行业专家独立背书，单方（主理人）即可点亮双签中的专家位（逻辑等效）；
- ❌ 破坏"所有工程阈值须经行业专家签字"的核心红线语义，审计链中缺 `expert_recheck` 事件；
- ❌ 若主理人越权，无第二道防线。

### 2.3 一致性
- ❌ 工程侧（双签）与设计侧（单签）语义分裂，治理代码需特例分支；
- ❌ 灰度门禁 G2 对部分接口失效，门禁逻辑复杂化（需区分"哪些接口允许单签"）；
- ❌ 与 3.2.5-C SoD 约束冲突（同一人可完成全部签署动作）。

### 2.4 长期影响
- ❌ 后续任何复用 D-TH 的接口都被默认置于"弱审核"状态，技术债累积；
- ❌ 审计与合规复核时难以解释"为何部分接口无专家签字"；
- ✅ 组织上省去一次专家签字流程（短期成本优势，但代价高昂）。

---

## 3. 对比矩阵

| 维度 | 方案 A（补双签） | 方案 B（保持单签） |
|---|---|---|
| 安全性 | 高（统一双签防线） | 低（单点可自批） |
| 一致性 | 高（全接口同构） | 低（工程/设计分裂） |
| 长期维护 | 低（无特例） | 高（豁免白名单蔓延） |
| 审计完整 | 完整（expert_recheck 齐） | 缺专家事件 |
| SoD 合规 | 满足 | 违反 |
| 组织成本 | 一次性专家签字 | 短期省，长期债 |
| 灰度门禁 G2 | 统一生效 | 需接口级豁免 |

---

## 4. 推荐

**推荐方案 A（D-TH 补专家双签位）。**

理由：
1. **安全优先**：工程审核闭环的核心价值即"行业专家独立背书"，方案 B 实质架空该防线；
2. **语义统一**：与 E-TH 同构，治理代码零特例，`governance_status` / `is_fully_verified` 一视同仁，降低长期维护成本；
3. **灰度合规**：G1/G2 门禁对所有接口统一生效，无需例外分支，符合 3.2.5-B 设计；
4. **可渐进**：首个灰度接口仍锁定 `wind_pressure`（仅依赖 E-TH-01 与 E-TH-03），D-TH 双签补全后 `profile` / `glass_safety` 可独立后续灰度，不阻塞 3.2.5 首发（pending_verification）。

**实施约束（方案 A）**：D-TH 补专家签字须与 E-TH 一样经 `review_log` 完整 `submit → review_approve → expert_recheck → threshold_verified` 链路，且专家签署人须与主理人异角色（SoD）。该约束写入 3.2.4 实施验收清单。

**待主理人定夺**：最终采纳方案 A 或方案 B，须以书面授权形式确认；若采纳 A，迁移脚本（3.2.4-D 迁移 M6）按方案 A 执行。本阶段不预置任何决策结果。

---

**本阶段交付边界**：本文档为 D-TH 双签路径决策设计，未修改任何代码、未修改 verified.json、未开启 engineering_enabled，全部阈值保持 pending_verification。最终决策待主理人书面授权。
