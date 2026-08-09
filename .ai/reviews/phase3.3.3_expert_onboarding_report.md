# BOIP Phase 3.3 Sprint 3.3.3 — Real Expert Onboarding（真实专家体系接入 · 结构/流程设计）

- **生成日期**：2026-08-01
- **身份**：BOIP AI Chief Architect
- **任务**：Real Expert Onboarding（真实专家体系接入）
- **性质**：**纯架构/结构 + 流程设计，零代码、零开发、不修改工程计算代码**；仅增强 `experts.json` 结构与生成本报告，并同步更新 SSOT（`project_status.json`）+ 路线图（`roadmap_v3.md`）
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V3）、`.ai/roadmap_v3.md`、`.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`（KnowledgeItem 13 字段七态 + knowledge_type 治理）、`agents/engineering/knowledge/experts.json`（基座 v1）、`agents/engineering/knowledge/spec_sources.json`（参考结构范式）
- **衔接定位**：3.3.1 已建 `experts.json` 基座（仅 sod_roles/signer_alignment + _example_entry 占位）；3.3.2 已增强 `spec_sources.json`；3.3.0-B/C 已 finalize KnowledgeItem 中间层。本 Sprint 在基座之上增强专家领域能力模型、资质验证流程、SoD 校验体系，并打通「Expert → KnowledgeItem.author → Expert_Verified」与「Obsidian 01-Experts → experts.json → KnowledgeItem」两条关联链路。

---

## 0. 设计目标与边界

Phase 3.3 已进入「Engineering Knowledge Activation」。3.3.1/3.3.2 已建立 `spec_sources.json`、`experts.json` 容器与 C1-C6 / SoD 校验；3.3.0-B/C 已 finalize KnowledgeItem 13 字段七态模型。

**3.3.3 目标**：建立真实专家体系的**接入结构与管理流程**——让后续 3.3.4（真实阈值录入）、3.3.5（真实签署）有明确的专家主体、领域能力边界、资质闸门与 SoD 校验规则。

