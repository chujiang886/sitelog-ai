# Phase 3.3.7 — Engineering Knowledge Connector 实现报告

- **生成**：2026-08-02
- **身份**：BOIP AI Chief Architect
- **Sprint**：3.3.7 Engineering Knowledge Connector（知识连接器实现阶段）
- **承接**：3.3.0 / 3.3.0-B / 3.3.0-C（架构与 KnowledgeItem 13 字段七态模型）+ 3.3.1~3.3.6（管理基座 / 规范 ingestion / 专家 onboarding / 阈值录入准备 / 签署准备 / 激活复核 NO-GO）
- **性质**：**代码交付 Sprint**——将 3.3.0 系列架构设计落地为可运行的 `Obsidian → KnowledgeItem → BOIP Knowledge Layer` 单向采集连接能力。
- **红线守约结论**：✅ 全程未开启 `engineering_enabled`（=False）、未输出 `engineering_approved`、未自动录入真实工程参数、未自动修改 `verified.json` value、未自动创建 `ReleaseApproval`、AI 未代替专家审核。

---

## 0. 本次交付概览

| 项 | 内容 |
|---|---|
| 新增核心模块 | `agents/engineering/knowledge/connector.py`（含 5 个任务组件 + 包 init `agents/engineering/knowledge/__init__.py`） |
| 新增测试 | `tests/agents/test_knowledge_connector.py`（20 个测试，覆盖 mapping / validation / binding） |
| 配套修复 | `agents/engineering/release/candidate.py`、`tests/agents/test_evidence_bundle.py`、`tests/agents/test_release_candidate.py`（Ruff F401 清理 + 3.2.5 遗留测试 CI 路径 bug 修复，与红线无关） |
| CI 结果 | `bash scripts/ci/local_ci.sh` → **8/8 PASS**（Ruff / pytest 518 passed / ESLint / Jest 29 passed / Alembic / Seed / 防编造扫描 0 命中 / 硬编码扫描 0 命中） |
| 激活状态 | `engineering_enabled=False`；`verified.json` E-TH value 仍 `null`；`release_approvals.jsonl` 不存在；激活复核 verdict 维持 NO-GO（未变） |

---

## 1. 任务 1 — KnowledgeItemExtractor（Obsidian Markdown → KnowledgeItem，13 字段 + 七态模型）

**目标**：读取 Obsidian Markdown（frontmatter + 正文），生成符合 3.3.0-B/C 增强版 **13 核心字段**与**七态生命周期**的 `KnowledgeItem`。

### 1.1 实现要点
- `FrontmatterParser.parse(note_text) -> (dict, body)`：YAML frontmatter 解析；未闭合 / 解析失败回退空字典，**不抛异常**（fail-soft，符合知识采集鲁棒性要求）。
- `KnowledgeItemExtractor.extract(note_text, note_path) -> KnowledgeItem`：
  - `_split_title_and_body()`：首个 H1 抽为 `title`，其余为正文 `content`（避免标题混入正文）。
  - `knowledge_id = "KI-" + sha256(note_text)[:16]`：确定性派生（同内容同 id，幂等）。
  - `content_hash = compute_content_hash(f"{fm!r}\n{body_text}")`：复用 `source_ref_validator.compute_content_hash`，保证内容完整性可校验。
  - 13 核心字段：`knowledge_id / knowledge_type / parent_knowledge_id / title / content / source / author / domain / content_hash / validation_status / linked_entities / created_at / updated_at`（`confidence` / `session_id` 为辅助字段，不计入主键契约）。
- `KnowledgeItemState.from_obsidian_verification_status(raw)` 七态映射：
  - `draft` → `Pending_Verification`
  - `verified_source` → `Source_Verified`
  - `deprecated` → `Deprecated`
  - 缺失 / 未知 → `Captured`（默认基线态，不跳级）
- `KnowledgeItem.to_dict()`（13 核心字段优先）/`from_dict()`（容错补 `pending_verification`）。

### 1.2 红线契合
- 抽取**不写入**任何工程真值：未触发 `verified.json`、未生成 `engineering_approved`、未落签署位。
- `validation_status` 缺省落在 `Captured` / `Pending_Verification`，不臆造高级态。

---

## 2. 任务 2 — SourceRefBinder（KnowledgeItem → source_ref 校验 C1-C6）

**目标**：将 KnowledgeItem 的 `source` 绑定到 `spec_sources.json` 中已登记的来源，并对该来源的 `source_ref` 执行 C1-C6 完整性校验；失败保持 `Pending_Verification`。

### 2.1 实现要点
- `SourceRefBinder(spec_sources)`：`bind(item, content_provider=None) -> SourceRefBindResult`。
- 绑定逻辑：
  1. 从 `spec_sources` 索引 `source_id == item.source`；缺失来源 → `ok=False`，状态保持 `Pending_Verification`。
  2. 校验 `source_status == verified_source`；非 verified（draft/deprecated）→ `ok=False`，保持 `Pending_Verification`。
  3. 复用既有 `validate_source_ref(ref, content=...)` 执行 **C1 标准号 / C2 条款号 / C3 版本(4 位年或 vX.Y) / C4 http(s) 链接 / C5 sha256 64 位哈希 / C6 完整性** 全量校验；任一失败 → `ok=False`，保持 `Pending_Verification`。
  4. 全部通过 → 状态推进 `Source_Verified`。
