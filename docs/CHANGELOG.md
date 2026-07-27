# BOIP 工程实施变更记录

本文件按时间顺序记录仓库工程变更，与上游设计文档互补；每次实施必须补充任务号、范围、影响、证据与责任人。

## 格式

```
## YYYY-MM-DD | <任务号> | <责任人>

- 范围：...
- 关键变更：...
- 验证：...
- 影响文档：...
- 关联技术债：...
```

---

## 2025-01-XX | T02 | 软件工程师·寇豆码

- 范围：Phase 0 前后端骨架扩展。
- 关键变更：新增 `/api/projects`、`/api/agents`、`/api/knowledge/rules` 路由；统一错误处理与开发 CORS；补充配置字段、Pydantic 健康模型与异步路由测试；新增前端多路由占位、API 客户端、Zustand UI store、跨层契约类型、主题色与健康测试。
- 文档：新增 `docs/API.md` 与 `docs/FRONTEND_STRUCTURE.md`，同步 `docs/PHASE0_LOG.md`。
- 业务边界：未连接真实外部服务，未实现业务逻辑；工程数值保持 `pending_verification`。
- 验证：待执行 T02 全量测试。


- 范围：建立 Phase 0 项目骨架（monorepo + 前端占位 + 后端占位 + Agent 文档骨架 + 部署配置 + 脚本 + 跨层测试入口）。
- 关键变更：
  - 新增 monorepo 目录：`frontend/`、`backend/`、`agents/`、`deployment/`、`docs/`、`tests/`、`scripts/`
  - 根目录新增 `.gitignore`、`.editorconfig`、`.nvmrc`、`.python-version`、`package.json`、`docker-compose.yml`、`.env.example`、`README.md`、`CONTRIBUTING.md`、`LICENSE`
  - 前端占位：Next.js 14 + TS + Tailwind + Zustand + Jest；`/api/health` 返回 `{success, data}` 信封
  - 后端占位：FastAPI + Pydantic Settings；`/health` 返回 `{success, data}` 信封；Alembic 配置占位
  - Agent 骨架：`BaseAgent`、`AgentRegistry`、`AgentContext`、`AgentResult`、`Evidence`，提供四个 Agent 目录的 `agent.md` / `prompt.md` / `tools.md` / `tests.md`
  - 部署：`docker-compose.yml` 五个服务（PostgreSQL / Redis / Qdrant / MinIO / Backend）、Dockerfile 模板、Nginx 反向代理占位、监控配置占位
  - 脚本：业务数字杜撰扫描、硬编码业务配置扫描、本地 CI
  - 测试：后端健康检查单元测试 + 前端 Jest 占位 + 评测集入口规范
- 验证：
  - `pytest backend/tests/test_health.py -v` 通过
  - `npm test -- --passWithNoTests` 通过（前端尚未添加测试用例）
  - `bash scripts/ci/local_ci.sh` 全部阶段通过
  - 业务数字扫描未发现未验证数值
  - 硬编码扫描未发现业务阈值、品牌或型号
- 影响文档：新增 `docs/README.md`、`docs/PHASE0_LOG.md`、本文件；未修改上游设计文档。
- 关联技术债：TD-001 至 TD-010 全部维持 OPEN；未新增技术债。

## 待办任务记录

- T04 / T05：见 `docs/PHASE0_LOG.md` 中的实施计划。

---

## 2025-01-XX | T03 | 软件工程师·寇豆码

- 范围：Phase 0 数据库骨架（ORM 模型 + Alembic 迁移 + 种子 + 测试 + 文档）。
- 关键变更：
  - 新增 `backend/app/db/{base.py, session.py, __init__.py}`：DeclarativeBase + NamingConvention + 同步 Session 工厂 + `get_db` 依赖。
  - 新增 `backend/app/db/models/{tenant, user, project, agent, knowledge, audit, threshold, __init__}.py`：8 张业务表，每张含 `tenant_id` FK、`status` CheckConstraint、`server_default=func.now()`、`deleted_at` 软删除字段；自定义 `GUID` 跨 PG/SQLite。
  - 新增 `backend/alembic/{env.py, script.py.mako, versions/.gitkeep}` 与首个 migration `d17f02429ce9_phase0_init_schema.py`；SQLite 自动 `render_as_batch`。
  - 新增 `backend/scripts/seed.py`：幂等写入 1 tenant + 1 user + 4 agents + 5 knowledge_rules + 5 knowledge_cases + 1 threshold_config；业务数值全部 `pending_verification`。
  - 新增 `backend/tests/test_db.py`（6 项）与 `backend/tests/test_migrations.py`（3 项，含 SQLite 端到端 upgrade/downgrade 演练）。
  - `scripts/ci/local_ci.sh` 升级为 6 步：pytest + jest + alembic roundtrip + seed + 业务数字扫描 + 硬编码扫描。
  - 新增 `backend/docs/DATABASE.md`：选型、8 表清单、Mermaid ER 图、tenant_id 隔离、迁移指南、种子说明。
