# Glass Safety 工程模块设计（Sprint D）

- **生成**：2026-07-30（Phase 3.1 Sprint D 设计阶段）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，未编码；**不进入实现**）
- **依赖**：Sprint A 已交付（Engineering 阈值体系 + ExpertBackedEngineeringValidation + review_log 审核链 + 防编造扫描 + CI 8/8）；Sprint B 已完成 wind_pressure 设计；Sprint C 已完成 wind_pressure 结构化编码（上游 w_k 供给方就绪，pending_verification）
- **红线守约**：本文件**零真实玻璃厚度值、零真实安全系数、零规范条款编号**；`engineering_enabled=false`；所有参数 `pending_verification`；不编写任何实现代码。

---

## 0. 设计范围与边界

| 项 | 范围 |
|---|---|
| ✅ 本次定义 | glass_safety 接口的分析设计（输入/输出/规则来源/阈值依赖/审核点/与 wind_pressure 连接/PDF/测试/风险） |
| ⛔ 本次不做 | 任何 Python/TS 实现、任何数值计算、任何 `verified=true` 写入、`engineering_enabled` 置真 |
| 🔗 衔接 | 复用 Sprint A 的 `ExpertBackedEngineeringValidation`、`INTERFACE_THRESHOLD_MAP`、`review_log`；复用 Design 侧 `field_provenance`/`threshold_refs` 契约；消费 Sprint C 的 wind_pressure 上游 `w_k` |

> 设计态正确表现：每个数值位均为 `<取自 D-TH-02 / wind_pressure，pending_verification>` 或符号占位；不得出现任何具体数字、厚度表、安全系数表、条款号。

---

## 1. 当前 glass_safety 接口分析

### 1.1 骨架现状（实读 `agents/engineering/agent.py`）

- `ANALYSIS_INTERFACES` 含 `"glass_safety"`，与 `wind_pressure`/`profile`/`hardware`/`installation_risk` 并列（五接口之一）。
- `EngineeringAgent.analyze_glass_safety(context_data)` 当前为**骨架实现**：
  - 签名 `(self, context_data: Mapping[str, Any]) -> dict[str, Any]`；
  - 内部 `del context_data`（不消费输入，仅锁定签名）；
  - 返回 `build_skeleton_output()`：四字段全空 + `verification_status="pending_verification"`。
- `invoke()` 调度：`dispatch["glass_safety"] = self.analyze_glass_safety`；每个接口产出经 `self._validator.validate(interface="glass_safety", payload=output)` 生成一条 `review_chain` 记录。
- 默认 validator：`PendingEngineeringValidation`（仅结构校验，恒 pending）。Sprint A 已新增可注入的 `ExpertBackedEngineeringValidation`（双签闸门）。

### 1.2 演进路径（Sprint D 设计 → 编码阶段）

**EngineeringAgent 侧零改动**（与 3.1 架构设计一致）。真实计算的接入方式：

- 新增独立计算单元 `agents/engineering/calc/glass_safety.py`（或等价的 `GlassSafetyCalculator`），**不修改** `agent.py`；
- `analyze_glass_safety()` 内部从骨架直返，改为调用计算单元并把结果按统一四字段结构封装；
- validator 仅替换为 `ExpertBackedEngineeringValidation`（已在 Sprint A 落地），Agent 调度逻辑不变；
- 计算单元的输出对象统一含 `result / confidence / evidence / verification_status` + 扩展字段（`intermediate` / `provenance` / `gaps` / `threshold_refs` / `sign_off_id` 占位），结构与 wind_pressure 的 `WindPressureResult` 同构。

### 1.3 与 wind_pressure 的关系

- wind_pressure 是 glass_safety 的**上游数据供给方**：wind_pressure 产出风荷载标准值 `w_k`（Pa），作为玻璃抗风压/最大许用面积计算的输入荷载（详见 §4、§7，pending_verification）。
- glass_safety **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03），只消费 wind_pressure 的 `w_k`。
- 跨模块退化传导：若 wind_pressure 的 `w_k` 不可信（`verification_status != engineering_approved` 或 `w_k.value=None`），glass_safety 即使自身阈值已签，结论仍须 `pending_verification`（详见 §7.3）。

