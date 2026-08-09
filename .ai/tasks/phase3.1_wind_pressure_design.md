# Wind Pressure 工程模块设计（Sprint B）

- **生成**：2026-07-30（Phase 3.1 Sprint B 设计阶段）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，未编码；**不进入实现**）
- **依赖**：Sprint A 已交付（Engineering 阈值体系 + ExpertBackedEngineeringValidation + review_log 审核链 + 防编造扫描 + CI 8/8）
- **红线守约**：本文件**零真实风压值、零真实系数、零规范条款编号**；`engineering_enabled=false`；所有参数 `pending_verification`。

---

## 0. 设计范围与边界

| 项 | 范围 |
|---|---|
| ✅ 本次定义 | wind_pressure 接口的分析设计（输入/输出/公式来源/阈值依赖/审核点/连接/PDF/测试/风险） |
| ⛔ 本次不做 | 任何 Python/TS 实现、任何数值计算、任何 `verified=true` 写入、`engineering_enabled` 置真 |
| 🔗 衔接 | 复用 Sprint A 的 `ExpertBackedEngineeringValidation`、`INTERFACE_THRESHOLD_MAP`、`review_log`；复用 Design 侧 `field_provenance`/`threshold_refs` 契约 |

> 设计态正确表现：每个数值位均为 `<取自 E-TH-0X，pending_verification>` 或符号占位；不得出现任何具体数字、系数表、条款号。

---

## 1. 当前 wind_pressure 接口分析

### 1.1 骨架现状（实读 `agents/engineering/agent.py`）

- `ANALYSIS_INTERFACES` 含 `"wind_pressure"`，与 `glass_safety`/`profile`/`hardware`/`installation_risk` 并列。
- `EngineeringAgent.analyze_wind_pressure(context_data)` 当前为**骨架实现**：
  - 签名 `(self, context_data: Mapping[str, Any]) -> dict[str, Any]`；
  - 内部 `del context_data`（不消费输入，仅锁定签名）；
  - 返回 `build_skeleton_output()`：四字段全空 + `verification_status="pending_verification"`。
- `invoke()` 调度：`dispatch["wind_pressure"] = self.analyze_wind_pressure`；每个接口产出经 `self._validator.validate(interface="wind_pressure", payload=output)` 生成一条 `review_chain` 记录。
- 默认 validator：`PendingEngineeringValidation`（仅结构校验，恒 pending）。Sprint A 已新增可注入的 `ExpertBackedEngineeringValidation`（双签闸门）。

### 1.2 演进路径（Sprint B → 编码阶段）

**EngineeringAgent 侧零改动**（与 3.1 架构设计一致）。真实计算的接入方式：

- 新增独立计算单元 `agents/engineering/calc/wind_pressure.py`（或等价的 `WindPressureCalculator`），**不修改** `agent.py`；
- `analyze_wind_pressure()` 内部从骨架直返，改为调用计算单元并把结果按统一四字段结构封装；
- validator 仅替换为 `ExpertBackedEngineeringValidation`（已在 Sprint A 落地），Agent 调度逻辑不变；
- 计算单元的输出对象统一含 `result / confidence / evidence / verification_status` + 扩展字段（`intermediate` / `provenance` / `gaps` / `threshold_refs` / `sign_off_id` 占位）。

### 1.3 输入/输出契约锚点

- 输入：`context_data`（来自 `AgentContext.input_data`）应透传 `project` / `environment_result` / `design_candidate` / `vision_result` 等上游产物。骨架阶段不消费，设计阶段明确其字段契约（见 §2）。
- 输出：统一四字段 + 扩展字段（见 §3），经 `ExpertBackedEngineeringValidation.validate` 产出七字段审核链记录。

---

## 2. 输入参数设计

wind_pressure 计算所需输入分四层，均须携带**溯源标签**（`measured` / `inferred` / `verified` / `unavailable`），任何 `inferred`/`unavailable` 输入 → 该模块结论 `pending_verification`。

### 2.1 项目输入（Project Input）

