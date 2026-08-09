# Profile（型材）工程模块设计（Sprint F）

- **生成**：2026-07-30（Phase 3.1 Sprint F 设计阶段）
- **身份**：BOIP AI 工程计算架构负责人
- **状态**：🟡 DESIGN_ONLY（仅设计，未编码；**不进入实现**）
- **依赖**：Sprint A 已交付可信审核基础设施（阈值体系 + ExpertBackedEngineeringValidation + review_log + 防编造扫描 + CI 8/8）；Sprint B wind_pressure 设计 + Sprint C 编码（上游 w_k 供给方就绪）；Sprint D/E glass_safety 设计与编码（并列模块，pending_verification）
- **红线守约**：本文件**零真实壁厚值、零真实强度值、零真实截面惯性矩、零规范条款编号**；`engineering_enabled=false`；所有参数 `pending_verification`；不编写任何实现代码。

---

## 0. 设计范围与边界

| 项 | 范围 |
|---|---|
| ✅ 本次定义 | profile（型材）接口的分析设计（输入/输出/规则来源/阈值依赖/审核点/与 wind_pressure 及 glass_safety 关系/PDF/测试/风险） |
| ⛔ 本次不做 | 任何 Python/TS 实现、任何数值计算、任何 `verified=true` 写入、`engineering_enabled` 置真 |
| 🔗 衔接 | 复用 Sprint A 的 `ExpertBackedEngineeringValidation`、`INTERFACE_THRESHOLD_MAP`、`review_log`；复用 Design 侧 `field_provenance`/`threshold_refs` 契约；消费 Sprint C 的 wind_pressure 上游 `w_k` |

> 设计态正确表现：每个数值位均为 `<取自 D-TH-01 / wind_pressure，pending_verification>` 或符号占位；不得出现任何具体壁厚、截面惯性矩、强度设计值、弹性模量、挠度限值或条款号。

---

## 1. 当前 profile 接口分析

### 1.1 骨架现状（实读 `agents/engineering/agent.py`）

- `ANALYSIS_INTERFACES` 含 `"profile"`，与 `wind_pressure`/`glass_safety`/`hardware`/`installation_risk` 并列（五接口之一）。
- `EngineeringAgent.analyze_profile(context_data)` 当前为**骨架实现**：
  - 签名 `(self, context_data: Mapping[str, Any]) -> dict[str, Any]`；
  - 内部 `del context_data`（不消费输入，仅锁定签名）；
  - 返回 `build_skeleton_output()`：四字段全空 + `verification_status="pending_verification"`。
- `invoke()` 调度：`dispatch["profile"] = self.analyze_profile`；每个接口产出经 `self._validator.validate(interface="profile", payload=output)` 生成一条 `review_chain` 记录。
- 默认 validator：`PendingEngineeringValidation`（仅结构校验，恒 pending）；可注入 `ExpertBackedEngineeringValidation`（双签闸门）。

### 1.2 演进路径（Sprint F 设计 → 编码阶段）

**EngineeringAgent 侧契约零改动**（与 3.1 架构设计一致）。真实计算的接入方式：

- 新增独立计算单元 `agents/engineering/calc/profile.py`（或等价的 `ProfileCalculator`），**不修改** `agent.py` 接口签名与调度；
- `analyze_profile()` 内部从骨架直返，改为调用计算单元并把结果按统一四字段结构封装；
- validator 仅替换为 `ExpertBackedEngineeringValidation`（Sprint A 已落地），Agent 调度逻辑不变；
- 计算单元的输出对象统一含 `result / confidence / evidence / verification_status` + 扩展字段（`intermediate` / `provenance` / `gaps` / `threshold_refs` / `sign_off_id` 占位），结构与 wind_pressure 的 `WindPressureResult`、glass_safety 的 `GlassSafetyResult` 同构。

### 1.3 与 wind_pressure / glass_safety 的关系