### 1.4 输入/输出契约锚点

- 输入：`context_data` 应透传 `project` / `environment_result` / `design_candidate` / `wind_pressure_result`（上游分析产物）/ `vision_result` 等；骨架阶段不消费，设计阶段明确其字段契约（见 §2，pending_verification）。
- 输出：统一四字段 + 扩展字段（见 §3），经 `ExpertBackedEngineeringValidation.validate` 产出审核链记录。

---

## 2. 输入参数设计

glass_safety 计算所需输入分四层，均须携带**溯源标签**（`measured` / `inferred` / `verified` / `unavailable`），任何 `inferred`/`unavailable` 关键输入 → 该模块结论 `pending_verification`。

### 2.1 项目输入（Project Input）

| 字段 | 含义 | 溯源预期 | 用途 |
|---|---|---|---|
| `project.glass_area` / `project.panel_short_side` / `project.panel_long_side` | 玻璃分格面积与边长 | `inferred`（来自 Vision/Design 候选） | 决定玻璃受荷面积与应力/挠度计算几何（符号占位，数值 pending） |
| `project.support_condition` | 玻璃支承条件（四边支承 / 对边支承） | `inferred`（来自几何识别） | 选择应力/挠度系数体系（符号占位，数值 pending） |
| `project.building_height` | 建筑高度 | `inferred`（来自 Vision/用户） | 与 wind_pressure 共享，间接影响 w_k；gaps 登记 |
| `project.opening_position` / `project.orientation` | 开口/幕墙位置与朝向 | `inferred`（Vision） | 间接影响上游 w_k 取值（由 wind_pressure 消费） |

### 2.2 Environment 输入（来自 `EnvironmentAgent` 输出 + 上游 wind_pressure）

- **wind_pressure 输出 `w_k`（关键跨模块输入）**：glass_safety 从 `context_data["wind_pressure_result"]` 读取（即 `WindPressureResult.as_full()` 或等价结构），取 `intermediate["w_k"]`：
  - 若 `wind_pressure_result.verification_status == engineering_approved` 且 `w_k.value` 非 None → 可信荷载；
  - 否则 → `w_k` 不可信，glass_safety 登记 gap 并结论 `pending_verification`（§7.3 退化传导）。
- 复用 `agents/environment/agent.py` 的 `field_provenance` 与 `facts`（如 `climate_zone`/`prevailing_wind` 仅作环境描述参考，不直接进入玻璃应力公式）。

> ⚠️ 红线：玻璃荷载来自 wind_pressure 的 `w_k`，**绝不**由 Environment 实时气象直接推算玻璃受荷（基本风压只来自 E-TH-01，由 wind_pressure 归一化后供给）。

### 2.3 Design 输入（来自 `DesignAgent` 候选）

复用 `agents/design/agent.py` 的候选结构与 `threshold_loader`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `design_candidate.glass_type` | Design 候选（**D-TH-02** 引用） | 玻璃选型（类型/构造/配置），glass_safety 核心消费项；数值 pending |
| `design_candidate.dimensions_hint` | Design 候选 | 分格尺寸建议，`inferred`；驱动 `project.glass_area` / 边长 |
| `design_candidate.frame_material` | Design 候选（D-TH-01 引用） | 型材选型，仅影响下游 `profile`；glass_safety 不直接消费 |
| `field_provenance` / `threshold_refs` | Design 输出 | 复用字段级溯源，glass_safety 仅读取，不改写 |

### 2.4 Engineering 阈值输入（来自 `verified.json` via `threshold_loader`）

| 阈值 ID | 参数 | 单位 | 喂给的变量 | 双签要求 |
|---|---|---|---|---|
| `D-TH-02` | 玻璃配置（玻璃类型 / 玻璃厚度 / 安全系数体系） | （配置标识，pending） | `glass_type` / `t`（玻璃厚度）/ `K`（安全系数）/ `σ_allow`（允许应力） | 主理人 + 行业专家双签 |

> 设计态：D-TH-02 `value=null`、`verified=false`、双签字段 `null`、`source_ref` 含 `pending_verification`。未双签前，计算单元不得取得任何玻璃配置数值（厚度/安全系数），输出恒 `pending_verification`。

