# Hardware（五金）工程模块设计（Sprint H）

- **生成**：2026-07-30（Phase 3.1 Sprint H 设计阶段）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，未编码；**不进入实现**）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 E-TH-04 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B/C wind_pressure 设计与编码（上游 w_k 供给方就绪，pending_verification）；Sprint D/E glass_safety 设计与编码（并列模块，pending_verification）；Sprint F/G profile 设计与编码（Hardware 直接上游，pending_verification）
- **红线守约**：本文件**零真实五金承载值、零真实寿命次数、零真实锁点数量、零规范条款编号**；`engineering_enabled=false`；所有参数 `pending_verification`；不编写任何实现代码。

---

## 0. 设计范围与边界

| 项 | 范围 |
|---|---|
| ✅ 本次定义 | hardware（五金）接口的分析设计（接口分析/输入/输出/规则来源/阈值依赖/审核点/与 Profile 及 Wind/Glass 连接/PDF/测试/风险） |
| ⛔ 本次不做 | 任何 Python/TS 实现、任何数值计算、任何 `verified=true` 写入、`engineering_enabled` 置真 |
| 🔗 衔接 | 复用 Sprint A 的 `ExpertBackedEngineeringValidation`、`INTERFACE_THRESHOLD_MAP`（hardware→E-TH-04）、`review_log`；复用 Design 侧 `field_provenance`/`threshold_refs` 契约；消费 Sprint C 的 wind_pressure 上游 `w_k`（经 Sprint G 的 profile 传递）；消费 Sprint G 的 `profile_result` |

> 设计态正确表现：每个数值位均为 `<取自 E-TH-04 / profile_result / wind_pressure，pending_verification>` 或符号占位（F / R / n_lock / n_req 等）；不得出现任何具体承载力基准、启闭寿命次数、锁点数量、型号规格数字或条款号。

---

## 1. 当前 hardware 接口分析

### 1.1 骨架现状（实读 `agents/engineering/agent.py`）

- `ANALYSIS_INTERFACES` 含 `"hardware"`，与 `wind_pressure`/`glass_safety`/`profile`/`installation_risk` 并列（五接口之一）。
- `EngineeringAgent.analyze_hardware(context_data)` 当前为**骨架实现**：
  - 签名 `(self, context_data: Mapping[str, Any]) -> dict[str, Any]`；
  - 内部 `del context_data`（不消费输入，仅锁定签名）；
  - 返回 `build_skeleton_output()`：四字段全空 + `verification_status="pending_verification"`。
- `invoke()` 调度：`dispatch["hardware"] = self.analyze_hardware`；每个接口产出经 `self._validator.validate(interface="hardware", payload=output)` 生成一条 `review_chain` 记录。
- 默认 validator：`PendingEngineeringValidation`（仅结构校验，恒 pending）；可注入 `ExpertBackedEngineeringValidation`（双签闸门，Sprint A 已落地）。

### 1.2 演进路径（Sprint H 设计 → 编码阶段）

**EngineeringAgent 侧契约零改动**（与 3.1 架构设计一致）。真实计算的接入方式：

- 新增独立计算单元 `agents/engineering/calc/hardware.py`（或等价的 `HardwareCalculator`），**不修改** `agent.py` 接口签名与调度；
- `analyze_hardware()` 内部从骨架直返，改为调用计算单元并把结果按统一四字段结构封装；
- validator 仅替换为 `ExpertBackedEngineeringValidation`（Sprint A 已落地），Agent 调度逻辑不变；
- 计算单元的输出对象统一含 `result / confidence / evidence / verification_status` + 扩展字段（`intermediate` / `provenance` / `gaps` / `threshold_refs` / `sign_off_id` 占位），结构与 wind_pressure 的 `WindPressureResult`、glass_safety 的 `GlassSafetyResult`、profile 的 `ProfileResult` 同构。

### 1.3 工程链路定位（Wind ↓ Profile ↓ Hardware）

- wind_pressure 是**最上游**数据供给方：产出风荷载标准值 `w_k`（Pa）。
- profile 是 hardware 的**直接上游**：消费 `w_k` 计算型材杆件内力（M/N/反力），其产出 `profile_result` 携带杆件反力/连接点受力，作为 hardware 的输入承载来源。
- hardware 位于链路末端：消费 `profile_result` 的杆件反力与扇荷载，校核五金（合页/锁点/滑轮/执手）承载力、锁点体系、连接可靠性、寿命等级。
- hardware **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03）与型材阈值（D-TH-01），只消费上游结果。