- 验证：
  - `pytest tests/ -v` 全部 15 项 PASSED（含 9 项新增）。
  - `bash scripts/ci/local_ci.sh` 6 步全部 PASSED（alembic upgrade head + downgrade base + 种子脚本）。
  - 业务数字扫描与硬编码扫描通过。
- 影响文档：新增 `backend/docs/DATABASE.md`、`docs/PHASE0_LOG.md` 追加 T03 段、本文件追加 T03 条目；新增 `BOIP_AI_Documents/technical_debt.md` 中 TD-011 / TD-012。
- 关联技术债：TD-011（SQLite ↔ PG JSONB 差异）、TD-012（同步 Session ↔ 异步 Session）。
- 业务边界：未连接真实 PostgreSQL；所有业务字段保持 `pending_verification`；未实现任何业务逻辑。

## 2025-01-XX | Phase 0 整体验收 | 软件工程师·寇豆码

- 范围：Phase 0 终验报告 + T01-T05 状态确认；新增 `docs/PHASE0_DONE.md`，同步更新本文件与 `README.md` 顶部阶段状态。
- 关键变更：
  - 新增 `docs/PHASE0_DONE.md`：T01-T05 状态表（IS_PASS：YES 五项全绿）、真实测试结果（pytest 65 项 + jest 6 项 + local_ci 8 步）、关键文件清单、已知未完成项（`docs/AGENTS.md` 缺失 / `test_factories.py` 收集冲突 / 真实 LLM 未接入 / 真实 PG/Redis/Qdrant/MinIO 未连 / 前端组件库未建）、技术债总览（11 OPEN + 1 RESOLVED + 6 FUTURE）、Phase 1 启动建议。
  - `README.md` 顶部阶段状态行由"Phase 0 / T01-T05 全部待办"改为"Phase 0 完成 / 进入 Phase 1"，并附 `docs/PHASE0_DONE.md` 与 `docs/PHASE0_LOG.md` 链接。
  - 本文件追加 Phase 0 整体验收条目。
- 验证：
  - `pytest backend/tests tests/agents tests/e2e --cov=app --cov=agents` ⇒ 65/65 passed / Coverage **91.18%**（门禁 60%）。
  - `npm test` ⇒ 2 suites / 6 tests passed；带 coverage ⇒ Stmt **93.15%** / Branch 78.57% / Funcs 100% / Lines 93.15%（门禁 50%）。
  - `bash scripts/ci/local_ci.sh` ⇒ 8 步全部 PASS（Ruff / pytest+coverage / ESLint / jest+coverage / alembic upgrade+downgrade / seed 1+1+4+5+5+1 / 业务数字扫描 / 硬编码扫描）；终态 `Local CI passed.`。
  - `bash scripts/ci/check_phase0_done.sh` ⇒ 全部产物 + 完成标记一致；终态 `Phase 0 verification passed.`。
- 影响文档：
  - 新增 `docs/PHASE0_DONE.md`。
  - 修改本文件追加 Phase 0 验收条目。
  - 修改 `README.md` 顶部阶段状态行。
  - 未修改 `BOIP_AI_Documents/` 下任何 18 份设计文档 / 4 份寇豆码方案。
  - 未修改 T01-T05 任何既有代码 / 既有工程文档。
