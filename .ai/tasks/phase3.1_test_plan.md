# Phase 3.1 工程智能闭环 — 测试方案设计（phase3.1_test_plan.md）

- **生成**：2026-07-28（Phase 3.1 设计阶段 · 任务4）
- **身份**：BOIP AI 首席工程架构师
- **性质**：**纯测试方案设计，不编写任何测试代码、不开启 `engineering_enabled`**。
- **依据**：
  - `.ai/tasks/phase3.1_engineering_architecture_design.md`（§2 五模块 / §3 审核链 / §4 六门槛）
  - `.ai/tasks/phase3.1_expert_review_process.md`（双签机制 / `is_fully_verified()` 升级 / `review_log.jsonl`）
  - `.ai/decisions/ADR-phase3.1-engineering-calculation.md`（§6 实施约束 / 红线测试）
  - `agents/engineering/agent.py` + `validation.py`（骨架契约，实读）+ `agents/design/threshold_loader.py`（复用）
  - 既有测试：`tests/agents/test_engineering.py`（骨架测试基线，本方案在其上扩展）
- **红线**：任何测试**不得**引入真实工程参数数值；测试仅验证"机制/契约/降级/防编造"，不验证"真实工程结论正确性"（后者属专家签字范畴）。

---

## 0. 测试战略总览

| 测试类别 | 目标 | 验证对象 | 是否可现在写 |
|---|---|---|---|
| 单元测试 | 单模块/单函数行为正确 | 五接口计算、审核链、阈值加载器 | 机制契约可写，数值断言标 pending |
| 集成测试 | 多组件协同链路正确 | `EngineeringAgent.invoke` 全链路 + Design/Environment 数据契约 | 契约可写 |
| 安全测试 | 越权/误开/降级防护 | 阈值未签字降级、enabled 误开、AI 不得填 verified | 防护语义可写 |
| 防编造测试 | 红线锁死 | 未签字参数不进 `engineering_approved`、零硬编码常数 | 红线可写 |

**四类别共同原则**：
1. **测试即契约**：所有测试断言基于本阶段已冻结的设计契约（四字段、审核链记录结构、双签字段、`review_chain`、`field_provenance`/`threshold_refs`）。
2. **pending 默认**：设计态下所有阈值 `value=null` + 双签缺失 → 测试结果**必须**恒为 `pending_verification` / `engineering_approved=False`；断言"工程确认 = 假"。
3. **零真实数值**：测试 fixtures 中的工程参数一律 `None` / `pending_verification`，禁止出现具体风压/壁厚/承载力数字。
4. **不触发 enabled**：所有测试在 `engineering_enabled=false` 下进行；任何测试不得将其置 `true`（误开防护见 §3.2）。

---

## 1. 单元测试（Unit Tests）

> 落点：`tests/agents/test_engineering_calc.py`（新建，编码阶段实施）。
> 复用 `tests/agents/test_engineering.py` 的骨架基线，本文件聚焦"真实计算替换后"的行为。

### 1.1 五接口计算模块

对每个接口（`wind_pressure` / `glass_safety` / `profile` / `hardware` / `installation_risk`）覆盖：

| 用例 | 输入 | 期望断言 |
|---|---|---|
| 缺阈值降级 | `verified.json` 全 `value=null`、双签缺失 | `verification_status == "pending_verification"`；`result` 为推导过程占位而非工程结论；`gaps` 含该接口 pending 登记 |
| 空输入不崩 | `payload = {}` | 不抛异常；`success=True`（Agent 级）；模块级 `verification_status == "pending_verification"` |
| 四字段强制 | 任意输入 | 输出键集合 `== REQUIRED_OUTPUT_KEYS`（`result/confidence/evidence/verification_status`） |
| 证据可回写 | 接口产出对象 | `evidence` 含 `source_ref` 槽位（规范条款，值 `pending_verification`）+ 参数来源标识（verified/inferred/measured） |
| 验证等级 | 未双签 | 顶层可信等级 `Level 0`（inferred），绝不 `Level 3` |

