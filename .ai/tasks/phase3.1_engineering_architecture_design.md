# Phase 3.1 Engineering 整体架构设计（phase3.1_engineering_architecture_design.md）

- **生成**：2026-07-28（Phase 3.1 设计阶段 · 任务1）
- **身份**：BOIP AI 首席工程架构师
- **性质**：**纯架构设计，不编写任何业务代码**；不填真实工程参数、不开启 `engineering_enabled`。
- **依据**：`agents/engineering/agent.py` / `validation.py`（2.1.5 骨架实读）、`agents/design/thresholds/verified.json` + `threshold_loader.py`（2.2.2 阈值治理）、`ADR-2.2.1`（可信等级 Level 0–3 模型）、`phase3_execution_plan.md` §2
- **红线**：任何无据行业数字必须标 `pending_verification`；工程参数（风压/楼层/壁厚/评分权重/防腐等级）未经专家签字不得转正。

---

## 1. 当前 Engineering Agent 状态分析

| 维度 | 现状（2.1.5 骨架） | 缺口（3.1 需补） |
|---|---|---|
| 结构 | 继承 `BaseAgent`；`ANALYSIS_INTERFACES` 五接口契约稳定（`wind_pressure`/`glass_safety`/`profile`/`hardware`/`installation_risk`） | 接口仅空实现，无真实计算 |
| 输出结构 | `build_skeleton_output()` 统一四字段 `result/confidence/evidence/verification_status` | 四字段恒空串（防编造），无计算产出 |
| 审核链 | `EngineeringValidation` 抽象 + `PendingEngineeringValidation`（仅结构校验，结论恒 `pending_verification`） | 无真实规则/规范校验，无专家签字校验 |
| 阈值治理 | **仅 Design 侧** `verified.json`（D-TH-01~05，全 `verified=false`） | **缺 Engineering 侧**阈值库（风压/壁厚/玻璃/五金/安装）（pending_verification） |
| 工具声明 | `tools` 声明 `structural_calc_mcp` / `engineering_rules_mcp`（未连接） | 无 Rules Engine / MCP / 规范库接入 |
| 编排 | `invoke()` 分发五接口 → 走审核链 → `gaps` 登记 pending | `engineering_enabled=false`，不进管道 |

**结论**：骨架已锁定"接口契约 + 四字段 + 审核链骨架 + pending 默认"四大机制，3.1 设计只需在**不破坏契约**前提下，把"骨架空实现"替换为"真实计算 + 规范校验 + 专家双签校验"，并补齐 Engineering 侧阈值库与 Rules 接入。

---

## 2. 五大模块设计

> 统一约定：
> - **输入参数**：来自上游（`Design` 候选 / `Vision` 识别 / `Environment` 实测 / `verified.json` 签字项 / 项目上下文）；所有数值类输入若为"待签字"则标 `pending_verification`。
> - **输出结构**：在四字段基础上扩展模块专属字段，但四字段为强制。
> - **证据要求**：每条结论必须可回写 `evidence`（公式出处 + 参数来源 + 专家签字 ID）。
> - **验证等级**：沿用 `ADR-2.2.1` Level 0–3；工程计算经审核链批准 = **Level 3（Engineering approved）**，否则 Level 0（inferred，恒 pending）。
> - **pending 规则**：任一关键输入/阈值未 `is_fully_verified()` → 该模块结论 `pending_verification`，前端/PDF 仅渲染"AI 推理·待确认"。

### 2.1 wind_pressure（风压分析）

- **输入参数**：地理位置（经纬度/气候区）、建筑高度与层数、地面粗糙度类别、基本风压（来自 Engineering 侧 `verified.json` 签字项，未签字则 pending_verification）、体型系数、围护/主体区分。
- **输出结构**：`{result: {风荷载标准值, 阵风系数, 围护结构风压, 各受荷面结果}, confidence, evidence, verification_status}`。
- **证据要求**：荷载规范公式编号（source_ref）、基本风压来源（verified 项或 Environment 实测 `measured`）、专家签字 ID。
- **验证等级**：全部关键阈值 verified + 专家双签 → Level 3；否则 Level 0。
- **pending 规则**：基本风压/体型系数任一未签字 → 整模块 pending；仅展示推导过程与待确认结论。