---

## 3. 输出结构设计

### 3.1 统一四字段（接口契约，勿改键名）

```jsonc
{
  "result": "<玻璃抗风压/最大许用面积结论，pending 态为空或推导占位；approved 后填符号化结论>",
  "confidence": "<可信等级标签：pending 态为 'pending_verification'；approved 后为 'verified'>",
  "evidence": "<来源说明：规则来源 + 各变量取值来源 + source_ref（规范条款号 pending_verification）>",
  "verification_status": "pending_verification"   // 双签齐 + enabled=true + w_k 可信 才转 engineering_approved
}
```

### 3.2 扩展字段（计算单元内部承载，供审核链/PDF 消费）

| 字段 | 含义 |
|---|---|
| `interface` | `"glass_safety"`（固定） |
| `intermediate` | 中间变量字典：`{ "w_k": <from wind_pressure, pending>, "t": <from D-TH-02 玻璃厚度, pending>, "A": <玻璃面积, pending>, "support": <支承条件, pending>, "sigma_g": <玻璃弯曲应力, pending>, "sigma_allow": <允许应力, pending>, "K": <安全系数, pending>, "A_max": <最大许用面积, pending> }` |
| `provenance` | 每个输入字段的溯源标签（`measured`/`inferred`/`verified`/`unavailable`） |
| `threshold_refs` | `["D-TH-02"]`（仅引用，数值 pending） |
| `gaps` | 缺失/未签字项登记（如 `D-TH-02: pending_verification`、`w_k: upstream_pending`） |
| `sign_off_id` | 占位 `null`（仅 approved 后由 `review_log.compute_sign_off_id` 派生） |

### 3.3 审核链记录（经 `ExpertBackedEngineeringValidation.validate` 产出）

七字段（Sprint A 已定义）：
`interface / structure_valid / threshold_verified / expert_signed / verification_status / sign_off_id / validator`。

- `threshold_verified`：`get_interface_thresholds("glass_safety")` 返回 `("D-TH-02",)`，D-TH-02 `mgmt_signed` 才 True；
- `expert_signed`：D-TH-02 `expert_signed` 才 True；
- 闸门：`structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` → `engineering_approved`，否则恒 `pending_verification`；
- **叠加跨模块闸门**：即便上述四项满足，若上游 `w_k` 不可信（wind_pressure 未 approved），glass_safety 计算单元在 `verification_status` 仍强制 `pending_verification` 并登记 `gaps`（见 §7.3）。

---

## 4. 规则体系设计（仅定义：公式来源 / 变量关系 / 数据来源；禁止真实参数）

建立 `agents/engineering/rules/glass_rules.py`，承载 glass_safety 的**符号级规则结构**：公式来源、变量关系、数据来源映射；**不保存任何真实工程常数（厚度 / 安全系数 / 许用应力数值 / 规范条款号）**。

### 4.1 公式来源（概念级）

- 参考建筑**玻璃幕墙/采光顶玻璃在风荷载下的强度与挠度**相关标准与规范（**具体标准号与条款号均由行业专家双签阶段填入，pending_verification**）。
- 采用业界通用的**荷载—应力—校核**结构：在风荷载标准值 `w_k` 作用下，玻璃弯曲应力 `σ_g` 与支承条件、分格几何、玻璃厚度相关；并对比允许应力 `σ_allow`（含安全系数 `K`）判定安全；同时校核最大许用面积 `A_max`。
- 适用性边界（四边支承/对边支承的系数体系、是否计入温度/地震组合、安全系数取值规则）由专家在双签时确认，设计态不固化。

### 4.2 变量关系（符号级，无数值）

令：

- `w_k` = 风荷载标准值（来自 wind_pressure，Pa）；
- `t` = 玻璃厚度（来自 D-TH-02 玻璃配置，mm，数值 pending）；
- `A` = 玻璃分格面积，`a`/`b` = 短边/长边长度（来自项目几何，数值 pending）；
- `support` = 支承条件标识（四边支承 / 对边支承，来自项目几何）；
- `σ_g` = 玻璃在 w_k 作用下的弯曲应力（目标量，Pa）；
- `σ_allow` = 玻璃允许应力（来自 D-TH-02，含安全系数，Pa，数值 pending）；
- `K` = 安全系数 / 安全裕度（来自 D-TH-02，无量纲，数值 pending）；
- `A_max` = 最大许用面积（由 w_k、t、support、σ_allow 推导，数值 pending）。

