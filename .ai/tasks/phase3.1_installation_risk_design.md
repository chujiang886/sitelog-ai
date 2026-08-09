# Installation Risk（安装施工风险）工程模块设计（Sprint J）

- **生成**：2026-07-30（Phase 3.1 Sprint J 设计阶段）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，未编码；**不进入实现**）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 E-TH-05/E-TH-06 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B/C wind_pressure 设计与编码（上游 w_k 供给方就绪，pending_verification）；Sprint D/E glass_safety 设计与编码（玻璃重量/玻璃安全并列，pending_verification）；Sprint F/G profile 设计与编码（型材条件上游，pending_verification）；Sprint H/I hardware 设计与编码（五金条件上游，pending_verification）
- **红线守约**：本文件**零真实风险分数、零真实承载参数、零真实施工安全距离、零规范条款编号**；`engineering_enabled=false`；所有参数 `pending_verification`；不编写任何实现代码。

---

## 0. 设计范围与边界

| 项 | 范围 |
|---|---|
| ✅ 本次定义 | installation_risk（安装施工风险）接口的分析设计（接口分析/输入/输出/规则来源/阈值依赖/与 Glass·Profile·Hardware 关系/审核点/PDF/测试/风险） |
| ⛔ 本次不做 | 任何 Python/TS 实现、任何数值计算、任何 `verified=true` 写入、`engineering_enabled` 置真 |
| 🔗 衔接 | 复用 Sprint A 的 `ExpertBackedEngineeringValidation`、`INTERFACE_THRESHOLD_MAP`（installation_risk→E-TH-05、E-TH-06）、`review_log`；复用 Design 侧 `field_provenance`/`threshold_refs` 契约；消费 Sprint E 的 `glass_safety_result`（玻璃重量）、Sprint G 的 `profile_result`（型材条件）、Sprint I 的 `hardware_result`（五金条件） |

> 设计态正确表现：每个数值位均为 `<取自 E-TH-05/E-TH-06 / glass_safety_result / profile_result / hardware_result，pending_verification>` 或符号占位（G_weight / H_floor / R_lift / Risk_total / D_safe 等）；不得出现任何具体风险分数、承载参数、施工安全距离数字或条款号。

---

## 1. 当前 installation_risk 接口分析

### 1.1 骨架现状（实读 `agents/engineering/agent.py`）

- `ANALYSIS_INTERFACES` 含 `"installation_risk"`，与 `wind_pressure`/`glass_safety`/`profile`/`hardware` 并列（五接口之一）。
- `EngineeringAgent.analyze_installation_risk(context_data)` 当前为**骨架实现**：
  - 签名 `(self, context_data: Mapping[str, Any]) -> dict[str, Any]`；
  - 内部 `del context_data`（不消费输入，仅锁定签名）；
  - 返回 `build_skeleton_output()`：四字段全空 + `verification_status="pending_verification"`。
- `invoke()` 调度：`dispatch["installation_risk"] = self.analyze_installation_risk`；每个接口产出经 `self._validator.validate(interface="installation_risk", payload=output)` 生成一条 `review_chain` 记录。
- 默认 validator：`PendingEngineeringValidation`（仅结构校验，恒 pending）；可注入 `ExpertBackedEngineeringValidation`（双签闸门，Sprint A 已落地）。

### 1.2 演进路径（Sprint J 设计 → 编码阶段）

**EngineeringAgent 侧契约零改动**（与 3.1 架构设计一致）。真实计算的接入方式：

- 新增独立计算单元 `agents/engineering/calc/installation_risk.py`（或等价的 `InstallationRiskCalculator`），**不修改** `agent.py` 接口签名与调度；
- `analyze_installation_risk()` 内部从骨架直返，改为调用计算单元并把结果按统一四字段结构封装；
- validator 仅替换为 `ExpertBackedEngineeringValidation`（Sprint A 已落地），Agent 调度逻辑不变；
- 计算单元的输出对象统一含 `result / confidence / evidence / verification_status` + 扩展字段（`intermediate` / `provenance` / `gaps` / `threshold_refs` / `sign_off_id` 占位），结构与 wind_pressure 的 `WindPressureResult`、glass_safety 的 `GlassSafetyResult`、profile 的 `ProfileResult`、hardware 的 `HardwareResult` 同构。

