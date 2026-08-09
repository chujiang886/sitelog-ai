# BOIP Phase 3.2 Sprint 3.2.4 — 工程阈值治理架构设计

> 身份：BOIP AI 工程治理负责人
> 阶段性质：**阈值治理体系准备（Governance Preparation）**，非真实参数填写、非开启 engineering_enabled、非输出 engineering_approved。
> 红线（全程守约）：不修改 verified.json 真实 `value`、不设置 `verified=true`、不开启 `engineering_enabled`、不填写真实专家姓名、不填写真实规范数值；全部保持 `pending_verification`。
> 本设计文档只建立"阈值治理体系"的规范、字段、流程与门禁，**不落地任何代码改动、不修改任何 verified.json、不新增测试文件**。

---

## 0. 治理目标与范围

目标：在真实审核闭环（3.2.5 enabled 开启灰度）之前，先把"如何把一条工程阈值从占位安全地转正为已验证"的规则、字段、生命周期、版本与回滚全部定义清楚，使后续 `verified.json` 真实化（3.2.4 实施）与 `engineering_enabled` 开启（3.2.5）有章可循、可审计、可回滚。

范围：
- 工程侧阈值库 `agents/engineering/thresholds/verified.json`（E-TH-01 至 E-TH-06）；
- 设计侧阈值库 `agents/design/thresholds/verified.json`（D-TH-01 至 D-TH-05，注：当前仅主理人单签，治理需统一双签语义）；
- 审核链日志 `agents/engineering/review_log.jsonl`（append-only 不可篡改）；
- 双签判定 `agents/engineering/threshold_loader.py`（`mgmt_signed` / `expert_signed` / `is_fully_verified`）；
- 四签状态机 `agents/engineering/validation.py`（`ExpertBackedEngineeringValidation`）。

所有数值在本阶段**一律 pending_verification**，本设计不出现任何真实工程取值。

---

## 1. 当前 E-TH-01 至 E-TH-06 结构分析

### 1.1 现状字段（schema_version=1）

| 字段 | 当前形态 | 治理缺口 |
|---|---|---|
| `param` | 中文参数名（如"基本风压"） | 缺失标准术语编码（如 GB/T 编号占位） |
| `value` | 全 `null` | 真实化需求：需承载数值 + 精度 + 容差 |
| `unit` | 部分写死（Pa / N / mm），部分写 `pending_verification` | 治理需求：单位统一为枚举，禁止字符串自由填写 |
| `verified` | 全 `false` | 需由"布尔"升级为"状态机值"（见 §2） |
| `verified_by` / `verified_at` | 全 `null`（主理人核准位） | 需补充角色与签署凭据引用 |
| `expert_verified_by` / `expert_verified_at` | 全 `null`（行业专家签字位） | 需补充角色与签署凭据引用 |
| `source_ref` | 占位文本"待行业专家签字填入规范/标准号 pending_verification" | 需结构化：标准号 + 条款 + 版本 + 链接 |
| `applies_to` | 数组（如 `["wind_pressure"]`） | 治理需求：与 `INTERFACE_THRESHOLD_MAP` 双向校验 |

**关键发现**：Design 侧 D-TH-01 至 D-TH-05 **仅有主理人单签**（`verified_by` / `verified_at`），**无专家签字位**；而工程侧 E-TH 已具备双签位。治理方案必须明确：D-TH 在真实化时是否补专家签字位，否则 `is_fully_verified` 对 D-TH 永远为 `False`，型材/玻璃接口无法转正（见 §5）。

### 1.2 与四签状态机的映射

`INTERFACE_THRESHOLD_MAP` 已将分析接口映射到阈值 ID：
- `wind_pressure` → E-TH-01、E-TH-02、E-TH-03
- `glass_safety` → D-TH-02
- `profile` → D-TH-01
- `hardware` → E-TH-04
- `installation_risk` → E-TH-05、E-TH-06