### 1.4 输入/输出契约锚点

- 输入：`context_data` 应透传 `project` / `environment_result` / `design_candidate` / `wind_pressure_result`（上游分析产物）/ `profile_result`（直接上游分析产物）/ `vision_result` 等；骨架阶段不消费，设计阶段明确其字段契约（见第 2 节，pending_verification）。
- 输出：统一四字段 + 扩展字段（见第 3 节），经 `ExpertBackedEngineeringValidation.validate` 产出审核链记录。

---

## 2. 输入参数设计

hardware 计算所需输入分四层，均须携带**溯源标签**（`measured` / `inferred` / `verified` / `unavailable`），任何 `inferred`/`unavailable` 关键输入 → 该模块结论 `pending_verification`。

### 2.1 项目输入（Project Input）

| 字段 | 含义 | 溯源预期 | 用途 |
|---|---|---|---|
| `project.opening_form` | 门窗开启形式（平开/推拉/上悬/外翻/内开内倒等**类别标识**） | `inferred`（来自 Vision/Design 候选） | 驱动五金类型选型（合页/滑轮/锁点体系）；类别标识，数值 pending |
| `project.load_condition` | 承载条件（扇重/受荷工况**类别**） | `inferred`（来自几何识别） | 驱动承载等级判定；具体扇重/荷载数值 pending |
| `project.hardware_config` | 五金配置（五金系列/型号候选） | `inferred`/`verified` | hardware 核心消费项（型号经 E-TH-04 双签后转 `verified`） |
| `project.usage_scenario` | 使用场景（使用频率/腐蚀环境**类别**） | `inferred`（Vision/用户） | 驱动寿命等级与选型（寿命次数 pending，禁止真实次数） |
| `project.sash_dimensions` | 扇分格尺寸（扇宽/扇高） | `inferred` | 驱动锁点数量与布置（数量 pending，禁止真实数量） |

### 2.2 Environment 输入（来自 `EnvironmentAgent` 输出 + 上游 wind_pressure/profile）

- **wind_pressure 输出 `w_k`（链路源头，经 profile 传递）**：hardware 通过 `context_data["profile_result"]` 间接消费 `w_k` 衍生的杆件反力（链路 Wind↓Profile↓Hardware）；亦可在 `context_data["wind_pressure_result"]` 读取用于溯源。hardware **不直接重算**风压。
- **profile_result 杆件反力（直接上游）**：hardware 从 `context_data["profile_result"]`（即 `ProfileResult.as_full()`）取 `intermediate` 中的杆件反力/连接点受力：
  - 若 `profile_result.verification_status == engineering_approved` 且相关反力 `value` 非 None → 可信承载来源；
  - 否则 → 上游 pending，hardware 登记 gap 并结论 `pending_verification`（第 6 节 降级传导）。
- 复用 `agents/environment/agent.py` 的 `field_provenance` 与 `facts`（如 `climate_zone`/`corrosion` 仅作环境描述参考；腐蚀类别由第 5 节 E-TH-04 子维度"连接要求/腐蚀适配"消费，数值 pending）。

> ⚠️ 红线：五金荷载只来自上游 profile 传递的杆件反力/扇荷载，**绝不**由 Environment 实时气象直接推算扇荷载（风荷载只来自 E-TH-01，经 wind_pressure→profile 归一化后供给）。

### 2.3 Design 输入（来自 `DesignAgent` 候选）

复用 `agents/design/agent.py` 的候选结构与 `threshold_loader`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `design_candidate.hardware_selection` | Design 候选 | 五金选型候选（型号/系列），hardware 核心消费项；数值 pending |
| `design_candidate.frame_series` | Design 候选（**D-TH-01** 引用） | 型材系列，经 profile 间接影响；hardware 不直接消费 |
| `design_candidate.opening_form_hint` | Design 候选 | 开启形式建议，`inferred`；驱动 `project.opening_form` |
| `field_provenance` / `threshold_refs` | Design 输出 | 复用字段级溯源，hardware 仅读取，不改写 |

