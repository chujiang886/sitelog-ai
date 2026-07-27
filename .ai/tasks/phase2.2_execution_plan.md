# BOIP Phase 2.2 专业能力增强执行计划（phase2.2_execution_plan.md）

- **生成**：2026-07-27
- **身份**：BOIP AI 产品架构负责人
- **性质**：**纯规划文档，本阶段零编码**。依据 `.ai/project_status.json`（SSOT）与 `.ai/roadmap_v2.md`（V2 权威路线）生成。
- **前置状态**：Phase 2.1 五子项全部 COMPLETED（2.1.1 / 2.1.4 / 2.1.5 / 2.1.6 / 2.1.7）；最新绿灯基线：`local_ci.sh` 8/8 全绿，backend pytest **164 passed**（覆盖率 83.17%），Jest **29 passed**（覆盖率 93.15%），合计 193。
- **状态**：`PENDING_REVIEW`——等待主理人审核，审核通过后按 Sprint 顺序进入实施。

---

## 一、Phase 2.2 目标

**主题**：能力深化——把 Phase 0–2.1 建立的"占位能力"做实为"专业能力"。

**roadmap_v2 §3 出口标准（原文承接）**：
1. Environment / Design 使用**真实数据**（不再是占位字段 / 未转正阈值）；
2. PDF 报告达到**可交付客户**的质量；
3. 图片进入**云存储（MinIO）**，具备去重与租户隔离；
4. 技术债 **OPEN ≤ 5**（当前 13，需净减 ≥8）；
5. 为 Phase 3（工程引擎闭环 + 企业 SaaS）铺好 RAG 与 RBAC 地基。

**红线（不可逾越，全程有效）**：
- 任何无据行业数字必须标 `pending_verification`；
- 工程参数（风压 / 楼层阈值 / 玻璃厚度 / 评分权重）**未经专家签字不得转正**；
- 真实外部数据（天气 / GIS）必须可溯源（evidence 带来源 + 时间戳），Agent 不得编造；
- `engineering_enabled` 在 Phase 2.2 全程保持 `false`（启用属 Phase 3.1）。

**范围外（明确不做）**：工程引擎真实计算（Phase 3.1）、CRM / 销售 AI（Phase 3.2）、track_b 启用评估（Phase 3.4）、数字孪生（Phase 3.3）。

---

## 二、Sprint 拆分

拆分原则：**依赖先行、红线隔离、每 Sprint 收口可验**。六个子任务按依赖关系与风险性质分入 4 个 Sprint：

| Sprint | 主题 | 包含任务 | 依赖关系 |
|---|---|---|---|
| **Sprint 1** | 真实数据接入 | 2.2.1 Environment 真实数据接入 | 无前置；产出被 2.2.2 / 2.2.3 消费 |
| **Sprint 2** | 专业化转正 + 可交付报告 | 2.2.2 Design 三方案专业化、2.2.3 PDF 增强 | 2.2.2 依赖专家评审排期（外部依赖）；2.2.3 依赖 2.2.1 产出真实数据字段 |
| **Sprint 3** | 存储基建 | 2.2.4 MinIO 图片存储切换 | 独立，可与 Sprint 2 并行启动；建议在 RAG 之前完成（对象存储运维经验复用） |
| **Sprint 4** | SaaS 地基 | 2.2.5 RAG 基础、2.2.6 RBAC 基础 | 2.2.5 依赖向量库（Qdrant）选型确认；2.2.6 依赖既有 tenant/user 模型；两者互不依赖可并行 |

每个 Sprint 收口条件（统一）：`local_ci.sh` 8/8 全绿 + 不降低覆盖率门槛（60%/50%）+ 输出该 Sprint 交付报告 + 更新 `project_status.json` / `roadmap_v2.md` + **等待主理人验收后进入下一 Sprint（不跳阶段）**。

---

## 三、每个 Sprint 任务明细

### Sprint 1 —— 2.2.1 Environment 真实数据接入（T09，P1）