| 字段 | 含义 | 溯源预期 | 用途 |
|---|---|---|---|
| `project.building_height` / `project.floor_count` | 建筑高度/层数 | `inferred`（来自 Vision/用户） | 决定高度变化系数 μ_z、风振/阵风系数依赖项 |
| `project.building_usage` / `project.importance_class` | 建筑用途/重要性 | `inferred` / `verified`（规范） | 影响风荷载分项/重要性系数（取值 pending） |
| `project.site_category` | 场地类别/地面粗糙度类别 | 来自 E-TH-03 或 `inferred` | 决定 μ_z 与风振系数（E-TH-03） |
| `project.opening_position` / `project.orientation` | 开口/幕墙位置与朝向 | `inferred`（Vision） | 体型系数 μ_s 选择（迎风/侧风/内区）、局部体型 |
| `project.panel_dimensions` | 分格尺寸、幕墙单元面积 | `inferred`（Design 候选 `dimensions_hint`） | 局部风压体型系数、玻璃/型材受荷面积 |

### 2.2 Environment 输入（来自 `EnvironmentAgent` 输出）

复用 `agents/environment/agent.py` 的 `field_provenance` 与 `facts`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `climate_zone` | `facts.climate_zone` | LLM 推理 → `inferred`（永远 pending）；若未来接区划静态表并已双签 → `verified` |
| `prevailing_wind` | `facts.prevailing_wind` + `WindClimate`（WeatherProvider） | `measured`（real_data=True 命中）/ `mock` / `inferred`；**主导风向不参与数值计算，仅作朝向校验参考** |
| `coordinates` / `geocode` | `coordinates` / `facts.geocode` | 定位用；不直接进入风压公式（基本风压来自 E-TH-01 阈值，而非实时气象） |
| `field_provenance` | `data.field_provenance` | 决定是否 `pending`：任一关键环境字段非 `measured`/`verified` → 模块 pending（ADR-2.2.1 §7） |

> ⚠️ 红线：基本风压 `w_0` **不**由 Environment 实时气象推算，只来自工程阈值 **E-TH-01**（专家双签后填入）。实时风速仅用于环境描述，禁止被风压计算模块当作 `w_0` 来源。

### 2.3 Design 输入（来自 `DesignAgent` 候选）

复用 `agents/design/agent.py` 的候选结构与 `threshold_loader`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `design_candidate.dimensions_hint` | Design 候选 | 分格尺寸建议，`inferred`；驱动 `project.panel_dimensions` |
| `design_candidate.frame_material` | Design 候选（D-TH-01 引用） | 型材选型，仅影响下游 `profile` 模块；风压层不直接消费 |
| `design_candidate.glass_type` | Design 候选（D-TH-02 引用） | 玻璃选型，仅影响下游 `glass_safety`；风压层不直接消费 |
| `field_provenance` / `threshold_refs` | Design 输出 | 复用字段级溯源，风压模块仅读取，不改写 |

### 2.4 Engineering 阈值输入（来自 `verified.json` via `threshold_loader`）

| 阈值 ID | 参数 | 单位 | 喂给的变量 | 双签要求 |
|---|---|---|---|---|
| `E-TH-01` | 基本风压（标准值） | Pa | `w_0` | 主理人 + 行业专家双签 |
| `E-TH-02` | 体型系数 | （无量纲，pending） | `μ_s` | 主理人 + 行业专家双签 |
| `E-TH-03` | 粗糙度类别 | （类别标识，pending） | `μ_z` 与风振系数取值依据 | 主理人 + 行业专家双签 |

> 设计态：上述三项 `value=null`、`verified=false`、双签字段 `null`、`source_ref` 含 `pending_verification`。未双签前，计算单元不得取得任何数值，输出恒 `pending_verification`。

---

## 3. 输出结构设计

### 3.1 统一四字段（接口契约，勿改键名）

```jsonc
{
  "result": "<风荷载标准值 w_k 计算结论，pending 态为空或推导占位；approved 后填符号化结论>",
  "confidence": "<可信等级标签：pending 态为 'pending_verification'；approved 后为 'verified'>",
  "evidence": "<来源说明：公式来源 + 各变量取值来源 + source_ref（规范条款号 pending_verification）>",
  "verification_status": "pending_verification"   // 双签齐 + enabled=true 才转 engineering_approved
}
```

### 3.2 扩展字段（计算单元内部承载，供审核链/PDF 消费）