### 1.3 工程链路定位（末端聚合）

- installation_risk 是**链路末端聚合模块**：它不直接产生风压/玻璃/型材/五金，而是消费前序四模块（Wind/Profile/Hardware 链路 + Glass 并列）的产出，评估安装施工风险。
- 上游耦合：
  - 玻璃重量 `G_weight` ← Design/Glass（经 `glass_safety_result` 透传或 Design `design_candidate` 玻璃配置）；
  - 型材条件 ← `profile_result`（型材承载/连接条件）；
  - 五金条件 ← `hardware_result`（五金承载/连接可靠性）；
  - 风荷载 `w_k` ← wind_pressure（经 profile/hardware 传递，数值 pending_verification）。
- installation_risk **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03）、型材阈值（D-TH-01）、玻璃阈值（D-TH-02）、五金阈值（E-TH-04），只消费上游结果。

### 1.4 输入/输出契约锚点

- 输入：`context_data` 应透传 `project` / `environment_result` / `design_candidate` / `glass_safety_result` / `profile_result` / `hardware_result`（上游分析产物）/ `vision_result` 等；骨架阶段不消费，设计阶段明确其字段契约（见第 2 节，pending_verification）。
- 输出：统一四字段 + 扩展字段（见第 3 节），经 `ExpertBackedEngineeringValidation.validate` 产出审核链记录。

---

## 2. 输入参数设计

installation_risk 计算所需输入分四层，均须携带**溯源标签**（`measured` / `inferred` / `verified` / `unavailable`），任何 `inferred`/`unavailable` 关键输入 → 该模块结论 `pending_verification`。

### 2.1 项目输入（Project Input）

| 字段 | 含义 | 溯源预期 | 用途 |
|---|---|---|---|
| `project.installation_scenario` | 门窗安装场景（新建/改造/高层/幕墙**类别标识**） | `inferred`（来自 Design/Vision 候选） | 驱动风险模型选择（类别标识，数值 pending） |
| `project.floor_height` | 楼层高度（吊运高度**类别**） | `inferred`（来自几何识别） | 驱动吊装风险判定；具体高度数值 pending（禁止真实高度数字） |
| `project.lift_risk` | 吊装风险（吊运条件**类别**） | `inferred` | 驱动吊装条件判定；具体指标 pending |
| `project.construction_env` | 施工环境（场地/临边/交叉作业**类别**） | `inferred`（Vision/用户） | 驱动环境风险评估；数值 pending |
| `project.weather_impact` | 天气影响（风速/雨雪/温度**类别**） | `inferred` | 驱动天气风险判定；数值 pending |
| `project.install_process` | 安装工艺（干法/湿法/单元式**类别**） | `inferred` | 驱动工艺流程风险判定；数值 pending |

### 2.2 Environment 输入（来自 `EnvironmentAgent` 输出 + 上游四模块）

- **风荷载 `w_k`（链路源头，经 profile/hardware 传递）**：installation_risk 通过 `context_data["wind_pressure_result"]` 或 `profile_result` 间接读取，仅作溯源参考；**不直接重算**风压（红线，数值 pending_verification）。
- **玻璃重量 `G_weight`（来自 Design/Glass）**：经 `context_data["glass_safety_result"]` 或 `design_candidate` 取玻璃配置/面板重量类别；installation_risk 消费其重量量级用于吊装/破碎风险评估（具体重量数值 pending，禁止真实重量）。
- **型材条件（来自 `profile_result`）**：取型材承载/连接条件；installation_risk 消费其结构支撑可靠性（数值 pending）。
- **五金条件（来自 `hardware_result`）**：取五金承载/连接可靠性；installation_risk 消费其连接可靠性（数值 pending）。
- 复用 `agents/environment/agent.py` 的 `field_provenance` 与 `facts`（如 `climate_zone`/`corrosion` 仅作环境描述参考；腐蚀类别由第 5 节 E-TH-05 子维度"环境风险"消费，数值 pending）。