### 2.4 Engineering 阈值输入（来自 `verified.json` via `threshold_loader`）

| 阈值 ID | 参数 | 单位 | 喂给的变量 | 双签要求 |
|---|---|---|---|---|
| `E-TH-04` | 五金承载力（五金件承载基准；含**五金配置 / 承载等级 / 锁点体系 / 连接要求**四子维度） | （配置/承载/数量标识，pending） | `hardware_type` / `hardware_model` / `load_capacity`(R) / `load_level` / `lock_point_system` / `connection_req` | 主理人 + 行业专家双签 |

> 设计态：E-TH-04 `value=null`、`verified=false`、双签字段 `null`、`source_ref` 含 `pending_verification`。未双签前，计算单元不得取得任何五金承载数值/锁点数量/寿命次数/型号规格，输出恒 `pending_verification`。

---

## 3. 输出结构设计

### 3.1 统一四字段（接口契约，勿改键名）

```jsonc
{
  "result": "<五金承载力/锁点体系/连接可靠性校核结论，pending 态为空或推导占位；approved 后填符号化结论>",
  "confidence": "<可信等级标签：pending 态为 'pending_verification'；approved 后为 'verified'>",
  "evidence": "<来源说明：规则来源 + 各变量取值来源 + source_ref（规范条款号 pending_verification）>",
  "verification_status": "pending_verification"   // 双签齐 + enabled=true + profile 可信 才转 engineering_approved
}
```

### 3.2 扩展字段（计算单元内部承载，供审核链/PDF 消费）

| 字段 | 含义 |
|---|---|
| `interface` | `"hardware"`（固定） |
| `intermediate` | 中间变量字典：`{ "w_k": <from wind_pressure via profile, pending>, "profile_reaction": <from profile_result 杆件反力, pending>, "opening_form": <开启形式类别, pending>, "hardware_type": <五金类型, pending>, "hardware_model": <五金型号, pending>, "load_capacity": <五金承载力基准 R, from E-TH-04, pending>, "load_level": <承载等级, pending>, "lock_point_system": <锁点体系/数量, pending>, "connection_req": <连接要求, pending>, "safety_factor": <安全裕度, pending>, "usage_scenario": <使用场景, pending>, "result_status": <校核结论, pending> }` |
| `provenance` | 每个输入字段的溯源标签（`measured`/`inferred`/`verified`/`unavailable`） |
| `threshold_refs` | `["E-TH-04"]`（仅引用，数值 pending） |
| `gaps` | 缺失/未签字项登记（如 `E-TH-04: pending_verification`、`profile_result: upstream_pending`） |
| `sign_off_id` | 占位 `null`（仅 approved 后由 `review_log.compute_sign_off_id` 派生） |

### 3.3 审核链记录（经 `ExpertBackedEngineeringValidation.validate` 产出）

七字段（Sprint A 已定义）：
`interface / structure_valid / threshold_verified / expert_signed / verification_status / sign_off_id / validator`。

- `threshold_verified`：`get_interface_thresholds("hardware")` 返回 `("E-TH-04",)`，E-TH-04 `mgmt_signed` 才 True；
- `expert_signed`：E-TH-04 `expert_signed` 才 True；
- 闸门：`structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` → `engineering_approved`，否则恒 `pending_verification`；
- **叠加跨模块闸门**：即便上述四项满足，若直接上游 `profile_result` 不可信（profile 未 approved），hardware 计算单元在 `verification_status` 仍强制 `pending_verification` 并登记 `gaps`（见第 6 节 降级传导，pending_verification）。

---

## 4. 规则体系设计（仅定义：公式来源 / 变量关系 / 数据来源；禁止真实参数）

建立 `agents/engineering/rules/hardware_rules.py`，承载 hardware 的**符号级规则结构**：公式来源、变量关系、数据来源映射；**不保存任何真实工程常数（承载力基准 / 锁点数量 / 启闭寿命次数 / 连接强度 / 规范条款号）**。

### 4.1 公式来源（概念级）