**目标**：EnvironmentAgent 的风压 / 湿度 / 盐雾 / 日照占位字段接入真实 weather / GIS 数据源，`pending_verification` 按"数据可溯源"原则逐字段收敛。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S1-1 | 数据源选型评审（文档先行） | 候选：公开气象 API（如和风天气/OpenWeather 类）、GIS 高程/海岸距离数据源；输出选型对比 + ADR | **需主理人确认数据源与预算**，未确认前不接 |
| S1-2 | `agents/environment/` 增加数据获取工具层 | 独立 `tools/weather_client.py`（或 MCP 工具）；带超时/重试/降级；不可用时回落 `pending_verification` | 不改 BaseAgent 契约 |
| S1-3 | 数据溯源结构 | evidence 字段必须含 `{source, fetched_at, raw_ref}`；无溯源数据一律不进 result | 红线 |
| S1-4 | 密钥管理 | 新增数据源 API key 走 `.env`（延续 ADR-001 模式），登记 TD-008 关联 | 不提交密钥 |
| S1-5 | 缓存策略 | 同一地理位置短期缓存（进程内或 DB 表），避免重复计费与限流 | 新表需 Alembic 迁移 |
| S1-6 | 测试与 Mock | 外部 API 全部 Mock 化测试（禁真实网络请求进 CI）；降级路径测试必备 | CI 不依赖外网 |

**关联债**：TD-002 延伸。**交付报告**：`.ai/reviews/2.2.1_environment_data_report.md`。

### Sprint 2A —— 2.2.2 Design 三方案专业化（T10，P1）

**目标**：DesignAgent 经济 / 舒适 / 高性能三方案的阈值经**专家评审签字**后由 `pending` 转正；prompt 场景化专业化。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S2A-1 | 阈值清单盘点 | 汇总当前全部 `pending_verification` 阈值项（来源 threshold 模型 + config），生成《阈值确认清单》 | 只盘点不改值 |
| S2A-2 | 专家评审包 | 输出可供行业专家逐项签字的评审文档（含每个阈值的用途 / 影响 / 建议来源） | **外部依赖：专家排期（TD-002/TD-016 遗留）** |
| S2A-3 | 签字转正机制 | 已签字阈值：配置中标记 `verified: true` + `verified_by` + `verified_at`；未签字维持 pending | 红线：无签字不转正 |
| S2A-4 | Design prompt 专业化 | 结合 2.1.3 Vision prompt 调优经验，三方案 prompt 注入已转正阈值与真实环境数据（消费 2.2.1 产出） | 不改 API 契约 |
| S2A-5 | 回归测试 | 三方案输出结构不变；新增"已转正阈值不再标 pending"断言 | 不降标准 |

**关联债**：TD-002（高）、TD-016（高）。**风险提示**：若专家评审无法排期，本任务可能整体顺延——**此为 Phase 2.2 最大外部依赖**，建议 Sprint 1 期间即启动专家预约。**交付报告**：`.ai/reviews/2.2.2_design_professional_report.md`。

### Sprint 2B —— 2.2.3 PDF 增强（T11，P2）

**目标**：PDF 方案书从"能生成"提升到"可交付客户"：模板美化 + 真实数据填充。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S2B-1 | 模板设计评审 | 版式 / 品牌区 / 三方案对比表 / 环境数据页 / 免责声明页；先出样张再实现 | 样张需主理人确认 |
| S2B-2 | 真实数据填充 | 消费 2.2.1 环境真实数据 + 2.2.2 已转正阈值；未转正项在 PDF 中**显式标注"待验证"**而非隐藏 | 红线：PDF 不得让 pending 数据看起来像已确认 |
| S2B-3 | 中文字体与排版 | 内嵌中文字体、分页 / 页眉页脚 / 目录；控制文件体积 | — |
| S2B-4 | 流式端点回归 | `/api/report/generate` 契约不变；大报告生成耗时监控（必要时 to_thread 化，复用 2.1.4 模式） | 不改 API 契约 |
| S2B-5 | 视觉回归测试 | PDF 结构断言（页数 / 关键章节存在）+ 黄金样本对比策略 | — |