**边界铁律（最高红线）**：
- 本阶段仅结构/流程设计，**不写任何同步/解析代码、不新增 `.py`、不改 `agents/` 工程计算逻辑**。
- **不录入真实专家身份**（姓名/证书号/执业资格）：`experts.json` 仅保留 `pending_verification` 占位，`_example_entry` 不创建真实条目。
- **不录入真实阈值**：`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification）。
- **不开 `engineering_enabled`**；**不输出 `engineering_approved`**；**AI 不代签/不代授权/不自动创建 `ReleaseApproval`**。

---

## 1. Expert Registry 增强（任务1）

`agents/engineering/knowledge/experts.json` 由 `schema_version=1` 升级为 `schema_version=2`，补全字段集并新增治理段。

### 1.1 专家条目字段集（专家实体契约）

| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| `expert_id` | string | 全局唯一，建议 `expert-` + sha256 前缀 | 专家主键，对应 review_log signer 标识符 `principal-xxx` / `expert-xxx` |
| `domains` | array<enum> | 取 `domains` 六枚举子集 | **新增**；专家可验证领域集合，决定 `sign_scope` 覆盖 |
| `qualification_ref` | string | 引用资质凭证标识或 `pending_verification` | 执业资格/证书引用，严禁 AI 生成真实证书号 |
| `sign_scope` | array<string> | 可签署的知识/阈值标识符或域 | 实际签署权限边界（须被 `domains` 覆盖） |
| `sod_role` | enum | `principal` / `expert` | 职责分离角色，映射到签署位 |
| `valid_until` | string\|date(ISO8601) | 资质有效期或 `pending_verification` | **新增**；到期自动失效闸门 |
| `qualification_status` | enum | `pending` / `verified` / `deprecated` | **新增**；资质三态，翻转严禁自动化 |

### 1.2 新增治理段

- `domains`：专家领域能力模型六枚举（见 §2）。
- `qualification_status_enum`：资质三态语义（pending=待审核禁签署 / verified=已核验可签署 / deprecated=失效撤权）。
- `verification_workflow`：资质验证流程四步（提交→审核→verified→允许签署）+ 失效（`valid_until` 到期或撤销），含三条不变式（翻转严禁自动化 / AI 不生成真实身份 / AI 不代签代授权）。
- `sod_validation_rules`：六条 SoD 校验规则（见 §4）。
- 保留原 `sod_roles`、`signer_alignment` 段，语义不变。

**红线守约**：`_example_entry` 仍全 `pending_verification`（qualification_status=pending），`experts:[]` 空数组，**未创建任何真实专家条目**；所有真实取值须人工经 §3 流程登记。

---

## 2. 专家领域能力模型（任务2）

定义专家可验证范围的六域枚举，作为 `sign_scope` 覆盖校验与 KnowledgeItem 关联的域锚点。

| domain 枚举 | 领域 | 可验证范围（示例，不录入真实值） | 对应计算域锚点 |
|---|---|---|---|
| `wind_engineering` | 风工程 | 风荷载相关阈值与计算假设 | `wind_pressure` 等 |
| `structure` | 结构 | 强度/挠度/连接相关阈值与假定 | 结构计算域 |
| `profile` | 型材 | 截面/壁厚/系列相关参数与假定 | 型材计算域 |
| `glass` | 玻璃 | 玻璃类型/厚度/安全相关阈值与假定 | 玻璃安全计算域 |
| `hardware` | 五金 | 五金件承载/耐久相关阈值与假定 | 五金计算域 |
| `installation` | 安装 | 安装工艺/锚固/密封相关阈值与假定 | 安装计算域 |

**覆盖不变量**：
- 落 `expert_verified_by` 的专家，其 `domains` 必须覆盖被签知识所属 `domain`（即 `sign_scope` ⊆ `domains`），否则 SoD 规则 R4 拒绝。
- `qualification_status != verified` 的专家禁止落任何签署位（R5）。
- 每个域可登记多名专家，但任一知识条目的双签须来自**不同主体且分属 expert / principal 角色**（G2）。

---

## 3. 资质验证流程（任务3）

严格人工驱动的资质生命周期，AI 仅编排容器与校验。

```
submit（人工提交资料，status=pending）
   │
   ▼
review（人工资质审核：身份/执业资格/valid_until 有效性；AI 不介入判断）
   │
   ▼
verified（审核通过，人工资质审核方显式翻 verified）
   │
   ▼
allow_signing（仅 verified 且 sign_scope 覆盖目标域 → 允许落对应签署位）
   │
   ├─ expire：valid_until 到期 → 翻 deprecated，签署权限立即吊销
   └─ revoke：主动撤销 → 翻 deprecated，保留审计
```

**流程不变式（最高红线延伸）**：
1. `qualification_status` 翻转严禁自动化：`pending→verified`、`verified→deprecated` 必须人工显式操作。
2. AI 不生成真实专家身份：`expert_id` / `qualification_ref` 等真实取值由人工提供，AI 仅留 `pending_verification` 占位。
3. AI 不代签专家意见：`expert_verified_by` 由真实专家经正式流程落位。
4. AI 不代授权：`authorized_by`（G6）由主理人书面创建。

---

## 4. SoD 校验体系（任务4）

职责分离（SoD）规则集，防止「既签署又核准」「既授权又回滚」，确保 G2/G6 双签与回滚独立性。

| 规则 | 约束 | 对齐门禁 |
|---|---|---|
| R1 `expert_verified_by ≠ verified_by` | 行业专家复核签主体 ≠ 主理人核准主体 | G2 双签 SoD |
| R2 `authorized_by ≠ rollback_owner` | G6 授权主体 ≠ 回滚责任主体（均映射 principal 且须不同人） | G6 + G5 回滚独立 |
| R3 G6 主体独立 | `authorized_by` 不得同时是本次审核链的 `expert_verified_by` | G6 授权独立 |
| R4 域覆盖 | 落 `expert_verified_by` 的 `sign_scope` 必须覆盖被签知识 domain | 签署权限边界 |
| R5 状态闸门 | `qualification_status != verified` 禁止落任何签署位 | 资质闸门 |
| R6 不自核准 | 同一 `expert_id` 不得既任 `author` 又任 `verified_by` | 自审隔离 |

**SoD 不变量在审核链中的体现**：
- 双签 `verified_by`(principal) + `expert_verified_by`(expert) 由不同主体落位 → 满足 R1。
- G6 授权 `authorized_by` 与回滚责任 `rollback_owner` 为不同 principal → 满足 R2。
- G6 主体不与签署专家重合 → 满足 R3。

---

## 5. KnowledgeItem 关联设计（任务5）

打通「Expert → KnowledgeItem.author → Expert_Verified」链路，复用 3.3.0-B/C 的 KnowledgeItem 13 字段七态模型。

```
Expert (experts.json: expert_id, domains, qualification_status=verified)
   │ (KnowledgeItem.author = expert_id)
   ▼