- wind_pressure 是 profile 的**上游数据供给方**：wind_pressure 产出风荷载标准值 `w_k`（Pa），作为型材杆件（幕墙立柱/横梁）受荷输入的线荷载来源（详见第 4 节、第 6 节，pending_verification）。
- glass_safety 与 profile **并列**，二者均消费 wind_pressure 的 `w_k`，但计算对象不同（玻璃面板 vs 型材杆件）；glass_safety 的结论**不替代** profile 计算（详见第 6 节，pending_verification）。
- profile **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03），只消费 wind_pressure 的 `w_k`。

### 1.4 输入/输出契约锚点

- 输入：`context_data` 应透传 `project` / `environment_result` / `design_candidate` / `wind_pressure_result`（上游分析产物）/ `vision_result` 等；骨架阶段不消费，设计阶段明确其字段契约（见第 2 节，pending_verification）。
- 输出：统一四字段 + 扩展字段（见第 3 节），经 `ExpertBackedEngineeringValidation.validate` 产出审核链记录。

---

## 2. 输入参数设计

profile 计算所需输入分四层，均须携带**溯源标签**（`measured` / `inferred` / `verified` / `unavailable`），任何 `inferred`/`unavailable` 关键输入 → 该模块结论 `pending_verification`。

### 2.1 项目输入（Project Input）

| 字段 | 含义 | 溯源预期 | 用途 |
|---|---|---|---|
| `project.member_span` / `project.member_height` | 型材杆件跨度/受力长度 | `inferred`（来自 Vision/Design 候选） | 决定杆件弯矩与挠度计算几何（符号占位，数值 pending） |
| `project.support_condition` | 杆件支承条件（简支 / 连续 / 悬臂） | `inferred`（来自几何识别） | 选择弯矩/挠度系数体系（符号占位，数值 pending） |
| `project.building_height` | 建筑高度 | `inferred`（来自 Vision/用户） | 与 wind_pressure 共享，间接影响 w_k；gaps 登记 |
| `project.opening_position` / `project.orientation` | 开口/幕墙位置与朝向 | `inferred`（Vision） | 间接影响上游 w_k 取值（由 wind_pressure 消费） |

### 2.2 Environment 输入（来自 `EnvironmentAgent` 输出 + 上游 wind_pressure）

- **wind_pressure 输出 `w_k`（关键跨模块输入）**：profile 从 `context_data["wind_pressure_result"]` 读取（即 `WindPressureResult.as_full()` 或等价结构），取 `intermediate["w_k"]`：
  - 若 `wind_pressure_result.verification_status == engineering_approved` 且 `w_k.value` 非 None → 可信荷载；
  - 否则 → `w_k` 不可信，profile 登记 gap 并结论 `pending_verification`（第 6 节 降级传导，pending_verification）。
- 复用 `agents/environment/agent.py` 的 `field_provenance` 与 `facts`（如 `climate_zone`/`prevailing_wind` 仅作环境描述参考，不直接进入型材应力/挠度公式）。

> ⚠️ 红线：型材受荷来自 wind_pressure 的 `w_k`，**绝不**由 Environment 实时气象直接推算杆件荷载（基本风压只来自 E-TH-01，由 wind_pressure 归一化后供给）。

### 2.3 Design 输入（来自 `DesignAgent` 候选）

复用 `agents/design/agent.py` 的候选结构与 `threshold_loader`：

| 字段 | 来源 | 说明 |
|---|---|---|
| `design_candidate.frame_series` | Design 候选（**D-TH-01** 引用） | 型材系列选型（系列标识），profile 核心消费项；数值 pending |
| `design_candidate.frame_material` | Design 候选（D-TH-01 引用） | 型材材质（铝合金牌号等），仅影响下游 profile；数值 pending |
| `design_candidate.dimensions_hint` | Design 候选 | 分格/杆件尺寸建议，`inferred`；驱动 `project.member_span` |
| `field_provenance` / `threshold_refs` | Design 输出 | 复用字段级溯源，profile 仅读取，不改写 |