| 字段 | 含义 |
|---|---|
| `interface` | `"wind_pressure"`（固定） |
| `intermediate` | 中间变量字典：`{ "w_0": <from E-TH-01, pending>, "mu_s": <from E-TH-02, pending>, "mu_z": <derived from E-TH-03 + height, pending>, "beta": <风振/阵风系数, pending>, "w_k": <product, pending> }` |
| `provenance` | 每个输入字段的溯源标签（`measured`/`inferred`/`verified`/`unavailable`） |
| `threshold_refs` | `["E-TH-01","E-TH-02","E-TH-03"]`（仅引用，数值 pending） |
| `gaps` | 缺失/未签字项登记（如 `E-TH-01: pending_verification`） |
| `sign_off_id` | 占位 `null`（仅 approved 后由 `review_log.compute_sign_off_id` 派生） |

### 3.3 审核链记录（经 `ExpertBackedEngineeringValidation.validate` 产出）

七字段（Sprint A 已定义）：
`interface / structure_valid / threshold_verified / expert_signed / verification_status / sign_off_id / validator`。

- `threshold_verified`：`get_interface_thresholds("wind_pressure")` 返回 `("E-TH-01","E-TH-02","E-TH-03")`，三项 `mgmt_signed` 才 True；
- `expert_signed`：三项 `expert_signed` 才 True；
- 闸门：`structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` → `engineering_approved`，否则恒 `pending_verification`。

---

## 4. 公式来源设计（仅定义：公式来源 / 变量关系 / 数据来源；禁止真实参数）

### 4.1 公式来源（概念级）

- 参考建筑**围护结构/幕墙风荷载计算**相关标准与规范（**具体标准号与条款号均由行业专家双签阶段填入，pending_verification**）。
- 采用业界通用的**乘积结构**：垂直于幕墙平面的风荷载标准值 = 风振/阵风系数 × 体型系数 × 高度变化系数 × 基本风压。
- 公式适用性边界（如适用高度范围、是否需考虑内压、阵风与风振二选一）由专家在双签时确认，设计态不固化。

### 4.2 变量关系（符号级，无数值）

令：

- `w_k` = 垂直于幕墙平面的风荷载标准值（目标量，Pa）；
- `β` = 风振系数 / 阵风系数（无量纲，依赖结构高度、自振特性、粗糙度类别）；
- `μ_s` = 风荷载体型系数（无量纲，依赖开口/幕墙位置与朝向，含局部体型系数 `μ_sl`）；
- `μ_z` = 风压高度变化系数（无量纲，依赖离地高度 `z` 与粗糙度类别 E-TH-03）；
- `w_0` = 基本风压标准值（来自 E-TH-01，Pa）。

关系：

```
w_k = β · μ_s · μ_z · w_0        （主公式，符号占位；系数选取规则 pending_verification）
```

衍生依赖（仅描述变量间因果，不填数）：

- `μ_z = f(z, 粗糙度类别)` —— 离地高度 `z` 来自项目输入，粗糙度类别来自 E-TH-03；
- `μ_s / μ_sl = g(开口位置, 朝向, 局部区域)` —— 来自 E-TH-02 与项目几何；
- `β = h(结构高度, 自振特性, 粗糙度类别)` —— 依赖项目输入与 E-TH-03；
- `w_0` 直接取自 E-TH-01（**不**由实时气象推算）。

### 4.3 数据来源映射（每个变量 → 哪一层输入）

| 变量 | 数据来源 | 溯源 |
|---|---|---|
| `w_0` | Engineering 阈值 **E-TH-01** | `verified`（双签后） |
| `μ_s` / `μ_sl` | Engineering 阈值 **E-TH-02** + 项目几何（位置/朝向） | `verified`/`inferred` |
| `μ_z` 的粗糙度项 | Engineering 阈值 **E-TH-03** | `verified` |
| `μ_z` 的高度项 `z` | 项目输入 `building_height` | `inferred` |
| `β` 的高度/自振项 | 项目输入 `building_height`/`importance_class` | `inferred` |
| 朝向校验 | Environment `prevailing_wind` | `measured`/`inferred`（仅校验，不进公式数值） |

---

## 5. verified.json 依赖设计（E-TH-01 / E-TH-02 / E-TH-03）

三项已在 Sprint A 的 `agents/engineering/thresholds/verified.json` 占位，本设计明确其**角色绑定**与**双签验收口径**：

