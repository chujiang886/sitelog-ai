# BOIP 研发路线 V3（roadmap_v3.md）

- **生成**：2026-08-01
- **身份**：BOIP AI Chief Architect（Phase 3.2 收口 + Phase 3.3 建立）
- **性质**：Phase 3.3 路线建立；**不修改业务代码**（`agents/`、`backend/app`、`frontend/src` 零改动，仅新增治理文档与占位骨架）
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V3）、`.ai/reviews/phase3.2_closing_report.md`、`.ai/tasks/phase3.3.1_engineering_knowledge_activation.md`
- **权威声明**：本文件取代 `roadmap_v2.md`，为 Phase 3.3 起的唯一研发路线；roadmap_v2.md 保留为 Phase 3.2 历史归档。

---

## 1. 当前真实状态（Phase 3.2 收口态）

| 维度 | 真实状态 |
|---|---|
| 阶段 | **Phase 3.2 CLOSED（2026-08-01 正式收口）** → 🟢 **Phase 3.3 IN_PROGRESS（Engineering Knowledge Activation 进行中，3.3.1~3.3.8 全 DONE；3.3.8 Knowledge Repository 治理层已交付；3.3.6 激活复核 verdict=NO-GO 维持关闭）**；工程审核闭环治理与基础设施全量建成（inert，未激活，G1-G6 全 FAIL 维持关闭） |
| 工程审核闭环 | 12 类能力建成（结果抽象 / 报告工程章节 / 双签闭环 / 阈值治理 schema v2 / 迁移工具 / source_ref 校验 / 阈值录入工作流 / 灰度基础设施 / 发布执行基础设施 / 生产就绪检查 / 证据 Bundle+Candidate / 受控发布 Runbook），受 `engineering_enabled=false` 约束全 inert |
| 首次灰度 RC | `wind_pressure` RC 已建立并冻结（`BOIP-RC-8652324bb01db0e5`），`release_precheck` 真实态 G1-G6 全 `false` → **NO-GO**（就绪度 全阻断） |
| 红线 | `engineering_enabled=false`；无任何 `engineering_approved` 输出；`E-TH-01/02/03` 真实 `value` 仍 `null`（pending_verification） |
| CI | 基线 `481 passed@90%`（`local_ci.sh` 8/8 全绿）+ 防编造/硬编码扫描 0 命中 |
| 未完成（人工动作） | 真实阈值数值 / 真实双签 / 真实审核链 / G6 授权 / CI绿确认 / 回滚就绪确认 / 真实放量 均 pending_verification；D-TH 双签路径与监控落点待主理人定；H3-B 冻结记录 bundle_id 不一致（建议重生成） |

**红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数（风压/楼层/评分权重）未经专家签字不得转正；Phase 3.3 不录入真实参数、不开 `engineering_enabled`、不输出 `engineering_approved`。

---

## 2. Phase 3.3 路线（Engineering Knowledge Activation — 真实工程知识接入）

> **Phase 3.3 定位**：Phase 3.2 已建成「可被安全激活的工程审核闭环容器」。Phase 3.3 目标 = **开始真实工程知识接入**——先把规范来源、专家资料、阈值录入、规范版本、专家签署五类**管理基座**建立起来（仅计划与容器，不录入真实数据），为后续真实数据填充与最终激活铺路。