**边界用例**（每个接口）：
- 输入字段类型错误（如高度为字符串）→ 降级 `pending` + `gaps` 登记，不崩。
- 输入缺失关键字段（如 `wind_pressure` 缺建筑高度）→ 该模块 `unavailable` 或 `pending`，不伪造。
- 超大/超小数值（设计不强制校验，但须保证不溢出、不抛异常）。

### 1.2 ExpertBackedEngineeringValidation 审核链（结构 + 双签）

| 用例 | 输入 | 期望断言 |
|---|---|---|
| 结构校验通过 | 四字段齐备 payload | `structure_valid == True`，`missing_keys == []` |
| 结构校验失败 | 缺 `confidence`/`evidence` | `structure_valid == False`，`missing_keys` 准确列出缺失键 |
| 阈值未签字 | `verified.json` 项 `is_fully_verified()==False` | `threshold_verified == False` |
| 专家未签字 | 无 `sign_off_id` | `expert_signed == False` |
| 双签齐全 | `threshold_verified && expert_signed` | `verification_status == "engineering_approved"`，`sign_off_id` 非空 |
| 单签缺 | 仅阈值签 / 仅专家签 | `verification_status == "pending_verification"`（一票否决） |
| 返回记录结构 | 任意接口 | 含 `interface/structure_valid/threshold_verified/expert_signed/verification_status/sign_off_id/validator` 七字段 |
| validator 可注入 | 自定义实现 | `EngineeringAgent(validator=...)` 生效（复用既有 `test_custom_validator_can_be_injected` 范式） |

### 1.3 阈值加载器（Engineering 侧）

| 用例 | 输入 | 期望断言 |
|---|---|---|
| 文件缺失降级 | `agents/engineering/thresholds/verified.json` 不存在 | `load_verified_thresholds()` 返回 `{}`（等价全 pending），零行为变化 |
| `is_fully_verified` 旧语义 | 仅 `verified` + 单签 | `False`（主理人签字缺失） |
| `is_fully_verified` 双签语义 | `verified + verified_by + verified_at + expert_verified_by + expert_verified_at` 全齐 | `True`（升级后） |
| `is_fully_verified` 局部缺失 | 缺 `expert_verified_at` | `False` |
| `build_threshold_refs` | — | 返回 Engineering 侧阈值 ID ↔ 字段映射槽位（仅引用，数值仍 pending） |
| 双签字段不被 AI 写入 | 任意加载路径 | 加载器/计算代码**不得**出现 `verified=true` 或伪造签字赋值（由防编造测试 §4.2 锁死） |

---

## 2. 集成测试（Integration Tests）

> 落点：`tests/agents/test_engineering_integration.py`（新建）。

### 2.1 EngineeringAgent.invoke 全链路

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 全五接口默认 | `input_data={}` | `analyses` 覆盖五接口；`review_chain` 长度 5；顶层 `pending_verification == True`；`stage == "engineering_skeleton"`（设计态）|
| 子集接口 | `analyses=["wind_pressure","glass_safety"]` | 仅执行子集；`review_chain` 长度 2（pending_verification） |
| 未知接口拒绝 | `analyses=["wind_pressure","bad"]` | `success=False`，`error.code == "ENGINEERING_UNKNOWN_INTERFACE"`，`analyses == {}` |
| 全 pending 聚合 | 设计态全阈值未签 | `review_chain` 任一接口 `verification_status != "engineering_approved"` → 顶层恒 `pending_verification` |
| 双签齐备端到端（编码后模拟） | fixture 注入双签 `verified.json` + 注入 `ExpertBackedEngineeringValidation` | 对应接口 `engineering_approved`；`review_chain` 记录含 `sign_off_id`；顶层 `verification_status` 反映已批准接口集合 |

