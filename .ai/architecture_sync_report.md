# BOIP 架构同步报告（Architecture Synchronization Report）

**生成日期**：2026-07-26
**生成人**：BOIP AI 首席架构整理工程师
**动作性质**：只读扫描 + 文档/状态同步；**不修改任何业务代码**
**扫描范围**：文档（`docs/`、`BOIP_AI_Documents/`、根 `README.md`）、源代码（`agents/`、`backend/`、`frontend/`）、配置（`.env`、`agents/config.yaml`、`docker-compose.yml`）、Git 历史、Agent 目录、`deliverables/`
**单一事实来源产出**：`.ai/project_status.json`（本报告的机器可读镜像）

---

## 第一部分：当前真实项目阶段

| 维度 | 文档声称 | 代码 / Git / 交付文档实测 | 结论 |
|---|---|---|---|
| 阶段 | README/CHANGELOG：Phase 0 完成、进入 Phase 1；CHANGELOG 末条停在 T08 | Git HEAD `22dc0ab`；`deliverables/software-company/boip-phase2-delivery-2026-07-25.md` 明确 Phase 2（T12–T15）已交付 | **真实阶段 = Phase 2 早期**，文档整体滞后约 2 个阶段 |
| 链路 | 仅占位 / mock | `deliverables` + commit `7e2a585`/`f53b4be`：真实三 Agent 链路 + Vision 多模态已跑通 | 已进入"真实 LLM 接入"期 |
| 分支 | 文档曾提 `main`/`develop` 受保护 | 实际 `master`，已 `git push origin master` 到 `github.com/chujiang886/sitelog-ai` | 实际主干为 `master` |

**当前真实里程碑**：
- ✅ Phase 0（T01–T05）验收通过
- ✅ Phase 1（T06 对话 / T07 真实 LLM 接入 / T08 Vision+上传）完成
- ✅ Phase 2（T12 asyncio 零告警 / T13 前端 consult+result 页 / T14 PDF 端点 / T15 真实三 Agent 链路 + Vision 多模态）完成
- LLM 真实接入状态：`llm.enabled=true`，`track_a` 当前指向 **腾讯混元 TokenHub `HY-Vision-2.0-Instruct`**（多模态，文本+视觉共用），`track_b=mock`（用户确认跳过冗余）。
- 最近绿灯（commit `fcb8a3c` 后）：agents 72 + backend 62 = **134 passed**，外加 `22dc0ab` 新增 1 项回归（当前约 135）；前端 **29 passed / 6 suites**。建议重跑 `local_ci.sh` 取得 Phase 2 权威门禁数。

---

## 第二部分：已完成功能清单

### A. 后端 API（FastAPI，`backend/app/main.py` 注册 9 个 router）

| 端点 | 方法 | 功能 | 阶段 |
|---|---|---|---|
| `/health` | GET | 健康检查（信封 `{success,data}`） | T02 |
| `/api/projects` | GET | 项目列表（占位） | T02 |
| `/api/agents` | GET / `{name}/invoke` | Agent 清单 + 调用 + 错误信封 | T04 |
| `/api/knowledge/rules` | GET | 知识规则 | T02 |
| `/api/conversations` | POST/GET | 会话创建/查询 | T06 |
| `/api/conversations/{id}/messages` | POST/GET | 对话消息 + 编排降级 | T06 |
| `/api/uploads` | POST/GET | 图片上传（本地存储占位） | T08 |
| `/api/vision/analyze` | POST | Vision 分析（异步任务骨架） | T08 |
| `/api/analysis/run` | POST | 串联 environment/design/vision 三 Agent → 结构化 dossier | T14(Phase2) |
| `/api/report/generate` | POST | 生成 PDF 方案书（流式 `application/pdf`） | T14(Phase2) |

### B. AI Agent 层（`agents/`）

- **BaseAgent / AgentRegistry / Loader / config**：稳定框架（T04）
- **CoreAgent + CoreOrchestrator + NLU（IntentExtractor）**：规则 + LLM 增强意图提取（T06）
- **EnvironmentAgent**：风压/湿度/盐雾/日照风险分析，走 `DualTrackRouter` 真实链路（T15）
- **VisionAgent**：多模态图片识别（scene_type/obstructions/orientation/quality/recommendations），无图/无网优雅降级 `pending_verification`（T08 + TokenHub 多模态 f53b4be）
- **DesignAgent**：经济/舒适/高性能三方案生成，真实链路（T15）
- **ReportGenerator**：`generate_project_report` 生成 PDF（Phase2）
- **LLM 双轨抽象**：`OpenAICompatProvider` / `AnthropicCompatProvider` / `MockProvider` / `DualTrackRouter`（fastest/first/consensus/fallback）；`jsonutil.extract_json` 鲁棒解析（T06 + Phase2 修复）