治理要求：每条阈值在 `verified.json` 中的 `applies_to` 必须与 `INTERFACE_THRESHOLD_MAP` 一致，CI 门禁（见附录B）须校验该双向映射无悬空引用。

---

## 2. 阈值生命周期设计

将 `verified` 布尔升级为四态生命周期枚举 `threshold_status`，用于表达一条阈值的真实化进度：

```
        draft ──(提交专家评审)──▶ review
          │                        │
          │ (驳回/撤回)             │ (双签完成 + 主理人核准)
          ▼                        ▼
       deprecated ◀──────────── verified
                                    │
                                    │ (规范修订 / 发现错误 / 标准作废)
                                    ▼
                               deprecated
```

| 状态 | 含义 | 进入条件 | 退出条件 |
|---|---|---|---|
| `draft` | 占位/草拟，数值可空或待填 | 初始或回滚产物 | 主理人发起评审 |
| `review` | 专家评审中，已填数值待双签 | 主理人提交 + `source_ref` 齐备 | 双签完成 + 核准 → verified；或驳回 → draft/deprecated |
| `verified` | 双签完整 + 主理人核准，可用于工程审核 | 四签（structure/threshold/expert/enabled 中的前三 + 主理人动作）齐备 | 规范修订/错误/作废 → deprecated |
| `deprecated` | 已废止，禁止用于工程审核 | 显式废止或新版本取代 | 不可恢复，仅留审计痕 |

**与现有字段的兼容**：保留 `verified`（布尔）作为 `threshold_status == "verified"` 的冗余镜像，不破坏 `threshold_loader.mgmt_signed` 既有判定；新增 `threshold_status` 与 `version`（见 §6）。本设计阶段**不修改**任何代码，仅规范未来实施。

---

## 3. source_ref 设计

`source_ref` 从自由文本升级为结构化对象（占位，不填真实值）：

```json
"source_ref": {
  "standard": "待专家填规范代号 pending_verification",
  "clause": "待专家填条款号 pending_verification",
  "edition": "待专家填版本年份 pending_verification",
  "url": "待专家填可复核链接 pending_verification",
  "retrieved_at": null
}
```

规范：
- `standard` 必须为标准代号占位或真实代号（真实化阶段由专家填入，非本阶段）；
- 缺失 `standard` 或 `clause` 视为 `source_ref` 不完整 → 门禁拦截（见附录B）；
- `url` 必须可公开复核（内部知识库链接亦可），禁止填写不可达/私域短链；
- 本阶段所有 `source_ref` 字段保持 `pending_verification` 占位，不写真实规范数值。

---

## 4. 专家审核流程

与项目既有 `review_log.jsonl` 审核链对齐，新增"阈值治理"动作类型：

```
专家提交(submit) → 主理人审核(review_approve) → 专家复核(expert_recheck)
→ verified → 可用于 engineering(release)
```

每个动作在 `review_log.jsonl` 追加一条 `append-only` 记录，含 `event_id`（内容哈希）、`threshold_id`、`action`、`signer_role`、`signer`（仅角色标识符，如 principal-001 / expert-001，禁止真实姓名）、`timestamp`、`source_ref`、`prev_event_id`（链指针）。

角色定义：
- `submitter`：发起阈值草拟/数值填写的工程师（系统账号或角色标识符）；
- `principal`：主理人，负责 `verified_by` / `verified_at`（主理人核准位）；
- `expert`：行业专家，负责 `expert_verified_by` / `expert_verified_at`（专家签字位）。

本阶段**不执行**任何真实签署，仅规范流程与字段。

---

## 5. 双签字段规范

统一工程侧 E-TH 与设计侧 D-TH 的双签语义：

