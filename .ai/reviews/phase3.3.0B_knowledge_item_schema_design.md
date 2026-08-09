# BOIP Phase 3.3.0-B / 3.3.0-C — Knowledge Item Schema Design（知识资产中间层设计 · 增强版）

- **生成日期**：2026-08-01
- **增强日期**：2026-08-01（Phase 3.3.0-C KnowledgeItem Schema Enhancement Review 补强）
- **身份**：BOIP AI Chief Architect
- **任务**：KnowledgeItem 标准模型 / 中间层（3.3.0-B 初版 + 3.3.0-C 长期演化增强）
- **性质**：**纯架构设计，零代码、零开发、不修改工程计算代码、不开发同步代码**；仅产出架构文档并更新 `roadmap_v3.md`
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V3）、`.ai/roadmap_v3.md`、`.ai/reviews/phase3.3.0_obsidian_integration_architecture.md`、`agents/engineering/knowledge/spec_sources.json`、`agents/engineering/knowledge/experts.json`、`agents/engineering/thresholds/verified.json`
- **衔接定位**：3.3.0 已设计 Obsidian↔BOIP 的采集入口与 Vault 七目录 + frontmatter 六字段；3.3.0-B 在其间补充**知识资产中间层 KnowledgeItem 标准模型**作为中间表示；3.3.0-C 在此基础上增强**长期演化能力**——新增 `knowledge_type`（治理差异）、`parent_knowledge_id`（知识谱系），并拆分 `Engineering_Verified / Engineering_Approved` 双态以对齐 G1-G6 + G6 授权框架。

---

## 0. 设计目标与边界

Phase 3.3 已进入「Engineering Knowledge Activation」。3.3.1/3.3.2 已建立 `spec_sources.json`、`experts.json` 容器与 C1-C6 / SoD 校验；3.3.0 已设计 Obsidian 侧采集架构；3.3.0-B 已定义 KnowledgeItem 11 字段 + 六态生命周期。

**3.3.0-C 增强目标**：让 KnowledgeItem 具备**长期演化能力**，解决初版两个缺口：
- 类型治理缺失：不同知识（规范/意见/案例/经验/规则/阈值候选）共用同一套字段，但治理闸门与消费权限不同，需显式区分。
- 谱系缺失：知识存在「旧→新→派生」的演化关系，初版无溯源链，导致派生规则无法级联约束、撤销无法定位继任。
- 核准边界模糊：初版 `Engineering_Verified` 同时隐含「技术就绪」与「主理人授权」，与 G1-G6 + G6 框架耦合不清，本版拆分为两态。

**边界铁律**：
- 本阶段仅架构设计，**不写任何同步/解析代码、不新增 `.py`、不改 `agents/` 工程计算逻辑**。
- 不录入真实工程参数；不修改 `verified.json`；不开启 `engineering_enabled`；不输出 `engineering_approved`。

---

## 1. KnowledgeItem Schema（增强版，13 字段）

标准模型 13 字段，作为中间层唯一契约对象（相对 3.3.0-B 的 11 字段，新增 `knowledge_type` 与 `parent_knowledge_id`）。

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `knowledge_id` | string | 全局唯一，建议 `KI-` + sha256 前缀 | 中间层主键，去重依据 |
| `knowledge_type` | enum | `spec / expert_opinion / case / experience / rule / threshold_candidate` | **3.3.0-C 新增**；治理差异见 §1.1 |
| `parent_knowledge_id` | string\|null | 引用另一 `KnowledgeItem.knowledge_id` 或 `pending_verification` | **3.3.0-C 新增**；知识谱系/溯源链，见 §1.2 |
| `title` | string | 非空 | 知识条目标题 |
| `content` | string | 非空（抽取的正文/结构化摘要） | 不含真实数值时可标 `pending_verification` |
| `source` | string | 引用 `spec_sources.source_id` 或 `pending_verification` | ↔ 3.3.0 frontmatter `source` |
| `author` | string | 引用 `experts.expert_id` 或 `pending_verification` | ↔ 3.3.0 frontmatter `author` |
| `domain` | string | 计算域标识（如 `wind_pressure`）或 `pending_verification` | ↔ 3.3.0 frontmatter `domain` |
| `content_hash` | string | sha256（笔记正文 + frontmatter 摘要） | 去重与变更检测；禁止手写 |
| `validation_status` | enum | 七态（§2）：`Captured / Pending_Verification / Source_Verified / Expert_Verified / Engineering_Verified / Engineering_Approved / Deprecated` | 生命周期态 |
| `linked_entities` | array<string> | 字母标识符（如 `E-TH-01`）或空 | ↔ 3.3.0 frontmatter `linked_threshold`，仅引用不承载值 |
| `created_at` | datetime(ISO8601) | 首次捕获时间 | 由采集流程写入 |
| `updated_at` | datetime(ISO8601) | 末次状态变更时间 | 每次升格/降级更新 |