| 阈值 ID | 绑定变量 | 在公式中角色 | 双签验收口径（专家须确认） |
|---|---|---|---|
| **E-TH-01** | `w_0` 基本风压 | 乘积基数 | 取值与项目所在地区/重现期匹配；单位 Pa；与当地气象/荷载标准一致 |
| **E-TH-02** | `μ_s` 体型系数 | 乘积因子 | 取值与幕墙迎风/侧风/内区及局部体型适用规则一致；无量纲 |
| **E-TH-03** | 粗糙度类别 | `μ_z` 与 `β` 的取值依据 | 类别判定与场地实际地形/周边环境一致；类别标识（非数值） |

- **双签字段要求**（Sprint A 机制）：`verified=true` + `verified_by` + `verified_at` + `expert_verified_by` + `expert_verified_at` 五字段俱全 → `is_fully_verified()=True`。
- **source_ref 要求**：专家填入规范/标准号与条款号（设计态全为 `pending_verification`）。
- **禁止**：AI 代码不得写入 `verified=true`、不得填写 `value`、不得伪造签字（由 `check_fabrication.py` + 防编造测试锁死）。
- **未双签后果**：`threshold_verified=False` → `verification_status` 恒 `pending_verification`，`sign_off_id=null`，绝不输出 `engineering_approved`。

---

## 6. Expert 审核点设计

专家双签阶段须对以下审核点逐一确认（设计态全部 `pending_verification`）：

1. **基本风压取值（E-TH-01）**：与项目地区、设计重现期、荷载标准口径一致；单位 Pa 正确。
2. **体型系数（E-TH-02）**：迎风/侧风/内区与局部体型系数选取规则正确，适用该幕墙构造。
3. **粗糙度类别（E-TH-03）**：场地类别判定与地形/周边环境一致，且 `μ_z`/`β` 取值规则与之匹配。
4. **公式适用性**：所选乘积结构与系数体系适用于本项目高度/构造；内压、阵风/风振二选一的边界成立。
5. **输入溯源合规**：项目高度、`inferred` 字段在签字时已被人工复核或转为 `verified`；不存在用 `inferred` 直接驱动确定性结论。
6. **单位与量纲一致**：Pa、无量纲系数、高度单位换算在 approved 后自洽。
7. **边界条件登记**：超高/特殊造型/开洞率的特殊工况是否在 `gaps`/`source_ref` 中显式标注待补充。

审核动作写入 `review_log.jsonl`（append-only，`event_id` 哈希链，`sign_off_id` 在 approved 时派生）。

---

## 7. 与 Glass Safety / Profile 连接方式

wind_pressure 是 **Glass Safety（玻璃抗风压）** 与 **Profile（型材受力）** 的上游数据供给方。

### 7.1 数据耦合

- wind_pressure 产出 `w_k`（风荷载标准值）→ 作为 `glass_safety` 的**玻璃抗风压/最大许用面积**计算输入，及 `profile` 的**杆件线荷载/挠度**计算输入。
- 耦合通过统一四字段结构 + `threshold_refs` 实现，不新增私有通道。

### 7.2 阈值跨库引用

| 下游模块 | 依赖的 wind 产出 | 自身阈值 |
|---|---|---|
| `glass_safety` | `w_k`（来自 wind_pressure） | D-TH-02（玻璃配置，Design 侧） |
| `profile` | `w_k` → 杆件受荷 | D-TH-01（型材壁厚，Design 侧） |

- 下游模块**不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03），只消费 wind_pressure 的 `w_k`。
- 下游 `verification_status` 独立判定：即使 wind_pressure 已 approved，下游仍需自身阈值双签 + `engineering_enabled` 才转 approved。

### 7.3 降级传导

- 若 wind_pressure `pending_verification`（阈值未签/输入 inferred）→ `w_k` 不可信 → 下游即使自身阈值已签，结论仍须 `pending_verification`（不得基于未验证风压推出"玻璃/型材达标"）。
- 跨模块 `gaps` 显式登记上游 pending 项。

---

## 8. PDF 展示方案

复用 Phase 3.1 设计就绪报告已确立的 PDF 契约（三态徽标 + `review_chain` 逐接口透出）：