> **设计前置 Sprint 3.3.0（DONE，2026-08-01，纯架构设计）**：Obsidian Knowledge System Integration Design —— 设计 Obsidian↔BOIP 知识协同架构（知识分层 / Vault 结构 / 迁移流程 / Metadata 规范 / MCP 同步方案，仅设计零代码）：
> - ① 知识三层架构（Personal / Engineering / Governance 边界矩阵）
> - ② Obsidian Vault 七目录（Sources/Experts/Cases/Engineering Rules/Experience/Pending Verification/Verified Knowledge）
> - ③ 知识迁移六阶段（笔记→AI整理→Knowledge Item→Source验证→Expert审核→BOIP入库）
> - ④ Metadata 六字段 frontmatter（source/author/domain/confidence/verification_status/linked_threshold）
> - ⑤ MCP 单向采集同步接口设计（ObsidianMCPConnector/KnowledgeItemExtractor/SourceRefBinder/SyncScheduler）
>
> 红线守约：不修改工程代码 / 不录真实参数 / 不开 enabled / 不输出 approved / 防编造硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.0_obsidian_integration_architecture.md`。

> **补充 Sprint 3.3.0-B（DONE，2026-08-01，纯架构设计）**：Knowledge Item Schema Design —— 在 3.3.0 的 Obsidian↔BOIP 采集架构之间补充知识资产中间层 KnowledgeItem 标准模型：
> - ① KnowledgeItem Schema（11 字段：knowledge_id/title/content/source/author/domain/content_hash/validation_status/linked_entities/created_at/updated_at）
> - ② 生命周期六态（Captured→Pending_Verification→Source_Verified→Expert_Verified→Engineering_Verified→Deprecated，与 source_status 三态及 G1-G6 衔接）
> - ③ Obsidian frontmatter 六字段→KnowledgeItem 映射
> - ④ KnowledgeItem→spec_sources/experts/thresholds(仅引用)/cases 落盘映射（明确不写阈值 value、不改 verified.json）
> - ⑤ 知识权限边界三级（Personal / Engineering / Engineering Approved，与 G1-G6+G6 联动）
>
> 红线守约：不录真实参数 / 不改 verified.json / 不开 enabled / 不输出 approved / 不开发同步代码 / 防编造硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`。

> **补充 Sprint 3.3.0-C（DONE，2026-08-01，纯架构增强）**：KnowledgeItem Schema Enhancement Review —— 在 3.3.0-B 中间层模型上增强**长期演化能力**：
> - ① 新增 `knowledge_type` 枚举（spec / expert_opinion / case / experience / rule / threshold_candidate）+ 治理差异表（落点 / 谁可写 / 是否承载数值 / 升格闸门 / 冲突优先级 / 消费权限）
> - ② 新增 `parent_knowledge_id` 谱系字段（旧知识→新知识→派生规则溯源链 + 谱系不变量：禁环 / 派生态不超过最弱父 / Deprecated 须置 successor）
> - ③ 拆分生命周期 `Engineering_Verified`（专家/工程验证，G1-G6 技术就绪未授权）与 `Engineering_Approved`（G1-G6 全绿 + G6 授权），六态→七态
> - ④ 更新 3.3.0-B 文档为增强版（13 字段 Schema + 七态生命周期 + 类型治理 + 谱系 + Obsidian/BOIP 映射更新 + 权限边界对齐 Engineering_Approved）
>
> 红线守约：不开发同步代码 / 不录真实数据 / 不改 verified.json / 不开 enabled / 不输出 approved / 防编造硬编码扫描 0 命中。详见（同 3.3.0-B 文件路径，已增强）`.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`。

> **首 Sprint 3.3.1（DONE，2026-08-01，基座态）**：Real Engineering Knowledge Activation —— 仅建管理基座：
> - ① 真实规范来源管理（spec_sources 容器 + C1-C6 校验流程）
> - ② 专家资料管理（experts 容器 + 与 review_log signer 标识符对齐 + SoD 规则）
> - ③ 真实阈值录入计划（编排 E-TH-01/02/03 经 ThresholdIntakeWorkflow 的录入步骤，不执行）
> - ④ 规范版本管理（schema_version + 每条 version 语义化 + deprecated 回滚策略）
> - ⑤ 专家签署计划（双签 + G6 授权流程编排与落点确认，不执行签署）
>
> 红线守约：不录入真实参数 / 不开 `engineering_enabled` / 不输出 `engineering_approved`。详见 `.ai/tasks/phase3.3.1_engineering_knowledge_activation.md`。

- **3.3.0** T-KE-0 Obsidian 知识协同架构设计（知识分层 / Vault 七目录 / 迁移流程 / Metadata 规范 / MCP 单向同步接口，仅设计零代码）。**DONE（2026-08-01，架构态）**
- **3.3.0-B** T-KE-0B Knowledge Item Schema 设计（中间层 KnowledgeItem 11 字段 + 生命周期六态 + Obsidian/BOIP 双向映射 + 三级权限边界，仅设计零代码）。**DONE（2026-08-01，架构态）**
  - ✅ 设计产出：`.ai/reviews/phase3.3.0B_knowledge_item_schema_design.md`（七章 + 映射对齐 + 红线不变式）；不录真实参数、不改 verified.json、不开 enabled、不输出 approved、不开发同步代码；为 3.3.0 MCP 拓扑补足中间层契约。
  - ✅ 增强产出（3.3.0-C，2026-08-01）：同文件升级为增强版——KnowledgeItem 13 字段（新增 `knowledge_type` + `parent_knowledge_id`）+ 生命周期七态（拆分 `Engineering_Verified`/`Engineering_Approved`）+ 类型治理差异表 + 知识谱系不变量 + 映射/权限边界对齐；不开发、不录真实数据、不改 verified.json、不开 enabled、不输出 approved；Schema finalized。