- 参考建筑**门窗五金（合页 / 锁点 / 滑轮 / 执手等）在风荷载与扇重作用下的承载力、锁点体系与连接可靠性**相关标准与规范（**具体标准号与条款号均由行业专家双签阶段填入，pending_verification**）。
- 采用业界通用的**荷载—承载校核**结构：在扇所受总荷载（扇重 + 风荷载作用于扇）与 profile 传递的杆件反力下，五金需承受的荷载 `F_hardware` 与五金承载力基准 `R`（含安全裕度）对比判定安全；同时校核锁点数量 `n_lock` 是否满足承载等级要求、连接强度 `C` 是否覆盖传递荷载、寿命等级 `N_life` 是否满足使用场景。
- 适用性边界（不同开启形式对应五金类型体系、是否计温度/地震组合、安全系数取值规则）由专家在双签时确认，设计态不固化。

### 4.2 变量关系（符号级，无数值）

令：

- `w_k` = 风荷载标准值（来自 wind_pressure，经 profile 传递，Pa）；
- `F_sash` = 扇所受总荷载（扇重 + w_k 作用于扇，数值 pending）；
- `R_profile` = profile 传递的杆件反力/连接点受力（来自 `profile_result`，数值 pending）；
- `F_hardware` = 五金需承受的荷载（目标量，由 F_sash 与 R_profile 导出，数值 pending）；
- `R` = 五金承载力基准（来自 E-TH-04，数值 pending）；
- `n_lock` = 锁点数量（来自锁点体系，数值 pending，禁止真实数量）；
- `n_req` = 所需锁点数量（由承载等级与几何导出，数值 pending）；
- `C` = 连接强度（合页/螺钉等，来自连接要求，数值 pending）；
- `N_life` = 启闭寿命等级（来自使用场景，次数 pending，禁止真实次数）；
- `safety` = 安全裕度（R / F_hardware，≥1 安全，数值 pending）。

关系（符号占位，系数选取规则 pending_verification）：

```
F_hardware = h(F_sash, R_profile, opening_form)   （五金承受荷载，系数规则 pending_verification）
承载判定:   F_hardware ≤ R                          （R 来自 E-TH-04，数值 pending_verification）
锁点判定:   n_lock ≥ n_req(load_level, geometry)    （锁点数量，数值 pending_verification）
连接判定:   C ≥ F_hardware                          （连接强度，数值 pending_verification）
寿命判定:   N_life ≥ N_required(usage_scenario)      （寿命等级，次数 pending_verification，禁止真实次数）
safety     = R / F_hardware                          （安全裕度，≥1 安全，数值 pending_verification）
```

衍生依赖（仅描述变量间因果，不填数）：

- `F_hardware` 取决于 `F_sash`（扇重+风压）+ `R_profile`（上游 profile）；
- `R` / `load_level` / `lock_point_system` / `connection_req` 取决于 `hardware_model` 与 E-TH-04 四子维度（双签后）；
- `n_lock` / `n_req` 取决于 `load_level` + 扇几何；
- `N_life` 取决于 `usage_scenario`（腐蚀/频率类别）；
- `w_k` / `R_profile` **不**由本模块推算，只消费上游产出（跨模块耦合，见第 6、7 节，pending_verification）。

### 4.3 数据来源映射（每个变量 → 哪一层输入）

| 变量 | 数据来源 | 溯源 |
|---|---|---|
| `w_k` | wind_pressure 上游产出（内部依赖 E-TH-01~03，pending_verification） | 随 wind_pressure 的 verification_status |
| `R_profile` | profile 上游产出（`profile_result`，内部依赖 D-TH-01 + w_k，pending_verification） | 随 profile 的 verification_status |
| `hardware_model` / `load_capacity`(R) / `load_level` / `lock_point_system` / `connection_req` | Engineering 阈值 **E-TH-04**（五金承载力，含四子维度） | `verified`（双签后） |
| `opening_form` | 项目几何 / Design `opening_form_hint` | `inferred` |
| `F_sash` / `F_hardware` / `n_req` / `C` / `N_life` / `safety` | 由上游 R_profile + E-TH-04 + 项目几何推导 | `inferred`/`pending` |

---

## 5. 阈值设计（E-TH-04 角色 与 四子维度审核占位）

### 5.1 E-TH-04（五金承载力）角色绑定