### C. 前端（Next.js 14，`frontend/src`）

- 页面：`/`（home）、`/consult`（结构化需求面板）、`/result`（三 Agent 结果 + PDF 下载）、`/upload`（图片上传 + Vision 结果卡）、`/agents`、`/projects`、`/knowledge`、`/login`
- 组件：`ChatMessage`、`IntentBadge`、`upload/ImageDropzone`、`upload/VisionResultCard`
- 库：`lib/api.ts`、`lib/chat.ts`、`lib/analysis.ts`（`runAnalysis`/`generateReport`/`downloadReport`）、`lib/upload.ts`、`lib/store.ts`（Zustand）
- 类型：`types/chat.ts`、`types/contracts.ts`、`types/vision.ts`
- 测试：6 个测试文件 / 29 用例（analysis、result、consult、health 等）

### D. 数据层（`backend/app/db`）

- 10+ ORM 模型：`tenant/user/project/agent/knowledge/audit/threshold/conversation/message/image`
- Alembic 迁移（Phase0 初始 + Phase1 conversations + T08 image）
- 种子脚本；自定义 `GUID` 跨 PG/SQLite

### E. 质量与工程

- `local_ci.sh` 8 步（Ruff/pytest/ESLint/jest/alembic roundtrip/seed/业务数字扫描/硬编码扫描）
- `check_fabrication.py` / `check_hardcoded.py` 合规扫描
- GitHub Actions `ci.yml` + `docs-check.yml`
- 双轨 LLM 无 key 不崩溃；Vision 不杜撰（合成图实测如实返回"未知"）

---

## 第三部分：代码实际架构

### 3.1 分层拓扑（实测）

```
[用户层] Web(Next.js14) ──→ /consult /result /upload /agents /projects /knowledge /login
   ↓
[API 网关] FastAPI(main.py, 9 routers) + CORS + 错误信封中间件
   ↓
[业务路由] health/projects/agents/knowledge/conversations/uploads/vision/analysis/report
   ↓
[Agent 编排] CoreOrchestrator.chat (NLU) ｜ /api/analysis/run 串联三 Agent
   ↓
[Agent 层] Core → Environment / Vision / Design（各自 build_router_from_config）
   ↓                         └→ DualTrackRouter(track_a=TokenHub / track_b=mock)
[LLM 抽象] OpenAICompat / AnthropicCompat / Mock ＋ extract_json
   ↓
[数据层] PostgreSQL(目标) / SQLite(Phase0 占位回归) / Redis / Qdrant / MinIO(待接)
[存储]   backend/app/core/storage.py → 本地 uploads/（TD-015 待接 MinIO）
```

### 3.2 关键设计决策（实测）