**辅助元数据（保留 3.3.0 confidence 语义，不进主键契约）**：`confidence`（枚举 `unverified / low / medium / high / verified`，禁手写数字），作为 `validation_status` 的辅助信号，仅在 Expert 审核通过后升 `verified`。

---

### 1.1 knowledge_type 治理差异（任务1）

不同 `knowledge_type` 的治理闸门、落盘目标、是否承载数值、消费权限差异显著。

| type | BOIP 落点 | 谁可写 | 是否承载数值 | 升格闸门 | 与规范冲突时 | 消费权限 |
|---|---|---|---|---|---|---|
| `spec` | `spec_sources.json` | 主理人/审核链（须 C1-C6 校验） | 否（仅引用条款号，value 仍 null） | `Source_Verified` 起 | **最高权威**，覆盖其他 | 工程 AI 引用（inert 直至激活） |
| `expert_opinion` | `experts.json` | 对应 `expert_id` | 否 | `Expert_Verified`（双签 SoD） | 让位 `spec` | 咨询性；规范缺位时作临时依据 |
| `case` | `cases`（02-Cases） | 任何人经审核 | 否（仅实证证据） | `Source_Verified` | 让位 `spec` | 阈值录入证据，不得直设值 |
| `experience` | Obsidian `04-Experience` | 个人 | 否 | **不自动升格** | 不具工程效力 | 不被工程计算消费 |
| `rule` | `03-Engineering-Rules`（派生） | 工程审核方 | 可承载派生约束，但阈值 value 仍 null | `Engineering_Verified` | 引用 `spec` 为准 | 激活态引用；须 `parent` 溯源 |
| `threshold_candidate` | `verified.json`（仅引用） | 录入申请人 | 候选 value（pending_verification） | `Engineering_Approved` 才转正 | 让位 `spec` | 转正前 inert |

**治理要点**：
- `experience` 是谱系源头，不入工程消费；`spec` / `expert_opinion` / `case` 是经审核的正式知识；`rule` / `threshold_candidate` 是派生/候选，须强约束溯源（见 §1.2）。
- 仅 `threshold_candidate` 允许携带「候选数值」，且必须标 `pending_verification`，直至 `Engineering_Approved` 才经 `ThresholdIntakeWorkflow` 转正写入 `verified.json` 的 `value`（属 3.3.4，本设计不执行）。
- `spec` 在权威链顶端：当 `expert_opinion` / `case` / `rule` 与 `spec` 冲突，以 `spec` 为准；`rule` 须显式引用其依赖的 `spec` 的 `knowledge_id` 作为 `parent`。

---

### 1.2 parent_knowledge_id 知识谱系（任务2）

定义知识的「旧知识 → 新知识 → 派生规则」演化链，使派生与撤销可溯源、可级联。

```
旧知识 (parent, 如 spec 旧版)
   │ (修订/补充 → 生成新 KnowledgeItem)
   ▼
新知识 (child, 引用 parent_knowledge_id = 旧知识 KI-xxx)
   │ (经工程审核方综合多条知识 → 派生)
   ▼
派生规则 (rule / threshold_candidate, 引用多条 parent)
```