E-TH-04 已在 Sprint A 的 `agents/engineering/thresholds/verified.json` 占位（`applies_to: ["hardware"]`），本设计明确其**角色绑定**与**四子维度审核占位**：

| 阈值 ID | 绑定变量 | 在公式中角色 | 双签验收口径（专家须确认） |
|---|---|---|---|
| **E-TH-04** | `hardware_model`（五金型号）、`R`（承载力基准）、`load_level`（承载等级）、`lock_point_system`（锁点体系）、`connection_req`（连接要求） | 五金承载力与连接可靠性的取值依据 | 取值与项目所选五金型号、承载等级、锁点布置、连接强度口径一致；单位与量纲在 approved 后自洽 |

E-TH-04 **四子维度审核占位**（设计态全 `value=null` / `verified=false`，专家双签时逐项填充）：

| 子维度 | 审核占位含义 | 双签时须确认 |
|---|---|---|
| 五金配置 | 五金型号/系列选型与项目开启形式匹配 | 型号规格与开启形式（平开/推拉等）对应，数值 pending |
| 承载等级 | 五金承载等级与扇荷载匹配 | 承载等级划分口径与 F_hardware 对应，数值 pending |
| 锁点体系 | 锁点数量/布置满足承载等级 | 锁点数量规则与扇几何对应，数量 pending（禁止真实数量） |
| 连接要求 | 连接强度（合页/螺钉）覆盖传递荷载 | 连接强度口径与腐蚀环境适配，数值 pending |

- **双签字段要求**（Sprint A 机制）：`verified=true` + `verified_by` + `verified_at` + `expert_verified_by` + `expert_verified_at` 五字段俱全 → `is_fully_verified()=True`。
- **source_ref 要求**：专家填入规范/标准号与条款号（设计态全为 `pending_verification`）。
- **禁止**：AI 代码不得写入 `verified=true`、不得填写 `value`（承载力/锁点数量/寿命次数）、不得伪造签字（由 `check_fabrication.py` + 防编造测试锁死）。
- **未双签后果**：`threshold_verified=False` → `verification_status` 恒 `pending_verification`，`sign_off_id=null`，绝不输出 `engineering_approved`。

### 5.2 审核流程（E-TH-04 双签 + 工程闸门 + 上游闸门）

- hardware 要 `engineering_approved`，须**同时**满足：
  1. 自身阈值 E-TH-04 双签完整（`threshold_verified` + `expert_signed`）；
  2. 直接上游 `profile_result` 可信（profile `verification_status == engineering_approved` 且相关反力 `value` 非 None）；
  3. `engineering_enabled=true`。
- 任一不满足 → 结论恒 `pending_verification`（计算单元显式登记 `gaps`，不依赖 validator 单接口判定）。

---

## 6. 与 Profile 关系

hardware 是 profile 的**下游消费者**；profile 的 `engineering_approved` **不替代** hardware 审核。

### 6.1 数据耦合

- profile 产出杆件反力/连接点受力 → 作为 hardware 的**五金承受荷载**计算输入来源。
- hardware 同时消费 Design 侧 E-TH-04（五金配置/承载力）与项目几何（开启形式/扇尺寸）。
- 耦合通过统一四字段结构 + `threshold_refs` + 上游 `profile_result` 实现，不新增私有通道。

### 6.2 阈值跨库引用

| 模块 | 依赖的上游产出 | 自身阈值 |
|---|---|---|
| `hardware` | `profile_result`（间接含 w_k） | E-TH-04（五金承载力，含四子维度） |
| `profile` | `w_k`（来自 wind_pressure） | D-TH-01（型材配置/截面属性，Design 侧） |

- hardware **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03）与型材阈值（D-TH-01），只消费上游结果。
- 下游 `verification_status` 独立判定：即使 profile 已 approved，hardware 仍需自身阈值双签 + `engineering_enabled` + profile 可信 才转 approved。

### 6.3 降级传导（profile pending → hardware pending）

- 若 profile `pending_verification`（阈值未签/输入 inferred/上游 w_k 不可信）→ `R_profile` 不可信 → hardware 即使自身阈值已签，结论仍须 `pending_verification`（不得基于未验证杆件反力推出"五金达标"）。
- hardware 计算单元显式检查 `profile_result.verification_status`，未 approved 时登记 `gaps: ["profile_result: upstream_pending"]` 并强制 pending。
- 跨模块 `gaps` 显式登记上游 pending 项（链路 Wind↓Profile↓Hardware 的逐级传导）。

