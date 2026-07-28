# BOIP Phase 3 施工计划（phase3_execution_plan.md）

- **生成**：2026-07-28（Phase 3.0 Final Go Preparation）
- **身份**：BOIP AI CTO
- **性质**：**计划文档，不编写任何业务代码**（本阶段仅做启动准备）。本文件描述 Phase 3 主线分解，供主理人评审后作为 Phase 3 执行的任务书。
- **依据**：`.ai/project_status.json`（SSOT，current_phase="Phase 3 Ready"）、`.ai/roadmap_v2.md`、`.ai/technical_debt/README.md`、`.ai/reviews/phase3_readiness_report.md`
- **红线（不可逾越）**：任何无据行业数字必须标 `pending_verification`；工程参数（风压/楼层/评分权重）未经专家签字不得转正；`engineering_enabled` 在 Phase 3.1 显式门槛达成前保持 `false`。

---

## 1. Phase 3 总体目标

把「机制就绪但未闭环」的平台，推进为「工程可信 + 企业可用 + 知识智能」的生产级产品，同时**严守安全红线**（不编造、不未经审核上线工程计算）。

**三大主线**：

| 主线 | 目标 | 关键产出 |
|---|---|---|
| **3.1 工程智能闭环** | 工程安全审核链正式闭合，行业阈值经专家签字转正，`engineering_enabled=true` 可控上线 | Engineering Agent 真实计算 + 阈值体系（已验证）+ 专家审核链 + 安全评分 |
| **3.2 企业 SaaS** | 多租户企业能力闭环，前端接入鉴权，用户可管理，数据层生产化 | 前端 `/login` 对接、JWT refresh、用户管理、SQLite→PostgreSQL 迁移 |
| **3.3 知识智能** | 行业知识库 + RAG 问答链 + 答案引用体系，成为设计辅助的"可信知识底座" | RAG 问答链、行业知识库入库、引用/溯源体系 |

**跨主线约束**：
- 技术债按 A/B/C 台账偿还（见 §5）。
- 每阶段结束必须 `local_ci.sh` 8/8 全绿且覆盖率不降（backend ≥60%、前端 ≥50%，实际基线 backend 87.34% / 前端 93.15%）。
- 所有外部服务（LLM/Embedding/MinIO/Qdrant/PG）支持 mock/disabled/fallback，CI 永不依赖真实外部服务。

---

## 2. Phase 3.1 工程智能闭环计划

> **目标**：在 2.1.5 Engineering Agent 骨架（enabled:false，仅接口契约）基础上，补真实工程计算 + 阈值体系（专家转正）+ 专家审核链，达成安全上线门槛后开启 `engineering_enabled`。

### 2.1 Engineering Agent（真实计算）
- **现状**：`agents/engineering/agent.py` 骨架已建（2.1.5）：五分析接口 `wind_pressure` / `glass_safety` / `profile` / `hardware` / `installation_risk`，统一输出四字段 `{result, confidence, evidence, verification_status:pending_verification}`，骨架内字段恒空串防编造；`EngineeringValidation` 抽象契约 + `PendingEngineeringValidation` 结构校验已实现。
- **Phase 3.1 动作**：
  1. 在 `agents/engineering/` 下实现五分析的真实计算逻辑（风压计算模型、玻璃安全系数、型材强度、五金选型、安装风险评分），所有数值来源强制回写 `evidence`（公式/规范条目/专家签字 ID）。
  2. 计算结果 `verification_status` 仍默认 `pending_verification`，仅当对应阈值已 `verified=true` 且经专家审核链通过，才允许标记受控确认。
  3. 不绕过红线：无据数值一律 pending；不得直接写死行业常数。

### 2.2 阈值体系
- **现状**：`agents/design/thresholds/verified.json`（D-TH-01~05，全 `verified=false`、`value=null`）+ `agents/design/threshold_loader.py`（`load_verified_thresholds` / `is_fully_verified` / `resolve_field_provenance` / `build_threshold_refs`）。Engineering 侧阈值沿用同套机制（新建 `agents/engineering/thresholds/verified.json`）。
- **Phase 3.1 动作**：
  1. 行业专家排期评审，填写工程阈值（风压/楼层/评分权重等）到 `verified.json`，`verified_by` / `verified_at` 双控落库。
  2. `is_fully_verified()` 作为 `engineering_enabled` 开启的硬前置；任一关键阈值未 verified → 计算链降级 pending，不报送"工程确认"。
  3. 阈值变更留审计痕迹（谁、何时、依据哪份规范）。