> ⚠️ 红线：承载参数与施工安全距离只来自上游产出与 E-TH-05/E-TH-06，**绝不**由 Environment 实时气象或本模块自算推导确定性风险分数/安全距离。

### 2.3 Design 输入（来自 `DesignAgent` 候选）

复用 `agents/design/agent.py` 的候选结构与 `threshold_loader`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `design_candidate.glass_config` | Design 候选（**D-TH-02** 引用） | 玻璃配置/面板重量，installation_risk 核心消费项（玻璃重量）；数值 pending |
| `design_candidate.frame_series` | Design 候选（**D-TH-01** 引用） | 型材系列，经 profile 间接影响；installation_risk 不直接消费 |
| `design_candidate.opening_form_hint` | Design 候选 | 开启形式建议，`inferred`；驱动安装场景分类 |
| `field_provenance` / `threshold_refs` | Design 输出 | 复用字段级溯源，installation_risk 仅读取，不改写 |

### 2.4 Engineering 阈值输入（来自 `verified.json` via `threshold_loader`）

| 阈值 ID | 参数 | 单位 | 喂给的变量 | 双签要求 |
|---|---|---|---|---|
| `E-TH-05` | 腐蚀等级（环境腐蚀等级） | （等级标识，pending） | `corrosion_level`（环境风险子维度） | 主理人 + 行业专家双签 |
| `E-TH-06` | 安装风险矩阵（安装风险评级矩阵，含**施工风险等级 / 吊装条件 / 人员操作风险 / 环境风险**四子维度） | （评级矩阵，pending） | `risk_level` / `lift_condition` / `personnel_risk` / `env_risk` / `Risk_total` | 主理人 + 行业专家双签 |

> 设计态：E-TH-05、E-TH-06 `value=null`、`verified=false`、双签字段 `null`、`source_ref` 含 `pending_verification`。未双签前，计算单元不得取得任何风险分数/承载参数/安全距离，输出恒 `pending_verification`。

---

## 3. 输出结构设计

### 3.1 统一四字段（接口契约，勿改键名）

```jsonc
{
  "result": "<安装风险评级/吊装条件/安全距离校核结论，pending 态为空或推导占位；approved 后填符号化结论>",
  "confidence": "<可信等级标签：pending 态为 'pending_verification'；approved 后为 'verified'>",
  "evidence": "<来源说明：规则来源 + 各变量取值来源 + source_ref（规范条款号 pending_verification）>",
  "verification_status": "pending_verification"   // 双签齐 + enabled=true + 上游可信 才转 engineering_approved
}
```

### 3.2 扩展字段（计算单元内部承载，供审核链/PDF 消费）

| 字段 | 含义 |
|---|---|
| `interface` | `"installation_risk"`（固定） |
| `intermediate` | 中间变量字典：`{ "G_weight": <玻璃重量，from glass_safety_result/Design，pending>, "H_floor": <楼层高度类别，pending>, "w_k": <from wind_pressure，pending>, "profile_cond": <from profile_result，pending>, "hardware_cond": <from hardware_result，pending>, "lift_condition": <吊装条件，pending>, "personnel_risk": <人员操作风险，pending>, "env_risk": <环境风险（含 E-TH-05 corrosion_level），pending>, "weather_impact": <天气影响，pending>, "process_risk": <工艺流程风险，pending>, "Risk_total": <综合安装风险评级，from E-TH-06，pending>, "D_safe": <施工安全距离，pending，禁止真实距离> }` |
| `provenance` | 每个输入字段的溯源标签（`measured`/`inferred`/`verified`/`unavailable`） |
| `threshold_refs` | `["E-TH-05", "E-TH-06"]`（仅引用，数值 pending） |
| `gaps` | 缺失/未签字项登记（如 `E-TH-06: pending_verification`、`glass_safety_result: upstream_pending`、`profile_result: upstream_pending`、`hardware_result: upstream_pending`） |
| `sign_off_id` | 占位 `null`（仅 approved 后由 `review_log.compute_sign_off_id` 派生） |