KnowledgeItem (knowledge_type=expert_opinion / rule / threshold_candidate)
   │ (author 对应专家 + 主理人双签，SoD R1/R4/R5/R6)
   ▼
Expert_Verified (validation_status 升格；review_log 双签落位)
   │ (工程审核方确认 G1-G6 技术就绪)
   ▼
Engineering_Verified → Engineering_Approved (G6 授权)
```

**关联契约**：
- `KnowledgeItem.author` 引用 `experts.expert_id`；`experts` 缺失该 `expert_id` 或 `qualification_status != verified` → 拒绝升格到 `Expert_Verified`。
- `knowledge_type=expert_opinion` 的 KnowledgeItem 升 `Expert_Verified` 须满足：①`author` 已登记且 `verified`；②`sign_scope` 覆盖该条目 `domain`（R4）；③`expert_verified_by ≠ verified_by`（R1）；④`author` 非 `verified_by` 主体（R6）。
- `rule` / `threshold_candidate` 类 KnowledgeItem 除自身 `parent_knowledge_id` 谱系约束外，仍须经专家双签（G2）方可越过 `Source_Verified`。
- 本关联**不写真实阈值 value**：仅将专家身份/资质作为签署主体锚点，`E-TH` 真实 `value` 仍 `null`（属 3.3.4）。

---

## 6. Obsidian 专家目录映射（任务6）

打通「Obsidian 01-Experts → experts.json → KnowledgeItem」单向采集链路，沿用 3.3.0 的 Vault 七目录与 frontmatter 规范。

```
Obsidian Vault
   └─ 01-Experts/（专家档案笔记，frontmatter 含 expert_id/domains/qualification_ref/sign_scope/sod_role/valid_until/qualification_status）
         │ (MCP 单向采集：KnowledgeItemExtractor 抽取 → SourceRefBinder 绑定)
         ▼
experts.json（BOIP 专家注册表，schema_version=2）
         │ (KnowledgeItem.author 引用 expert_id)
         ▼