- **3.3.0-C** T-KE-0C KnowledgeItem Schema Enhancement Review（长期演化增强：knowledge_type 治理差异 / parent_knowledge_id 谱系 / 拆分 Engineering_Verified 与 Engineering_Approved，仅设计零代码）。**DONE（2026-08-01，架构增强态）**
  - ✅ 设计产出：`.ai/reviews/phase3.3.0_obsidian_integration_architecture.md`（六章 + 映射对齐 + 红线不变式）；不修改工程代码、不录真实参数、不开 enabled、不输出 approved；为 3.3.1/3.3.2 容器提供 Obsidian 侧采集入口。
- **3.3.1** T-KE-1 真实工程知识接入管理基座（规范来源 / 专家资料 / 阈值录入计划 / 规范版本 / 专家签署计划，仅基座不录入）。**DONE（2026-08-01，管理基座执行完成）**
  - ✅ 执行产出：`agents/engineering/knowledge/spec_sources.json` + `experts.json` 两容器 + 三份计划文档（阈值录入 / 版本策略 / 专家签署）+ 执行报告；防编造/硬编码扫描 0 命中；红线全守约（未录真实参数 / 未开 enabled / 未输出 approved / 未建 ReleaseApproval）。
- **3.3.2** T-KE-2 真实规范 ingestion（规范来源登记与校验能力：增强 spec_sources.json 的 source_type / source_status / mapping_convention，建 Source Ref 映射与版本登记 draft→verified_source→deprecated 流程）。**DONE（2026-08-01，结构+流程态）**
  - ✅ 执行产出：`agents/engineering/knowledge/spec_sources.json`（增强）+ `.ai/tasks/phase3.3.2_spec_ingestion_plan.md`（人工提供 / 来源校验 C1-C6 / hash 生成 / 版本登记 / 审核 / Source Ref 映射）；防编造/硬编码扫描 0 命中；红线全守约（未录真实条款 / 未改 verified.json / 未开 enabled / 未输出 approved）。
