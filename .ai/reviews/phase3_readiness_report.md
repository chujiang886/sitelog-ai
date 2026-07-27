# BOIP Phase 3 启动准备报告（Phase 3 Readiness）

- **生成**：2026-07-28（Phase 3.0 前置整理 Sprint）
- **身份**：BOIP AI CTO
- **目的**：在 Phase 3 启动前给出权威「准备度」结论 —— 当前能力 / 架构基线 / 技术债 / 风险 / 建议路线。供主理人验收并决策 Phase 3 启动时机。
- **关联**：`.ai/roadmap_v2.md` §4、`.ai/project_status.json`（SSOT）、`.ai/technical_debt/README.md`、`.ai/reviews/phase2.2_release_freeze_report.md`

> **状态声明**：本报告生成时 **Phase 3 开发未启动**，当前处于 **Phase 3 planning**。3.0 前置整理（Git 冻结 + 文档收敛 + 技术债 A/B/C 重分类 + SSOT 同步）已完成。

---

## 1. 当前能力（Capabilities）

Phase 2.2 在稳定架构上把占位能力做实，六 Sprint 全部交付：

| 能力域 | 状态 | 说明 |
|---|---|---|
| **LLM 双轨** | ✅ 生产可用 | `track_a` = 腾讯混元 TokenHub `HY-Vision-2.0-Instruct`（openai_compat，文本+视觉共用）；`track_b`=mock；ADR-001 确立 `.env::LLM_A_*` 唯一事实源 |
| **Environment Agent** | ✅ 机制做实 | 数据 Provider 抽象层（base/mock/factory），field_provenance 溯源 + pending 语义；真实 weather/gis 厂商按 ADR 流程 DEFERRED |
| **Design Agent** | ✅ 机制做实 | 三方案专业化（经济/舒适/高性能）；`thresholds/verified.json` 机器可读结构；LLM 成功不再误标 pending；专家签字字段 DEFERRED（全程 Level 0 pending，无编造） |
| **Report Agent** | ✅ 可交付 | PDF 方案书含可信等级可视化（Level 0~3）+ 三方案对比 + 防编造溯源；pypdf 校验 |
| **Engineering Agent** | 🟠 骨架已建 | `agents/engineering/*` 五接口统一输出 + EngineeringValidation 审核链；`enabled:false` 未进管道（安全决策） |
| **Storage 抽象** | ✅ 多做 | `StorageBackend` 抽象 + Local/Memory/MinIO 三后端；逻辑 key `{tenant_id}/{sha256}.{ext}` 租户隔离 + 内容去重 |
| **RAG 基础设施** | ✅ 地基 | embedding（Mock/OpenAICompat）+ vector_store（InMemory/Qdrant 懒加载）+ chunking/ingestion 强制溯源；`/api/rag/ingest|search|mode` |
| **RBAC 企业权限** | ✅ 地基 | 四表（roles/permissions/role_permissions/user_roles）+ JWT HS256 纯标准库 + 三角色 + 受保护端点鉴权矩阵；tenant 由 JWT 签发 |
| **PDF / 流式** | ✅ | `/api/report/generate` 流式 PDF；`/api/analysis/run` 串联三 Agent → dossier |
| **前端** | ✅ | 8 页面 + 29 Jest 用例（覆盖 93.15%）；登录页为占位，未对接 `/api/auth/login` |
| **后端路由** | ✅ | 11 个 router（含 `/api/auth/*`、`/api/rag/*`） |
| **数据层** | ⚠️ 占位 | 10+ ORM 模型；**SQLite 占位**；Alembic 迁移；RBAC migration `637cbf3eafca` |

**测试基线**：backend **246 passed / 覆盖 87.34%** + 前端 **29 passed / 覆盖 93.15%** = **275 passed**；`local_ci.sh` 8/8 全绿。

---

## 2. 架构基线（Architecture）

```
用户浏览器 (Next.js 14 + TS + Tailwind + Zustand)
        │  REST / WS
        ▼
FastAPI 后端 (backend/app)
  ├─ api/        11 routers (analysis/report/agents/uploads/vision/
  │               conversations/projects/knowledge/health/auth/rag)
  ├─ core/       rag/ · security(JWT) · storage_backends · config
  ├─ db/         SQLAlchemy2 models + AsyncSession + Alembic
  └─ main.py     装配
        │  invoke(AgentContext)->AgentResult
        ▼
多 Agent 运行时 (agents/)
  ├─ environment  (Provider 抽象 + field_provenance)
  ├─ design       (三方案 + verified.json + decision_trace)
  ├─ report       (PDF 可信交付 + 防编造)
  └─ engineering  (骨架 enabled:false，审核链就绪)
        │
        ▼
LLM Provider 抽象 (agents/llm)
  ├─ track_a: 腾讯混元 TokenHub (文本+视觉)
  └─ track_b: mock (容灾保留)
```

**架构治理要点**：
- **SSOT**：`.ai/project_status.json` 为机器可读单一事实来源；`.ai/` 体系（tasks/reviews/decisions/technical_debt）为人读镜像。
- **防编造铁律**：任何无据行业数字标 `pending_verification`；工程参数（风压/楼层/评分权重）未经专家签字不得转正（红线）。
- **溯源机制**：Environment `field_provenance`、Design `threshold_refs/decision_trace`、RAG 入库强制 source/created_at/raw_ref。
- **渐进保护**：真实外部数据源按 ADR 流程 DEFERRED；Engineering 骨架 `enabled:false`。

---

## 3. 技术债（Tech Debt）— A/B/C 重分类

> 全量台账见 `.ai/technical_debt/README.md`；OPEN = **11**（3.0 偿还 TD-003/017/018 + TD-013 收口，较 Phase 2.2 末 13 下降）。