### 2.2 与 Design Agent 数据契约

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 候选传参 | 编排器传 `design_candidate`（frame_material/glass_type/dimensions_hint/estimated_cost_tier）| Engineering 能读取且不改 Design 输出 |
| 溯源对齐 | `field_provenance` 含 `verified/inferred` | Engineering 复用 `threshold_loader.resolve_field_provenance` 判定每个输入可信等级；`inferred` 输入 → 依赖模块 `pending` |
| pending 传导 | Design 候选字段 `inferred`（未签字）| 依赖该输入的 Engineering 模块结论 `pending_verification`，不伪造"基于未验证设计的可信工程结论" |
| 阈值跨库引用 | Engineering 读 Design 侧 D-TH-01/D-TH-02 | `threshold_refs` 返回跨库引用槽位，不重复定义 |
| 契约冻结 | 改 Design 侧字段名 | 集成测试断言失败（契约漂移预警，R-E5 缓解）|

### 2.3 与 Environment / PDF 契约

| 用例 | 场景 | 期望断言 |
|---|---|---|
| Environment 实测接入 | `Environment` 输出 `measured` 工况 | Engineering `installation_risk` 消费 `measured` 标 `measured`，非 `inferred` |
| PDF 消费点 | `ReportGenerator` 读 `analyses + review_chain + verification_status` | 三态徽标渲染 `[已验证]`/`[AI推理·待确认]`/`[待确认]`；`review_chain` 逐接口透出（接口名/阈值校验/专家签字/状态）|
| 统一可信等级章节 | PDF 合并 Level 0–3 | Engineering 等级与 Design/Environment 同源说明段 |

---

## 3. 安全测试（Security Tests）

### 3.1 阈值未签字降级防护

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 缺签字禁止报送 | 任一关键阈值未双签 | 该模块及依赖链 `verification_status == "pending_verification"`，**绝不** `engineering_approved` |
| 一票否决 | 仅 1/6 阈值签字 | 顶层 `pending_verification == True`；已签阈值不得"让未签模块"转正 |
| 误标拦截 | 测试尝试将未签模块标 `engineering_approved` | `ExpertBackedEngineeringValidation` 因 `threshold_verified=False` 拒绝，状态回落 pending |

### 3.2 engineering_enabled 误开防护

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 配置缺省 | `config.yaml engineering.enabled=false` | `config.engineering_enabled is False`；loader 不注册 engineering 条目；不进编排管道 |
| 测试不得置 true | 任意测试代码 | 全量测试运行后 `config.engineering_enabled` 仍 `False`（CI 不自动开，R-E6 缓解）|
| 六门槛门禁 | 仅满足部分门槛 | `engineering_enabled` 保持 `false`，计算链降级 pending；仅主理人授权 + 全门槛满足方可开（§4 门槛由人工/CI 外部校验，不单测绕过）|

### 3.3 审核日志防篡改

| 用例 | 场景 | 期望断言 |
|---|---|---|
| append-only | 写入 `review_log.jsonl` | 新事件追加；不存在"修改历史 event"路径 |
| 哈希链连续 | `prev_event_id` 串联 | 任一事件 `prev_event_id` 指向已存在事件；断链检测告警 |
| 签字不可伪造 | 代码尝试写 `verified_by` | 仅审核流程写入；计算/加载代码路径无赋值点（静态扫描 + 防编造测试锁死）|

---

## 4. 防编造测试（Anti-Fabrication Tests）— 红线锁死

> 本类别为 R-E1/R-E2 的**硬性闸门**，CI 必须全绿，否则禁止开启 `engineering_enabled`。

### 4.1 未签字参数不进 engineering_approved

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 零签字零批准 | 设计态全 `value=null` | 全量 `review_chain` `verification_status != "engineering_approved"`；顶层 `pending_verification == True` |
| 数值不出现 | 任意未签模块输出 | `result` 字段不得含具体工程数值（风压 kN/m²、壁厚 mm、承载力 N）；仅推导过程占位 + `pending_verification` 标注 |
| 静态扫描 | 扫描 `agents/engineering/**/*.py` | 不存在"未走 `verified.json` 直接 hardcode 工程常数"的赋值（配合 `scripts/lint/check_fabrication.py` 业务词 + 真实数字规则）|

