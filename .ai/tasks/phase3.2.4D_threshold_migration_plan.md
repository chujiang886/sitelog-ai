# BOIP Phase 3.2 Sprint 3.2.4-D — 真实阈值接入实施方案（迁移 / 验证 / 录入 / 回滚）

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：进入真实阈值接入（3.2.4 实施）前的「实施方案」设计——**本阶段不填写真实工程参数、不修改 verified.json 真实 value、不设置 verified=true、不开 engineering_enabled、不输出 engineering_approved**，全部保持 `pending_verification`。本文档只把"未来 verified.json 真实化时如何迁移、如何校验 source_ref、如何录入、如何回滚"定义成可执行步骤，待主理人书面授权后方可落地。

---

## 0. 目标与范围

**目标**：把既有 `schema_version=1` 的占位阈值库（E-TH-01~06 / D-TH-01~05）安全迁移到支持真实化的结构（`schema_version=2`），并定义 source_ref validator、真实录入流程与回滚机制，使 3.2.4 实施（须单独书面授权、仍 `engineering_enabled=false` 直到 3.2.5 灰度）有章可循、可审计、可回滚。

**红线（全程守约）**：① 不填真实工程阈值 ② 不改 verified.json 真实 value ③ 不置 verified=true ④ 不开 engineering_enabled ⑤ 不输出 engineering_approved。所有示例数值一律 `pending_verification` 占位。

**范围**：
- 工程侧 `agents/engineering/thresholds/verified.json`（E-TH-01~06）
- 设计侧 `agents/design/thresholds/verified.json`（D-TH-01~05）
- 复用：3.2.4-A `thresholds/schema.py`（ThresholdStatus / ThresholdSourceRef / ThresholdGovernanceView）、`threshold_loader.governance_status`、3.2.5-B 门禁 G1~G6、3.2.5-C 录入接口契约与权限矩阵。

> 本文档为「实施方案设计」，不落地代码、不修改任何文件、不新增测试。真实落库动作属于 3.2.4 实施（须单独书面授权）。

---

## 1. 当前 E-TH / D-TH 状态（迁移基线）

### 1.1 工程侧 E-TH（schema_version=1，六条）

| 阈值 ID | param | value | unit | verified | 双签位现状 | source_ref 现状 |
|---|---|---|---|---|---|---|
| E-TH-01 | 基本风压 | null | Pa | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |
| E-TH-02 | 体型系数 | null | pending_verification | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |
| E-TH-03 | 粗糙度类别 | null | pending_verification | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |
| E-TH-04 | 五金承载力 | null | N | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |
| E-TH-05 | 腐蚀等级 | null | pending_verification | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |
| E-TH-06 | 安装风险矩阵 | null | pending_verification | false | 双签位齐备（全 null） | 自由文本占位 pending_verification |

**结论**：E-TH 已具备 `expert_verified_by / expert_verified_at` 字段位，治理升级只需填值 + 加 `threshold_status` + 结构化 `source_ref`，无需改字段结构骨架。

### 1.2 设计侧 D-TH（schema_version=1，五条）

| 阈值 ID | param | value | unit | verified | 双签位现状 | source_ref 现状 |
|---|---|---|---|---|---|---|
| D-TH-01 | 型材壁厚/系列 | null | mm | false | **仅主理人单签位**（`verified_by/at`），**缺专家签字位** | 自由文本占位 pending_verification |
| D-TH-02 | 玻璃厚度/配置 | null | mm | false | **仅主理人单签位**，缺专家签字位 | 自由文本占位 pending_verification |
| D-TH-03 | 开口尺寸阈值 | null | pending_verification | false | 仅主理人单签位，缺专家签字位 | 自由文本占位 pending_verification |
| D-TH-04 | 成本档位映射 | null | pending_verification | false | 仅主理人单签位，缺专家签字位 | 自由文本占位 pending_verification |
| D-TH-05 | 三方案选型权重 | null | pending_verification | false | 仅主理人单签位，缺专家签字位 | 自由文本占位 pending_verification |

**关键缺口**：D-TH-01~05 比 E-TH 少 `expert_verified_by / expert_verified_at` 两个字段位。若保持单签，则 `is_fully_verified` 对 D-TH 永远为 `False`，`profile` / `glass_safety` 接口无法 `engineering_approved`（见 §6 与独立决策文档）。该缺口的处置路径由 `phase3.2.4D_dth_double_sign_decision.md` 给出推荐。

### 1.3 与四签状态机 / 接口映射对照