### 2.3 专家审核链
- **现状**：`EngineeringValidation` 抽象 + `review_chain` 逐接口落记录，验证器可注入替换（2.1.5）。
- **Phase 3.1 动作**：
  1. 实现 InjectableReviewer：专家签字 → `verification_status` 由 pending 翻为受控确认（需主理人 + 行业专家双签，呼应 ADR-2.2.1/2.2.2 双控）。
  2. 审核链输出结构化报告（每个接口：输入/计算/证据/审核结论/签字），进入 PDF 方案书可信等级章节。
  3. 审核链未闭合的接口，前端/API 仅展示"AI 推理·待确认"，绝不包装成工程确认。

### 2.4 `engineering_enabled` 开启条件（准入门槛）
满足**全部**以下条件方可置 `config.yaml: engineering.enabled=true`：
1. `agents/engineering/thresholds/verified.json` 关键阈值 `is_fully_verified() == True` 且 `verified_by`/`verified_at` 齐备（TD-002 偿还）。
2. `Vision prompt` 专家调优完成并附评测集（TD-016，与 2.1.3 同批）。
3. Engineering Agent 五接口真实计算单元测试 + 集成测试通过，`local_ci.sh` 8/8 全绿。
4. 专家审核链端到端跑通（注入式 Reviewer 双签生效）。
5. 主理人最终授权（本计划评审通过 + 验收）。

---

## 3. Phase 3.2 企业 SaaS 计划

> **目标**：把 2.2.6 RBAC 地基（三角色、JWT HS256、四端点保护、tenant 由 JWT 签发）推进为企业可用闭环。**本阶段不开发 CRM / 销售 AI / 完整 SaaS 业务功能**，仅做鉴权与数据层生产化前置（受"禁止事项"约束）。

### 3.1 前端 `/login` 对接（TD-019 收敛）
- **现状**：前端 `/login` 页面已存在（`frontend/src/pages/login.tsx`）但未对接 `POST /api/auth/login`；当前匿名开发模式。
- **动作**：对接 `POST /api/auth/login`（统一 401 防枚举）→ 存储 JWT → 受保护路由读 `GET /api/auth/me` 渲染角色；`User.role` 遗留列收敛到 `user_roles` 新表。

### 3.2 JWT 完善 + Refresh Token（TD-019）
- **现状**：`backend/app/core/security.py` 仅 access token（HS256，纯标准库，零新依赖）；无 refresh/吊销机制。
- **动作**：新增 refresh token（独立签名/短生命周期 access + 长生命周期 refresh，存储于服务端可吊销表或签名白名单）；实现 `/api/auth/refresh`；logout 支持吊销；密钥仅 `.env`（gitignored），fail-closed。

### 3.3 用户管理（RBAC 收口 TD-019）
- **现状**：权限模型 `resource:action`（upload/analysis/report create/read + user:manage/tenant:manage）已建；`seed_rbac_catalog` 注入目录 + 三演示账户。
- **动作**：实现 `user:manage` 端点（创建/停用/角色分配，受 admin 保护）；停用用户即时失效（已有 403 测试）；tenant 级用户隔离。

### 3.4 PostgreSQL 迁移（TD-011）
- **现状**：SQLite 占位 + Alembic；JSONB 差异未验证（R5）。
- **动作**：接 PG 后验证 JSONB 查询 + `gin` 索引；`EXPLAIN ANALYZE` 评估；Alembic 迁移兼容双方言；CI 仍可用 SQLite 跑回归（PG 仅集成校验）。

---

## 4. Phase 3.3 知识智能计划

> **目标**：把 2.2.5 RAG 基础设施（embedding 抽象 + 向量库抽象 + ingest/search API + 强制三要素溯源）升级为可用的知识问答能力。

### 4.1 RAG 问答链
- **现状**：`backend/app/core/rag/`（embeddings 工厂默认 mock、vector_store InMemory/Qdrant 懒加载、chunking、ingestion 强制 source/created_at/raw_ref）+ `backend/app/api/rag.py`（ingest/search/mode）；默认 `BOIP_EMBEDDING_PROVIDER=mock`。
- **动作**：接真实 Embedding（显式 env 配置后启用，不默认开）→ 检索命中 chunks → 注入 LLM 生成答案（track_a）→ 答案回带 chunk 引用；端到端问答接口 `POST /api/rag/ask`（或扩展 search）。