### 3.3 审核链记录（经 `ExpertBackedEngineeringValidation.validate` 产出）

七字段（Sprint A 已定义）：
`interface / structure_valid / threshold_verified / expert_signed / verification_status / sign_off_id / validator`。

- `threshold_verified`：`get_interface_thresholds("installation_risk")` 返回 `("E-TH-05", "E-TH-06")`，两阈值 `mgmt_signed` 才 True；
- `expert_signed`：E-TH-05/06 `expert_signed` 才 True；
- 闸门：`structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` → `engineering_approved`，否则恒 `pending_verification`；
- **叠加跨模块闸门**：即便上述四项满足，若任一上游（glass_safety/profile/hardware）`verification_status != engineering_approved`，installation_risk 计算单元在 `verification_status` 仍强制 `pending_verification` 并登记 `gaps`（见第 6 节 降级传导，pending_verification）。

---

## 4. 规则体系设计（仅定义：风险模型 / 变量关系 / 数据来源；禁止真实参数）

建立 `agents/engineering/rules/installation_rules.py`，承载 installation_risk 的**符号级规则结构**：风险模型、变量关系、数据来源映射；**不保存任何真实工程常数（风险分数 / 承载参数 / 施工安全距离 / 规范条款号）**。

### 4.1 风险模型来源（概念级）

- 参考建筑门窗**安装施工（吊装 / 临边作业 / 玻璃破碎 / 连接可靠）相关安全与风险评级标准与规范**（**具体标准号与条款号均由行业专家双签阶段填入，pending_verification**）。
- 采用业界通用的**多因素风险评级**结构：在玻璃重量、楼层高度、吊装条件、施工环境、天气影响、安装工艺、腐蚀环境（E-TH-05）等多因素下，综合评估安装施工风险等级 `Risk_total`；同时校核吊装条件 `lift_condition`、施工安全距离 `D_safe`、人员操作风险 `personnel_risk`、环境风险 `env_risk` 是否落在可接受区间。
- 适用性边界（不同安装场景对应风险评级矩阵口径、是否计风速阈值、安全距离取值规则）由专家在双签时确认，设计态不固化。

### 4.2 变量关系（符号级，无数值）

令：

- `G_weight` = 玻璃面板重量（来自 Design/Glass，经 glass_safety_result 透传，数值 pending）；
- `H_floor` = 楼层高度（来自项目几何，数值 pending，禁止真实高度）；
- `w_k` = 风荷载标准值（来自 wind_pressure，经上游传递，Pa，数值 pending）；
- `P_profile` = 型材条件（来自 `profile_result`，数值 pending）；
- `P_hardware` = 五金条件（来自 `hardware_result`，数值 pending）；
- `lift_condition` = 吊装条件指标（来自 E-TH-06，数值 pending）；
- `personnel_risk` = 人员操作风险（来自 E-TH-06，数值 pending）；
- `env_risk` = 环境风险（含 E-TH-05 腐蚀等级，数值 pending）；
- `weather_impact` = 天气影响（风速/雨雪类别，数值 pending）；
- `process_risk` = 安装工艺风险（数值 pending）；
- `Risk_total` = 综合安装风险评级（来自 E-TH-06，数值 pending，禁止真实分数）；
- `D_safe` = 施工安全距离（来自 E-TH-06，数值 pending，禁止真实距离）。

关系（符号占位，系数/矩阵选取规则 pending_verification）：

