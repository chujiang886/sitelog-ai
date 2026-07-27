# BOIP 建筑开口智能设计平台

BOIP（Building Opening Intelligence Platform）定位为面向建筑开口行业的 AI Native 智能设计基础设施。当前 **Phase 2.2（能力深化）已全部收口**：Environment 数据 Provider 抽象、Design 三方案专业化、PDF 可信交付、Storage 抽象（MinIO 可切换）、RAG 基础设施、RBAC 企业权限基础六大 Sprint 均已完成并通过 CI 门禁；行业工程参数在未经专家验证前一律以 `pending_verification` 标识。

## 当前阶段

- **当前真实阶段：Phase 2.2 = COMPLETED（2026-07-28 验收）**，当前处于 **Phase 3 planning**（未开始 Phase 3 开发）。
- 单一事实来源（SSOT）：[`.ai/project_status.json`](.ai/project_status.json)；阶段总结：[`.ai/reviews/phase2.2_final_review.md`](.ai/reviews/phase2.2_final_review.md)；路线图：[`.ai/roadmap_v2.md`](.ai/roadmap_v2.md)。
- 历史里程碑：Phase 0（T01–T05）✅ → Phase 1（T06–T08）✅ → Phase 2 早期（T12–T15）✅ → Phase 2.1 架构稳定（AsyncSession / Provider 解耦 / Engineering 骨架 / 测试基线）✅ → Phase 2.2 能力深化（2.2.1–2.2.6）✅。

## Current Architecture Status

> 机器可读单一事实来源：[`.ai/project_status.json`](.ai/project_status.json) ｜ 阶段验收：[`.ai/reviews/phase2.2_final_review.md`](.ai/reviews/phase2.2_final_review.md) ｜ Provider 状态：[`.ai/provider_status.md`](.ai/provider_status.md) ｜ 决策记录：[`.ai/decisions/`](.ai/decisions/)

### 当前 Phase（Current Phase）

- **Phase 2.2 COMPLETED — 能力深化六 Sprint 全部交付；Phase 3 planning**
- LLM 真实接入：`llm.enabled = true`；`providers.text/vision` 指向 **腾讯混元 TokenHub `HY-Vision-2.0-Instruct`**（多模态），`fallback = mock`（容灾 / 离线兜底）；配置事实源为 `.env::LLM_A_*`。
- 主干分支：`master`（远端 `github.com/chujiang886/sitelog-ai`）。
- 最新权威绿灯（2026-07-27，`local_ci.sh` 8/8 全绿）：backend pytest **246 passed / 覆盖率 87.34%**（门槛 60%）+ 前端 Jest **29 passed / 6 suites / 覆盖率 93.15%**（门槛 50%）= **275 passed**。

### 已完成模块（Completed Modules）

**后端 API（11 个 router，FastAPI）**
- `/health`、`/api/projects`、`/api/agents`（+`/{name}/invoke`）、`/api/knowledge/rules`
- `/api/conversations`（+`/{id}/messages`）、`/api/uploads`、`/api/vision/analyze`
- `/api/analysis/run`（串联 Environment / Vision / Design 三 Agent → 结构化 dossier）
- `/api/report/generate`（PDF 方案书，可信徽标 + 溯源子表，流式 `application/pdf`）
- `/api/rag/ingest|search|mode`（RAG 基础设施：入库强制三要素溯源）
- `/api/auth/login|me`（JWT 认证；uploads / analysis / report 已接 RBAC 权限保护）

**AI Agent 层**
- 框架：BaseAgent / AgentRegistry / Loader / config（T04 稳定）
- CoreAgent + CoreOrchestrator + NLU（IntentExtractor）
- EnvironmentAgent（数据 Provider 抽象 + field_provenance 溯源）、VisionAgent（HY-Vision 多模态）、DesignAgent（经济 / 舒适 / 高性能三方案 + 阈值 verified 一票否决）
- EngineeringAgent 骨架（`enabled:false` 不进管道，零真实工程计算）
- ReportGenerator（→ 可信 PDF）、LLM 抽象（ProviderRole 语义枚举 + OpenAICompat / AnthropicCompat / Mock / DualTrackRouter + EmbeddingProvider）

**前端（Next.js 14）**：8 个页面（home / consult / result / upload / agents / projects / knowledge / login）、ChatMessage / IntentBadge / ImageDropzone / VisionResultCard 组件、analysis / chat / upload / store 库、29 个 Jest 用例。

**数据层**：14+ ORM 模型（含 RBAC 四表）、Alembic 迁移（双向可逆）、StorageBackend 抽象（Local 默认 / MinIO 可配置 / Memory 测试）、向量库抽象（InMemory 默认 / Qdrant 懒加载）。

**企业能力**：RBAC（admin / designer / viewer 三角色 + `resource:action` 权限模型）、JWT HS256 认证（纯标准库，secret 仅 `.env`）、tenant_id 服务端签发隔离。

**质量体系**：`local_ci.sh` 8 步门禁、业务数字杜撰扫描、硬编码扫描、GitHub Actions。

### 当前风险（Current Risks）

| 级别 | 风险 | 说明 / 动作 |
|---|---|---|
| 🔴 高 | 工程安全审核链未闭合 | `engineering_enabled = false`，风压 / 阈值全 `pending_verification`；上线前需 Engineering 计算闭环 + 专家签字（Phase 3 主线） |
| 🟠 中 | 技术债 OPEN 13 项超标 | Phase 2.2 出口目标 ≤5 未达成；分类与还债计划见 [`.ai/technical_debt/`](.ai/technical_debt/) |
| 🟠 中 | 真实外部数据源未接入 | Environment 天气 / GIS、真实 Embedding / Qdrant 均按 ADR 流程 DEFERRED，机制已就绪待选型 |
| 🟠 中 | SQLite↔PG JSONB 差异未验证（TD-011） | 接 PG 后需 `EXPLAIN ANALYZE` + gin 索引评估 |
| 🟡 低 | 前端 `/login` 未对接 `/api/auth/login` | RBAC 后端已就绪，前端仍为占位页（Phase 3.2 首步） |

## 环境要求

- Node.js：22.22.2
- Python：3.11
- Docker 与 Docker Compose

版本与端口属于工程环境配置；行业工程参数必须以 `pending_verification` 标识后方可进入实现。

## 启动方式

### Docker Compose

```bash
cp .env.example .env
# 填写本地开发所需变量后启动
docker-compose up --build
```

### 后端

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

健康检查：`GET http://localhost:8000/health`。

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端地址：`http://localhost:3000`；健康检查：`GET http://localhost:3000/api/health`。

## 测试与检查

```bash
bash scripts/ci/local_ci.sh
```

该命令执行后端健康检查测试、前端 Jest、业务数字杜撰扫描与硬编码扫描。

## 目录说明

- `frontend/`：Next.js 前端工程
- `backend/`：FastAPI 后端工程
- `agents/`：Agent 基础抽象、注册表与文档契约
- `deployment/`：容器、Nginx 与部署说明
- `docs/`：工程实施记录
- `tests/`：跨层端到端测试与 AI 评测集入口
- `scripts/`：本地 CI 与静态扫描脚本

## 文档索引

- [产品与架构设计文档](../BOIP_AI_Documents/)
- [工程实施文档](docs/)

## 团队角色

- 主理人：项目决策与总协调
- 许清楚：产品经理
- 高见远：系统架构师
- 寇豆码：软件工程师
- 严过关：质量负责人

## 安全声明

不得提交 `.env`、访问令牌、API 密钥、用户数据或企业敏感数据。`.env.example` 仅提供空值模板。