- **三态徽标**：`[已验证]`（engineering_approved）/ `[AI推理·待确认]`（inferred）/ `[待确认]`（pending_verification）按 `verification_status` 渲染。
- **wind_pressure 章节内容**：
  - 输入摘要：项目高度/粗糙度类别/开口朝向及其溯源标签；
  - 公式来源：乘积结构符号展示 `w_k = β·μ_s·μ_z·w_0` + 规范来源占位（条款号 pending）；
  - 中间变量表：`w_0`/`μ_s`/`μ_z`/`β`/`w_k` 各取值来源（E-TH-01~03 或 pending）；
  - 审核状态：七字段 `review_chain` 记录透出（接口名/结构合法/阈值校验/专家签字/状态/ `sign_off_id`）；
  - 专家签字区：`verified_by`/`verified_at`/`expert_verified_by`/`expert_verified_at` 占位（未签显示"待行业专家双签"）。
- **防误显**：`verification_status != engineering_approved` 时，绝不渲染任何具体风压数值或"达标"结论；仅显示推导占位与 `pending_verification` 标注。

---

## 9. 测试方案

> 落实 `.ai/tasks/phase3.1_test_plan.md` 四类别；**编码阶段**实施，本阶段仅定方案。所有用例零真实数值。

### 9.1 单元（wind_pressure 计算单元）

| 用例 | 输入 | 期望 |
|---|---|---|
| 阈值缺失降级 | 三项 E-TH 全 `value=null` | `verification_status=="pending_verification"`；`intermediate` 各量为 pending 占位；`gaps` 含 E-TH-01~03 pending |
| 输入 inferred 降级 | `building_height` 为 inferred | 结论 pending，不伪造 w_k 数值 |
| 四字段强制 | 任意 | 输出键集合 ⊇ `REQUIRED_OUTPUT_KEYS` |
| 证据可回写 | 产出对象 | `evidence` 含 `source_ref` 槽位（值 pending）+ 参数来源标识 |
| 验证等级 | 未双签 | 可信等级 Level 0/1，绝不 Level 3 |

### 9.2 集成（EngineeringAgent.invoke 全链路）

- `analyses=["wind_pressure"]` → `review_chain` 仅含一条记录，`verification_status` 恒 pending（设计态）；
- `analyses=["wind_pressure","glass_safety","profile"]` → 上游 wind_pressure 的 pending 状态传导至下游 pending（详见降级传导小节）。

### 9.3 安全（降级/误开/防篡改）

- 阈值未双签 → 该模块及依赖链绝不 `engineering_approved`（一票否决）；
- 测试全程 `engineering_enabled=false`；不得置 true；
- `review_log` append-only + `prev_event_id` 哈希链连续。

### 9.4 防编造（红线锁死）

- 扫描 `agents/engineering/calc/wind_pressure.py`：不含未走 `verified.json` 的硬编码工程常数；
- 含业务词（风压/体型系数/基本风压/粗糙度）行均配对 `pending_verification`，无真实数字；
- `result` 在未 approved 时不含具体风压数值（kN/m²/Pa）。

### 9.5 覆盖率

- backend ≥ 60%（随真实计算补全后 ≥ 70%）；`bash scripts/ci/local_ci.sh` 维持 8/8 全绿、覆盖率不降。

---

## 10. 风险分析

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-WP-1 | 风压阈值（E-TH-01、E-TH-02、E-TH-03）长期未双签 | wind_pressure 永久 pending，下游连带 pending | 专家双签流程 + `review_log` 追踪；CI 防编造闸门 |
| R-WP-2 | 误将 Environment 实时风速当作 `w_0` | 来源错误，结论失真 | 环境输入红线：基本风压只来自 E-TH-01；代码审查锁死 |
| R-WP-3 | 输入 `inferred` 直接驱动确定性结论 | 编造工程判断 | `field_provenance` 判定：inferred → pending（ADR-2.2.1 §7） |
| R-WP-4 | 跨模块耦合错误传导 | wind 错值污染 glass/profile | §7.3 降级传导；下游独立审核 |
| R-WP-5 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | §8 防误显；状态 != approved 仅显 pending 占位 |
| R-WP-6 | `engineering_enabled` 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-WP-7 | 公式系数体系选择不当 | 适用边界错误 | §6 审核点4 由专家在双签时确认；设计态不固化 |

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含任何实现代码，未开启 `engineering_enabled`，全参数 `pending_verification`）