### 2.2 glass_safety（玻璃安全）

- **输入参数**：玻璃配置（厚度/类型，来自 `Design` 候选 + `verified.json` D-TH-02）、风压分析输出、玻璃面积、边框支承条件。
- **输出结构**：`{result: {玻璃应力, 挠度, 安全系数, 是否达标}, confidence, evidence, verification_status}`。
- **证据要求**：玻璃规范公式、玻璃参数来源（D-TH-02 verified）、专家签字 ID。
- **验证等级**：玻璃参数 verified + 双签 → Level 3；否则 Level 0。
- **pending 规则**：玻璃厚度/类型未签字 → pending；面积等非签字输入缺失则降级 unavailable。

### 2.3 profile（型材分析）

- **输入参数**：型材系列与壁厚（来自 `verified.json` D-TH-01）、风压/自重受力、截面特性、连接条件。
- **输出结构**：`{result: {型材强度应力, 挠度, 安全系数}, confidence, evidence, verification_status}`。
- **证据要求**：型材规范公式、壁厚来源（D-TH-01 verified）、专家签字 ID。
- **验证等级**：壁厚/系列 verified + 双签 → Level 3（pending_verification）；否则 Level 0。
- **pending 规则**：型材壁厚未签字 → pending；截面特性由规则引擎计算并附 source。

### 2.4 hardware（五金分析）

- **输入参数**：五金选型（铰链/锁点/滑撑）、窗型与开启方式、受力（风压/自重）、使用频率。
- **输出结构**：`{result: {五金承载力, 安全余量, 推荐规格}, confidence, evidence, verification_status}`。
- **证据要求**：五金产品库（需新建，条目带 source + verified）、五金规范、专家签字 ID。
- **验证等级**：五金参数库 verified + 双签 → Level 3；否则 Level 0。
- **pending 规则**：无产品库/未签字 → pending；本模块强依赖"五金参数库"建设（3.1 实施子项）。

### 2.5 installation_risk（安装风险）

- **输入参数**：安装工况（高度/洞口/墙体材质）、窗型、环境（风/腐蚀等级，来自 `Environment` 实测或 `verified.json`）。
- **输出结构**：`{result: {风险等级, 薄弱点, 防护建议}, confidence, evidence, verification_status}`。
- **证据要求**：安装规范、工况数据来源（measured 或 verified）、专家签字 ID。
- **验证等级**：工况数据 verified/measured + 双签 → Level 3；否则 Level 0。
- **pending 规则**：工况数据未签字/未实测 → pending；风险等级结论不得仅凭 AI 推断。

---

## 3. EngineeringValidation 审核链设计

**演进原则**（不破坏骨架）：`EngineeringAgent` 侧零改动，仅将注入的 validator 由 `PendingEngineeringValidation` 替换为"真实校验实现"。

新增审核链实现（设计命名 `ExpertBackedEngineeringValidation`）的 `validate(interface, payload)` 返回记录扩展为：

```json
{
  "interface": "wind_pressure",
  "structure_valid": true,
  "threshold_verified": false,
  "expert_signed": false,
  "verification_status": "pending_verification",
  "sign_off_id": null,
  "validator": "ExpertBackedEngineeringValidation"
}
```

**校验门（逐接口）**：
1. 结构校验：四字段齐备（沿用 `REQUIRED_OUTPUT_KEYS`）。
2. 阈值校验：该模块依赖的 `verified.json` 项 `is_fully_verified()`（verified + verified_by + verified_at 俱全）。
3. 专家校验：审核链记录携带 `sign_off_id`（双签产物，见任务3）。
4. 状态裁定：`threshold_verified && expert_signed` → `verification_status="engineering_approved"`（Level 3）；否则 `pending_verification`（Level 0）。

**聚合**：`invoke()` 收集五接口记录成 `review_chain`；整体 `pending_verification` = 任一接口非 engineering_approved。`AgentResult.data.review_chain` 直接供 PDF 渲染审核链章节。

---

## 4. engineering_enabled 开启条件设计

满足**全部**六门槛方可置 `config.yaml: engineering.enabled=true`：