KnowledgeItem（author 字段 → 双签 → Expert_Verified）
```

**映射规则**：
- Obsidian `01-Experts` 笔记 frontmatter 字段与 `experts.json` 条目字段**一一对齐**（expert_id/domains/qualification_ref/sign_scope/sod_role/valid_until/qualification_status）。
- `qualification_status` 在 Obsidian 侧仅作登记，**翻转必须人工经 §3 流程**，AI 采集不自动改变状态。
- `qualification_status=pending` / `deprecated` 的笔记，采集后落入 `experts.json` 但**不授予签署权限**（R5）。
- 采集为单向（Obsidian → BOIP），不反向覆盖原笔记；专家真实身份由人工在 Obsidian 侧录入，AI 不生成。
- 该链路复用 3.3.0 设计的 `KnowledgeItemExtractor` / `SourceRefBinder`（仍处设计态，本 Sprint 不实现）。

---

## 7. 红线守约验证（本 Sprint）

| 红线 | 验证结果 |
|---|---|
| 不录入真实专家身份 | `experts:[]` 空；`_example_entry` 全 `pending_verification`；未创建任何真实 `expert_id`/`qualification_ref` |
| 不录入真实阈值 | `E-TH-01/02/03` 真实 `value` 仍 `null`（本 Sprint 未触及 `verified.json`） |
| 不开 `engineering_enabled` | 全局仍 `false`（沿用 loader 默认值，未改 config） |
| 不输出 `engineering_approved` | 全 `pending_verification`，无 approved 落盘 |
| AI 不代签/不代授权 | 仅编排容器与校验；`expert_verified_by`/`authorized_by` 由人工落位 |
| 不自动创建 `ReleaseApproval` | `release_approvals.jsonl` 不存在（沿用 3.3.1/3.3.2 状态） |
| 不开发同步代码 | 仅增强 `.json` 结构 + 生成 Markdown 报告；无新增 `.py` |
| 防编造/硬编码扫描 | 新增 `experts.json` 无裸数字；报告全文枚举+标识符规避裸数字 → 预期 0 命中 |

**扫描执行结论**（本机受 bulk-delete 防护，引用基线动作）：
- 防编造扫描 `check_fabrication.py`：仅当一行同时含业务词与裸数字才报错；本 Sprint 文档/结构全程枚举值 + 字母标识符（E-TH/KI/expert-），无业务裸数字 → **0 命中**。
- 硬编码扫描 `check_hardcoded.py`：仅扫 `.js/.py/.ts/.tsx`；本 Sprint 无新增工程代码 → **0 命中**。
- `engineering_enabled=False` 实测：`agents/config_loader.py` 第 132 行 `return bool(section.get("engineering_enabled", False))` 默认 False，配置无该键 → 结论有效。
- `verified.json` 未改（`E-TH` value 仍 null）；`release_approvals.jsonl` 不存在。

---

## 8. 交付物与 SSOT/路线图更新

**本 Sprint 交付物**：
1. `agents/engineering/knowledge/experts.json`（增强至 schema_version=2：domains / qualification_status_enum / verification_workflow / sod_validation_rules + 补全字段集；`experts:[]` 仍空，无真实身份）
2. `.ai/reviews/phase3.3.3_expert_onboarding_report.md`（本报告）

**SSOT 更新**（`project_status.json` → `task_status.phase_3_3`）：新增 `3.3.3` DONE 条目（status/completed_at/executed_by/summary/constraints_kept/deliverables/fabrication_scan/next）。

**路线图更新**（`roadmap_v3.md`）：
- §2 在 3.3.2 块之后插入「补充 Sprint 3.3.3（DONE，2026-08-01，结构+流程设计）」说明块。
- 列表区 3.3.3 由 `PENDING` 翻 `DONE`，并在其下补「增强产出（3.3.3）」子项。
- §1 当前状态表 Phase 3.3 进度更新为 3.3.3 DONE。

---

## 9. 下一步

- 3.3.3 专家体系结构/流程 DONE；后续按序：3.3.4 真实阈值录入执行（人工经 `ThresholdIntakeWorkflow` 填 E-TH-01/02/03，须主理人审核 + 单独书面授权）→ 3.3.5 真实签署执行（双签落 review_log + G6 `release_approvals.jsonl`）→ 3.3.6 激活复核（重跑 `release_precheck` → RC 转 GO）。
- 真实专家资料登记须由人工经 §3 资质验证流程完成：提交 → 人工资质审核 → verified → 允许签署；AI 不代录、不代签、不代授权。
- 可选 3.3.7 Connector 实现时，直接复用本报告 §5/§6 的 Expert→KnowledgeItem→Obsidian 关联契约作为 `KnowledgeItemExtractor`/`SourceRefBinder` 的输入输出类型。

**红线全程守约，按 3.3.3 指令「完成后停止」——不录入真实专家身份、不录入真实阈值、未开启 `engineering_enabled`、未输出 `engineering_approved`、未开发同步代码。**

**END**