### 4.2 行业知识库
- **动作**：建立行业知识入库流程（规范条文/案例/产品库），经 `ingest` 强制三要素溯源入库；缺 source/created_at/raw_ref 即拒（已有 `IngestionError` 防护）；知识库内容治理（谁维护、更新频率）。

### 4.3 引用体系
- **动作**：答案标注引用块（来源文档 + 段落 + 入库时间 + raw_ref），前端渲染可点击溯源；与 PDF 方案书可信等级体系打通（同源 provenance 模型）。

---

## 5. 技术债偿还路线

依据 `.ai/technical_debt/README.md` A/B/C 台账（当前 OPEN=11）：

| 债 | 级别 | 偿还阶段 | 动作 |
|---|---|---|---|
| TD-002 工程阈值未确认 | **A（Phase3前必须）** | 3.1 | 专家签字转正 verified.json（高，阻塞工程闭环） |
| TD-008 密钥管理基建 | **A（Phase3前必须）** | 3.2 前置 | Vault/云密钥（中→高，SaaS 前置） |
| TD-019 RBAC 遗留收敛 | **A（Phase3前必须）** | 3.2 | refresh token / 前端 login 对接 / User.role 双轨收敛 |
| TD-011 SQLite↔PG JSONB | B（Phase3期间） | 3.2 | PG 验证 + gin 评估 |
| TD-016 Vision prompt 调优 | B（Phase3期间） | 3.1（与 TD-002 同批） | 专家调优 + 评测集 |
| TD-006 LLM 选型/成本评测 | B（Phase3期间） | 3.1（并入原 TD-013 成本项） | 双轨成本/性能治理 |
| TD-010 后端拆分粒度 | B（Phase3期间） | 3.2 | 评估拆分 |
| TD-005 Engineering 启用决策 | B（Phase3期间） | 3.1 | enabled 决策（受 §2.4 门槛约束） |
| TD-001 阶段编号不一致 | C（长期） | — | SSOT 已隔离影响（中→低） |
| TD-007 i18n | C（长期） | — | 评估 |
| TD-009 前端组件库 | C（长期） | — | 评估 |

**偿还节奏（OPEN 计数）**：11 → login 对接后 10 → 专家评审批（TD-002/016）后 8 → Phase 3.1/3.2 收口后 5（达标线）。

---

## 6. 每阶段验收标准

### 3.1 工程智能闭环 — 验收门槛
- [ ] `agents/engineering/thresholds/verified.json` 关键阈值 `is_fully_verified()==True`，`verified_by`/`verified_at` 齐备（TD-002）。
- [ ] Vision prompt 专家调优完成 + 评测集（TD-016）。
- [ ] Engineering Agent 五接口真实计算 + 单元测试/集成测试通过。
- [ ] 专家审核链端到端跑通（双签生效，报告结构化）。
- [ ] `engineering_enabled=true` 仅在上述全满足后开启，且 `local_ci.sh` 8/8 全绿、覆盖率不降。
- [ ] 无编造事件（编造/硬编码扫描通过）。

### 3.2 企业 SaaS — 验收门槛
- [ ] 前端 `/login` 对接 `POST /api/auth/login`，受保护路由读 `/me`（TD-019）。
- [ ] refresh token + `/api/auth/refresh` + logout 吊销（TD-019）。
- [ ] `user:manage` 端点 + 角色分配 + 停用即时失效（TD-019）。
- [ ] SQLite→PostgreSQL 迁移 + JSONB/gin 验证通过（TD-011）。
- [ ] 密钥基建（TD-008）就绪（Vault/云密钥或等价方案）。
- [ ] `local_ci.sh` 8/8 全绿、覆盖率不降。

### 3.3 知识智能 — 验收门槛
- [ ] 真实 Embedding 接入（显式 env 启用），检索命中准确。
- [ ] RAG 问答链端到端（检索 → LLM 生成 → 答案带引用）。
- [ ] 行业知识库入库流程 + 三要素溯源强制（缺 source 即拒）。
- [ ] 引用体系前端渲染可点击溯源，与 PDF 可信等级打通。
- [ ] `local_ci.sh` 8/8 全绿、覆盖率不降。

---

**END**（本文件为计划，不含代码实现；执行须在主理人授权 Phase 3 后启动）