**交付报告**：`.ai/reviews/2.2.3_pdf_enhancement_report.md`。

### Sprint 3 —— 2.2.4 MinIO 图片存储切换（TD-015，P2）

**目标**：`backend/app/core/storage.py` 从本地 `uploads/` 切换到 MinIO 对象存储，支持去重 + 租户隔离。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S3-1 | 存储抽象层 | 定义 `StorageBackend` 接口（put/get/exists/url）；`LocalStorage` 与 `MinIOStorage` 双实现，配置开关切换 | **保留本地实现**，CI 与开发环境默认 local，不引 MinIO 硬依赖 |
| S3-2 | MinIO 部署与配置 | docker-compose 本地 MinIO；bucket 命名含租户前缀（`{tenant_id}/…`）实现隔离 | 凭证走 `.env` |
| S3-3 | 内容去重 | 以内容 hash（sha256）作对象 key；Image 模型增加 `content_hash` 列（Alembic 迁移） | 迁移可回滚 |
| S3-4 | 存量迁移脚本 | `scripts/migrate_uploads_to_minio.py`：本地 → MinIO 幂等迁移 + 校验 | 迁移前备份 |
| S3-5 | 测试 | MinIO 用内存/临时 mock（或 local backend 等价测试）；uploads/vision 路由回归不破坏 2.1.4 异步链路 | CI 不依赖真实 MinIO |

**关联**：R4 前置、TD-015。**交付报告**：`.ai/reviews/2.2.4_minio_storage_report.md`。

### Sprint 4A —— 2.2.5 RAG 基础（T16 前奏，P2）

**目标**：知识库 RAG 奠基：knowledge 表扩展 + 向量检索链路（embedding → 存储 → 召回），**不做完整问答产品**。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S4A-1 | 向量库选型确认 | SSOT 已列 Qdrant 为目标；确认部署形态（docker-compose 本地）与 collection 设计 | 需主理人确认 |
| S4A-2 | Embedding provider 接入 | 复用 2.1.6 的 `providers.embedding` 占位（当前 disabled）；接入真实 embedding 服务并保留 disabled 降级 | 沿 ProviderRole.EMBEDDING 语义，不新造配置体系 |
| S4A-3 | knowledge 表扩展 | 增加 chunk / embedding 元数据字段（向量本体存 Qdrant，DB 只存引用）；Alembic 迁移 | 迁移可回滚 |
| S4A-4 | 检索 API | `POST /api/knowledge/search`（top-k 语义召回 + 关键词回落）；返回带 source 引用 | 新端点需补 docs/API.md（防 TD-018 复发） |
| S4A-5 | 灌注管道 | 规则/规范文档的 chunk → embed → upsert 脚本；来源可溯 | 红线：入库内容必须有出处 |
| S4A-6 | 测试 | embedding 与 Qdrant 全 mock；召回排序逻辑单测 | CI 不依赖外部服务 |

**交付报告**：`.ai/reviews/2.2.5_rag_foundation_report.md`。

### Sprint 4B —— 2.2.6 RBAC 基础（T13 前奏，P2）

**目标**：在既有 tenant / user 模型上建立最小可用 RBAC：角色 / 权限模型 + API 鉴权中间件骨架，**不做完整多租户 SaaS**。

| # | 任务 | 说明 | 约束 |
|---|---|---|---|
| S4B-1 | 角色模型设计 | 最小集：`admin` / `designer` / `viewer`；Role / Permission / UserRole 表（Alembic 迁移） | 复用既有 tenant/user，不重建 |
| S4B-2 | 认证骨架 | JWT（或 session）签发与校验依赖项 `get_current_user`；登录端点对接前端 `/login` 页 | 密钥走 `.env`（TD-008 关联） |
| S4B-3 | 鉴权依赖注入 | FastAPI `Depends(require_permission(...))` 模式；**先只挂敏感端点**（uploads / report / analysis），只读端点暂开放 | 渐进式，不一刀切破坏现有前端流程 |
| S4B-4 | 租户数据隔离预埋 | 查询层按 `tenant_id` 过滤的通用模式确立（与 MinIO 租户前缀呼应） | 不改现有 API 响应契约 |
| S4B-5 | 测试 | 角色矩阵测试（谁能/不能访问什么）；未认证降级行为测试 | — |