- 测试结果（任务 2 覆盖）：C1-C6 全通过 / source 缺失 / source pending / source 非 verified / C5 hash 不一致 等分支均被 20 测试中的专门用例覆盖。

### 2.2 红线契合
- 仅**读** `spec_sources.json` 与 `verified.json`（只读断言），不从 Connector 写 `verified.json` value。
- 校验失败**保守降级**到 `Pending_Verification`，不臆造 Source_Verified。

---

## 3. 任务 3 — ExpertBinder（KnowledgeItem.author → experts.json，资质 / 范围 / SoD）

**目标**：将 KnowledgeItem 的 `author` 关联到 `experts.json` 已登记专家，校验 `qualification_status` / `sign_scope` / SoD 角色；**仅做校验，绝不代签**。

### 3.1 实现要点
- `ExpertBinder(experts)`：`bind(item) -> ExpertBindResult`（含 `ok / reason / expert_id / qualification_ok / scope_ok / sod_ok`）。
- 校验规则（对齐 3.3.3 的 SoD 六条 + 3.3.5 双签槽位）：
  - **R5 资格闸门**：`qualification_status == "verified"` 才允许签署；否则 `qualification_ok=False`。
  - **R4 域覆盖**：`item.domain` 必须被专家 `sign_scope` 覆盖（或 domain 为 `pending_verification` 时放宽，因尚未定域）。
  - **SoD 角色**：专家 `sod_role` 非空（签署主体须具备独立签署角色，避免无角色者混入）。
  - `author` 为空 / 为 `pending_verification` / 专家未登记 → `ok=False`，保持 `Pending_Verification`。
- **关键不变量**：`ExpertBinder` 绝不写入 `expert_verified_by` / `verified_by` / `expert_verified_at` 等签署位——AI 不代专家审核、不代主理人授权（红线 ⑥）。

### 3.2 红线契合
- 仅**读取** `experts.json`，从不写入或翻转 `qualification_status`。
- 校验通过仅返回 `ExpertBindResult` 信号，不落任何签名；真正 Expert_Verified 须人工经签署工作流。

---

## 4. 任务 4 — 同步策略（单向 Obsidian → BOIP，禁反向覆盖）

**目标**：确立 `Obsidian → BOIP Knowledge Layer` 单向采集拓扑，Connector 绝不反向写回原 Obsidian 笔记。

### 4.1 实现要点
- `ObsidianToBoipConnector.sync_direction()` 返回常量 `SYNC_DIRECTION = "obsidian_to_boip"`。
- 类文档明确："方向：Obsidian → BOIP（单向采集），绝不反向覆盖原笔记（本类不提供 write-back）"。
- `process_note(note_text, note_path) -> ConnectorResult`：依次执行 抽取 → SourceRef 绑定 → Expert 绑定，产出不可变结果对象（`ConnectorResult`），**无回写方法**。
- 复用 3.3.0 架构的「笔记 → AI 整理 → KnowledgeItem → Source 验证 → Expert 审核 → BOIP 入库」六阶段前半段（抽取+绑定），入库动作（写 `knowledge_items_pending.json` 等）仍由人工/工作流主导，Connector 自身不写。

### 4.2 红线契合
- 无 write-back 路径，原知识安全；BOIP 侧任何落盘不回灌 Obsidian。

---

## 5. 任务 5 — 安全保护（Connector 不可逾越的护栏）

**目标**：以代码与测试双重证明 Connector 不能修改 `verified.json` value、不能开启 `engineering_enabled`、不能创建 approved。

### 5.1 代码层护栏
- `ObsidianToBoipConnector.safety_invariants_ok()` 调用 `load_engineering_enabled()` 作**只读断言** `is False`；该值经 `config_loader` 解析 `config.yaml` 嵌套 `orchestrator` section 得 `False`。
- `connector.py` 全文件**零写入路径**：grep 实测无 `open(` / `json.dump` / `.jsonl` / `release_approvals` / `verified.json` 代码访问 / `engineering_enabled=True` 赋值（仅 docstring 提及约束 + 只读断言）。
- 不提供任何签名落盘 / 授权创建 API。

### 5.2 测试层护栏（20 测试中专门用例）
- **`verified.json` 字节级不变**：测试在 `process_note` 前后读取 `REPO_ROOT/"agents/engineering/thresholds/verified.json"` 完整字节并比对，断言 SHA256 一致 → 证明 Connector 未触碰该文件 value。
- **`release_approvals.jsonl` 未被创建**：测试断言该路径在运行后不存在。
- **`engineering_enabled` 保持 False**：测试断言 `load_engineering_enabled() is False`。