### A 类：Phase 3 启动前必须（3 项）🔴
| 债 | 级 | 阻塞点 |
|---|---|---|
| **TD-002** 工程阈值未确认 | 高 | 3.1 工程闭环唯一硬阻塞（安全红线 + 产品价值） |
| **TD-008** 密钥管理基建缺失 | 中→高 | SaaS 生产部署硬门禁（JWT/LLM/MinIO 密钥轮换/托管） |
| **TD-019** RBAC 遗留收敛 | 中 | ② 前端 login 对接（SaaS 首步前置）；③ `User.role` 双轨授权隐患 |

### B 类：Phase 3 期间处理（5 项）
| 债 | 级 | 绑定子阶段 |
|---|---|---|
| **TD-011** SQLite↔PG JSONB | 中 | 3.2 接真实 PG |
| **TD-016** Vision prompt 调优 | 高 | 3.1 与 TD-002 同批专家 |
| **TD-006** LLM 选型/成本评测 | 中 | 3.1 |
| **TD-010** 后端拆分粒度 | 中 | 3.2 负载出现后 |
| **TD-005** Engineering 启用决策 | 低→中 | 3.1 |

### C 类：长期优化（3 项）
| 债 | 级 | 说明 |
|---|---|---|
| **TD-001** 阶段编号不一致 | 中→低 | SSOT 已隔离 |
| **TD-007** i18n | 低 | 无海外需求前不做 |
| **TD-009** 前端组件库 | 低 | 规模翻倍前不引入 |

**还债路线（达成 OPEN≤5）**：Phase 3 启动前清 TD-019② → OPEN 10；3.1 同批专家解 TD-002+TD-016 → OPEN 8；3.1~3.2 清 TD-005/006/019①③ → OPEN 5。

---

## 4. 风险（Risks）

| 风险 | 状态 | 说明 |
|---|---|---|
| R1 文档滞后 | ✅ RESOLVED（3.0） | README/CHANGELOG/LLM.md/AGENTS.md/API.md 刷至 Phase 2.2 COMPLETED |
| R2 provider 矛盾 | ✅ RESOLVED（2.1.6+3.0） | `.env::LLM_A_*` 唯一事实源全文档贯彻 |
| R3 async 阻塞 | ✅ RESOLVED（2.1.4） | AsyncSession 已验证 |
| R4 工程审核链未闭环 | 🟠 OPEN | 依赖 TD-002 专家签字（3.1） |
| R5 PG 生产化 | 🟠 OPEN | 依赖 TD-011（3.2） |
| R6/R7 测试基线 | ✅ RESOLVED（2.1.7） | 基线已刷新，R7 不复现 |
| R8 仓库卫生 | ✅ RESOLVED（3.0） | `.next.trash`/`deliverables`/`backend-storage`/`coverage.xml` 忽略 |
| **R-N1 未 commit** | ✅ RESOLVED（3.0） | 5 批提交完成 |
| **R-N2 未 push 远端** | 🟠 **OPEN（medium）** | 本地 `master` 领先 `origin/master`；主理人验收后 `git push` |

**结论**：无 P0 级遗留风险阻断 Phase 3 规划；R-N2 为唯一待主理人动作的运维项。

---

## 5. Phase 3 建议路线（Recommended Route）

**总原则**：安全红线 > 一致性 > 工程闭环 > SaaS 规模 > 远期战略。

### 3.1 工程引擎闭环（最高优先，绑定 TD-002/016/005）
- 主理人排期**行业专家评审**：回填 `verified.json`（风压/楼层/评分权重）→ Design 转正。
- Engineering Agent `enabled=true` 上线，闭合风压/玻璃/型材/五金/评分/审核全链路。
- Vision prompt 专家调优（与阈值评审同批，省专家时间）。
- 出口：`engineering_enabled=true` + 阈值全部 verified + 审核链生产可用。

### 3.2 企业 SaaS（绑定 TD-019/011/006/010）
- **RBAC 收口**：前端 `/login` 对接 `/api/auth/login`（TD-019②）；refresh token/吊销设计（TD-019①）；`User.role` 双轨收敛（TD-019③）。
- **数据层生产化**：SQLite → PostgreSQL，JSONB + gin 索引评估（TD-011）。
- **LLM 成本治理**：TokenHub 账单回填 + 成本/性能评测，定长期选型（TD-006，并入原 TD-013 成本项）。
- **CRM / 知识库 RAG 问答 / 销售 AI**：基于 2.2.5 RAG 地基与 2.2.6 RBAC 渐进。
- **密钥基建**：云 Secrets Manager（腾讯云 SSM）方案定稿（TD-008 生产硬门禁）。

### 3.3 数字孪生 / 施工交付 / 产业生态 / AI 大脑
- 远期战略，依赖 3.1/3.2 夯实后机会性推进。

### 3.4 双轨 LLM 治理
- 启用 `track_b`（容灾/多供应商）正式评估（TD-013 成本项）。

---

## 6. 启动前清单（Go/No-Go）

| 项 | 状态 |
|---|---|
| 文档与代码一致（D2–D7 闭环） | ✅ |
| 技术债 A/B/C 分类清晰、路线可达 OPEN≤5 | ✅ |
| SSOT（project_status.json / roadmap_v2）同步至 Phase 3 planning | ✅ |
| 测试基线 8/8 全绿、覆盖率不降 | ✅ |
| 版本冻结（R-N1 消除） | ✅ |
| 主理人验收本报告 | ⏳ 待办 |
| `git push origin master`（R-N2） | ⏳ 验收后 |

**建议**：主理人验收后 `git push` 并启动 3.1 工程引擎闭环（优先排专家评审 TD-002/016）。**当前不得直接进入 Phase 3 开发，须先验收。**

**END**