### 2.4 Engineering 阈值输入（来自 `verified.json` via `threshold_loader`）

| 阈值 ID | 参数 | 单位 | 喂给的变量 | 双签要求 |
|---|---|---|---|---|
| `D-TH-01` | 型材配置（型材系列 / 壁厚 / 截面属性 / 强度设计值 / 弹性模量） | （配置标识，pending） | `series` / `t`（壁厚）/ `I`（截面惯性矩）/ `W`（截面模量）/ `A`（截面积）/ `f`（强度设计值）/ `E`（弹性模量） | 主理人 + 行业专家双签 |

> 设计态：D-TH-01 `value=null`、`verified=false`、双签字段 `null`、`source_ref` 含 `pending_verification`。未双签前，计算单元不得取得任何型材配置数值（壁厚/截面属性/强度），输出恒 `pending_verification`。

---

## 3. 输出结构设计

### 3.1 统一四字段（接口契约，勿改键名）

```jsonc
{
  "result": "<型材杆件应力/挠度校核结论，pending 态为空或推导占位；approved 后填符号化结论>",
  "confidence": "<可信等级标签：pending 态为 'pending_verification'；approved 后为 'verified'>",
  "evidence": "<来源说明：规则来源 + 各变量取值来源 + source_ref（规范条款号 pending_verification）>",
  "verification_status": "pending_verification"   // 双签齐 + enabled=true + w_k 可信 才转 engineering_approved
}
```

### 3.2 扩展字段（计算单元内部承载，供审核链/PDF 消费）

| 字段 | 含义 |
|---|---|
| `interface` | `"profile"`（固定） |
| `intermediate` | 中间变量字典：`{ "w_k": <from wind_pressure, pending>, "series": <型材系列, pending>, "t": <壁厚, pending>, "I": <截面惯性矩, pending>, "W": <截面模量, pending>, "A": <截面积, pending>, "f": <强度设计值, pending>, "E": <弹性模量, pending>, "M": <杆件弯矩, pending>, "N": <轴力, pending>, "sigma": <型材弯曲/组合应力, pending>, "delta": <挠度, pending>, "delta_lim": <挠度限值, pending> }` |
| `provenance` | 每个输入字段的溯源标签（`measured`/`inferred`/`verified`/`unavailable`） |
| `threshold_refs` | `["D-TH-01"]`（仅引用，数值 pending） |
| `gaps` | 缺失/未签字项登记（如 `D-TH-01: pending_verification`、`w_k: upstream_pending`） |
| `sign_off_id` | 占位 `null`（仅 approved 后由 `review_log.compute_sign_off_id` 派生） |

### 3.3 审核链记录（经 `ExpertBackedEngineeringValidation.validate` 产出）

七字段（Sprint A 已定义）：
`interface / structure_valid / threshold_verified / expert_signed / verification_status / sign_off_id / validator`。

- `threshold_verified`：`get_interface_thresholds("profile")` 返回 `("D-TH-01",)`，D-TH-01 `mgmt_signed` 才 True；
- `expert_signed`：D-TH-01 `expert_signed` 才 True；
- 闸门：`structure_valid AND threshold_verified AND expert_signed AND engineering_enabled` → `engineering_approved`，否则恒 `pending_verification`；
- **叠加跨模块闸门**：即便上述四项满足，若上游 `w_k` 不可信（wind_pressure 未 approved），profile 计算单元在 `verification_status` 仍强制 `pending_verification` 并登记 `gaps`（见第 6 节 降级传导，pending_verification）。

---

## 4. 规则体系设计（仅定义：公式来源 / 变量关系 / 数据来源；禁止真实参数）

建立 `agents/engineering/rules/profile_rules.py`，承载 profile 的**符号级规则结构**：公式来源、变量关系、数据来源映射；**不保存任何真实工程常数（壁厚 / 截面惯性矩 / 截面模量 / 强度设计值 / 弹性模量 / 挠度限值 / 规范条款号）**。

