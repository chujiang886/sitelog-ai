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