- `INTERFACE_THRESHOLD_MAP`：`wind_pressure → E-TH-01 与 E-TH-03`、`glass_safety → D-TH-02`、`profile → D-TH-01`、`hardware → E-TH-04`、`installation_risk → E-TH-05 与 E-TH-06`（pending_verification）。
- 首个灰度接口仍为 `wind_pressure`（3.2.5-A 锁定），其 E-TH-01~03 为 Engineering 侧可独立双签，不依赖 D-TH 决策即可转正（pending_verification）。

---

## 2. 迁移步骤（schema_version 1 → 2）

> 下列为「迁移脚本/过程」设计；实施时须在主理人书面授权 + `engineering_enabled=false` 约束下进行，每步产出一条 `review_log` 审计事件。

| 步骤 | 动作 | 输入 | 输出 | 门禁 |
|---|---|---|---|---|
| M1 | 快照基线 | 现有 verified.json（v1） | `snapshots/verified.<hash>.v1.json`（内容哈希） | 快照失败则中止 |
| M2 | 顶层 `schema_version` 1 → 2 | v1 文件 | v2 头 | 不兼容版本号 → 拒绝并降级（零行为变化） |
| M3 | 每条阈值补 `threshold_status=draft` | v1 单条 | 加 `threshold_status` 字段 | draft 缺省降级（3.2.4-A `from_raw`） |
| M4 | 每条阈值补 `version=1.0` | v1 单条 | 加 `version` 字段 | 未声明 → 拒绝转正（附录 B.1-6） |
| M5 | `source_ref` 自由文本 → 结构化对象 | 自由文本 | `source_ref{standard,clause,edition,url,retrieved_at,hash}` | 完整性校验（任务3） |
| M6 | D-TH 按决策补 `expert_verified_*` 字段位（或保持单签，见 §6） | D-TH 单条 | 结构对齐 | 取决于 D-TH 决策 |
| M7 | 写入 `review_log action=threshold_migrated` | 迁移完成 | append-only 事件 | 链指针连续 |
| M8 | 跑门禁 B.1 + CI（3.2.5-B G3） | 迁移后文件 | 全绿方可合入 | 任一红 → 回滚（§5） |

**零破坏原则**：M2~M4 中任何字段缺失均按 3.2.4-A 既有 `from_raw` 降级为最保守态，绝不抛错中断加载；`verified` 布尔镜像保留，`mgmt_signed / expert_signed / is_fully_verified` 语义零变化。

---

## 3. 字段升级方案

### 3.1 顶层字段

| 字段 | v1 | v2 | 说明 |
|---|---|---|---|
| `schema_version` | 1（整数） | 2（整数） | 结构变更标记 |
| `note` | 自由文本 | 自由文本（更新说明） | 仅注释 |
| `thresholds` | dict | dict（结构升级） | 见 §3.2 |

### 3.2 单条阈值字段

| 字段 | v1 | v2 | 必填条件（转正时） |
|---|---|---|---|
| `param` | 中文名 | 中文名 + `param_code`（标准术语编码占位） | 建议补 |
| `value` | null | 真实数值（实施时由专家填，本阶段 null） | verified 态必填 |
| `unit` | 字符串 | 受控枚举（Pa / N / mm / 无量纲） | verified 态必填 |
| `verified` | bool | bool（镜像 `threshold_status==verified`） | — |
| `verified_by` / `verified_at` | 主理人位（null） | 角色标识符 + UTC ISO8601 | verified 态必填 |
| `expert_verified_by` / `expert_verified_at` | E-TH 有位 / D-TH 缺位 | 统一补齐（见 §6） | verified 态必填 |
| `source_ref` | 自由文本 | 结构化对象（见 §4） | verified 态必填完整 |
| `threshold_status` | 无 | draft / review / verified / deprecated | 新增 |
| `version` | 无 | 语义化 `MAJOR.MINOR` | 新增，必填 |
| `applies_to` / `applies_to_scheme` | 数组 | 与 `INTERFACE_THRESHOLD_MAP` 双向校验 | 校验悬空引用 |

### 3.3 向后兼容

- v1 文件无 `threshold_status` → `from_raw` 降级 `draft`；
- v1 `source_ref` 自由文本 → `ThresholdSourceRef.from_raw` 落入 `standard`，`is_complete()` 因缺 `clause` 返回 `False` → 治理态不完整 → 门禁拦截（符合预期，强制转正前补结构化）；
- 旧 `verified=false` 全部条目在 v2 仍 `threshold_status=draft`，无任何条目自动转正。

---

## 4. 任务3：source_ref 验证设计（validator）

### 4.1 目标数据结构（v2 扩展）

在 3.2.4-A `ThresholdSourceRef`（standard / clause / edition / url / retrieved_at）基础上，新增 `hash` 字段用于**引用不可变性校验**：