### 4.1 公式来源（概念级）

- 参考建筑**幕墙/门窗型材杆件在风荷载下的强度与挠度**相关标准与规范（**具体标准号与条款号均由行业专家双签阶段填入，pending_verification**）。
- 采用业界通用的**荷载—内力—应力/挠度校核**结构：在风荷载标准值 `w_k` 作用导出的杆件线荷载下，型材弯曲（及可能的组合）应力 `σ` 与截面模量、截面积相关；并对比强度设计值 `f` 判定安全；同时校核挠度 `δ` 与挠度限值 `δ_lim`。
- 适用性边界（简支/连续/悬臂的系数体系、是否计入温度/地震组合、强度与挠度双控取值规则）由专家在双签时确认，设计态不固化。

### 4.2 变量关系（符号级，无数值）

令：

- `w_k` = 风荷载标准值（来自 wind_pressure，Pa）；
- `series` = 型材系列（来自 D-TH-01，标识，数值 pending）；
- `t` = 壁厚（来自 D-TH-01 型材配置，mm，数值 pending）；
- `I` / `W` / `A` = 截面惯性矩 / 截面模量 / 截面积（来自 D-TH-01 截面属性，数值 pending）；
- `f` = 型材强度设计值（来自 D-TH-01，MPa，数值 pending）；
- `E` = 弹性模量（来自 D-TH-01，MPa，数值 pending）；
- `L` = 杆件跨度/受力长度（来自项目几何，数值 pending）；
- `support` = 支承条件标识（简支/连续/悬臂，来自项目几何）；
- `q` = 杆件线荷载（由 w_k 与分格几何导出，数值 pending）；
- `M` / `N` = 杆件弯矩 / 轴力（目标内力，数值 pending）；
- `σ` = 型材弯曲/组合应力（目标量，MPa）；
- `δ` = 挠度（目标量，mm）；
- `δ_lim` = 挠度限值（来自规范/项目要求，数值 pending）。

关系（符号占位，系数选取规则 pending_verification）：

```
q      = p(w_k, 分格几何)              （杆件线荷载，系数规则 pending_verification）
M, N   = r(q, L, support)              （内力，系数规则 pending_verification）
σ      = M / W + N / A                 （型材应力，截面属性来自 D-TH-01，数值 pending_verification）
强度判定: σ ≤ f                         （f 来自 D-TH-01，数值 pending_verification）
δ      = s(q, L, E, I, support)        （挠度，数值 pending_verification）
挠度判定: δ ≤ δ_lim                     （δ_lim 数值 pending_verification）
```

衍生依赖（仅描述变量间因果，不填数）：

- `σ` 取决于 `M`/`N`（内力）+ `W`/`A`（D-TH-01 截面属性）；
- `δ` 取决于 `q`/`L`/`E`/`I`/`support`；
- `q`/`M`/`N` 取决于 `w_k`（上游 wind_pressure）+ 项目几何；
- `t`/`I`/`W`/`A`/`f`/`E` 取决于 `series`（D-TH-01）；
- `w_k` **不**由本模块推算，只消费 wind_pressure 产出（跨模块耦合，见第 6 节，pending_verification）。

### 4.3 数据来源映射（每个变量 → 哪一层输入）

| 变量 | 数据来源 | 溯源 |
|---|---|---|
| `w_k` | wind_pressure 上游产出（内部依赖 E-TH-01~03，pending_verification） | 随 wind_pressure 的 verification_status |
| `series` / `t` / `I` / `W` / `A` / `f` / `E` | Engineering 阈值 **D-TH-01**（型材配置/截面属性/强度/弹性模量） | `verified`（双签后） |
| `L` / `support` | 项目几何 / Design `dimensions_hint` | `inferred` |
| `q` / `M` / `N` / `σ` / `δ` / `δ_lim` | 由上游 w_k + D-TH-01 + 项目几何推导 | `inferred`/`pending` |