```
Risk_total   = r(G_weight, H_floor, lift_condition, env_risk, weather_impact, process_risk, P_profile, P_hardware)   (E-TH-06, 评级 pending_verification)
吊装判定:     lift_condition ≥ lift_required(H_floor, G_weight)        (吊装条件，数值 pending_verification)
安全距离:     D_safe ≥ D_required(scenario, H_floor)                    (施工安全距离，数值 pending_verification，禁止真实距离)
环境判定:     env_risk ≤ env_threshold(E-TH-05 corrosion_level)         (环境风险，数值 pending_verification)
人员判定:     personnel_risk ≤ personnel_threshold(E-TH-06)             (人员操作风险，数值 pending_verification)
工艺判定:     process_risk ≤ process_threshold(E-TH-06)                 (工艺流程风险，数值 pending_verification)
```

衍生依赖（仅描述变量间因果，不填数）：

- `Risk_total` 取决于玻璃重量、楼层高度、吊装条件、环境、天气、工艺与上游结构条件（型材/五金）的聚合；
- `lift_condition` / `personnel_risk` / `env_risk` / `process_risk` / `D_safe` 取决于 E-TH-06 风险矩阵与 E-TH-05 腐蚀等级（双签后）；
- `G_weight` / `P_profile` / `P_hardware` / `w_k` **不**由本模块推算，只消费上游产出（跨模块耦合，见第 6 节，pending_verification）。

### 4.3 数据来源映射（每个变量 → 哪一层输入）

| 变量 | 数据来源 | 溯源 |
|---|---|---|
| `G_weight` | Design/Glass（`glass_safety_result` / `design_candidate.glass_config`，内部依赖 D-TH-02，pending_verification） | 随 glass_safety 的 verification_status |
| `P_profile` | profile 上游产出（`profile_result`，内部依赖 D-TH-01 + w_k，pending_verification） | 随 profile 的 verification_status |
| `P_hardware` | hardware 上游产出（`hardware_result`，内部依赖 E-TH-04，pending_verification） | 随 hardware 的 verification_status |
| `w_k` | wind_pressure 上游产出（内部依赖 E-TH-01、E-TH-02、E-TH-03，pending_verification） | 随 wind_pressure 的 verification_status |
| `lift_condition` / `personnel_risk` / `env_risk` / `process_risk` / `Risk_total` / `D_safe` | Engineering 阈值 **E-TH-05 / E-TH-06**（安装风险矩阵 + 腐蚀等级） | `verified`（双签后） |
| `H_floor` / `weather_impact` / `install_process` | 项目几何 / Environment / Design 候选 | `inferred`/`pending` |

---

## 5. 阈值设计（E-TH-05 / E-TH-06 角色 与 四子维度审核占位）

### 5.1 E-TH-05（腐蚀等级）与 E-TH-06（安装风险矩阵）角色绑定

E-TH-05、E-TH-06 已在 Sprint A 的 `agents/engineering/thresholds/verified.json` 占位（`applies_to: ["installation_risk"]`），本设计明确其**角色绑定**与**四子维度审核占位**：

| 阈值 ID | 绑定变量 | 在模型中角色 | 双签验收口径（专家须确认） |
|---|---|---|---|
| **E-TH-05** | `corrosion_level`（环境腐蚀等级） | 环境风险 `env_risk` 的取值依据 | 腐蚀等级与施工环境/地域气候口径一致；单位与量纲在 approved 后自洽 |
| **E-TH-06** | `risk_level` / `lift_condition` / `personnel_risk` / `env_risk` / `Risk_total` / `D_safe` | 安装风险评级矩阵（综合风险/吊装/人员/环境/工艺/安全距离） | 评级矩阵口径与项目安装场景、玻璃重量、楼层高度对应；数值与量纲在 approved 后自洽 |

E-TH-06 **四子维度审核占位**（设计态全 `value=null` / `verified=false`，专家双签时逐项填充）：