关系（符号占位，系数选取规则 pending_verification）：

```
σ_g    = w_k · f(A, t, support)        （玻璃弯曲应力，系数规则 pending_verification）
σ_allow = g(glass_type, K)             （允许应力，来自 D-TH-02，数值 pending_verification）
安全判定:  σ_g ≤ σ_allow 且 A ≤ A_max  →  安全（符号比较，数值 pending_verification）
K      = σ_allow / σ_g                 （安全裕度，≥1 安全，数值 pending_verification）
A_max  = h(w_k, t, support, σ_allow)   （最大许用面积，数值 pending_verification）
```

衍生依赖（仅描述变量间因果，不填数）：

- `σ_g` 取决于 `w_k`（上游 wind_pressure）+ `A`/`t`/`support`（项目几何与玻璃配置）；
- `σ_allow` / `K` 取决于 `glass_type`（D-TH-02）；
- `A_max` 取决于 `w_k` + `t` + `support` + `σ_allow`；
- `w_k` **不**由本模块推算，只消费 wind_pressure 产出（跨模块耦合，见 §7，pending_verification）。

### 4.3 数据来源映射（每个变量 → 哪一层输入）

| 变量 | 数据来源 | 溯源 |
|---|---|---|
| `w_k` | wind_pressure 上游产出（内部依赖 E-TH-01~03，pending_verification） | 随 wind_pressure 的 verification_status |
| `t`（玻璃厚度） | Engineering 阈值 **D-TH-02**（玻璃配置） | `verified`（双签后） |
| `glass_type` | Engineering 阈值 **D-TH-02** + Design 候选 `glass_type` | `verified`/`inferred` |
| `A` / `a` / `b` | 项目几何 / Design `dimensions_hint` | `inferred` |
| `support` | 项目几何（支承条件识别） | `inferred` |
| `σ_allow` / `K` | Engineering 阈值 **D-TH-02** | `verified`（双签后） |

---

## 5. 阈值依赖设计（D-TH-02 与 wind_pressure w_k）

### 5.1 D-TH-02（玻璃配置）角色绑定

D-TH-02 已在 Sprint A 的 `agents/design/thresholds/verified.json` 占位（映射 Design 候选字段 `glass_type`），本设计明确其**角色绑定**与**双签验收口径**：

| 阈值 ID | 绑定变量 | 在公式中角色 | 双签验收口径（专家须确认） |
|---|---|---|---|
| **D-TH-02** | `glass_type`（玻璃类型/构造）、`t`（玻璃厚度）、`σ_allow`（允许应力）、`K`（安全系数） | 玻璃强度与许用面积的取值依据 | 取值与项目所选玻璃类型（钢化/夹层/中空等构造）及安全系数体系一致；单位与量纲在 approved 后自洽 |

- **双签字段要求**（Sprint A 机制）：`verified=true` + `verified_by` + `verified_at` + `expert_verified_by` + `expert_verified_at` 五字段俱全 → `is_fully_verified()=True`。
- **source_ref 要求**：专家填入规范/标准号与条款号（设计态全为 `pending_verification`）。
- **禁止**：AI 代码不得写入 `verified=true`、不得填写 `value`（厚度/安全系数）、不得伪造签字（由 `check_fabrication.py` + 防编造测试锁死）。
- **未双签后果**：`threshold_verified=False` → `verification_status` 恒 `pending_verification`，`sign_off_id=null`，绝不输出 `engineering_approved`。

### 5.2 与 wind_pressure w_k 的关系（跨模块阈值耦合）

- glass_safety **不重新定义**风压阈值，仅消费 wind_pressure 的 `w_k`。
- 双闸门约束：glass_safety 要 `engineering_approved`，须**同时**满足：
  1. 自身阈值 D-TH-02 双签完整（`threshold_verified` + `expert_signed`）；
  2. 上游 `w_k` 可信（wind_pressure `verification_status == engineering_approved` 且 `w_k.value` 非 None）；
  3. `engineering_enabled=true`。