---

## 5. 阈值依赖设计（D-TH-01 角色）

### 5.1 D-TH-01（型材配置）角色绑定

D-TH-01 已在 Sprint A 的 `agents/design/thresholds/verified.json` 占位（映射 Design 候选字段 `frame_series`/`frame_material`），本设计明确其**角色绑定**与**双签验收口径**：

| 阈值 ID | 绑定变量 | 在公式中角色 | 双签验收口径（专家须确认） |
|---|---|---|---|
| **D-TH-01** | `series`（型材系列）、`t`（壁厚）、`I`/`W`/`A`（截面属性）、`f`（强度设计值）、`E`（弹性模量） | 型材强度与挠度校核的取值依据 | 取值与项目所选型材系列、壁厚、截面属性及材质强度一致；单位与量纲在 approved 后自洽 |

- **双签字段要求**（Sprint A 机制）：`verified=true` + `verified_by` + `verified_at` + `expert_verified_by` + `expert_verified_at` 五字段俱全 → `is_fully_verified()=True`。
- **source_ref 要求**：专家填入规范/标准号与条款号（设计态全为 `pending_verification`）。
- **禁止**：AI 代码不得写入 `verified=true`、不得填写 `value`（壁厚/截面属性/强度）、不得伪造签字（由 `check_fabrication.py` + 防编造测试锁死）。
- **未双签后果**：`threshold_verified=False` → `verification_status` 恒 `pending_verification`，`sign_off_id=null`，绝不输出 `engineering_approved`。

### 5.2 审核流程（D-TH-01 双签 + 工程闸门）

- profile 要 `engineering_approved`，须**同时**满足：
  1. 自身阈值 D-TH-01 双签完整（`threshold_verified` + `expert_signed`）；
  2. 上游 `w_k` 可信（wind_pressure `verification_status == engineering_approved` 且 `w_k.value` 非 None）；
  3. `engineering_enabled=true`。
- 任一不满足 → 结论恒 `pending_verification`（计算单元显式登记 `gaps`，不依赖 validator 单接口判定）。

---

## 6. 与 wind_pressure / glass_safety 关系

profile 是 wind_pressure 的**下游消费者**，与 glass_safety **并列**。

### 6.1 数据耦合

- wind_pressure 产出 `w_k`（风荷载标准值）→ 作为 profile 的**型材杆件受荷**计算输入线荷载来源。
- profile 同时消费 Design 侧 D-TH-01（型材配置/截面属性）与项目几何（跨度/支承条件）。
- 耦合通过统一四字段结构 + `threshold_refs` + 上游 `wind_pressure_result` 实现，不新增私有通道。

### 6.2 阈值跨库引用

| 模块 | 依赖的上游产出 | 自身阈值 |
|---|---|---|
| `profile` | `w_k`（来自 wind_pressure） | D-TH-01（型材配置/截面属性，Design 侧） |
| `glass_safety` | `w_k` → 面板受荷 | D-TH-02（玻璃配置，Design 侧） |

- profile **不重复定义**风压阈值（E-TH-01、E-TH-02、E-TH-03），只消费 wind_pressure 的 `w_k`。
- 下游 `verification_status` 独立判定：即使 wind_pressure 已 approved，profile 仍需自身阈值双签 + `engineering_enabled` + `w_k` 可信 才转 approved。

### 6.3 降级传导（wind pending → profile pending）

- 若 wind_pressure `pending_verification`（阈值未签/输入 inferred）→ `w_k` 不可信 → profile 即使自身阈值已签，结论仍须 `pending_verification`（不得基于未验证风压推出"型材达标"）。
- profile 计算单元显式检查 `wind_pressure_result.verification_status`，未 approved 时登记 `gaps: ["w_k: upstream_pending"]` 并强制 pending。
- 跨模块 `gaps` 显式登记上游 pending 项。