**谱系字段约束**：
- `parent_knowledge_id` 为可空；`experience` / 首版 `spec` 等源头知识可空（或填 `pending_verification` 占位）。
- 派生型（`rule` / `threshold_candidate`）**必须**至少引用一个 `parent`，否则映射闸门拒绝升格。
- `parent` 必须存在（指向已落盘的 `knowledge_id`）；不可指向自身，禁止成环（采集流程做有向无环图校验）。

**谱系不变量**：
- 级联闸门：派生规则 (`rule` / `threshold_candidate`) 的 `validation_status` **不得超过其最弱 parent 的状态**（如任一 parent 仍为 `Source_Verified`，派生规则不得越过 `Source_Verified`）。
- 撤销连续：某 KnowledgeItem 进入 `Deprecated` 时，须置 `successor_knowledge_id`（下一版图腾）或显式标记 `orphan`，确保引用方可平滑迁移；`parent` 被 `Deprecated` 不自动降级 child，但 child 升格闸门须重新评估。
- 审计保留：`parent_knowledge_id` 一旦写入**不可篡改**（仅追加新版本，旧链保留），支撑事后溯源与回滚。

**Obsidian 映射**：frontmatter 新增 `upstream`（wikilink 或 `KI-xxx` 列表）→ `parent_knowledge_id`；多父以数组表示。

---

## 2. 生命周期设计（增强版，七态）

原六态在末态 `Engineering_Verified` 处拆分为 `Engineering_Verified`（工程技术验证）与 `Engineering_Approved`（G1-G6 + G6 授权），形成七态，与既有 G1-G6 门禁及 `release_approvals.jsonl` 框架精确对齐。

```
Captured
   │ (AI 抽取 frontmatter → KnowledgeItem)
   ▼
Pending_Verification
   │ (C1-C6 校验通过)
   ▼
Source_Verified            ↔ spec_sources.source_status = verified_source
   │ (专家 sign_scope 覆盖 + 双签 SoD)
   ▼
Expert_Verified           ↔ experts 双签落 review_log（verified_by / expert_verified_by）
   │ (工程审核方确认 G1-G6 技术项就绪，release_precheck 技术维度通过)
   ▼
Engineering_Verified      ↔ 工程技术就绪（未授权）；对应 release_precheck 技术项全绿
   │ (G1-G6 全绿 + G6 书面授权 + release_approvals.jsonl 落盘)
   ▼
Engineering_Approved      ↔ 正式核准，可触发真实工程计算（属 3.3.6 激活态）
   │ (被新版本取代 / 撤销)
   ▼
Deprecated                ↔ spec_sources.source_status = deprecated；须置 successor
```

### 2.1 状态转移规则
- `Captured → Pending_Verification`：AI 整理完成，生成 `content_hash`，暂存 `05-Pending-Verification`。
- `Pending_Verification → Source_Verified`：复用 `validate_source_ref` 语义做 C1-C6 校验；任一不满足退回。
- `Source_Verified → Expert_Verified`：由 `author` 对应专家 + 主理人双签（SoD：`authorized_by` 须另选 `rollback_owner`）；满足 G2。
- `Expert_Verified → Engineering_Verified`：工程审核方（工程专家）确认该知识在 G1-G6 **技术门禁**层面已就绪——即 `release_precheck` 的技术维度（阈值治理 G1 / 双签 G2 / CI G3 / 审核链 G4 / 回滚就绪 G5）通过。**注意：此态仍无主理人 G6 授权，不触发真实计算。**
- `Engineering_Verified → Engineering_Approved`：G1-G6 **全绿** + **G6 书面授权**（主理人创建 `release_approvals.jsonl` 条目）同时满足；满足 G6 与 SoD（`authorized_by` ≠ `rollback_owner`）。
- 任意态 → `Deprecated`：来源失效或撤销，须置 `successor_knowledge_id` 或标 `orphan`，保留审计。
- **不变量**：`Engineering_Approved` 之前，KnowledgeItem 不得向 `verified.json` 写入任何真实 `value`；`threshold_candidate` 的候选 value 在 `Engineering_Approved` 前恒为 `pending_verification`。