| 子维度 | 审核占位含义 | 双签时须确认 |
|---|---|---|
| 施工风险等级 | 综合安装风险评级 `Risk_total` 与场景匹配 | 评级矩阵口径与安装场景/玻璃重量/楼层高度对应，评级 pending（禁止真实分数） |
| 吊装条件 | 吊装条件 `lift_condition` 与吊运工况匹配 | 吊装条件口径与楼层高度/玻璃重量对应，数值 pending |
| 人员操作风险 | 人员操作风险 `personnel_risk` 与作业方式匹配 | 人员风险口径与工艺流程/临边作业对应，数值 pending |
| 环境风险 | 环境风险 `env_risk`（含腐蚀）与施工环境匹配 | 环境风险口径与腐蚀等级（E-TH-05）/天气对应，数值 pending |

- **双签字段要求**（Sprint A 机制）：`verified=true` + `verified_by` + `verified_at` + `expert_verified_by` + `expert_verified_at` 五字段俱全 → `is_fully_verified()=True`。
- **source_ref 要求**：专家填入规范/标准号与条款号（设计态全为 `pending_verification`）。
- **禁止**：AI 代码不得写入 `verified=true`、不得填写 `value`（风险分数/承载参数/安全距离）、不得伪造签字（由 `check_fabrication.py` + 防编造测试锁死）。
- **未双签后果**：`threshold_verified=False` → `verification_status` 恒 `pending_verification`，`sign_off_id=null`，绝不输出 `engineering_approved`。

### 5.2 审核流程（E-TH-05/06 双签 + 工程闸门 + 上游闸门）

- installation_risk 要 `engineering_approved`，须**同时**满足：
  1. 自身阈值 E-TH-05、E-TH-06 双签完整（`threshold_verified` + `expert_signed`）；
  2. 上游 `glass_safety_result` / `profile_result` / `hardware_result` 可信（三者 `verification_status == engineering_approved`）；
  3. `engineering_enabled=true`。
- 任一不满足 → 结论恒 `pending_verification`（计算单元显式登记 `gaps`，不依赖 validator 单接口判定）。

---

## 6. 与其他模块关系

installation_risk 是**末端聚合消费者**；Glass/Profile/Hardware 的 `engineering_approved` **不替代** installation_risk 审核。

### 6.1 数据耦合

- **玻璃重量来自 Design/Glass**：`G_weight` ← `design_candidate.glass_config`（D-TH-02）或 `glass_safety_result` 透传；installation_risk 消费其重量量级用于吊装/破碎风险评估。
- **型材条件来自 Profile**：`P_profile` ← `profile_result`（型材承载/连接条件）；installation_risk 消费其结构支撑可靠性。
- **五金条件来自 Hardware**：`P_hardware` ← `hardware_result`（五金承载/连接可靠性）；installation_risk 消费其连接可靠性。
- 耦合通过统一四字段结构 + `threshold_refs` + 上游 `xxx_result` 实现，不新增私有通道。

### 6.2 阈值跨库引用

| 模块 | 依赖的上游产出 | 自身阈值 |
|---|---|---|
| `installation_risk` | `glass_safety_result` / `profile_result` / `hardware_result`（间接含 w_k） | E-TH-05（腐蚀等级）+ E-TH-06（安装风险矩阵） |
| `hardware` | `profile_result`（间接含 w_k） | E-TH-04（五金承载力） |
| `profile` | `w_k`（来自 wind_pressure） | D-TH-01（型材配置） |
| `glass_safety` | `w_k`（来自 wind_pressure） | D-TH-02（玻璃配置） |

- installation_risk **不重复定义**风压/型材/玻璃/五金阈值，只消费上游结果。
- 下游 `verification_status` 独立判定：即使上游已 approved，installation_risk 仍需自身阈值双签 + `engineering_enabled` + 上游可信 才转 approved。

### 6.3 降级传导（上游 pending → installation_risk pending）