### 6.4 Glass 结果不替代 Profile

- glass_safety 计算对象为**玻璃面板**在风压下的强度与挠度；profile 计算对象为**型材杆件**在风压下的强度与挠度。二者物理对象与阈值（D-TH-02 vs D-TH-01）均不同。
- glass_safety 的 `engineering_approved` **不替代** profile 的计算与审核：即便玻璃已审定，型材杆件仍需独立双签 + 自身阈值 + 可信 w_k 才允许 approved。
- 两模块在 `invoke()` 中各自独立走审核链，互不为前置（仅共享上游 `w_k` 的可信态）。

---

## 7. Expert 审核点设计

专家双签阶段须对以下审核点逐一确认（设计态全部 `pending_verification`）：

1. **型材配置取值（D-TH-01）**：与项目所选型材系列、壁厚 `t`、截面属性（`I`/`W`/`A`）、材质强度 `f`、弹性模量 `E` 口径一致。
2. **截面参数适用性**：所选型材系列的截面惯性矩/截面模量/截面积与计算假定一致；非标截面是否在 `gaps` 中显式标注。
3. **强度规则**：所选荷载—内力—应力校核结构（σ = M/W + N/A，σ ≤ f）适用于本项目杆件构造；组合工况（风+重力+温度/地震）是否成立。
4. **挠度规则**：挠度公式（δ = s(q,L,E,I,support)）与挠度限值 `δ_lim` 取值规则适用于本项目（如立柱 L/180、横梁 L/60 等口径由专家双签确认，数值 pending）。
5. **边界条件**：杆件支承条件（简支/连续/悬臂）系数体系适用于本项目分格与连接构造。
6. **风荷载输入合法性**：上游 `w_k` 来自 wind_pressure 且已 approved；未使用 Environment 实时气象直接推算。
7. **输入溯源合规**：型材跨度/支承条件等 `inferred` 字段在签字时已被人工复核或转为 `verified`；不存在用 `inferred` 直接驱动确定性结论。
8. **单位与量纲一致**：Pa、mm、MPa、m、无量纲系数在 approved 后自洽。

审核动作写入 `review_log.jsonl`（append-only，`event_id` 哈希链，`sign_off_id` 在 approved 时派生）。

---

## 8. PDF 展示方案

复用 Phase 3.1 设计就绪报告已确立的 PDF 契约（三态徽标 + `review_chain` 逐接口透出）：

- **三态徽标**：`[已验证]`（engineering_approved）/ `[AI推理·待确认]`（inferred）/ `[待确认]`（pending_verification）按 `verification_status` 渲染。
- **profile 章节内容**：
  - 输入摘要：型材系列/壁厚/截面属性/跨度/支承条件及其溯源标签；
  - 上游荷载：wind_pressure 的 `w_k` 来源与可信状态（随 wind_pressure 章节联动）；
  - 公式来源：荷载—内力—应力/挠度校核结构符号展示 + 规范来源占位（条款号 pending）；
  - 中间变量表：`w_k`/`series`/`t`/`I`/`W`/`A`/`f`/`E`/`M`/`N`/`σ`/`δ`/`δ_lim` 各取值来源（D-TH-01 或 wind_pressure 或 pending）；
  - 审核状态：七字段 `review_chain` 记录透出（接口名/结构合法/阈值校验/专家签字/状态/ `sign_off_id`）；
  - 专家签字区：`verified_by`/`verified_at`/`expert_verified_by`/`expert_verified_at` 占位（未签显示"待行业专家双签"）。
- **防误显**：`verification_status != engineering_approved` 时，绝不渲染任何具体壁厚、截面惯性矩、强度设计值、弹性模量、挠度或"达标"结论；仅显示推导占位与 `pending_verification` 标注。

---

## 9. 测试方案

> 落实 `.ai/tasks/phase3.1_test_plan.md` 四类别；**编码阶段**实施，本阶段仅定方案。所有用例零真实数值。