---

## 7. 与 Wind / Glass 关系

### 7.1 工程链路（Wind ↓ Profile ↓ Hardware）

```
Wind（风压）
   │  w_k（风荷载标准值）
   ▼
Profile（型材杆件内力 M/N/反力）
   │  profile_result（杆件反力/连接点受力）
   ▼
Hardware（五金承载 / 锁点 / 连接 / 寿命）
```

- `w_k` 由 wind_pressure 产出（E-TH-01、E-TH-02、E-TH-03），是链路源头。
- profile 消费 `w_k` 计算杆件内力，产出 `profile_result`。
- hardware 消费 `profile_result`，校核五金承载体系。
- 三级 `pending_verification` 逐级传导：任一上游未 approved，下游恒 pending。

### 7.2 Glass 独立并列

- glass_safety 与 hardware **并列**，二者均消费 wind_pressure 的 `w_k`（glass 直接消费 w_k；hardware 经 profile 间接消费），但计算对象不同（玻璃面板 vs 五金体系）；glass_safety 的结论**不替代** hardware 计算（详见第 6 节，pending_verification）。
- 三模块在 `invoke()` 中各自独立走审核链，互不为前置（仅共享上游 `w_k` / `profile_result` 的可信态）。

---

## 8. Expert 审核点设计

专家双签阶段须对以下审核点逐一确认（设计态全部 `pending_verification`）：

1. **五金型号（硬件配置）**：与项目所选五金系列、型号规格口径一致（E-TH-04 子维度"五金配置"）。
2. **承载能力**：五金承载力基准 `R` 与扇荷载 `F_hardware` 口径一致；承载等级划分适用（E-TH-04 子维度"承载等级"）。
3. **开启方式**：开启形式（平开/推拉/上悬/外翻等）对应的五金类型体系（合页/滑轮/锁点）适用于本项目构造。
4. **连接可靠性**：连接强度 `C`（合页/螺钉等）覆盖传递荷载；连接要求与腐蚀环境适配（E-TH-04 子维度"连接要求"）。
5. **使用场景**：使用频率/腐蚀环境类别对应的寿命等级 `N_life` 适用；启闭寿命等级口径由专家确认（次数 pending，禁止真实次数）。
6. **锁点体系**：锁点数量 `n_lock` 与布置满足承载等级要求（E-TH-04 子维度"锁点体系"，数量 pending，禁止真实数量）。
7. **风荷载输入合法性**：上游 `w_k` 经 profile 传递且 profile 已 approved；未使用 Environment 实时气象直接推算。
8. **输入溯源合规**：开启形式/扇尺寸/使用场景等 `inferred` 字段在签字时已被人工复核或转为 `verified`；不存在用 `inferred` 直接驱动确定性结论。
9. **单位与量纲一致**：N、N·mm、次、无量纲系数在 approved 后自洽。

审核动作写入 `review_log.jsonl`（append-only，`event_id` 哈希链，`sign_off_id` 在 approved 时派生）。

---

## 9. PDF 展示方案

复用 Phase 3.1 设计就绪报告已确立的 PDF 契约（三态徽标 + `review_chain` 逐接口透出）：

- **三态徽标**：`[已验证]`（engineering_approved）/ `[AI推理·待确认]`（inferred）/ `[待确认]`（pending_verification）按 `verification_status` 渲染。
- **hardware 章节内容**：
  - 输入摘要：开启形式/五金型号候选/承载条件/使用场景及其溯源标签；
  - 上游荷载：wind_pressure 的 `w_k` 来源与 profile 的 `profile_result` 杆件反力可信状态（随 wind_pressure/profile 章节联动）；
  - 公式来源：荷载—承载校核结构符号展示 + 规范来源占位（条款号 pending）；
  - 中间变量表：`w_k`/`R_profile`/`opening_form`/`hardware_model`/`load_capacity`/`load_level`/`lock_point_system`/`connection_req`/`safety`/`usage_scenario` 各取值来源（E-TH-04 或 profile_result 或 pending）；
  - 审核状态：七字段 `review_chain` 记录透出（接口名/结构合法/阈值校验/专家签字/状态/ `sign_off_id`）；
  - 专家签字区：`verified_by`/`verified_at`/`expert_verified_by`/`expert_verified_at` 占位（未签显示"待行业专家双签"）。