```json
"source_ref": {
  "standard": "待专家填规范代号 pending_verification",
  "clause": "待专家填条款号 pending_verification",
  "edition": "待专家填版本年份 pending_verification",
  "url": "待专家填可复核链接 pending_verification",
  "retrieved_at": null,
  "hash": "待专家填入引用源内容摘要 pending_verification"
}
```

### 4.2 validator 检查项

设计 `validate_source_ref(ref) -> (ok, reason)`，逐项校验：

| 检查项 | 字段 | 规则 | 失败原因 |
|---|---|---|---|
| C1 标准号完整 | `standard` | 非空且非 `pending_verification` 占位 | `SOURCE_REF_STANDARD_MISSING` |
| C2 条款号完整 | `clause` | 非空且非占位 | `SOURCE_REF_CLAUSE_MISSING` |
| C3 版本合规 | `edition` | 非空且为 4 位年份格式或显式版本标识 | `SOURCE_REF_EDITION_INVALID` |
| C4 链接可达 | `url` | 非空且为 http(s) 可公开复核链接，禁止私有短链/内网不可达 | `SOURCE_REF_URL_INVALID` |
| C5 内容哈希 | `hash` | 与 `url` 指向文档内容摘要一致（实施时由脚本计算并比对） | `SOURCE_REF_HASH_MISMATCH` |
| C6 引用完整性 | 组合 | C1 + C2 满足即 `is_complete()`；C3~C5 为增强校验（增强态） | `SOURCE_REF_INCOMPLETE` |

**与既有治理衔接**：C1+C2 即 3.2.4-A `ThresholdSourceRef.is_complete()` 语义；C3~C5 为 v2 新增增强层，由迁移步骤 M5 在真实化时填充，本阶段不填真实值。

**安全约束**：`hash` 一律由内容派生（sha256 摘要），禁止手写；`url` 必须可复核，防止"引用一个不存在的条款"骗过门禁（3.2.4 附录 B.1-3 升级）。

---

## 5. 回滚方案（迁移与真实化双用）

> 原则同 3.2.4 §7：**阈值库只读快照 + 审核链不可篡改**，回滚即"恢复上一可信快照 + 追加 deprecated 事件"，绝不物理删除。

- **R1 快照**：M1 生成 `snapshots/verified.<hash>.v1.json`；每次真实化提交追加新快照 `.<hash>.v2.<ts>.json`。
- **R2 回滚触发**：规范废止 / 数值错误 / 标准版本过期 / 主理人驳回 / CI 门禁变红。
- **R3 回滚动作**：目标阈值 `threshold_status=deprecated`，新数值以新 `version` 另起 `review → verified`，旧版保留审计痕（append-only）。
- **R4 快照恢复**：`git checkout` 历史版本或恢复快照哈希，`review_log` 不受影响（仅追加 deprecated 事件）。
- **R5 CI 保护**：回滚后必须重新通过 B.1 + G1~G6 方可合入。
- **本阶段不执行任何回滚**，仅定义机制。

---

## 6. 与 D-TH 双签决策的关系（详见独立文档）

D-TH-01~05 缺专家签字位是迁移 M6 的关键分支：
- **若采用方案 A（补专家双签）**：M6 为 D-TH 补 `expert_verified_by / expert_verified_at` 字段位，与 E-TH 同构，迁移后 `profile` / `glass_safety` 接口具备转正前提；
- **若采用方案 B（保持单签）**：M6 不动 D-TH 结构，`validation.py` 须对复用 D-TH 的接口放宽双签要求（破坏统一语义，不推荐）。

推荐与判定见 `phase3.2.4D_dth_double_sign_decision.md`。迁移脚本须读取该决策结果再执行 M6。

---

## 7. 迁移后准入闸门（衔接 3.2.5-B G1~G6）

迁移完成 ≠ 可启用。真实化后仍需经 `can_enable_engineering()` 六项门禁全绿（G1 阈值治理 / G2 双签 / G3 CI / G4 审核链 / G5 回滚就绪 / G6 授权）且主理人显式置 `engineering_enabled=true`（3.2.5 实施，须单独书面授权）方可输出 `engineering_approved`。本阶段**不开启**任何门禁外部条件。

---

**本阶段交付边界**：本文档为真实阈值接入的「实施方案设计」，未修改任何代码、未修改 verified.json、未新增测试、未开启 engineering_enabled，全部阈值保持 pending_verification。待主理人审核 + 单独书面授权后，方可进入 3.2.4 实施（verified.json 真实化）与 3.2.5 实施（engineering_enabled 开启灰度）。