### 9.1 单元（ProfileCalculator）

| 用例 | 输入 | 期望 |
|---|---|---|
| 阈值缺失降级 | D-TH-01 `value=null` | `verification_status=="pending_verification"`；`intermediate` 各量为 pending 占位；`gaps` 含 D-TH-01 pending |
| 上游 w_k 未签降级 | `wind_pressure_result.verification_status != engineering_approved` | 结论 pending，登记 `gaps: ["w_k: upstream_pending"]`，不伪造 σ/δ 数值 |
| 输入 inferred 降级 | `member_span` 为 inferred | 结论 pending，不伪造应力/挠度 |
| 四字段强制 | 任意 | 输出键集合 ⊇ `REQUIRED_OUTPUT_KEYS` |
| 证据可回写 | 产出对象 | `evidence` 含 `source_ref` 槽位（值 pending）+ 参数来源标识 |
| 验证等级 | 未双签 | 可信等级 Level 0/1，绝不 Level 3 |

### 9.2 集成（EngineeringAgent.invoke 全链路）

- `analyses=["profile"]` → `review_chain` 仅含一条记录，`verification_status` 恒 pending（设计态）；
- `analyses=["wind_pressure","profile"]` → 上游 wind_pressure 的 pending 状态传导至 profile pending（详见第 6 节 降级传导，pending_verification）。

### 9.3 安全（降级/误开/防篡改）

- 阈值未双签 → 该模块及依赖链绝不 `engineering_approved`（一票否决）；
- 测试全程 `engineering_enabled=false`；不得置 true；
- `review_log` append-only + `prev_event_id` 哈希链连续。

### 9.4 防编造（红线锁死）

- 扫描 `agents/engineering/calc/profile.py`：不含未走 `verified.json`/D-TH-01 的硬编码工程常数（壁厚/截面惯性矩/强度设计值/弹性模量）；
- 含业务词（壁厚）行均配对 `pending_verification`，无真实数字；
- `result` 在未 approved 时不含具体壁厚/截面属性/强度/挠度数值。

### 9.5 覆盖率

- backend ≥ 60%（随真实计算补全后 ≥ 70%）；`bash scripts/ci/local_ci.sh` 维持 8/8 全绿、覆盖率不降。

---

## 10. 风险分析

| ID | 风险 | 影响 | 缓解 |
|---|---|---|---|
| R-PF-1 | 型材配置阈值（D-TH-01）长期未双签 | profile 永久 pending | 专家双签流程 + `review_log` 追踪；CI 防编造闸门 |
| R-PF-2 | 误将 Environment 实时气象当作杆件荷载 | 来源错误，结论失真 | 荷载只来自 wind_pressure 的 w_k；代码审查锁死 |
| R-PF-3 | 上游 w_k 不可信却被当作确定输入 | 编造型材达标结论 | 第 6 节 降级传导；计算单元显式检查 w_k 可信态 |
| R-PF-4 | 输入 `inferred` 直接驱动确定性结论 | 编造工程判断 | `field_provenance` 判定：inferred → pending（ADR-2.2.1 第 7 节） |
| R-PF-5 | 跨模块耦合错误传导 | wind 错值污染 profile | 第 6 节 降级传导；下游独立审核 |
| R-PF-6 | PDF 误显"已验证"/具体数值 | 用户误解为已审定结论 | 第 8 节 防误显；状态 != approved 仅显 pending 占位 |
| R-PF-7 | `engineering_enabled` 误开 | 未签阈值被放行 | Sprint A 闸门 + 测试不得置 true + 六门槛门禁 |
| R-PF-8 | 公式系数体系选择不当（强度/挠度双控） | 适用边界错误 | 第 7 节 审核点 3/4 由专家在双签时确认；设计态不固化 |

---

**END**（DESIGN_ONLY，等待主理人审核；本文件不含任何实现代码，未开启 `engineering_enabled`，全参数 `pending_verification`）