- 若任一上游 `pending_verification`（阈值未签/输入 inferred/上游不可信）→ 相应输入不可信 → installation_risk 即使自身阈值已签，结论仍须 `pending_verification`（不得基于未验证玻璃重量/型材/五金推出"安装风险可控"）。
- installation_risk 计算单元显式检查上游 `verification_status`，未 approved 时登记 `gaps: ["glass_safety_result: upstream_pending" / "profile_result: upstream_pending" / "hardware_result: upstream_pending"]` 并强制 pending。
- 跨模块 `gaps` 显式登记上游 pending 项（五接口逐级/并列传导）。

---

## 7. Expert 审核点设计

专家双签阶段须对以下审核点逐一确认（设计态全部 `pending_verification`）：

1. **施工环境**：场地条件/临边作业/交叉作业类别与风险评级口径一致（E-TH-06 子维度"施工风险等级"）。
2. **吊装方案**：吊装条件 `lift_condition` 与楼层高度/玻璃重量工况匹配；吊运方案可行（E-TH-06 子维度"吊装条件"）。
3. **人员风险**：人员操作风险 `personnel_risk` 与作业方式/培训/防护对应（E-TH-06 子维度"人员操作风险"）。
4. **设备条件**：吊装/施工设备能力覆盖玻璃重量与楼层高度；设备条件与 `lift_condition` 对应（E-TH-06 矩阵）。
5. **工艺流程**：安装工艺 `process_risk` 与干法/湿法/单元式对应；工艺风险口径由专家确认（E-TH-06 子维度"施工风险等级"/工艺）。
6. **环境风险**：腐蚀等级（E-TH-05）与施工环境/地域气候一致；天气影响 `weather_impact` 口径合理（E-TH-06 子维度"环境风险"）。
7. **安全距离**：施工安全距离 `D_safe` 与场景/楼层高度对应，数值 pending（禁止真实距离）。
8. **上游可信态**：glass_safety/profile/hardware 已 approved，玻璃重量/型材/五金输入可信（第 6 节 降级传导，pending_verification）。
9. **输入溯源合规**：楼层高度/施工环境/天气/工艺等 `inferred` 字段在签字时已被人工复核或转为 `verified`；不存在用 `inferred` 直接驱动确定性结论。
10. **单位与量纲一致**：N、m、等级、无量纲系数在 approved 后自洽。

审核动作写入 `review_log.jsonl`（append-only，`event_id` 哈希链，`sign_off_id` 在 approved 时派生）。

---

## 8. PDF 展示方案

复用 Phase 3.1 设计就绪报告已确立的 PDF 契约（三态徽标 + `review_chain` 逐接口透出）：

- **三态徽标**：`[已验证]`（engineering_approved）/ `[AI推理·待确认]`（inferred）/ `[待确认]`（pending_verification）按 `verification_status` 渲染。
- **installation_risk 章节内容**：
  - 输入摘要：安装场景/楼层高度类别/吊装风险/施工环境/天气影响/安装工艺及其溯源标签；
  - 上游耦合：glass_safety 的玻璃重量、profile 的型材条件、hardware 的五金条件可信状态（随各上游章节联动）；
  - 风险模型：多因素风险评级结构符号展示 + 规范来源占位（条款号 pending）；
  - 中间变量表：`G_weight`/`H_floor`/`lift_condition`/`personnel_risk`/`env_risk`/`weather_impact`/`process_risk`/`Risk_total`/`D_safe` 各取值来源（E-TH-05/E-TH-06 或上游 result 或 pending）；
  - 审核状态：七字段 `review_chain` 记录透出（接口名/结构合法/阈值校验/专家签字/状态/ `sign_off_id`）；
  - 专家签字区：`verified_by`/`verified_at`/`expert_verified_by`/`expert_verified_at` 占位（未签显示"待行业专家双签"）。
- **防误显**：`verification_status != engineering_approved` 时，绝不渲染任何具体风险分数、承载参数、施工安全距离数字或"可控"结论；仅显示推导占位与 `pending_verification` 标注。

---

## 9. 测试方案

> 落实 `.ai/tasks/phase3.1_test_plan.md` 四类别；**编码阶段**实施，本阶段仅定方案。所有用例零真实数值。