1. Engineering 侧 `verified.json` 关键阈值 `is_fully_verified()==True` 且 `verified_by`/`verified_at` 齐备（TD-002 偿还）。
2. `Vision` prompt 专家调优完成并附评测集（TD-016，与阈值同批）。
3. Engineering Agent 五接口真实计算 + 单元测试/集成测试通过（见任务4 测试方案）。
4. 专家审核链端到端跑通（`ExpertBackedEngineeringValidation` 双签生效，见任务3）。
5. `bash scripts/ci/local_ci.sh` 8/8 全绿、覆盖率不降（backend ≥60% / 前端 ≥50%）。
6. 主理人最终授权（本设计评审通过 + 验收）。

> 任一门未过 → 保持 `enabled=false`，计算链降级 pending，绝不报送"工程确认"。

---

## 5. 与 Design Agent 连接方式

- **数据契约**：`analysis/run` 编排器将 `Design` 候选（`frame_material`/`glass_type`/`dimensions_hint`/`estimated_cost_tier`/`scheme_scoring`）与 `field_provenance`（verified/inferred）一并传入 `EngineeringAgent.invoke(input_data.design_candidate)`。
- **阈值联动**：Engineering 读取 Design 侧 `verified.json`（D-TH-01~05）与 Engineering 侧阈值库，经 `threshold_loader.build_threshold_refs()` 获取引用槽位，判定每个输入是 verified 还是 inferred。
- **pending 传导**：若 Design 候选字段为 `inferred`（未签字），Engineering 将该输入标 `pending_verification`，依赖此输入的模块结论保持 pending（不伪造"基于未验证设计的可信工程结论"）。
- **双 Agent 协同语义**：Design = "方案建议（含待确认参数）"；Engineering = "在已签字参数上做安全审核"。二者通过 `threshold_refs` + `field_provenance` 对齐，共用同一可信等级模型。

---

## 6. 与 PDF Report 连接方式

- **消费点**：`ReportGenerator` 读取 `EngineeringAgent` 的 `analyses` + `review_chain` + 顶层 `verification_status`，渲染"工程审核"章节。
- **可信徽标**：每个模块沿用 PDF 既有三态徽标 —— `[已验证]`（Level 3 engineering_approved）/ `[AI推理·待确认]`（Level 0）/ `[待确认]`（unavailable）；落实"不把 AI 推理包装成工程确认"。
- **审核链透出**：`review_chain` 逐接口渲染（接口名 / 阈值校验 / 专家签字 / 状态），形成可追溯审核记录。
- **待确认脚注**：pending 模块下方渲染"工程参数待专家签字确认（pending_verification）"，与 Design/Environment 的 provenance 脚注同源。
- **统一模型**：Engineering 的 Level 0–3 与 Design/Environment 的可信等级章节合并为单一"数据可信等级"说明段。

---

## 7. 风险分析

| ID | 风险 | 等级 | 缓解（设计层） |
|---|---|---|---|
| R-E1 | 阈值未签字即上线报送"工程确认" | 高 | `is_fully_verified()` 一票否决 + pending 默认 + 六门槛 |
| R-E2 | AI 自行推导工程公式/参数（红线） | 高 | 公式来自规范（verified source_ref）；参数来自 `verified.json`；AI 不推导数值（见 ADR） |
| R-E3 | 专家双签流程执行不严 | 中 | 审核链强制 `verified_by`+`verified_at`+`sign_off_id` 三字段齐全 |
| R-E4 | 计算引擎数值错误 | 中 | 对照样本测试 + 确定性复算 + 边界用例 |
| R-E5 | 与 Design/Environment 数据契约漂移 | 中 | 统一四字段 + `field_provenance` + `threshold_refs`，契约冻结 |
| R-E6 | `engineering_enabled` 误开 | 中 | 六门槛 + 主理人授权，CI 不自动开 |
| R-E7 | 五金参数库缺失致 hardware 模块长期 pending | 低 | 3.1 实施子项明确"建五金产品库"，未建前该模块显式 pending |

**END**（本文件为架构设计，不含代码实现；编码须在主理人授权 Phase 3.1 后启动）