| 字段 | 角色 | 必填条件 |
|---|---|---|
| `verified` | — | 镜像 `threshold_status == "verified"` |
| `verified_by` | 主理人 | verified 状态时必填（角色标识符，非真实姓名） |
| `verified_at` | 主理人 | verified 状态时必填（UTC ISO8601） |
| `expert_verified_by` | 行业专家 | verified 状态时必填（角色标识符，非真实姓名） |
| `expert_verified_at` | 行业专家 | verified 状态时必填（UTC ISO8601） |
| `threshold_status` | — | 四态枚举（见 §2） |
| `version` | — | 语义化版本（见 §6） |

**D-TH 治理决策（待主理人确认）**：D-TH-01 至 D-TH-05 当前仅主理人单签位。治理方案给出两条路径，由主理人验收时定夺：
- 路径一：D-TH 补 `expert_verified_by` / `expert_verified_at` 字段，与 E-TH 同构双签（推荐，保证型材/玻璃接口可统一转正）；
- 路径二：保留 D-TH 单签，但 `validation.py` 对复用 D-TH 的接口（profile/glass_safety）放宽双签要求（不推荐，破坏统一语义）。

本设计默认按路径一规划，真实实施待主理人书面授权。

---

## 6. 版本管理设计

`verified.json` 升级字段：
- 顶层 `schema_version`：由整数递增（当前 1 → 未来 2），标记结构变更；
- 每条阈值新增 `version`：语义化版本 `MAJOR.MINOR`（如 `1.0`），数值修订升 MINOR，规范/语义修订升 MAJOR；
- 历史版本不覆盖：修订时保留上一版 `version` 于 `superseded_by` 指针或独立 `history` 段（append-only 思想，见 §7）；
- 加载器（`threshold_loader`）按 `version` 解析，`schema_version` 不兼容时拒绝加载并降级为全 `pending_verification`（零行为变化）。

---

## 7. 回滚方案

原则：**阈值库只读快照 + 审核链不可篡改**，回滚即"恢复上一可信快照 + 追加一条 deprecated 事件"，绝不物理删除历史。

- 回滚触发：规范废止、数值错误、标准版本过期、主理人驳回；
- 回滚动作：将目标阈值 `threshold_status` 置 `deprecated`，新数值以新 `version` 另起一条 `review` → `verified`，旧版保留审计痕；
- 快照机制（建议，非本阶段实施）：每次 `verified.json` 提交生成内容哈希快照存于 `snapshots/` 目录，回滚时 `git checkout` 历史版本或恢复快照哈希；
- CI 保护：回滚后必须重新通过附录B门禁（非法 verified / 缺 source_ref / 缺双签 / 版本冲突）方可合入；
- 本阶段不执行任何回滚，仅定义机制。

---

## 附录A（任务2融合）：verified.json 治理方案（未来字段，仅设计不填值）

未来 `verified.json` 单条阈值目标形态（占位，真实值由专家双签阶段填入）：

| 目标字段 | 说明 | 本阶段值 |
|---|---|---|
| `threshold_id` | 唯一键（E-TH-xx / D-TH-xx） | 保持现有键 |
| `value` | 真实工程数值 | `null`（pending_verification） |
| `unit` | 单位枚举（Pa / N / mm / 无量纲） | 禁止自由字符串 |
| `source_ref` | 结构化规范引用（见 §3） | 占位 pending_verification |
| `version` | 语义化版本 | 初始 `1.0` |
| `verified_by` | 主理人角色标识符 | `null` |
| `verified_at` | 主理人核准时间 | `null` |
| `expert_verified_by` | 行业专家角色标识符 | `null` |
| `expert_verified_at` | 专家签字时间 | `null` |
| `threshold_status` | 四态枚举（见 §2） | `draft` |

设计约束：仅设计，不填写真实工程值、不设置 `verified=true`、不填真实专家姓名/规范数值。

---

## 附录B（任务4融合）：安全门禁设计

### B.1 进入 `verified=true` 的门禁（阈值转正条件）