### 2.2 与初版差异说明
初版 `Engineering_Verified` 同时隐含「技术就绪」与「主理人授权」，本版明确拆分：
- `Engineering_Verified` = **专家/工程验证**（技术就绪，未经 G6 授权）；
- `Engineering_Approved` = **G1-G6 全绿 + G6 授权**（正式核准）。
二者之间的唯一闸门是 **G6 主理人书面授权**，与 Phase 3.2 审核闭环的 G6 门禁完全对齐。

---

## 3. Obsidian 映射（增强版）

定义 3.3.0 的 frontmatter → KnowledgeItem 13 字段的映射规则（单向采集，不反向覆盖原笔记）。

| Obsidian frontmatter | KnowledgeItem 字段 | 映射说明 |
|---|---|---|
| `source` | `source` | 直映射；须为 `spec_sources.source_id` 或 `pending_verification` |
| `author` | `author` | 直映射；须为 `experts.expert_id` 或 `pending_verification` |
| `domain` | `domain` | 直映射；计算域标识 |
| `confidence` | `validation_status`(辅助) | 等级枚举转入辅助元数据；不入主键契约 |
| `verification_status` | `validation_status` | 三态直映射（draft→Pending_Verification / verified_source→Source_Verified / deprecated→Deprecated） |
| `linked_threshold` | `linked_entities` | 字母标识符（如 `E-TH-01`）转入数组；仅引用 |
| `knowledge_type` | `knowledge_type` | **3.3.0-C 新增**；frontmatter 新增枚举，决定治理闸门与落点 |
| `upstream` | `parent_knowledge_id` | **3.3.0-C 新增**；wikilink / `KI-xxx` 列表 → 单父或数组 |
| （笔记路径/标题） | `knowledge_id` / `title` | `knowledge_id = KI-` + 正文 sha256 前缀；`title` 取笔记 H1 或文件名 |
| （笔记正文） | `content` | AI 抽取结构化摘要；缺失标 `pending_verification` |
| （自动计算） | `content_hash` / `created_at` / `updated_at` | sha256 与 ISO8601 时间戳，由采集流程写入，禁止手写 |

**映射闸门**：`verification_status=draft` 或 `source=pending_verification` 的笔记，映射后停留在 `Pending_Verification`；`rule` / `threshold_candidate` 缺 `parent_knowledge_id` 时拒绝越过 `Source_Verified`。

---

## 4. BOIP 映射（增强版）

定义 KnowledgeItem → BOIP 四类容器的落盘映射；按 `knowledge_type` 路由，明确「仅元数据、不写阈值 value、不改 verified.json」。

| knowledge_type + 条件 | BOIP 落盘目标 | 落盘内容 | 红线约束 |
|---|---|---|---|
| `spec`（`>= Source_Verified` 且 `source` 已登记） | `spec_sources.json` | 来源元数据（standard/edition/url/clause） | `source_status=verified_source`；不写条款数值 |
| `expert_opinion`（`>= Expert_Verified` 且 `author` 已登记） | `experts.json` | 专家资料（domain/qualification_ref/sign_scope/sod_role） | 不写真实姓名/证书号（仍 `pending_verification` 占位） |
| `case`（`>= Source_Verified`） | `cases`（02-Cases 落点） | 案例元数据 + rationale | 仅作阈值录入证据，不改阈值 value |
| `rule`（`>= Engineering_Verified`，须 `parent` 齐全） | `03-Engineering-Rules` | 派生规则 + 溯源引用 | 派生约束 value 仍 null；须引用 `spec` parent |
| `threshold_candidate`（`linked_entities` 含 `E-TH-xx`） | `verified.json`（仅引用） | 阈值 `source_ref` 指向本 KnowledgeItem 的 `source` | **绝不写 `value`**；候选 value 仍 `pending_verification` |
| 任意类型（含 `experience`） | 不落盘至工程容器 | — | `experience` 仅留 Obsidian，不被工程消费 |

**不变量（强约束）**：
- 本中间层映射**只读消费** `verified.json` 的结构（建 `source_ref` 引用），**不修改、不写入真实阈值数值**。
- 所有真实参数（含 `experts` 真实身份、`spec_sources` 真实条款）仍保持 `pending_verification`，由人工经 3.3.3~3.3.5 正式流程登记。

