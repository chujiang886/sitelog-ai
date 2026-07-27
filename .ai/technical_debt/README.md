# BOIP 技术债台账（Phase 3.0 重分类）

**整理时间**：2026-07-28（Phase 3.0 前置整理 Sprint）
**整理人**：BOIP AI CTO
**上游历史台账**：`../BOIP_AI_Documents/technical_debt.md`（TD-001~TD-016 原始登记，保留作历史档案；本目录为**当前有效分类视图**，二者冲突以本目录为准）
**关联**：`.ai/project_status.json::tech_debt`（机器可读镜像）

---

## 分类原则

- **A 类：Phase 3 启动前必须解决** —— 阻塞 Phase 3 主线（工程闭环 / SaaS 渐进 / RAG 问答）或存在安全/一致性风险。
- **B 类：Phase 3 期间处理** —— 与 Phase 3 具体子阶段绑定，提前做浪费、拖后做阻塞。
- **C 类：长期优化** —— 不阻塞主线，机会性偿还。

---

## 状态总览（2026-07-28）

| 状态 | 数量 | 清单 |
|---|---|---|
| OPEN | **11** | TD-001, 002, 005, 006, 007, 008, 009, 010, 011, 016, 019 |
| RESOLVED（本次 3.0 新增偿还） | 3 | TD-003, TD-017, TD-018 |
| RESOLVED（历史） | 4 | TD-004, TD-012, TD-013, TD-014, TD-015（TD-013 按 2.1.6 Provider 解耦收口，成本评测项并入 TD-006） |

> Phase 2.2 出口目标 OPEN≤5 未达成（当时 13）；本次 3.0 偿还 3 项（TD-003/017/018）并将 TD-013 收口，OPEN 降至 **11**。达标路径见文末「还债路线」。

---

## A 类：Phase 3 启动前必须解决（3 项）

### TD-002 | 工程阈值未确认（高）🔴
- **现状**：`agents/design/thresholds/verified.json` D-TH-01~05 全部 `verified=false`、`value=null`；Engineering 五分析接口输出恒 `pending_verification`。
- **为什么是 A**：Phase 3.1 工程引擎闭环是主线，没有专家确认的阈值，闭环无法转正——这是唯一同时阻塞安全红线与产品价值的债。
- **动作**：主理人排期**行业专家评审**（阈值清单已具备机器可读结构，评审即回填 `value` + `verified_by/verified_at`）。转正需主理人+专家双控，AI 不得代填。
- **责任分工**：主理人（约专家）→ 专家（给数）→ 工程（回填+测试）。

### TD-008 | 密钥管理基础设施缺失（中→升高）🔴
- **现状**：JWT_SECRET / LLM_A_* / MinIO 密钥全部依赖本机 `.env`（已 gitignore）。开发期可接受。
- **为什么是 A**：Phase 3.2 SaaS 渐进意味着出现真实用户与真实凭据；无密钥轮换/托管机制前不得部署生产。
- **动作**：Phase 3 启动前定方案（最低成本路径：云厂商 Secrets Manager / 腾讯云 SSM；不自建 Vault）。生产部署为硬门禁。

### TD-019 | RBAC 遗留收敛（新登记，中）🟠
- **现状**（2.2.6 遗留）：① 无 refresh token / 吊销机制（token 60min 自然过期）；② 前端 `/login` 占位页未对接 `/api/auth/login`；③ `User.role` 遗留列（CHECK admin/designer/sales/customer/worker）与 `user_roles` 新表并存双轨。
- **为什么是 A**：③ 双轨授权模型是数据一致性隐患，越晚收敛迁移成本越高；② 是 Phase 3.2 SaaS 首步的前置。
- **动作**：Phase 3 启动前完成 ②（前端对接，1 个 Sprint 内）；① ③ 给出设计决策（可实施放 B 类执行）。

## B 类：Phase 3 期间处理（5 项）

| 债 | 级别 | 绑定子阶段 | 说明 |
|---|---|---|---|
| **TD-011** SQLite↔PG JSONB 差异 | 中 | Phase 3.2（接真实 PG 时） | 接 PG 后 `EXPLAIN ANALYZE` + gin 索引评估；提前做无实数据支撑 |
| **TD-016** Vision prompt 专家调优 | 高 | Phase 3.1（与 TD-002 同批专家） | prompt 骨架已稳定，与阈值评审合并排期节省专家时间 |
| **TD-006** LLM 模型选型/成本评测 | 中 | Phase 3.1 | TokenHub 已可用；账单回填 + 成本/性能评测后再定长期选型（并入原 TD-013 成本项） |
| **TD-010** 后端拆分粒度 | 中 | Phase 3.2（负载出现后） | 单体 FastAPI 当前足够；SaaS 用户量出现前不拆 |
| **TD-005** Agent 数量取舍 / Engineering 启用 | 低→中 | Phase 3.1 | Engineering 骨架已建，启用决策与工程闭环绑定 |

## C 类：长期优化（3 项）

| 债 | 级别 | 说明 |
|---|---|---|
| **TD-001** 阶段编号不一致 | 中→低 | SSOT（project_status.json）已成为唯一事实源，历史文档编号冲突影响已被隔离；机会性清理 |
| **TD-007** i18n | 低 | 无海外需求前不做 |
| **TD-009** 前端组件库 | 低 | Tailwind 原子类当前足够；组件规模翻倍前不引入 |

---

## 本次 3.0 偿还记录（2026-07-28）

| 债 | 偿还方式 |
|---|---|
| **TD-003** 文档/代码版本联动 | 建立收敛机制：CHANGELOG 补齐 2.1.4~2.2.6 全部条目；README/LLM.md/AGENTS.md/API.md 刷至 Phase 2.2 COMPLETED；SSOT 与文档双向引用。后续每 Sprint 报告即文档（流程已固化） |
| **TD-017** provider 注释/文档漂移 | 2.1.1/2.1.6 已清理 config.yaml 与 LLM.md；本次补 embedding 段落收口。`.env::LLM_A_*` 唯一事实源已全文档贯彻 |
| **TD-018** analysis/report 端点缺文档 | docs/API.md 已含 `/api/analysis/run`、`/api/report/generate`，本次再补 auth/rag 端点与鉴权矩阵 |

## 还债路线（达成 OPEN≤5）

1. **Phase 3 启动前**（A 类）：TD-019② 前端 login 对接（1 Sprint）→ OPEN 10；TD-008 方案定稿（文档级）→ 可标 IN_PROGRESS。
2. **Phase 3.1**（专家评审批）：TD-002 + TD-016 同批专家解决 → OPEN 8。
3. **Phase 3.1~3.2**：TD-005（Engineering 启用决策）、TD-006（成本评测）、TD-019①③ 收口 → OPEN 5。
4. C 类 3 项（TD-001/007/009）长期挂账，不计入达标口径需主理人确认；若计入，则 Phase 3 末再清 TD-001。