- 关联技术债：
  - TD-004 维持 **RESOLVED**（T05 已硬约束 60%/50% 门禁）。
  - TD-001 ~ TD-003、TD-005 ~ TD-012 维持 OPEN，共 11 条（低于 Phase 0 末目标 15 条）。
  - 新增 Phase 1 待办项：修复 `backend/tests/test_factories.py` 在合并收集时的 import 冲突；详见 `docs/PHASE0_DONE.md` 第四章。
- 业务边界：未连接真实 LLM / PostgreSQL / Redis / Qdrant / MinIO；所有业务字段保持 `pending_verification`；未实现任何业务逻辑。`docs/AGENTS.md` 未单独建，Agent 说明分布在 `agents/README.md` + 各 Agent `agent.md`，是否补建交由主理人决策。
- 整体结论：**Phase 0 IS_PASS：YES**，可进入 Phase 1。

## 2025-01-XX | T06（Phase 1 / T06a + T06b + T06c） | 软件工程师·寇豆码

- 范围：Phase 1 对话能力端到端落地（LLM 抽象 + NLU + 后端会话 API + 前端 chat UI + 文档 / 配置）。
- 关键变更：
  - **agents**：新增 `agents/llm/` 双轨 LLM 抽象（OpenAI / Anthropic 兼容 + MockProvider + DualTrackRouter）；`agents/core/nlu.py` 规则+LLM 增强意图提取；`agents/core/orchestrator.py::chat()` 串联 NLU + 占位 step + placeholder_reply。
  - **后端**：新增 `Conversation` / `Message` ORM（带 CheckConstraint / Index / JSONB intent+evidence）；Alembic 迁移 `eb1c2d3e4f5a_phase1_t06_conversations`；4 条 REST 路由 + tenant 隔离 + chat 编排降级；9 项测试覆盖。
  - **前端**：`types/chat.ts` 契约 + `lib/chat.ts` API 封装；`components/IntentBadge` + `components/ChatMessage`；`app/consult/page.tsx` 完整聊天页（自动建会话、乐观发送、历史拉取、加载/错误态）；3 项 Jest 测试。
  - **配置**：`agents/config.yaml` 追加 `llm.*` 双轨段；`.env.example` 追加 6 个 LLM 占位。
  - **文档**：新增 `docs/LLM.md`（双轨架构 + provider 切换 + 成本/性能占位）、`docs/CONVERSATION_API.md`（4 路由 + 信封 + 错误码）、`docs/AGENTS.md`（Agent 清单 + invoke 协议 + chat 时序）；同步 `docs/PHASE0_LOG.md` 与本文件。
  - **技术债**：`BOIP_AI_Documents/technical_debt.md` 新增 TD-013 / TD-014，OPEN 总数 12 → 14。
- 验证（待本轮结束真实命令输出）：
  - `pytest tests/ tests/agents/ -v --tb=short` 应全绿，新增 9 项 T06b 集成测试。
  - `npm test` 应 3 suite / 6+ tests passed。
  - `bash scripts/ci/local_ci.sh` 8 步全绿（Ruff / pytest+coverage / ESLint / jest+coverage / alembic roundtrip / seed / fabrication scan / hardcoded scan）。
- 业务边界：
  - 未连接真实 LLM / PG；`llm.enabled=false` 维持；所有 chat 回复 `pending_verification=true`；
  - `agents/core/orchestrator_chat_integration.py` 前序交付物格式异常，但未被任何代码 import，不影响运行（已在 PHASE0_LOG 显式登记）；
  - 未修改 18 份上游设计文档 + 4 份寇豆码方案 + T01-T05 既有产物。
- 关联技术债：TD-013（双轨 LLM 成本/性能待评测）、TD-014（真实 API key 接入）。
- 整体结论：**T06 IS_PASS：YES（待本轮测试输出确认）**。

## T08｜Vision Agent + 图片上传（Phase 1）