- 任一不满足 → 结论恒 `pending_verification`（计算单元显式登记 `gaps`，不依赖 validator 单接口判定）。

---

## 6. Expert 审核点设计

专家双签阶段须对以下审核点逐一确认（设计态全部 `pending_verification`）：

1. **玻璃配置取值（D-TH-02）**：与项目所选玻璃类型（钢化/夹层/中空等构造）、玻璃厚度 `t`、安全系数 `K`、允许应力 `σ_allow` 口径一致。
2. **风荷载输入合法性**：上游 `w_k` 来自 wind_pressure 且已 approved；未使用 Environment 实时气象直接推算。
3. **支承条件适用性**：四边支承/对边支承系数体系适用于本项目分格构造。
4. **公式适用性**：所选荷载—应力—校核结构适用于本项目高度/构造；温度、地震组合等边界是否成立。
5. **输入溯源合规**：玻璃面积/边长、`inferred` 字段在签字时已被人工复核或转为 `verified`；不存在用 `inferred` 直接驱动确定性结论。
6. **单位与量纲一致**：Pa、mm、m²、无量纲系数在 approved 后自洽。
7. **边界条件登记**：超大分格/异形/特殊构造工况是否在 `gaps`/`source_ref` 中显式标注待补充。

审核动作写入 `review_log.jsonl`（append-only，`event_id` 哈希链，`sign_off_id` 在 approved 时派生）。

---

## 7. 与 wind_pressure / 下游模块连接方式

glass_safety 是 wind_pressure 的**下游消费者**，是 Profile（型材受力）的**并列/相关模块**。

### 7.1 数据耦合

- wind_pressure 产出 `w_k`（风荷载标准值）→ 作为 glass_safety 的**玻璃抗风压/最大许用面积**计算输入荷载。
- glass_safety 同时消费 Design 侧 D-TH-02（玻璃配置）与项目几何（面积/边长/支承条件）。
- 耦合通过统一四字段结构 + `threshold_refs` + 上游 `wind_pressure_result` 实现，不新增私有通道。

### 7.2 阈值跨库引用

| 模块 | 依赖的上游产出 | 自身阈值 |
|---|---|---|
| `glass_safety` | `w_k`（来自 wind_pressure） | D-TH-02（玻璃配置，Design 侧） |
| `profile` | `w_k` → 杆件受荷 | D-TH-01（型材壁厚，Design 侧） |

- glass_safety **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03），只消费 wind_pressure 的 `w_k`。
- 下游 `verification_status` 独立判定：即使 wind_pressure 已 approved，glass_safety 仍需自身阈值双签 + `engineering_enabled` + `w_k` 可信 才转 approved。

### 7.3 降级传导

- 若 wind_pressure `pending_verification`（阈值未签/输入 inferred）→ `w_k` 不可信 → glass_safety 即使自身阈值已签，结论仍须 `pending_verification`（不得基于未验证风压推出"玻璃达标"）。
- glass_safety 计算单元显式检查 `wind_pressure_result.verification_status`，未 approved 时登记 `gaps: ["w_k: upstream_pending"]` 并强制 pending。
- 跨模块 `gaps` 显式登记上游 pending 项。

---

## 8. PDF 展示方案

复用 Phase 3.1 设计就绪报告已确立的 PDF 契约（三态徽标 + `review_chain` 逐接口透出）：

- **三态徽标**：`[已验证]`（engineering_approved）/ `[AI推理·待确认]`（inferred）/ `[待确认]`（pending_verification）按 `verification_status` 渲染。
- **glass_safety 章节内容**：
  - 输入摘要：玻璃配置（glass_type）/ 玻璃面积 / 支承条件及其溯源标签；
  - 上游荷载：wind_pressure 的 `w_k` 来源与可信状态（随 wind_pressure 章节联动）；
  - 公式来源：荷载—应力—校核结构符号展示 + 规范来源占位（条款号 pending）；
  - 中间变量表：`w_k`/`t`/`A`/`support`/`σ_g`/`σ_allow`/`K`/`A_max` 各取值来源（D-TH-02 或 wind_pressure 或 pending）；
  - 审核状态：七字段 `review_chain` 记录透出（接口名/结构合法/阈值校验/专家签字/状态/ `sign_off_id`）；
  - 专家签字区：`verified_by`/`verified_at`/`expert_verified_by`/`expert_verified_at` 占位（未签显示"待行业专家双签"）。