---

## 5. 知识权限边界（增强版）

明确三个等级，对应 3.3.0 的三层知识架构与治理闸门；本版将末级触发前置精确对齐 `Engineering_Approved`。

### 5.1 Personal Knowledge（个人知识）
- **范围**：Obsidian `04-Experience` / `05-Pending-Verification` 中未升格内容；`validation_status ∈ {Captured, Pending_Verification}`；含 `experience` 类型。
- **消费权限**：**不被 BOIP 工程计算消费**；仅作个人参考与待核实线索。
- **出口**：经映射 + 升格后，方可进入下一等级。

### 5.2 Engineering Knowledge（工程知识）
- **范围**：`spec_sources` / `experts` / `cases` 已登记元数据 + `verified.json` 阈值引用；`validation_status ∈ {Source_Verified, Expert_Verified, Engineering_Verified}`。
- **消费权限**：受 C1-C6 / SoD 约束；在 `engineering_enabled=false` 下引用即 **inert**，不触发真实计算；仅工程 AI 可在激活态引用。
- **出口**：经 G1-G6 技术全绿升 `Engineering_Verified`，再经 G6 授权升下一等级。

### 5.3 Engineering Approved Knowledge（工程核准知识）
- **范围**：`validation_status = Engineering_Approved`；已通过 G1-G6 门禁 + G6 书面授权 + `release_approvals.jsonl` 落盘。
- **消费权限**：在激活态（3.3.6 后）可触发真实工程计算；仍受 `approved_monitor.jsonl` 监控与回滚约束。
- **边界铁律**：本等级**不归本 Sprint 设计落地**，仅在权限边界中定义其触发前置（G1-G6 + G6）；真实核准动作属 3.3.5/3.3.6 范畴。

### 5.4 权限跃迁闸门

| 跃迁 | 前置条件 | 闸门 |
|---|---|---|
| Personal → Engineering | Source_Verified + Expert_Verified | C1-C6 + SoD 双签 |
| Engineering → Approved | Engineering_Verified → Engineering_Approved | G1-G6 全绿 + G6 授权（release_approvals.jsonl） |
| 任意 → Deprecated | 来源失效/撤销 | 保留审计，置 successor，拒绝被新引用 |

---

## 6. 红线与治理不变式（本 Sprint 串接 3.3.0-B + 3.3.0-C）

1. **不录入真实工程参数**：所有 `content`/`source`/`author`/`linked_entities` 取值保持 `pending_verification`；`threshold_candidate` 候选 value 亦标 `pending_verification`；真实条款经 3.3.3~3.3.4 人工流程登记。
2. **不修改 `verified.json`**：本设计仅定义 KnowledgeItem 对 `verified.json` 的**引用映射**，明确不写真实 `value`。
3. **不开 `engineering_enabled`**：全局仍 `false`；引用即 inert。
4. **不输出 `engineering_approved`**：全 `pending_verification`，无 approved 落盘。
5. **不开发同步代码**：本产出仅为 Markdown 架构文档；3.3.0 的 `KnowledgeItemExtractor` / `SourceRefBinder` 仍停留在设计态。
6. **防编造/硬编码扫描**：本设计文档持续 0 命中（数值以枚举/字母标识符表达）。

---

## 7. 下一步

- 本增强版为 3.3.0 的 MCP 同步拓扑补足**可演化**中间层契约（13 字段 + 七态 + 谱系 + 类型治理）；建议后续 3.3.7 Connector 实现时，直接以增强版 KnowledgeItem 作为 `KnowledgeItemExtractor` 的输出类型与 `SourceRefBinder` 的输入类型。
- 进入 3.3.3（真实专家 onboarding，填充 `experts.json`）与 3.3.4（真实阈值录入，消费 `threshold_candidate` 转正）时，可复用本设计的 Schema、类型治理与谱系作为人工操作手册。
- 红线全程守约，按 3.3.0-C 指令「完成后停止」——不开发、不录真实数据、未开启 `engineering_enabled`。

**END**