1. **Agent 四件套契约**：每个 Agent 目录含 `agent.py/agent.md/prompt.md/tools.md/tests.md`，`invoke(AgentContext)→AgentResult`，`to_envelope()` 统一信封。
2. **LLM 双轨 + Mock 兜底**：`_build_provider` 在 `provider=mock` 或 key 缺省/`pending_verification` 时自动降级 `MockProvider`；`MockProvider.complete` 现改为抛 `LLMProviderError`，避免污染 `fastest` 真实链路（Phase2 修复）。
3. **单一 track_a 服务多模态**：当前所有 Agent 共用 `track_a`（TokenHub HY-Vision，openai_compat）。**架构局限**：文本 Agent（environment/design）与视觉 Agent（vision）共用同一端点，未区分"文本 provider"与"视觉 provider"。
4. **JSON 鲁棒解析**：`agents/llm/jsonutil.extract_json` 直解 → 剥 ```` ```json ```` → 截取首尾 `{}`，三 Agent 共用。
5. **Vision 优雅降级**：无图/无网/LLM 不可用 → `LLMRouterError` 捕获 → `success=True` 的 `pending_verification` 占位（契约合规）。
6. **前端契约封装**：`lib/analysis.ts` 统一 `runAnalysis`/`generateReport`/`downloadReport`，对接 `/api/analysis/run` 与 `/api/report/generate`。

### 3.3 目录规模（git 跟踪）

- 19257 文件（含 node_modules/.next 等构建产物）；源码以 `.py`(2594)/`.ts`(1043)/`.json`(1212)/`.md`(22 in docs) 为主。
- 后端测试文件 27 个；前端测试文件 6 个（29 用例）。

---

## 第四部分：文档缺失和过期内容

> 评级：🔴 高（影响决策/协作）｜🟠 中（误导）｜🟡 低（卫生）

| # | 文档/位置 | 问题 | 真实状态 | 评级 |
|---|---|---|---|---|
| D1 | `README.md` 顶部 | "Phase 0 完成 / 进入 Phase 1" | 已到 Phase 2 | 🔴 |
| D2 | `docs/CHANGELOG.md` | 末条停在 T08；无 Phase 2 / T12–T15 / TokenHub / minimax 记录 | Phase 2 已交付 | 🔴 |
| D3 | `docs/PHASE0_LOG.md` | T07 段写 "track_a：DashScope qwen-max"；无 T12–T15 章 | 现为 TokenHub | 🟠 |
| D4 | `docs/LLM.md` | 架构图画 OpenAI/Anthropic 双云；§4 表 `model: gpt-4o/claude-3-5-sonnet`、`是否启用: false`；"Phase1.0 必须 llm.enabled=false" | 实际 `enabled=true`、track_a=TokenHub、track_b=mock | 🔴 |
| D5 | `agents/config.yaml` 注释 | "T07 起接入真实 track_a：DashScope（OpenAI 兼容）qwen-max" | 现为 TokenHub（且曾为 minimax） | 🟠 |
| D6 | `docs/AGENTS.md` | 缺 Vision/Environment/Design 真实接入细节、缺 `analysis`/`report` router、缺 `ReportGenerator` | 已存在 | 🟠 |
| D7 | `docs/API.md` | 未含 `/api/analysis/run`、`/api/report/generate` | Phase2 新增 | 🟠 |
| D8 | （无）`docs/ANALYSIS_REPORT.md` | 缺少 analysis/report 端点与 PDF 生成的专文档 | 缺 | 🟡 |
| D9 | `BOIP_PROJECT_TASK_TREE.md` | 任务树停 Phase 0 视角；T06–T20 已实际开工/超前，未入账 | 需升级为"实时任务树" | 🟠 |
| D10 | `BOIP_AI_Documents/technical_debt.md` | TD-013/TD-014 仍标 minimax/DashScope 语境；TD-015/TD-016 已加但 R1/R2 类新债未登记 | 债册滞后 | 🟠 |
| D11 | `deliverables/`（3 份 md） | 处于 untracked，未纳入版本/文档体系 | 含真实状态，应归档 | 🟡 |
| D12 | `.gitignore` | 未忽略 `frontend/.next.trash/`（构建垃圾）、`deliverables/` | 易误提交 | 🟡 |
| D13 | `backend/app/db/session.py` | 仅同步 `SessionLocal`，FastAPI 路由为 `async def` | TD-012 未决，Phase2 已真实查库 | 🟠 |

---

## 第五部分：配置冲突分析

### 5.1 核心冲突：LLM provider 身份在多处互相矛盾

| 来源 | 声明 track_a 身份 | 真相 |
|---|---|---|
| `agents/config.yaml` 注释 | "DashScope qwen-max"（T07 语境） | 三代前，已过时 |
| `docs/LLM.md` §4 | model `gpt-4o` / `claude-3-5-sonnet`，track_b=anthropic | 与当前实现不符 |
| `docs/PHASE0_LOG.md` T07 | "track_a：DashScope qwen-max" | 已过时 |
| `deliverables/...phase2-delivery` | "track_a 指向 minimax（`minimax.chat/v1`）" | 被 f53b4be 覆盖 |
| **`.env` 注释 + 实际值** | "track_a：腾讯混元 TokenHub HY-Vision-2.0-Instruct"（值已设、已 gitignore） | **当前事实** |

**结论**：代码机制本身健康（`config.yaml::track_a.provider=openai_compat` + `${LLM_A_BASE_URL}` 插值 → 指向 `.env` 的 TokenHub）。问题纯粹在**注释/文档层的三次漂移**（DashScope → minimax → TokenHub），导致任何读文档的人无法得知真实 provider。

### 5.2 修正上一轮误判

上一轮（phase0_initial_analysis.md）曾写"`.env` 中 `LLM_A_*` 全为空值 / 密钥悬空"。**该判断错误**——当时仅 `grep` 了键名未看值；实测 `.env` 的 `LLM_A_*` 均已填入 TokenHub 密钥（已 gitignore，未泄漏）。真实问题不是"密钥缺失"，而是"**配置语义在文档/注释间自相矛盾**"。本报告以此为准。

### 5.3 track_b 死配置

- `.env` 含 `LLM_B_*` 键（值为 `pending_verification`），但 `config.yaml::llm.track_b.provider=mock` → `_build_provider` 恒返回 `MockProvider`。`LLM_B_*` 当前为**无效死配置**，除非把 `track_b.provider` 改为 `openai_compat` 才会生效。属冗余但未造成故障。

### 5.4 单 track_a 多模态混用（架构级隐患）

- environment/design（文本）与 vision（视觉）共用 `track_a=HY-Vision`。HY-Vision 是多模态模型，文本推理可用但非最优；若未来切换 track_a 为纯文本模型，Vision 将失效。建议架构上区分 `text_provider` 与 `vision_provider`（Phase 3 前偿还）。

### 5.5 配置事实源建议（供下一步）

单一事实源应为：**`agents/config.yaml` 的 `llm.track_a.base_url/model` 经 `${LLM_A_*}` 解析到 `.env`**，文档/注释一律引用该链路，不再硬编码 provider 名称。JSON 产物 `.ai/project_status.json` 即以此为准，供后续 AI 直接读取。

---

## 第六部分：未来推荐路线

### 6.1 立即可做（文档同步，不改业务代码）

1. **刷新 README 顶部** → "Phase 2 进行中（T12–T15 已交付）"。
2. **补 `docs/CHANGELOG.md`** → 追加 T12–T15、TokenHub 接入、minimax→TokenHub 演进、真实测试数。
3. **修订 `docs/LLM.md`** → 架构图改为 track_a=TokenHub(openai_compat)/track_b=mock；§4 表删除 gpt-4o/claude 占位，标 `enabled=true`；删除"必须 enabled=false"。
4. **修订 `agents/config.yaml` 注释** → 删除 DashScope/qwen-max，改注"track_a 由 `.env::LLM_A_*` 注入，当前 TokenHub HY-Vision；track_b 维持 mock（冗余已跳过）"。
5. **补 `docs/AGENTS.md` / 新建 `docs/ANALYSIS_REPORT.md`** → 覆盖 analysis/report router、ReportGenerator、PDF 流程。
6. **`.gitignore` 追加** `frontend/.next.trash/`；将 `deliverables/` 归档或加入忽略。
7. **升级任务树** → 把 T06–T20 实际进度入账（见 `.ai/project_status.json`）。

### 6.2 近期架构决策（需主理人拍板）

- **TD-012 Session 模型**：建议引入 `AsyncSession` + `async_get_db`，避免 async 路由阻塞事件循环（Phase2 已真实查库）。
- **TD-011 SQLite↔PG**：接入真实 PostgreSQL 后跑 `EXPLAIN ANALYZE` 比对 JSON 查询，必要时补 `gin` 索引。
- **provider 分离**：文本 vs 视觉 provider 解耦（见 5.4）。
- **TD-015 MinIO**：图片存储从本地切换到 MinIO（去重 + 租户隔离）。
- **TD-002/TD-016**：工程阈值（风压/楼层/权重）与 Vision prompt 需建筑开口设计师专家签字，方可从 `pending_verification` 转正。

### 6.3 按任务树的中长期路线（T09 → T20）

- **T09 Environment Agent 深化**（当前已真实但占位字段多）→ 接 weather/gis 真实数据。
- **T10 Design Agent 三方案** 已初步真实，需专家评审阈值。
- **T11 PDF 报告** 已落地端点，需模板美化 + 真实数据填充。
- **T12 工程引擎**（风压/玻璃/型材/五金/评分/审核）→ 闭合"工程安全审核链"（当前 `engineering_enabled=false`）。
- **T13–T17 企业 SaaS**（RBAC/多租户/CRM/知识库 RAG/销售 AI）。
- **T18–T20 数字孪生 / 施工交付 / 产业生态 / AI 大脑**。

### 6.4 技术债偿还节奏（来自 `technical_debt.md` 规则）

- Phase 1 末 OPEN ≤ 10；Phase 2 末 ≤ 5。
- **当前 OPEN = 14（TD-001~016，其中 TD-004 RESOLVED）**，已超 Phase 1 末目标；且 R1/R2 类"文档-代码漂移"新债尚未登记。建议本轮同步时新增 TD-017（配置注释漂移）、TD-018（analysis/report 缺文档）。

---

## 附：本报告证据索引

- Git：`22dc0ab`(回归测试)、`fcb8a3c`(load_dotenv)、`f53b4be`(TokenHub 多模态)、`7e2a585`(Phase2 三 Agent 链路)
- 交付文档：`deliverables/software-company/boip-phase2-delivery-2026-07-25.md`、`boip-nextsteps-execution-2026-07-26.md`、`boip-wrapup-overview-2026-07-25.md`
- 配置：`.env`（脱敏）、`agents/config.yaml`、`backend/app/main.py`、`agents/llm/router.py`、`agents/vision/agent.py`
- 文档：`README.md`、`docs/CHANGELOG.md`、`docs/PHASE0_LOG.md`、`docs/LLM.md`、`docs/AGENTS.md`、`docs/API.md`、`BOIP_AI_Documents/BOIP_PROJECT_TASK_TREE.md`、`technical_debt.md`

**END**