- **防误显**：`verification_status != engineering_approved` 时，绝不渲染任何具体玻璃厚度、安全系数、许用面积数值或"达标"结论；仅显示推导占位与 `pending_verification` 标注。

---

## 9. 测试方案

> 落实 `.ai/tasks/phase3.1_test_plan.md` 四类别；**编码阶段**实施，本阶段仅定方案。所有用例零真实数值。

### 9.1 单元（GlassSafetyCalculator）

| 用例 | 输入 | 期望 |
|---|---|---|
| 阈值缺失降级 | D-TH-02 `value=null` | `verification_status=="pending_verification"`；`intermediate` 各量为 pending 占位；`gaps` 含 D-TH-02 pending |
| 上游 w_k 未签降级 | `wind_pressure_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["w_k: upstream_pending"]`，不伪造 σ_g 数值 |
| 输入 inferred 降级 | `glass_area` 为 inferred | 结论 pending，不伪造许用面积 |
| 四字段强制 | 任意 | 输出键集合 ⊇ `REQUIRED_OUTPUT_KEYS` |
| 证据可回写 | 产出对象 | `evidence` 含 `source_ref` 槽位（值 pending）+ 参数来源标识 |
| 验证等级 | 未双签 | 可信等级 Level 0/1，绝不 Level 3 |

### 9.2 集成（EngineeringAgent.invoke 全链路）

- `analyses=["glass_safety"]` → `review_chain` 仅含一条记录，`verification_status` 恒 pending（设计态）；
- `analyses=["wind_pressure","glass_safety"]` → 上游 wind_pressure 的 pending 状态传导至 glass_safety pending（详见 §7.3 降级传导，pending_verification）。

### 9.3 安全（降级/误开/防篡改）

- 阈值未双签 → 该模块及依赖链绝不 `engineering_approved`（一票否决）；
- 测试全程 `engineering_enabled=false`；不得置 true；
- `review_log` append-only + `prev_event_id` 哈希链连续。

### 9.4 防编造（红线锁死）

- 扫描 `agents/engineering/calc/glass_safety.py`：不含未走 `verified.json`/D-TH-02 的硬编码工程常数（玻璃厚度/安全系数/许用应力）；
- 含业务词（玻璃配置/玻璃厚度/安全系数）行均配对 `pending_verification`，无真实数字；
- `result` 在未 approved 时不含具体玻璃厚度/安全系数/面积数值。

### 9.5 覆盖率

- backend ≥ 60%（随真实计算补全后 ≥ 70%）；`bash scripts/ci/local_ci.sh` 维持 8/8 全绿、覆盖率不降。

---

## 10. 风险分析

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-GS-1 | 玻璃配置阈值（D-TH-02）长期未双签 | glass_safety 永久 pending | 专家双签流程 + `review_log` 追踪；CI 防编造闸门 |
| R-GS-2 | 误将 Environment 实时气象当作玻璃荷载 | 来源错误，结论失真 | 荷载只来自 wind_pressure 的 w_k；代码审查锁死 |
| R-GS-3 | 上游 w_k 不可信却被当作确定输入 | 编造玻璃达标结论 | §7.3 降级传导；计算单元显式检查 w_k 可信态 |
| R-GS-4 | 输入 `inferred` 直接驱动确定性结论 | 编造工程判断 | `field_provenance` 判定：inferred → pending（ADR-2.2.1 §7） |
| R-GS-5 | 跨模块耦合错误传导 | wind 错值污染 glass | §7.3 降级传导；下游独立审核 |
| R-GS-6 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | §8 防误显；状态 != approved 仅显 pending 占位 |
| R-GS-7 | `engineering_enabled` 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-GS-8 | 公式系数体系选择不当 | 适用边界错误 | §6 审核点4 由专家在双签时确认；设计态不固化 |

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含任何实现代码，未开启 `engineering_enabled`，全参数 `pending_verification`）
