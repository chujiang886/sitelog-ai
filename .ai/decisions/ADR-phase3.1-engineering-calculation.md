# ADR-phase3.1-engineering-calculation：工程计算架构决策

- **状态**：✅ ACCEPTED（架构级决策生效；真实规范条款号与参数值显式 DEFERRED，见各模块"规范依据/数据来源"）
- **日期**：2026-07-28
- **决策人**：BOIP AI 首席工程架构师（Phase 3.1 设计阶段，主理人授权自动执行模式）
- **依据**：`.ai/tasks/phase3.1_engineering_architecture_design.md`、`.ai/tasks/phase3_execution_plan.md` §2、`ADR-2.2.1`（可信等级模型）、`agents/engineering/validation.py`（审核链契约）
- **红线**：本 ADR **不填写任何真实工程参数**（风压/楼层/壁厚/评分权重/防腐等级数值均 `pending_verification`）；**不开启 `engineering_enabled`**；AI 不得自行推导规范公式或工程常数。

---

## 0. 全局原则（适用于全部计算模块）

1. **参数唯一事实源 = `verified.json`**：所有工程常数（基本风压、体型系数、壁厚、玻璃配置、五金承载力、腐蚀等级）必须由专家签字填入，AI 不得凭训练记忆补值。
2. **公式唯一事实源 = 国家/行业现行规范**：公式结构由规范给定，`source_ref` 记录条款；AI 不重写、不近似、不外推。
3. **验证状态二分**：经"阈值 verified + 专家双签"→ `engineering_approved`（Level 3）；否则 `pending_verification`（Level 0），前端/PDF 仅渲染"AI 推理·待确认"。
4. **降级不阻断**：任何输入缺失/未签字 → 该模块降级 pending + `gaps` 登记，`invoke` 永不因计算失败崩溃。

---

## 1. wind_pressure（风压分析）

- **数据来源**：
  - 基本风压：Engineering 侧 `verified.json`（E-TH-01，当前 `value=null`，`pending_verification`）；
  - 地理位置/气候区/粗糙度：项目上下文 + `Environment` Agent 实测（若启用，标 `measured`）；
  - 建筑高度与层数：项目上下文（数值由用户输入，非 AI 推断）。
- **公式来源**：国家建筑结构荷载相关规范给定的风荷载标准值计算式（变量形式 `wk = βgz · μs · μz · w0`，系数由 `verified.json` 提供，`pending_verification`）；AI 不推导系数。
- **规范依据**：建筑结构荷载相关国家规范（具体条款号由专家签字确认，`pending_verification`）；现行版本以专家核定为准。
- **专家审核点**：E-TH-01 基本风压值 + E-TH-02 体型系数 + E-TH-03 粗糙度类别，须经行业专家签字（`verified_by`/`verified_at` 双控）。
- **禁止 AI 自行推导范围**：不得用训练记忆中的任何风压常数；不得自造体型系数；不得在未签字时声称风压达标；不得将 LLM 估算包装成规范值。

## 2. glass_safety（玻璃安全）

- **数据来源**：
  - 玻璃厚度/配置：Design 侧 `verified.json` D-TH-02（当前 `pending_verification`）；
  - 风压输出：本 Agent `wind_pressure` 模块结果；
  - 玻璃面积/支承：项目上下文。
- **公式来源**：建筑玻璃应用相关国家规范给定的应力/挠度计算式（变量形式，系数来自 `verified.json`，`pending_verification`）；AI 不推导。
- **规范依据**：建筑玻璃应用技术标准（具体条款由专家签字确认，`pending_verification`）。
- **专家审核点**：D-TH-02 玻璃配置阈值 + 安全系数判据，须专家签字。
- **禁止 AI 自行推导范围**：不得自造玻璃厚度/许用应力；不得在未签字玻璃参数下断言"安全/不安全"；不得用常识估算替代规范校核。

## 3. profile（型材分析）

- **数据来源**：
  - 型材系列/壁厚：Design 侧 `verified.json` D-TH-01（当前 `pending_verification`）；
  - 受力：本 Agent `wind_pressure` + 自重；
  - 截面特性：由规则引擎按型材库计算（库条目带 `source`）。
- **公式来源**：铝合金门窗/型材相关国家规范的强度与挠度计算式（变量形式，系数来自 `verified.json`，`pending_verification`）。
- **规范依据**：铝合金门窗工程技术相关国家规范（具体条款由专家签字确认，`pending_verification`）。
- **专家审核点**：D-TH-01 型材壁厚/系列阈值 + 许用应力，须专家签字。
- **禁止 AI 自行推导范围**：不得自造壁厚或截面惯性矩；不得将 LLM 估算的强度当作规范结论；未签字型材参数下结论恒 pending。

## 4. hardware（五金分析）

- **数据来源**：
  - 五金承载力：须新建"五金参数库"（条目带 `source` + `verified`，当前未建，`pending_verification`）；
  - 窗型/开启方式/受力：Design 候选 + `wind_pressure` 输出。
- **公式来源**：五金选型相关行业规范/产品手册给定的承载力计算式（变量形式，系数来自参数库，`pending_verification`）。
- **规范依据**：门窗五金相关国家/行业规范与产品标准（具体条款由专家签字确认，`pending_verification`）。
- **专家审核点**：五金参数库条目 + 选型判据，须专家签字入库。
- **禁止 AI 自行推导范围**：不得凭记忆编造五金规格承载力；参数库未建前该模块显式 pending，不得给出"推荐规格"结论。

## 5. installation_risk（安装风险）

- **数据来源**：
  - 安装工况（高度/洞口/墙体材质）：项目上下文；
  - 腐蚀等级：Environment 实测（若启用，标 `measured`）或 `verified.json`（当前 `pending_verification`）；
  - 窗型：Design 候选。
- **公式来源**：安装风险评级采用规范给定的评级矩阵（非连续公式），矩阵由 `verified.json` 提供，`pending_verification`；AI 不推导评级阈值。
- **规范依据**：门窗安装相关国家/行业规范（具体条款由专家签字确认，`pending_verification`）。
- **专家审核点**：腐蚀等级阈值 + 风险评级矩阵，须专家签字。
- **禁止 AI 自行推导范围**：不得自造风险等级阈值；不得仅凭 LLM 常识判定"高风险/低风险"；工况数据缺失时结论恒 pending。

---

## 6. 实施约束（编码阶段遵守，本 ADR 生效范围）

| 项 | 本 ADR 强制 |
|----|------------|
| 参数填充 | 仅经专家双签写入 `verified.json`，AI 代码零硬编码工程常数 |
| 公式实现 | 严格按 `source_ref` 规范条款，系数全部取自 `verified.json`/参数库 |
| 状态输出 | 未达"阈值 verified + 双签"→ `pending_verification`，不得标 `engineering_approved` |
| 开关 | `engineering_enabled` 保持 `false` 直至 §4 六门槛全满足 + 主理人授权 |
| 红线测试 | 新增"防编造"测试锁死：任何未签字参数不得出现于 `engineering_approved` 输出 |

*ADR-phase3.1-engineering-calculation ｜ 生效：2026-07-28 ｜ 上游：.ai/tasks/phase3.1_engineering_architecture_design.md ｜ 下游：.ai/reviews/phase3.1_design_readiness_report.md*