- **防误显**：`verification_status != engineering_approved` 时，绝不渲染任何具体承载力基准、锁点数量、启闭寿命次数、型号规格数字或"达标"结论；仅显示推导占位与 `pending_verification` 标注。

---

## 10. 测试方案

> 落实 `.ai/tasks/phase3.1_test_plan.md` 四类别；**编码阶段**实施，本阶段仅定方案。所有用例零真实数值。

### 10.1 单元（HardwareCalculator）

| 用例 | 输入 | 期望 |
|---|---|---|
| 阈值缺失降级 | E-TH-04 `value=null` | `verification_status=="pending_verification"`；`intermediate` 各量为 pending 占位；`gaps` 含 E-TH-04 pending |
| 上游 profile 未签降级 | `profile_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["profile_result: upstream_pending"]`，不伪造 F_hardware/R 数值 |
| 输入 inferred 降级 | `opening_form` 为 inferred | 结论 pending，不伪造承载力/锁点数量 |
| 四字段强制 | 任意 | 输出键集合 ⊇ `REQUIRED_OUTPUT_KEYS` |
| 证据可回写 | 产出对象 | `evidence` 含 `source_ref` 槽位（值 pending）+ 参数来源标识 |
| 验证等级 | 未双签 | 可信等级 Level 0/1，绝不 Level 3 |

### 10.2 集成（EngineeringAgent.invoke 全链路）

- `analyses=["hardware"]` → `review_chain` 仅含一条记录，`verification_status` 恒 pending（设计态）；
- `analyses=["wind_pressure","profile","hardware"]` → 上游 pending 状态逐级传导至 hardware pending（详见第 6 节 降级传导，pending_verification）。

### 10.3 安全（降级/误开/防篡改）

- 阈值未双签 → 该模块及依赖链绝不 `engineering_approved`（一票否决）；
- 测试全程 `engineering_enabled=false`；不得置 true；
- `review_log` append-only + `prev_event_id` 哈希链连续。

### 10.4 防编造（红线锁死）

- 扫描 `agents/engineering/calc/hardware.py`：不含未走 `verified.json`/E-TH-04 的硬编码工程常数（承载力基准/锁点数量/启闭寿命次数/连接强度）；
- 含业务词（五金/承载/锁点/寿命/开启）行均配对 `pending_verification`，无真实数字；
- `result` 在未 approved 时不含具体承载力/锁点数量/寿命次数/型号规格数值。

### 10.5 覆盖率

- backend ≥ 60%（随真实计算补全后 ≥ 70%）；`bash scripts/ci/local_ci.sh` 维持 8/8 全绿、覆盖率不降。

---

## 11. 风险分析

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-HW-1 | 五金承载力阈值（E-TH-04）长期未双签 | hardware 永久 pending | 专家双签流程 + `review_log` 追踪；CI 防编造闸门 |
| R-HW-2 | 误将 Environment 实时气象当作扇荷载 | 来源错误，结论失真 | 荷载只来自上游 profile 传递的杆件反力；代码审查锁死 |
| R-HW-3 | 上游 profile_result 不可信却被当作确定输入 | 编造五金达标结论 | 第 6 节 降级传导；计算单元显式检查 profile 可信态 |
| R-HW-4 | 输入 `inferred` 直接驱动确定性结论 | 编造工程判断 | `field_provenance` 判定：inferred → pending（ADR-2.2.1 第 7 节） |
| R-HW-5 | 跨模块耦合错误传导 | wind/profile 错值污染 hardware | 第 6 节 降级传导；下游独立审核 |
| R-HW-6 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | 第 9 节 防误显；状态 != approved 仅显 pending 占位 |
| R-HW-7 | `engineering_enabled` 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-HW-8 | 公式系数体系选择不当（承载力/锁点/连接/寿命） | 适用边界错误 | 第 8 节 审核点由专家在双签时确认；设计态不固化 |

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含任何实现代码，未开启 `engineering_enabled`，全参数 `pending_verification`）