### 4.2 零硬编码工程常数

| 用例 | 场景 | 期望断言 |
|---|---|---|
| 常量源唯一 | 代码审查 + 单测 | 所有工程常数（基本风压/体型系数/壁厚/玻璃许用应力/五金承载力/腐蚀等级）取值**仅**来自 `verified.json`/参数库；代码中无字面量常数 |
| AI 不自推 | `wind_pressure` 等计算 | 系数全部取自 `verified.json`（pending 态下为 `None`）；不得用训练记忆补值（由 prompt 约束 + 输出断言双重锁死）|
| 禁止自造结论 | 未签字模块 | 不得输出"安全/不安全""达标/不达标"等确定性结论；仅 "AI 推理·待确认" |

### 4.3 fabrication 扫描器联动

- 复用在位 `scripts/lint/check_fabrication.py` 规则：**含业务词（风压/楼层/壁厚/评分权重/防腐等级等）+ 含真实数字 + 不含 `pending_verification`** → 标记。
- 本阶段设计文档与测试 fixtures 主动规避：所有含业务词行均配对 `pending_verification`，且**不写任何真实数值**。
- CI 门：`check_fabrication.py` 对 `agents/engineering/` + `.ai/` 设计文档零告警（继承 Phase 2.2 惯例）。

---

## 5. 测试执行与门禁

### 5.1 运行方式（编码阶段）

```bash
# 后端（agents 包）
BOIP/backend/.venv/bin/python -m pytest tests/agents -q          # 含 test_engineering*.py
BOIP/backend/.venv/bin/python -m pytest tests/agents/test_engineering_calc.py -q
BOIP/backend/.venv/bin/python -m pytest tests/agents/test_engineering_integration.py -q

# 防编造静态扫描
python scripts/lint/check_fabrication.py agents/engineering .ai
```

### 5.2 覆盖率基线（继承 Phase 2.2）

- backend ≥ 60%（Engineering 模块目标随真实计算补全后 ≥ 70%）。
- 前端 ≥ 50%（PDF 审核链渲染组件需配套测试）。
- `bash scripts/ci/local_ci.sh` 维持 **8/8 全绿、覆盖率不降**。

### 5.3 开门禁（engineering_enabled 六门槛映射测试）

| 门槛 | 对应测试 |
|---|---|
| 1. 阈值双签 | §1.3 `is_fully_verified` 双签语义 + §3.1 降级防护 |
| 2. Vision 调优 | （属 Vision 范畴，本测试方案不覆盖，列观察项）|
| 3. 五接口计算+单测/集成 | §1.1 + §2.1 |
| 4. 审核链端到端 | §1.2 + §2.1 双签齐备用例 |
| 5. CI 8/8 + 覆盖率 | §5.1/§5.2 |
| 6. 主理人授权 | 人工/外部，不在自动化测试范围 |

> 仅当 §1–§4 全绿 + §5.2 达标 + 主理人授权（门槛6）后，方可置 `engineering.enabled=true`。

---

## 6. 待主理人审核项（测试维度）

1. **ID 一致性**：ADR 用 `E-TH-wp-01`（风压）而专家流程用 `E-TH-01~06`，编码前须统一阈值 ID 命名（建议统一为 `E-TH-01~06`，ADR 同步修订）（pending_verification）。
2. **测试 fixtures 真实性**：确认所有测试零真实数值，符合红线。
3. **六门槛门禁自动化程度**：门槛 2（Vision）/ 6（主理人授权）是否需额外 CI 钩子，或纯人工确认。
4. **防编造扫描范围**：是否将 `agents/engineering/` 纳入 `check_fabrication.py` 强制扫描（建议：是）。

---

**END**（本文件为测试方案设计，不含测试代码实现；编码须在主理人授权 Phase 3.1 后启动）