**交付报告**：`.ai/reviews/2.2.6_rbac_foundation_report.md`。

---

## 四、技术风险

| ID | 风险 | 等级 | 影响 | 缓解 |
|---|---|---|---|---|
| P22-R1 | **专家评审排期不可控**（2.2.2 阈值签字、TD-002/TD-016 遗留） | 高 | 2.2.2 整体顺延，Design 转正卡壳 | Sprint 1 期间即启动专家预约；2.2.2 拆出"盘点+评审包"（不依赖专家）与"签字转正"（依赖专家）两段，前段先行 |
| P22-R2 | **外部数据源可用性/成本**（天气/GIS API 限流、计费、国内可达性） | 高 | Environment 真实数据不稳定 | 选型 ADR 先行 + 缓存 + 降级回落 pending_verification；CI 全 mock |
| P22-R3 | **新增基建服务运维负担**（MinIO + Qdrant 两个新服务） | 中 | 本地/CI 环境复杂化 | 存储与向量库都做"抽象接口 + local/mock 回落"；docker-compose 统一编排；CI 零外部依赖 |
| P22-R4 | **SQLite↔PG JSONB 差异未验证**（R5/TD-011，2.1.8 尚未执行） | 中 | RAG/RBAC 新表在 PG 上行为未验证 | 建议将 2.1.8 PG 验证**前置插入 Sprint 3/4 之间**或并入 Sprint 4 前置检查（需主理人决策） |
| P22-R5 | **PDF 呈现误导**：pending 数据在客户报告中被误读为确认值 | 高（红线级） | 合规/安全风险 | S2B-2 强制"待验证"显式标注 + 编造扫描（CI 第 7 步）覆盖 PDF 模板文案 |
| P22-R6 | **鉴权引入破坏现有前端流程**（前端多数页面无 token 逻辑） | 中 | 页面 401 大面积报错 | S4B-3 渐进式挂载；先敏感端点后全量；前端改动最小化并单列清单审批 |
| P22-R7 | **Embedding 成本与供应商锁定** | 低 | RAG 成本失控 | 复用 providers.embedding 抽象，可替换；灌注量 Phase 2.2 控制在规则库小规模 |
| P22-R8 | **范围蔓延**：RAG/RBAC 属 Phase 3 主题的前奏，易越界做成完整功能 | 中 | Sprint 4 无法收口 | 本计划已用"基础/前奏/最小集"限定；验收标准（§六）逐条限界 |

---

## 五、测试策略

**总原则（承接 2.1.7 权威基线）**：不降低任何标准——覆盖率门槛 backend 60% / frontend 50% 不变；零 skip；`local_ci.sh` 8 步不删不改门槛；每 Sprint 收口必须 8/8 全绿。

1. **基线保护**：当前基线 backend 164 + frontend 29 = 193 passed。任何 Sprint 只增不减；既有用例失败 = 回归，按 2.1.7 四分类法（A 代码 / B 测试 / C 文档误报 / D 配置）处置后重跑。
2. **外部依赖零入 CI**：天气/GIS API、MinIO、Qdrant、embedding 服务在 CI 中一律 mock 或 local 等价实现；真实联调用独立脚本手动执行并把结果写入交付报告（不进 CI）。
3. **降级路径必测**：每个外部依赖必须有"不可用 → 降级 pending_verification / local 回落"的显式测试（延续 Vision 降级测试模式）。
4. **红线扫描扩展**：CI 第 7 步（check_fabrication）与第 8 步（check_hardcoded）覆盖新增目录（PDF 模板、RAG 灌注脚本、阈值配置）；阈值转正必须携带 `verified_by` 元数据，扫描规则识别"无签字的非 pending 数值"。
5. **迁移测试**：每个含 Alembic 迁移的 Sprint（S1-5 / S3-3 / S4A-3 / S4B-1）必须通过 CI 第 5 步 head↔base 双向 roundtrip。
6. **契约测试**：`/api/analysis/run`、`/api/report/generate`、uploads/vision 端点响应契约在全部 Sprint 中锁定不变（新增字段允许，破坏性变更禁止）；前端 Jest 29 用例作为契约消费方回归。
7. **分层测试配比**：单测（工具层/校验逻辑）为主，路由级集成测试次之，端到端（e2e）每 Sprint 至多补 1–2 条关键链路。