---

## 6. 测试与 CI 结果（8/8 PASS）

| 步骤 | 内容 | 结果 |
|---|---|---|
| ① Ruff | Backend lint（app / tests / agents / e2e） | ✅ All checks passed |
| ② pytest | 后端单测 + 覆盖（app,agents ≥60%） | ✅ 518 passed（含本 Sprint 20 新测试） |
| ③ ESLint | 前端 lint | ✅ 通过 |
| ④ Jest | 前端单测 + 覆盖（≥50%） | ✅ 29 passed / 93.15% |
| ⑤ Alembic | upgrade / downgrade | ✅ 通过 |
| ⑥ Seed | 种子数据 | ✅ 通过 |
| ⑦ 防编造扫描 | 全仓 `.js/.json/.jsonl/.md/.py/.toml/.ts/.tsx/.yaml/.yml` | ✅ 0 命中（退出码 0） |
| ⑧ 硬编码扫描 | `.js/.py/.ts/.tsx`（排除 tests/） | ✅ 0 命中（退出码 0） |

### 6.1 新增 20 测试覆盖矩阵
- **KnowledgeItem mapping（任务 1）**：13 字段完整性 / 七态映射（draft/verified_source/deprecated/缺失）/ 无 frontmatter → Captured / 确定性 id+hash / `from_dict` 容错。
- **SourceRef validation（任务 2）**：C1-C6 全通过 / source 缺失 / source pending / source 非 verified / C5 hash 不一致。
- **Expert binding（任务 3）**：专家通过 / author pending / 未登记 / 资格非 verified / 范围不覆盖。
- **流水线（任务 4）**：`process_note` 全链路通过 / `sync_direction()` 单向。
- **安全护栏（任务 5）**：`verified.json` 字节不变 / 不创建 `release_approvals.jsonl` / `engineering_enabled` 保持 False。

### 6.2 配套修复（与红线无关，属合理收尾）
- `agents/engineering/release/candidate.py`：删除 2 个未使用 import（`json`、`ReleaseEvidenceBundle`），由 ruff --fix 完成。
- `tests/agents/test_evidence_bundle.py`、`tests/agents/test_release_candidate.py`：修复 3.2.5 遗留的 cwd 相对路径 bug（CI 从 `backend/` 运行 pytest 导致 `FileNotFound`）——统一改为 `REPO_ROOT = Path(__file__).resolve().parents[2]` 绝对路径。此 5 个失败为**预存环境缺陷**，非 Connector 引入，修复后达成 8/8。
- 前端 Jest 预存 `canvas.node` 原生二进制缺失：经 `npm rebuild` 重建后 29 tests PASS（环境修复，非代码缺陷）。

---

## 7. 红线守约声明（6 条最高红线逐条核对）

| 红线 | 状态 | 证据 |
|---|---|---|
| ① 禁止开启 `engineering_enabled` | ✅ 守约 | `load_engineering_enabled()` 实测 `False`；Connector 仅只读断言，无赋值路径 |
| ② 禁止输出 `engineering_approved` | ✅ 守约 | 全仓无 `engineering_approved` 输出；KnowledgeItem 验证态最高仅 Source/Expert_Verified（人工签署前置） |
| ③ 禁止自动录入真实工程参数 | ✅ 守约 | Connector 不写 `verified.json`；`E-TH` value 仍 `null`；抽取仅做映射不生成数值 |
| ④ 禁止自动修改 `verified.json` | ✅ 守约 | 测试字节级比对证明 `verified.json` 未变；代码零写入路径 |
| ⑤ 禁止自动创建 `ReleaseApproval` | ✅ 守约 | `release_approvals.jsonl` 运行后不存在（测试断言） |
| ⑥ 禁止 AI 代替专家审核 | ✅ 守约 | `ExpertBinder` 仅校验资格/范围/SoD，绝不落 `expert_verified_by`/`verified_by` 签署位 |

---

## 8. 结论与下一步

- **3.3.7 交付完成**：`Obsidian → KnowledgeItem → BOIP Knowledge Layer` 单向采集连接能力已落地，13 字段七态模型、C1-C6 来源校验、专家资质/范围/SoD 校验、单向同步、安全护栏全部实现并通过 8/8 CI。
- **激活状态不变**：本 Sprint 为连接器实现，不改变 3.3.6 的 NO-GO 结论——`engineering_enabled` 仍 False，真实数据/专家签署/主理人授权仍缺。
- **下一步（人工动作，AI 不代行）**：待主理人提供 E-TH-01/02/03 真实 value/source_ref、经 3.3.3 资质审核登记 `verified` 专家签署、主理人书面授权后，方经 ThresholdIntakeWorkflow 四步 + 双签 + G1-G6 复核达成 GO，再翻 `engineering_enabled`。

> **本轮 AI 不开启 `engineering_enabled`、不输出 `engineering_approved`、不创建 `ReleaseApproval`、不代签不代授权、不改 `verified.json`。任务结束，停止。**