一条阈值允许 `verified=true`（即 `threshold_status=verified`）**当且仅当**全部满足：
1. `value` 非空且为数值/受控枚举；
2. `unit` 为受控单位枚举；
3. `source_ref.standard` 与 `source_ref.clause` 均非空（结构完整）；
4. `verified_by` 与 `verified_at` 均非空（主理人核准）；
5. `expert_verified_by` 与 `expert_verified_at` 均非空（行业专家签字）；
6. `version` 已声明；
7. 该阈值 `applies_to` 与 `INTERFACE_THRESHOLD_MAP` 无悬空引用；
8. `review_log.jsonl` 中存在该 `threshold_id` 的完整 `submit → review_approve → expert_recheck → verified` 链路，且 `event_id` 与 `prev_event_id` 链可回溯；
9. CI 门禁（非法 verified / 缺 source_ref / 缺双签 / 版本冲突）全绿。

一票否决：任一不满足 → 强制 `pending_verification`，禁止转正。

### B.2 进入 `engineering_enabled=true` 的门禁（系统放行条件）

系统允许 `engineering_enabled=true`（即四签状态机的第四个签点亮，可输出 `engineering_approved`）**当且仅当**全部满足：
1. 目标分析接口所需的全部阈值（`get_interface_thresholds`）均已 `verified=true` 且双签完整（即 `is_fully_verified` 为真）；
2. 该接口 `structure_valid`（四字段齐备）；
3. 主理人已书面授权开启（独立授权，不与 A/B 系列混同，见历史 Sprint 约定）；
4. 灰度开关已在 `config.yaml` 显式置 `true`，且经 CI 配置校验；
5. 回滚快照机制就绪；
6. 审计日志（`review_log.jsonl`）写入"系统放行"事件。

**本阶段红线**：`engineering_enabled` 在 `config.yaml` 中恒为 `false`，门禁 B.2 仅作规范定义，不开启。

---

## 附录C（任务5融合）：阈值治理测试方案（未来实施，非本阶段执行）

未来在 3.2.4 实施 / 3.2.5 灰度时落地的测试覆盖设计：

1. **非法 verified**：`verified=true` 但缺 `source_ref` / 缺双签 / `value=null` → 门禁必须拒绝，强制 `pending_verification`；
2. **缺 source_ref**：`source_ref.standard` 或 `source_ref.clause` 为空 → 加载器标记不完整，双签判定为 `False`；
3. **缺双签**：仅主理人单签（缺专家签字）或反之 → `is_fully_verified` 必须为 `False`；重点覆盖 D-TH 单签现状的回归；
4. **版本冲突**：`schema_version` 不兼容 / 同 `threshold_id` 多 `version` 并存无 `superseded_by` → 加载器拒绝并降级为全 `pending_verification`；
5. **回滚**：构造 deprecated 事件 + 新 version 记录，验证旧版保留审计痕、新版 `verified` 生效、回滚后门禁仍全绿。

本阶段**不新增测试文件**，测试方案仅作为 3.2.4 实施的验收清单。

---

## 8. 风险与开放问题

- **D-TH 双签缺口**（高）：D-TH-01 至 D-TH-05 现状仅主理人单签，若不补专家签字位，`profile` / `glass_safety` 接口永远无法 `engineering_approved`。路径选择待主理人确认（§5）。
- **单位枚举缺失**（中）：E-TH-02 / E-TH-03 / E-TH-05 / E-TH-06 的 `unit` 当前为 `pending_verification`，需治理为受控枚举。
- **source_ref 自由文本**（中）：当前为占位长文本，结构化改造需向后兼容解析。
- **授权耦合**（高）：`engineering_enabled=true` 须独立书面授权，不可与 A/B 系列（结果抽象 / 报告章节）混同。

---

**本阶段交付边界**：本文档为纯治理设计，未修改任何代码、未修改任何 verified.json、未新增测试、未开启 engineering_enabled，全部阈值保持 pending_verification。待主理人审核通过后，方可进入 3.2.4 实施（verified.json 真实化，须单独书面授权）与 3.2.5（engineering_enabled 开启灰度，须单独书面授权）。