---

## 六、验收标准

### 分任务验收（每项完成即对照）

| 任务 | 验收标准 |
|---|---|
| 2.2.1 | ①数据源 ADR 获主理人批准；②Environment 输出的风压/湿度/盐雾/日照字段带 `{source, fetched_at}` 溯源；③数据源不可用时降级 pending_verification 有测试实证；④CI 无真实网络调用；⑤local_ci 8/8 全绿 |
| 2.2.2 | ①《阈值确认清单》完整覆盖全部 pending 项；②已签字阈值带 `verified_by/verified_at` 转正、未签字保持 pending（**一票否决项**）；③三方案 prompt 消费真实环境数据；④转正状态有测试锁定 |
| 2.2.3 | ①PDF 样张获主理人确认后实现；②pending 数据在 PDF 中显式标"待验证"（**一票否决项**）；③中文排版正常、结构断言测试通过；④`/api/report/generate` 契约不变 |
| 2.2.4 | ①StorageBackend 抽象 + local/minio 双实现，配置可切换；②对象 key 含租户前缀实现隔离；③content_hash 去重生效；④存量迁移脚本幂等且有校验；⑤CI 不依赖真实 MinIO |
| 2.2.5 | ①Qdrant collection 设计获确认；②embedding 走 providers.embedding 抽象且保留 disabled 降级；③`POST /api/knowledge/search` 返回带 source 引用；④入库内容 100% 有出处（**一票否决项**）；⑤docs/API.md 同步更新 |
| 2.2.6 | ①三角色最小集 + 迁移双向通过；②敏感端点（uploads/report/analysis）鉴权生效且角色矩阵测试覆盖；③只读端点不破坏现有前端流程（Jest 29 用例全过）；④JWT 密钥走 .env |

### Phase 2.2 整体收口标准

1. 六任务全部单项验收通过（含各自"一票否决项"零违反）；
2. `local_ci.sh` 8/8 全绿，覆盖率 ≥ 基线（backend ≥83%、frontend ≥93% 力争，不低于门槛 60%/50% 为硬线）；
3. 技术债 **OPEN ≤ 5**（当前 13；预期偿还：TD-015(MinIO)、TD-002(阈值签字)、TD-016(prompt 调优收尾)、TD-001(阶段编号统一)、TD-017/TD-018(登记即清)等，路径在各 Sprint 报告中逐一记账）；
4. 红线零违反：无签字转正、无编造数值、无不可溯源数据进 result；
5. 六份交付报告齐备 + `project_status.json` / `roadmap_v2.md` 状态同步；
6. 主理人逐 Sprint 验收记录完整（不跳阶段）。

---

## 七、待主理人决策项（审核时请一并给出）

| # | 决策项 | 建议 |
|---|---|---|
| D1 | Sprint 顺序确认（1→2→3→4）或允许 Sprint 2B/3 并行 | 建议串行为主，2B 与 3 可并行 |
| D2 | Environment 数据源选型与预算（S1-1） | Sprint 1 首个动作出 ADR 供选 |
| D3 | 专家评审排期（2.2.2 硬依赖） | **建议立即启动预约**，早于 Sprint 2 |
| D4 | 2.1.8 PG 验证是否前置插入 Phase 2.2（P22-R4） | 建议插入 Sprint 3 与 4 之间 |
| D5 | RBAC 认证方案（JWT vs session） | 建议 JWT（无状态，利于后续多实例） |

---

**本文档为规划交付物，未做任何代码改动。等待审核。**

**END**