- **新增**：models/image.py、alembic c2f4a6b8d901、uploads.py、vision.py、vision_tasks.py、agents/vision/agent.py、image_processor.py、tests/test_uploads.py、tests/test_vision_routes.py、frontend upload/*、docs/VISION.md
- **修改**：agents/vision 四件套、backend/app/main.py、technical_debt.md（TD-015/016）
- **IS_PASS**：待测试验证

---

## 2026-07-25 | T12–T15（Phase 2 早期）| AI 工程链

- **范围**：Phase 2 早期——真实三 Agent 链路 + PDF 方案书端点 + Vision 多模态。
- **关键变更**：
  - 真实 LLM 接入：`track_a` 当前指向 **腾讯混元 TokenHub `HY-Vision-2.0-Instruct`**（openai_compat，多模态，文本+视觉共用）；`llm.enabled=true`；`track_b=mock`（容灾兜底）。
  - 三 Agent 真实链路：Environment / Vision / Design 经 `DualTrackRouter` 跑通。
  - Vision 多模态：接入 TokenHub（commit `f53b4be`），无图/无网/无 key 优雅降级 `pending_verification`。
  - 后端新增 `POST /api/analysis/run`（串联三 Agent → 结构化 dossier）与 `POST /api/report/generate`（流式 PDF 方案书）。
  - 前端 `consult` / `result` 页打通；`lib/analysis.ts` 封装 `runAnalysis` / `generateReport` / `downloadReport`。
  - 入口修复：`backend/app/main.py` 在导入任何 agents/config 前 `load_dotenv`，确保运行时拿到 `.env::LLM_A_*`。
  - asyncio 零告警（commit `22dc0ab` 回归测试）。
- **验证（依据 git HEAD 与交付文档）**：
  - 后端 agents 72 + backend 62 ≈ **135 passed**（22dc0ab 后约 135）。
  - 前端 **29 passed / 6 suites**。
  - 真实 Vision 端到端：`SUCCESS=True`、`PROVIDER=HY-Vision-2.0-Instruct`、`pending_verification=False`。
- **影响文档**：本文件补 Phase 2 段；`docs/LLM.md`、`docs/PHASE0_LOG.md`、`docs/AGENTS.md`、`docs/API.md` 在 2.1.1 同步刷新；架构同步/对齐产出见 `.ai/`。
- **关联技术债**：TD-002（工程阈值待专家签字，高）、TD-016（Vision prompt 调优，高）、TD-012（Session 异步，Phase 2.1 处理）、TD-013（双轨成本/性能）、TD-014（真实 key 接入，已接 TokenHub 标记 RESOLVED）、TD-006（选型，ADR-001 收敛）。
- **业务边界**：行业工程阈值（风压/楼层/评分权重）仍 `pending_verification`；`engineering_enabled=false`，工程安全审核链未闭合。

---

## 2026-07-26 | 2.1.1（Phase 2.1 Sprint 1） | AI 高级工程负责人

- **范围**：文档/配置全面对齐收尾（roadmap_v2 任务 2.1.1）；不开发新业务功能。
- **关键变更**：
  - 本文件补 Phase 2 段（T12–T15 / TokenHub / 真实测试数）。
  - `docs/LLM.md`：架构图改为 `track_a=TokenHub(openai_compat)` / `track_b=mock`；§4 表删除 gpt-4o/claude 占位、标 `enabled=true`、删除"必须 enabled=false"；补充 §4 vision/text provider 解耦（2.1.6）。
  - `docs/PHASE0_LOG.md`：T07 段标注 provider 已演进为 TokenHub（DashScope→minimax→TokenHub 三代漂移，ADR-001 收敛）。
  - `docs/AGENTS.md`：补 Vision/Environment/Design 真实接入、analysis/report router、ReportGenerator。
  - `docs/API.md`：补 `/api/analysis/run`、`/api/report/generate` 两个 Phase 2 端点。
  - `agents/config.yaml`：删除 "DashScope qwen-max" 注释；顶层 `llm_enabled:false` 遗留键标注为已废弃（统一到 `llm.enabled`）；新增 `llm.vision` 块（与 track_a 同源，2.1.6 解耦能力）。
  - `.gitignore`：补 `frontend/.next.trash/`、`deliverables/`（2.1.1 仓库卫生）。
- **验证**：后端 pytest 全绿（见 2.1.4/2.1.7 实测）；文档一致性问题 D1–D13 大部分闭合。
- **关联技术债**：TD-017（配置注释漂移，部分偿还）、TD-018（analysis/report 缺文档，偿还）。

---

## 2026-07-26 | 2.1.6（Phase 2.1 Sprint 1） | Provider 架构解耦

- **范围**：LLM Provider 调用链语义化解耦（C4 / TD-013）；不开发新业务功能、不修改 Agent prompt、不修改前端。
- **设计审核**：`.ai/tasks/2.1.6_provider_decoupling_design.md` 审核通过，落地 4 条执行约束（保留 `modality=` deprecated 别名 / 保留 `track_a/track_b` 兼容解析不作为新入口 / embedding 仅 disabled 占位不接服务 / 不扩大范围）。
- **关键变更**：
  - `agents/llm/router.py`：新增 `ProviderRole` 枚举（TEXT/VISION/EMBEDDING/FALLBACK）；`build_router_from_config` 新增语义化 `role=` 参数（保留 `modality=` deprecated 别名，经 `_modality_to_role` 映射）；新增 `resolve_provider(config, role)` 命名注册表解析（vision→text 回落、旧 `track_a/track_b` 键兼容回落、embedding→None）；新增 `build_embedding_provider`（disabled→None）。
  - `agents/config.yaml`：旧 `track_a/track_b/vision` 键迁移为 `llm.providers:{text,vision,embedding,fallback}`（text/vision 同源 TokenHub、fallback=mock、embedding=disabled）；顶层注释保留"router.py 仍兼容旧键"说明。
  - `agents/vision/agent.py`：`build_router_from_config(llm_cfg, role=ProviderRole.VISION)`（原 modality="vision"）；顺手移除未用 `import json`（ruff F401）。
  - `agents/environment/agent.py` / `agents/design/agent.py`：`build_router_from_config(llm_cfg, role=ProviderRole.TEXT)`。
  - `agents/core/orchestrator_chat_integration.py`（修复 P2 既有 bug）：`_ensure_initialized` 改为先 `load_llm_config(config_path)` 再 `build_router_from_config(llm_cfg, role=ProviderRole.TEXT)`；原代码误把 `config_path`（str）当 Mapping 传入导致 `router=None`、聊天真实 LLM 增强静默失效。占位文案去掉 `LLM_B_API_KEY` 误导。
  - `tests/agents/test_router.py`：重写为 10 项（role 选块 / vision→text 回落 / fallback=mock / modality 弃用别名 / 旧键兼容 / embedding→None / router 子块 strategy/timeout）。
  - `tests/agents/test_orchestrator_chat_integration.py`：新增，验证 P2 修复后 `llm_enabled is True` 且 `_router is not None`。
  - `tests/agents/test_environment.py` / `test_design.py`：共 5 处 monkeypatch 桩改为 `lambda _cfg, **_kw: fake_router` 兼容 `role=` 关键字。
  - `scripts/lint/check_fabrication.py`（修复 2.1.7 遗留扫描器倒退）：`OUTLINE_SECTION_RE` 改为行首前缀判定，避免把含数值的示例串误当大纲编号放行；新增表格 `|` 与字母紧邻编号（P0/R4/D1）跳过，真实业务数值仍被拦下。
  - `docs/LLM.md` / `docs/AGENTS.md`：同步 ProviderRole + resolve_provider 说明、Agent 状态、`modality=` deprecated 标注。
- **验证（2026-07-26 实测）**：
  - agents **83 passed** + backend **64 passed** + 前端 **29 passed / 6 suites** = **176 passed**。
  - `bash scripts/ci/local_ci.sh` 8 步全绿（"Local CI passed"，含业务数字 + 硬编码扫描）。
- **保留的兼容层（按审核约束）**：`modality=` 弃用别名、`track_a/track_b` 兼容解析、embedding disabled 占位——均不删除，仅不作为新配置入口。
- **待跟进项（不属本任务范围）**：`orchestrator_chat_integration.chat()` 存在独立元组解包 bug（`route()` 返回 `(response, results)` 被赋值给 `response` 后 `.finish_reason` 抛 AttributeError），已单列待修。
- **关联技术债**：TD-013（Provider 解耦，本任务偿还）、TD-017（配置注释漂移，进一步偿还）。

---

## 2026-07-27 | 2.1.4–2.1.7（Phase 2.1 架构稳定收口） | AI 高级研发/质量负责人

- **范围**：AsyncSession 落地（TD-012）、Engineering Agent 骨架（2.1.5）、Provider 解耦收口（2.1.6）、测试基线刷新（2.1.7）。
- **关键变更**：
  - `backend/app/db/session.py`：引入 `async_engine / AsyncSessionLocal / async_get_db`；conversations / vision / uploads 三路由切异步；`process_image` 经 `asyncio.to_thread` 解耦。
  - `agents/engineering/`：EngineeringAgent 骨架，五分析接口统一输出 `{result, confidence, evidence, verification_status: pending_verification}`；`EngineeringValidation` 审核链；`config.yaml` 登记但 `enabled:false` 不进管道。
  - `backend/requirements.txt`：登记 aiosqlite + greenlet。
- **验证**：2.1.7 `local_ci.sh` 8/8 全绿，backend 151→164 passed，覆盖率 82.67%→83.17%。
- **关联技术债**：TD-012（偿还）、TD-013/C4（偿还）。

---

## 2026-07-27 | 2.2.1–2.2.6（Phase 2.2 能力深化六 Sprint） | AI 研发/架构负责人

- **范围**：Environment 真实数据机制 → Design 专业化 → PDF 可信交付 → Storage 抽象 → RAG 基础设施 → RBAC 权限基础（逐 Sprint 设计→编码→测试→报告，各自 CI 8/8 全绿）。
- **关键变更**：
  - **2.2.1 Environment**：`agents/environment/providers/`（base/mock/factory），GeoResult/WindClimate 强制 `source/fetched_at/raw_ref` 三要素溯源；`environment_data` 配置段默认 disabled；`field_provenance` + Level 0 推理永远 pending 语义。
  - **2.2.2 Design**：`thresholds/verified.json`（D-TH-01~05 全 `verified=false`、`value=null`）+ `threshold_loader`（verified 一票否决）；经济/舒适/高性能三方案 Prompt 专业化 + `decision_trace`。
  - **2.2.3 PDF**：可信等级章节（Level 0~3）+ 可信徽标 + 溯源子表 + 三方案渲染；「不把 AI 推理包装成工程确认」落地。
  - **2.2.4 Storage**：`StorageBackend` 抽象（Local 默认 / MinIO 可配置 / Memory 测试），逻辑 key `{tenant_id}/{sha256}.{ext}`；`BOIP_STORAGE_BACKEND` 切换；密钥仅 `.env`。
  - **2.2.5 RAG**：`EmbeddingProvider`（Mock 确定性 / OpenAICompat 真实，零新依赖）；`backend/app/core/rag/`（chunking / vector_store InMemory+Qdrant 懒加载 / ingestion 强制溯源）；`/api/rag/*` 三端点。
  - **2.2.6 RBAC**：roles/permissions/role_permissions/user_roles 四表（Alembic `637cbf3eafca` 双向可逆）；JWT HS256 纯标准库 + pbkdf2 十万轮；`get_current_user`(401)/`require_permission`(403)；`/api/auth/login|me`；保护 uploads/analysis/report；tenant_id 改由 JWT 服务端签发。
- **验证**：最终基线 `local_ci.sh` 8/8 全绿：backend **246 passed / 87.34%** + Jest **29 passed / 93.15%** = **275 passed**。
- **影响文档**：各 Sprint 报告见 `.ai/reviews/2.2.*.md`；阶段总结 `.ai/reviews/phase2.2_final_review.md`。
- **关联技术债**：TD-015（偿还）；新登记 TD-017/TD-018（本次 3.0 文档收敛偿还）。

---

## 2026-07-28 | 3.0（Phase 3 前置整理） | AI CTO

- **范围**：Git Release Freeze（Phase 2.1/2.2 全部改动分批提交）、文档体系收敛（README/CHANGELOG/LLM.md/AGENTS.md/API.md 刷至 Phase 2.2 COMPLETED）、技术债 A/B/C 重分类（`.ai/technical_debt/`）、SSOT 同步（current_phase = Phase 3 planning）。
- **关键变更**：仓库卫生（忽略 `backend/storage/`、`coverage.xml`）；`.ai/` SSOT 体系首次入库。
- **验证**：`local_ci.sh` 8/8 全绿（见 `.ai/reviews/phase2.2_release_freeze_report.md`）。
- **关联技术债**：TD-017（偿还：provider 注释/文档漂移清理）、TD-018（偿还：API 文档补全）、TD-003（偿还：文档/代码联动机制落地）。