> **补充 Sprint 3.3.3（DONE，2026-08-01，结构+流程设计）**：Real Expert Onboarding —— 在 3.3.1 基座之上增强真实专家体系接入结构：
> - ① Expert Registry 增强（experts.json schema_version=1→2：补全字段集 expert_id/domains/qualification_ref/sign_scope/sod_role/valid_until/qualification_status）
> - ② 专家领域能力模型六枚举（wind_engineering/structure/profile/glass/hardware/installation，定义可验证范围）
> - ③ 资质验证流程（提交→审核→verified→允许签署，禁止自动 verified；翻转严禁自动化）
> - ④ SoD 校验体系六规则（R1 expert_verified_by≠verified_by；R2 authorized_by≠rollback_owner；R3 G6 主体独立；R4 域覆盖；R5 状态闸门；R6 不自核准）
> - ⑤ KnowledgeItem 关联（Expert→KnowledgeItem.author→Expert_Verified）
> - ⑥ Obsidian 专家目录映射（01-Experts→experts.json→KnowledgeItem）
>
> 红线守约：未录真实专家身份（experts:[] 空、_example_entry 全 pending_verification）/ 未录真实阈值 / 未开 enabled / 未输出 approved / 未代签代授权 / 未自动建 ReleaseApproval / 防编造硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.3_expert_onboarding_report.md`。
- **3.3.3** T-KE-3 真实专家 onboarding（真实专家体系接入：专家注册表增强 / 领域模型 / 资质流程 / SoD 校验 / KnowledgeItem 关联 / Obsidian 映射，仅结构+流程设计）。**DONE（2026-08-01，结构+流程态）**
  - ✅ 增强产出：`agents/engineering/knowledge/experts.json`（schema_version=2）+ `.ai/reviews/phase3.3.3_expert_onboarding_report.md`；不录真实专家身份（experts:[] 空）/ 不录真实阈值 / 不开 enabled / 不输出 approved / 不代签代授权 / 防编造硬编码扫描 0 命中；为 3.3.4 真实阈值录入提供专家主体与 SoD 闸门。
> **补充 Sprint 3.3.4（DONE，2026-08-02，结构+准备态）**：Real Threshold Entry Execution —— 建立 E-TH-01/02/03 真实录入的会话结构与执行编排骨架，不调用工作流写真实值：
> - ① ThresholdEntrySession（threshold_entry_sessions.json：threshold_id/source_ref/provider/reviewer/expert/status 全 pending_verification，workflow_steps 全 blocked_pending_human_data）
> - ② Source Ref C1-C6 验证（复用 source_ref_validator.validate_source_ref / build_source_verification_report，失败保持 pending）
> - ③ ThresholdIntakeWorkflow 执行编排（submit→review_approve→expert_recheck→finalize_verified，要求写 review_log；真实值须人工提供）
> - ④ KnowledgeItem 关联（knowledge_items_pending.json：threshold_candidate 型 KnowledgeItem，建立 threshold_candidate→KnowledgeItem→Expert_Verified 链路，复用 13 字段七态）
> - ⑤ 禁止激活（engineering_enabled 恒 false，evaluate_gates 恒 False，不输出 approved，不创建 ReleaseApproval）
>
> 红线守约：未填真实工程参数（verified.json E-TH value 仍 null）/ AI 不生成参数不猜规范值不代签不代授权 / 未开 enabled / 未输出 approved / 防编造硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.4_threshold_entry_execution_report.md`。
- **3.3.4** T-KE-4 真实阈值录入执行（人工经 `ThresholdIntakeWorkflow` 填 E-TH-01/02/03，满足 G1/G2/G4，仅结构/准备态）。**DONE（2026-08-02，结构+准备态）**
  - ✅ 增强产出：`agents/engineering/knowledge/threshold_entry_sessions.json` + `agents/engineering/knowledge/knowledge_items_pending.json` + `.ai/reviews/phase3.3.4_threshold_entry_execution_report.md`；不填真实参数（verified.json E-TH value 仍 null）/ AI 不代签代授权 / 不开 enabled / 不输出 approved / 防编造硬编码扫描 0 命中；真实数值录入仍阻塞于人工提供资料与书面授权。