### 9.1 单元（InstallationRiskCalculator）

| 用例 | 输入 | 期望 |
|---|---|---|
| 阈值缺失降级 | E-TH-06 `value=null` | `verification_status=="pending_verification"`；`intermediate` 各量为 pending 占位；`gaps` 含 E-TH-05/E-TH-06 pending |
| 上游 glass pending 降级 | `glass_safety_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["glass_safety_result: upstream_pending"]`，不伪造 G_weight/Risk_total 数值 |
| 上游 profile pending 降级 | `profile_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["profile_result: upstream_pending"]` |
| 上游 hardware pending 降级 | `hardware_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["hardware_result: upstream_pending"]` |
| 输入 inferred 降级 | `floor_height` 为 inferred | 结论 pending，不伪造风险分数/安全距离 |
| 四字段强制 | 任意 | 输出键集合 ⊇ `REQUIRED_OUTPUT_KEYS` |
| 证据可回写 | 产出对象 | `evidence` 含 `source_ref` 槽位（值 pending）+ 参数来源标识 |
| 验证等级 | 未双签 | 可信等级 Level 0/1，绝不 Level 3 |

### 9.2 集成（EngineeringAgent.invoke 全链路）

- `analyses=["installation_risk"]` → `review_chain` 仅含一条记录，`verification_status` 恒 pending（设计态）；
- `analyses=["wind_pressure","profile","hardware","glass_safety","installation_risk"]` → 上游 pending 状态逐级/并列传导至 installation_risk pending（详见第 6 节 降级传导，pending_verification）。

### 9.3 安全（降级/误开/防篡改）

- 阈值未双签 → 该模块及依赖链绝不 `engineering_approved`（一票否决）；
- 测试全程 `engineering_enabled=false`；不得置 true；
- `review_log` append-only + `prev_event_id` 哈希链连续。

### 9.4 防编造（红线锁死）

- 扫描 `agents/engineering/calc/installation_risk.py`：不含未走 `verified.json`/E-TH-05/E-TH-06 的硬编码工程常数（风险分数/承载参数/施工安全距离）；
- 含业务词（风压/楼层/壁厚/使用寿命/防腐等级/评分权重）行均配对 `pending_verification`，无真实数字；
- `result` 在未 approved 时不含具体风险分数/承载参数/安全距离数值。

### 9.5 覆盖率

- backend ≥ 60%（随真实计算补全后 ≥ 70%）；`bash scripts/ci/local_ci.sh` 维持 8/8 全绿、覆盖率不降。

---

## 10. 风险分析

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-IR-1 | 安装风险矩阵（E-TH-06）长期未双签 | installation_risk 永久 pending | 专家双签流程 + `review_log` 追踪；CI 防编造闸门 |
| R-IR-2 | 误将 Environment 实时气象当作风险判定 | 来源错误，结论失真 | 风险只来自上游产出与 E-TH-05/E-TH-06；代码审查锁死 |
| R-IR-3 | 上游 glass/profile/hardware_result 不可信却被当作确定输入 | 编造风险可控结论 | 第 6 节 降级传导；计算单元显式检查上游可信态 |
| R-IR-4 | 输入 `inferred` 直接驱动确定性结论 | 编造工程判断 | `field_provenance` 判定：inferred → pending（ADR-2.2.1 第 7 节） |
| R-IR-5 | 跨模块耦合错误传导 | 上游错值污染 installation_risk | 第 6 节 降级传导；下游独立审核 |
| R-IR-6 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | 第 8 节 防误显；状态 != approved 仅显 pending 占位 |
| R-IR-7 | `engineering_enabled` 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-IR-8 | 风险评级矩阵口径选择不当（吊装/人员/环境/工艺） | 适用边界错误 | 第 7 节 审核点由专家在双签时确认；设计态不固化 |

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含任何实现代码，未开启 `engineering_enabled`，全参数 `pending_verification`）
