# BOIP 研发路线 V2（roadmap_v2.md）

- **生成**：2026-07-26
- **身份**：BOIP AI CTO（Phase 2.1 架构稳定阶段）
- **性质**：重新建立真实研发路线；**不修改业务代码**（`agents/`、`backend/app`、`frontend/src` 零改动）
- **依据**：`.ai/project_status.json`（SSOT，current_roadmap_version=V2）、`.ai/architecture_sync_report.md`
- **权威声明**：本文件取代 `project_status.json` 内旧 `roadmap` 块（V1），为当前唯一研发路线。

---

## 1. 当前真实状态

| 维度 | 真实状态 |
|---|---|
| 阶段 | **Phase 2.2 COMPLETED → 🟢 Phase 3 Ready**（2.1 架构稳定 + 2.2 能力深化 2.2.1~2.2.6 六 Sprint 全部收口，2026-07-28 总结验收；2026-07-28 完成 3.0 前置整理 Sprint + Final Go Preparation；**Phase 3 Readiness 已审核通过**，开发未启动，等待主理人最终授权）；**Phase 3.1 工程智能闭环设计 🟡 DESIGN_READY（2026-07-28 四任务交付，待主理人审核，未进入编码）** |
| LLM | `track_a` = 腾讯混元 TokenHub `HY-Vision-2.0-Instruct`（openai_compat，文本+视觉共用），`llm.enabled=true`；`track_b`=mock；**ADR-001 确立 `.env::LLM_A_*` 为唯一事实源** |
| 后端 | 11 个 router（含 /api/auth/*、/api/rag/*）；`/api/analysis/run` 串联三 Agent → dossier；`/api/report/generate` 流式 PDF |
| 前端 | 8 个页面（home/consult/result/upload/agents/projects/knowledge/login）+ 29 个 Jest 用例 |
| 数据层 | 10+ ORM 模型；SQLite 占位；Alembic 迁移；本地 uploads 存储 |
| 测试门禁 | backend **246 passed**（覆盖 87.34%，门槛 60%）+ 前端 **29/6 suites**（覆盖 93.15%，门槛 50%）= **275 passed**（2.2.6 刷新；local_ci.sh 8/8 全绿） |
| 分支 | `master`，**本地领先 `origin/master` 5 提交（R-N2，未 push）**；远端 `github.com/chujiang886/sitelog-ai`。等待主理人确认后 `git push origin master`（密钥自查已过：`.env` 未入库） |
| 🔴 红灯未闭合 | `engineering_enabled = false` → 工程安全审核链未闭环；行业阈值（风压/楼层/评分权重）全 `pending_verification` |
| 技术债 | **OPEN = 11**（3.0 偿还 TD-003/017/018 + TD-013 收口；A/B/C 重分类见 `.ai/technical_debt/README.md`） |
| 文档 | ✅ 已收敛（3.0 偿还 TD-003/017/018）：README/CHANGELOG/LLM.md/AGENTS.md/API.md 全部刷至 Phase 2.2 COMPLETED，D2–D7 全闭环 |

**红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数（风压/楼层/评分权重）未经专家签字不得转正。

---

## 2. Phase 2.1 任务树（架构稳定）

**目标**：把"已跑通"提升为"可生产、可维护、可审计"。出口标准：文档/配置零矛盾、工程审核链能力就绪、数据访问非阻塞、测试基线权威、债 OPEN≤8。

| ID | 任务 | 关联债/风险 | 优先级 | 关键产出 |
|---|---|---|---|---|
| 2.1.1 | 文档/配置全面对齐收尾：刷新 CHANGELOG/LLM.md/PHASE0_LOG/AGENTS/API；清理 `config.yaml` 注释 "DashScope qwen-max" + 遗留 `llm_enabled:false`；补 `.gitignore`（`.next.trash`/`deliverables`）；归档 `deliverables/` | D1–D13、C1、C3、C5、TD-017/018 | **P0** | 文档与代码一致 |
| 2.1.2 | 工程阈值专家签字（风压/楼层/评分权重）→ 部分 `pending` 转正 | TD-002(高)、R4 | **P0** | 阈值确认书 + 配置项 |
| 2.1.3 | Vision prompt 专家调优（建筑开口场景化） | TD-016(高)、R4 | **P0** | 调优后 prompt + 评测集 |
| 2.1.4 | `AsyncSession` 引入 + `async_get_db`（消除 async 路由同步阻塞事件循环） | TD-012(中)、R3 | **P0** | 非阻塞数据访问（✅ **COMPLETED 2026-07-27**，backend 64 + agents 86 = 150 passed，已验收） |
| 2.1.5 | 工程安全审核链能力前置：Engineering Agent 骨架 + `engineering_enabled` 开关框架（先建能力，不强制上线） | R4、TD-002 | P1 | Engineer Agent 骨架（✅ **COMPLETED 2026-07-27**：agents/engineering/ 五文档 + 五接口统一输出 + EngineeringValidation 审核链，enabled:false 未进管道；local_ci 8/8 全绿 164 passed，待用户验收） |
| 2.1.6 | Provider 架构解耦：`vision_provider` / `text_provider` 分离配置（C4） | C4(中)、TD-013 | P1 | 双 provider 配置（✅ **COMPLETED 2026-07-27**） |
| 2.1.7 | 测试基线刷新：重跑 `local_ci.sh` 更新门禁数；修 R7 pytest collection conflict | R6、R7 | P1 | 新基线 + 可独立跑（✅ **COMPLETED 2026-07-27**，第 1 轮 8/8 全绿：pytest 151 passed/覆盖 82.67%，Jest 29 passed/覆盖 93.15%；R6 基线已刷新，R7 实证不复现；报告 `.ai/reviews/2.1.7_test_baseline_report.md`） |
| 2.1.8 | 数据层生产化前置：PostgreSQL 接入验证 JSONB 查询 + `gin` 索引评估 | TD-011(中)、R5 | P1 | PG 验证报告 |
| 2.1.9 | 仓库卫生：`.gitignore` 补 `.next.trash`；确认分支模型（master 为主干） | R8、D12 | P2 | 干净仓库 |

---

## 3. Phase 2.2 任务树（能力深化）✅ **PHASE 2.2 = COMPLETED（2026-07-28 总结验收）**

**目标**：在稳定架构上把占位能力做实。出口标准：Environment/Design 用真实数据、PDF 可交付、图片云存储、债 OPEN≤5。

> **收口结论**（详见 `.ai/reviews/phase2.2_final_review.md`）：6/6 Sprint 全部交付，最终基线 **275 passed**（backend 246/覆盖 87.34% + Jest 29/覆盖 93.15%），每 Sprint local_ci.sh 8/8 全绿。机制层出口标准全部达成（Provider 抽象+溯源防编造+可交付 PDF+存储抽象+RAG 地基+RBAC 地基）；真实外部数据源接入按 ADR 流程 DEFERRED（安全决策）；**债 OPEN≤5 未达标（实际 13）**，建议 Phase 3 前插入还债专项 Sprint。全部改动已于 3.0 前置整理分批提交（5 批 commit，HEAD 见 `git log`），local_ci.sh 8/8 全绿。**不进入 Phase 3，当前进入 Phase 3 planning。**

| ID | 任务 | 关联 | 优先级 |
|---|---|---|---|
| 2.2.1 | T09 Environment 接真实 weather/gis 数据（Provider 抽象层，替换占位字段） | TD-002 延伸 | P1 | Provider 抽象层 + mock/disabled 三模式（✅ **COMPLETED 2026-07-27**：agents/environment/providers/ 新建 base/mock/factory + agent.py 升至 1.1.0-phase2.2.1，前置数据段 + field_provenance + pending 语义修正；local_ci 8/8 全绿 backend 177 passed/覆盖 83.95%，Jest 29 passed/覆盖 93.15%；真实厂商 DEFERRED 待 ADR-02；报告 .ai/reviews/2.2.1_environment_data_report.md） |
| 2.2.2 | T10 Design 三方案专业化（机制先行：语义修正 + 阈值治理 + Prompt 专业化） | TD-002、TD-016 | P1 | 机制段（不依赖专家）✅ **COMPLETED 2026-07-27（Sprint 2A）**：agent.py 升至 1.1.0-phase2.2.2（LLM 成功不再 pending=False，field_provenance/threshold_refs/decision_trace 齐全，顶层 pending 由 provenance 计算对齐 ADR-2.2.1 §7）；新建 agents/design/thresholds/verified.json（D-TH-01~05 全 verified=false、value=null）+ threshold_loader.py + config_loader.load_verified_thresholds；Prompt 专业化（环境感知 + 经济/舒适/高性能三方案约束 + 阈值引用槽位）；local_ci 8/8 全绿 backend 185 passed/覆盖 84.15%、Jest 29 passed/覆盖 93.15%；报告 .ai/reviews/2.2.2_design_professional_report.md。**专家签字段（S2A-3 转正，原 T10 本质）DEFERRED** 待行业专家排期 + 主理人双控，Design 全程保持 Level 0 pending（安全，无编造） |
| 2.2.3 | T11 PDF 方案书增强（客户可交付：可信等级可视化 + 三方案对比 + 防编造） | 质量 | P2 | ✅ **COMPLETED 2026-07-27（Sprint 2B）**：重写 agents/report/generator.py（数据可信等级说明章节 Level0~3 + 环境可信度列/溯源 + 设计经济/舒适/高性能三原型 + 项目基础信息 + 统一徽标不包装 AI 推理为工程确认）；新增 tests/agents/test_report_provenance.py 10 用例；local_ci 8/8 全绿 backend 194 passed/覆盖 84.58%、Jest 29 passed/覆盖 93.15%；pypdf 入 test extras；报告 .ai/reviews/2.2.3_pdf_enhancement_report.md |
| 2.2.4 | TD-015 MinIO 图片存储切换（去重 + 租户隔离） | R4 前置 | P2 | ✅ **COMPLETED 2026-07-27（Sprint 3）**：新建 backend/app/core/storage_backends.py（StorageBackend 抽象 + LocalStorage/MemoryStorage/MinIOStorage 三后端 + get_storage_backend() 按 BOIP_STORAGE_BACKEND 切换 + migrate_storage()）；逻辑 key 统一 {tenant_id}/{sha256}.{ext}（租户隔离 + 内容 hash 去重）；MinIO 密钥仅 .env、缺项 fail-fast、CI 不依赖真实 MinIO（fake-minio 注入测试覆盖逻辑）；uploads.py/vision_tasks.py 接入；local_ci 8/8 全绿 backend 209 passed/覆盖 85%（84.58%→85% 不降反升）、Jest 29 passed/覆盖 93.15%；新增 test_storage_backends.py 15 用例；报告 .ai/reviews/2.2.4_minio_storage_report.md |
| 2.2.5 | 知识库 RAG 奠基：knowledge 表 + 向量检索（T16 前奏） | 中 | P2 | ✅ **COMPLETED 2026-07-27（Sprint 4A）**：新建 agents/llm/embedding.py（EmbeddingProvider + MockEmbeddingProvider 确定性 + OpenAICompatEmbeddingProvider 真实 /embeddings，复用 ProviderRole.EMBEDDING）+ 扩展 build_embedding_provider；backend/app/core/rag/（embeddings 工厂 env 切换默认 mock、vector_store 抽象 InMemory/Qdrant 懒加载、chunking、ingestion 强制 source/created_at/raw_ref）；backend/app/api/rag.py（POST /ingest、POST /search、GET /mode）；入库强制溯源、缺失即拒（禁止无来源入库）；CI 不依赖真实 Embedding/Qdrant（mock+memory）；local_ci 8/8 全绿 backend 224 passed/覆盖 85%（维持）、Jest 29 passed/覆盖 93.15%；新增 test_rag.py 15 用例；报告 .ai/reviews/2.2.5_rag_foundation_report.md |
| 2.2.6 | 多租户 / RBAC 基础（T13 前奏） | 中 | P2 | ✅ **COMPLETED 2026-07-27（Sprint 4B）**：新建 backend/app/db/models/rbac.py（roles/permissions/role_permissions/user_roles 四表，Alembic 637cbf3eafca 双向可逆）+ app/core/security.py（pbkdf2_hmac 密码哈希 + JWT HS256 纯标准库零新依赖 + get_current_user/require_permission）+ app/api/auth.py（/api/auth/login + /me）；三角色 admin/designer/viewer + resource:action 权限模型；保护 uploads/analysis/report 四端点（401/403 错误信封统一），其余 API 保持开放；tenant_id 改由 JWT 服务端签发（弃用 X-Tenant-Id 头）；JWT_SECRET 仅 .env；local_ci 8/8 全绿 backend 246 passed/覆盖 87.34%（≥85% 达标）、Jest 29 passed/覆盖 93.15%；新增 test_rbac.py 17 用例 + 三测试文件 Bearer 改造；报告 .ai/reviews/2.2.6_rbac_foundation_report.md。**Phase 2.2 基础建设收口** |

---

## 4. Phase 3 路线（企业 SaaS + 工程引擎成熟）— 🟢 **Phase 3 Ready（2026-07-28，Phase 3 Readiness 审核通过，开发未启动）** / 🟡 **Phase 3.1 工程智能闭环 DESIGN_READY（2026-07-28，设计完成待审核，未进入编码）**

> 当前处于就绪态，未进入开发。启动前全部准备已完成：文档收敛（3.0）+ 技术债 A/B/C 重分类 + SSOT 同步 + 最终启动准备（git 同步准备 + 施工计划 + SSOT 刷新 + 最终启动报告），见 `.ai/reviews/phase3_readiness_report.md`（能力/架构/债/风险/路线）、`.ai/reviews/phase3_go_report.md`（启动确认/条件/风险/首阶段建议）、`.ai/reviews/phase3_git_sync_report.md`（远端同步清单）、`.ai/tasks/phase3_execution_plan.md`（施工计划）。Phase 3 主线建议顺序：3.1 工程引擎闭环（TD-002/016/005）→ 3.2 企业 SaaS（RBAC 收口 TD-019 / PG TD-011 / 成本 TD-006）→ 3.3 数字孪生。

> **Phase 3.1 设计态（2026-07-28，DESIGN_READY）**：四任务已交付 —— ① 整体架构设计（`.ai/tasks/phase3.1_engineering_architecture_design.md`，含五大模块 + ExpertBackedEngineeringValidation 审核链 + 六门槛 + Design/PDF 连接 + R-E1~R-E7 风险）；② 工程计算 ADR 体系（`.ai/decisions/ADR-phase3.1-engineering-calculation.md`，五模块数据来源/公式来源/规范依据/专家审核点/禁止 AI 自推范围 + §6 实施约束）；③ 专家审核流程（`.ai/tasks/phase3.1_expert_review_process.md`，四步阈值提交 + E-TH-01~06 + 双签 is_fully_verified 升级 + review_log.jsonl）；④ 测试方案（`.ai/tasks/phase3.1_test_plan.md`，单元/集成/安全/防编造四类别 + 六门槛门禁映射）。收口报告见 `.ai/reviews/phase3.1_design_readiness_report.md`。**红线守约**：设计物零真实工程参数、未开 `engineering_enabled`、未写业务代码。🔴 **待主理人审核闭合项**：ADR 阈值 ID `E-TH-wp-01` 与专家流程 `E-TH-01~06` 命名不一致，编码前须统一。**未授权前禁止进入 Phase 3.1 编码。**

- **3.1** T12 工程引擎完整闭环：风压 / 玻璃 / 型材 / 五金 / 评分 / 审核 → 工程安全审核链正式闭合（`engineering_enabled=true` 上线）。**设计已 DESIGN_READY，待主理人审核 + 六门槛全满足后编码。**
- **3.2** T13–T17 企业 SaaS：RBAC / 多租户 / CRM / 知识库 RAG / 销售 AI。
- **3.3** T18–T20 数字孪生 / 施工交付 / 产业生态 / AI 大脑。
- **3.4** 双轨 LLM 成本 / 性能治理（TD-013）正式评估并启用 `track_b`（容灾 / 多供应商）。

---

## 5. 优先级排序（总表）

**排序原则**：安全红线 > 一致性 > 可维护性 > 能力深化 > 新功能。

| 优先级 | 任务 | 理由 |
|---|---|---|
| **P0** | 2.1.1 文档配置对齐、2.1.2 阈值签字、2.1.3 Vision 调优、2.1.4 AsyncSession | 上线前置或一致性硬约束，不可绕过 |
| **P1** | 2.1.5 工程审核能力、2.1.6 provider 解耦、2.1.7 测试基线、2.1.8 PG 验证、2.2.1 环境真实数据、2.2.2 设计转正 | 稳定与可信产出必需 |
| **P2** | 2.1.9 仓库卫生、2.2.3 PDF 美化、2.2.4 MinIO、2.2.5 RAG、2.2.6 RBAC | 深化与规模化的准备 |
| **P3** | Phase 3 全量（T12 闭环 / SaaS / 数字孪生） | 远期战略 |

---

## 6. 技术债偿还计划

| 债 | 级别 | 偿还阶段 | 动作 |
|---|---|---|---|
| TD-002 工程阈值未确认 | 高 | 2.1.2 | 专家签字转正 |
| TD-016 Vision prompt 调优 | 高 | 2.1.3 | 专家调优 + 评测集 |
| TD-012 Session 异步 | 中 | 2.1.4 | AsyncSession |
| TD-011 SQLite↔PG JSONB | 中 | 2.1.8 | PG 验证 + gin 评估 |
| TD-013 双轨成本/性能 | 高 | 2.1.6（provider 分离已偿还）/ Phase3 | provider 分离 + 启用评估 |
| TD-017 配置注释漂移 | 中 | 2.1.1 | 清理注释（C1） |
| TD-018 analysis/report 缺文档 | 中 | 2.1.1 | 补文档（D7/D8） |
| TD-006 LLM 选型 | 中 | **已解（ADR-001）** | 标记 RESOLVED |
| TD-014 真实 LLM key | IN_PROGRESS | **已解（TokenHub）** | 标记 RESOLVED |
| TD-008 密钥管理基建 | 中 | 2.1.1 启动 | Vault/云密钥前置（正式环境前置） |
| TD-001 阶段编号 | 中 | 2.2 | 统一编号 |
| TD-003 文档/代码联动 | 中 | 2.1.1 | CI 文档检查 |
| TD-015 MinIO | 中 | 2.2.4 | 存储切换（✅ **RESOLVED 2026-07-27**） |
| TD-005 Agent 数量 | 低 | Phase3 | 评估取舍 |
| TD-007 i18n | 低 | Phase3 | 评估 |
| TD-009 前端组件库 | 低 | Phase3 | 评估 |
| TD-010 后端拆分粒度 | 中 | Phase3 | 评估 |

**偿还节奏（技术债册规则）**：Phase 1 末 OPEN≤10（已超标，当前 14）；**Phase 2.1 末 OPEN≤8；Phase 2.2 末 OPEN≤5**。TD-006/TD-014 因 ADR-001 + TokenHub 接入标记 RESOLVED；TD-015 因 2.2.4 存储抽象标记 RESOLVED（2.2.4 后 OPEN=13，距 ≤5 仍有差距，后续需还清其余 OPEN 债）。

---

## 附：与 V1 路线（`project_status.json.roadmap`）的差异

- V1 `roadmap.immediate_doc_sync_no_code` 已部分落地（README 对齐、ADR-001、provider_status、文档索引）；剩余文档刷新并入 **2.1.1**。
- V1 未区分"稳定"与"深化"，V2 显式拆为 **2.1 架构稳定 / 2.2 能力深化**，并明确各自出口标准。
- V2 将技术债（TD-001~018）逐条映射到阶段与动作，闭环"债册—路线"联动（呼应 TD-003）。
- V2 严守红线：`engineering_enabled` 与行业阈值在 2.1.2/2.1.3/2.1.5 完成前不得上线。

**END**