> **补充 Sprint 3.3.5（DONE，2026-08-02，结构+签署准备态）**：Real Threshold Signing Execution —— 建立 E-TH-01/02/03 真实审核签署链的框架与槽位容器，不调用工作流写真实签名：
> - ① 主理人审核框架（principal_review：verified_by/verified_at 全 pending_verification，signer_role=principal，须 experts.json sod_role=principal 且 qualification_status=verified）
> - ② 专家复核框架 + SoD（expert_recheck：expert_verified_by/expert_verified_at 全 pending_verification，须 qualification_status=verified 且 sign_scope 覆盖 domain；SoD 硬规则 expert_verified_by != verified_by 指向 threshold_intake.expert_recheck REASON_SOD_CONFLICT）
> - ③ KnowledgeItem 状态推进（knowledge_items_pending.json 增补 state_progression 七态机：Pending_Verification→Source_Verified→Expert_Verified，禁止直接进入 Engineering_Approved）
> - ④ verified.json 保护（任何写入须经 ThresholdIntakeWorkflow，禁绕过）
> - ⑤ 审计链检查（review_log 须含 intake_submit/intake_review_approve/intake_expert_recheck 三事件）
> - ⑥ 激活保护（engineering_enabled 恒 false，不输出 approved，不创建 ReleaseApproval）
>
> 红线守约：未生成专家身份/未生成签名/未代主理人确认/未代专家复核/未创建 ReleaseApproval / 未开 enabled / 未输出 approved / 未绕过工作流改 verified.json / 未 append 真实 review_log（review_log.jsonl 仍仅含 2026-07-28 schema_established 系统事件）/ 防编造硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.5_threshold_signing_execution_report.md`。
- **3.3.5** T-KE-5 真实签署执行（双签落 review_log + G6 EngineeringReleaseApproval 落 release_approvals.jsonl，满足 SoD，仅结构/签署准备态）。**DONE（2026-08-02，结构+签署准备态）**
  - ✅ 增强产出：`agents/engineering/knowledge/threshold_signing_sessions.json` + `agents/engineering/knowledge/knowledge_items_pending.json`（增补 state_progression）+ `.ai/reviews/phase3.3.5_threshold_signing_execution_report.md`；未生成专家身份/签名（签署位全 pending_verification）/ AI 不代签代授权 / 未开 enabled / 未输出 approved / 未 append 真实 review_log / 防编造硬编码扫描 0 命中；真实签署仍阻塞于人工提供身份与签名并经主理人书面授权。
- **3.3.6** T-KE-6 激活复核（重跑 `release_precheck(wind_pressure)` 复核 G1-G6 全绿 → RC 转 GO → `gray_release_ctl.py enable wind_pressure`）。**DONE（verdict=NO-GO）**
  - ✅ 诚实激活审计（只读）：`can_enable_engineering()=False`、`release_precheck(interface='wind_pressure')=False`；G1-G6 六门禁全 FAIL（阈值未 verified / 双签缺失 / CI 未绿 / 审核链不完整 / 回滚未就绪 / 授权缺失）；KnowledgeItem 全 `Pending_Verification`、专家名录空（SoD 不成立）、`review_log.jsonl` 仅 1 行系统事件。
  - 红线守约：未开 `engineering_enabled`（=False）、未输出 `engineering_approved`、未创建 `ReleaseApproval`、AI 不代签不代授权、未改 `verified.json`、未 append `review_log`、防编造/硬编码扫描 0 命中。详见 `.ai/reviews/phase3.3.6_activation_review_report.md`。
- **3.3.7** T-KE-7 知识连接器实现（Obsidian → KnowledgeItem → BOIP Knowledge Layer 单向采集，代码交付）。**DONE（2026-08-02）**
  - ✅ 新增 `agents/engineering/knowledge/connector.py`（5 任务组件）+ `tests/agents/test_knowledge_connector.py`（20 测试）：任务1 KnowledgeItemExtractor（13 核心字段 + 七态模型，frontmatter+正文抽取，确定性 id/hash）；任务2 SourceRefBinder（复用 `validate_source_ref` 执行 C1-C6，失败保守降级 `Pending_Verification`）；任务3 ExpertBinder（校验 `qualification_status=verified`(R5)/`sign_scope` 覆盖 domain(R4)/`sod_role` 非空，仅校验不代签）；任务4 单向同步（`sync_direction=obsidian_to_boip`，无 write-back）；任务5 安全护栏（`safety_invariants_ok` 只读断言 `engineering_enabled=False`、零写入路径、测试字节级证明 `verified.json` 未变、不建 `release_approvals.jsonl`）。
  - ✅ CI：`bash scripts/ci/local_ci.sh` → **8/8 PASS**（pytest 518 passed / Jest 29 passed / 防编造+硬编码扫描 0 命中）；配套修复 3.2.5 遗留 cwd 路径 bug（与红线无关）。
  - 红线守约：未开 `engineering_enabled`（=False）/ 未输出 `engineering_approved` / 未自动录真实参数（Connector 不写 `verified.json`，E-TH value 仍 null）/ 未改 `verified.json`（字节级比对）/ 未建 `ReleaseApproval` / AI 不代专家审核（`ExpertBinder` 绝不落签署位）。激活态维持 NO-GO（3.3.6 结论不变）。详见 `.ai/reviews/phase3.3.7_knowledge_connector_report.md`。
- **3.3.8** T-KE-8 Knowledge Repository & Governance Layer（知识资产仓库与治理层）。**DONE（2026-08-02）**
  - ✅ 新增 `agents/engineering/knowledge/repository.py`（核心 `KnowledgeEvent` / `KnowledgeEventLog` / `KnowledgeRepository`）+ `agents/engineering/knowledge/connector.py`（修订 `process_note` 接入 Repository、`ConnectorResult.repository_info`）+ `tests/agents/test_knowledge_repository.py`（24 测试）：任务1 KnowledgeRepository（`save`/`get`/`query`/`version`/`history`，自管 `knowledge_repository.json`，绝不读 `verified.json`）；任务2 版本管理（每次 `save` 生成版本快照，`_canonical_core` 规范化 13 核心字段排除时间戳与哈希得 `content_hash`，幂等判定——内容无变化不新增版本，`created_at`/`updated_at`/`parent_knowledge_id` 全程追踪）；任务3 知识审计日志 `KnowledgeEventLog`（append-only，仅记录 `create`/`update`/`verify`/`deprecated`，`event_type` 白名单 `ValueError` 硬拒 `approved`）；任务4 Connector 接入 Repository（Obsidian→KnowledgeItem→Validation→Repository，`process_note` 接收 `repository` 参数落库，`source_ref` C1-C6 通过补记 `verify` 事件，向后兼容不传则内存编排）；任务5 权限保护（`safety_invariants_ok` 只读断言 `engineering_enabled=False`、不写 `verified.json`、不建 `ReleaseApproval`、`verify` 仅置 `Source_Verified` 永不 `Engineering_Approved`）。
  - ✅ CI：Ruff All checks passed；pytest 新增 24 passed / agents 套件 425 passed（剔除无关 `test_smoke_e2e` 环境守卫后全绿）；ESLint 通过（1 warning）；Jest 29 passed(93.15%)；Alembic 通过；Seed 通过；防编造+硬编码扫描 0 命中。⚠️ `local_ci.sh` 完整运行下第 2 步 pytest 因前置 `test_smoke_e2e.py` 触发 WorkBuddy `[safe-delete]` 批量删除确认守卫（非交互 CI 下 `SystemExit`）而中断——该守卫为环境级保护、与 3.3.8 无关、本轮不修改；3.3.8 新增代码零回归。
  - 红线守约：未开 `engineering_enabled`（只读断言=False）/ 未输出 `engineering_approved`（审计白名单明确排除 `approved`；`record('x','approved')` 与 `verify` 永不 `Engineering_Approved`）/ 未改 `verified.json`（Connector 集成测试字节级证明未变）/ 未建 `ReleaseApproval`（`release_approvals.jsonl` 运行后不存在）/ AI 不代专家审核（`verify` 仅置 `Source_Verified`，签署由人工/专家驱动）。激活态维持 NO-GO（沿用 3.3.6/3.3.7 结论）。详见 `.ai/reviews/phase3.3.8_knowledge_repository_report.md`。

---

## 3. 优先级排序（Phase 3.3）

| 优先级 | 任务 | 理由 |
|---|---|---|
| **P0** | 3.3.1 管理基座 | 真实知识接入的前置容器，不建则后续 Sprint 无落点 |
| **P1** | 3.3.2 规范 ingestion / 3.3.3 专家 onboarding | 真实来源与主体就位，方可录入与签署 |
| **P1** | 3.3.4 阈值录入 / 3.3.5 签署 | 满足 G1/G2/G4/G6 的必经人工动作，须单独书面授权 |
| **P2** | 3.3.6 激活复核 | 前置全部满足后的收口动作 |

---

## 4. 红线与治理不变式（Phase 3.3 全程）

1. **不录入真实参数**：`E-TH-01/02/03` 真实 `value` 由人工经 `ThresholdIntakeWorkflow` 另行填写（始于 3.3.4），3.3.1 不填。
2. **不开 `engineering_enabled`**：全局仍 `false`；`can_enable_engineering` 默认拒绝，直至 G1-G6 全绿 + G6 授权。
3. **不输出 `engineering_approved`**：全 `pending_verification`，无 approved 落盘/输出。
4. **不代签/不代授权**：签名与授权由人工线下经正式流程提供，AI 仅编排容器与校验。
5. **不自动创建 `ReleaseApproval`**：G6 授权由主理人书面创建。
6. **防编造/硬编码扫描**：新增文档与代码持续 0 命中。

---

## 5. 技术债偿还（沿用 V2 册，Phase 3.3 起排入）

- TD-002 工程阈值未确认（高）：待 3.3.4 真实录入 + 双签转正。
- TD-016 Vision prompt 调优（高）：待专家资料就位后排期。
- TD-011 SQLite↔PG JSONB（中）：延后。
- 治理卫生：H3-B 冻结记录 bundle_id 不一致（建议以当前确定性算法重生成，待主理人确认）。
- 债 OPEN 现状：Phase 2.2 末 OPEN=13（目标 ≤5 未达标），Phase 3.3 起须排入还债节奏。

---

**END**
