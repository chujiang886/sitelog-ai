# BOIP 文档索引（Document Index）

**维护方**：架构治理（`.ai/` 为 AI 生成、机器可读的实时状态）
**最后更新**：2026-07-28（3.0 前置整理 Sprint 文档收敛）
**说明**：本索引区分「真实项目状态入口（AI 维护、优先读取）」与「手写工程文档（3.0 已收敛至 Phase 2.2 COMPLETED）」。

---

## 一、真实项目状态入口（优先读取）

> 以下文件是 AI 会话间的**单一事实来源（SSOT）**，反映代码真实状态，优于滞后的手写文档。后续 AI 会话应优先读取。

- [`.ai/project_status.json`](.ai/project_status.json) — 机器可读单一事实来源（阶段 / LLM / 已完成模块 / 技术债 / 风险）
- [`.ai/architecture_sync_report.md`](.ai/architecture_sync_report.md) — 六部分人读架构同步报告
- [`.ai/provider_status.md`](.ai/provider_status.md) — LLM Provider 真实状态（Vision / Text / Mock / 环境变量来源）
- [`.ai/decisions/ADR-001-provider-alignment.md`](.ai/decisions/ADR-001-provider-alignment.md) — LLM Provider 统一决策
- [`.ai/tasks/phase0_initial_analysis.md`](.ai/tasks/phase0_initial_analysis.md) — Phase 0 初始化分析
- [`.ai/alignment_completion_report.md`](.ai/alignment_completion_report.md) — 架构收敛完成报告
- [`.ai/technical_debt/README.md`](.ai/technical_debt/README.md) — 技术债 A/B/C 分类台账（3.0 重分类，SSOT 镜像）
- [`.ai/reviews/phase2.2_release_freeze_report.md`](.ai/reviews/phase2.2_release_freeze_report.md) — 3.0 版本冻结报告（5 批 commit 清单）
- [`.ai/reviews/phase3_readiness_report.md`](.ai/reviews/phase3_readiness_report.md) — Phase 3 启动准备报告（能力/架构/债/风险/路线）

---

## 二、工程实施文档（`docs/`）

| 文档 | 状态 |
|---|---|
| `docs/README.md` | 工程文档索引（✅ 已刷 Phase 2.2 COMPLETED / Phase 3 planning） |
| `docs/PHASE0_DONE.md` | Phase 0 验收（准确，历史） |
| `docs/PHASE0_LOG.md` | Phase 0 实施日志（历史，T07 provider 标注为当时语境，非缺陷） |
| `docs/CHANGELOG.md` | ✅ 已补 2.1.4~2.2.6 全条目 + TokenHub / 3.0 专项 |
| `docs/AGENTS.md` | ✅ 已补 Vision / Environment(2.2.1) / Design(2.2.2) / RBAC(2.2.6) 接入细节 |
| `docs/LLM.md` | ✅ 已刷 Phase 2.2 COMPLETED + embedding 落地（2.2.5） |
| `docs/API.md` | ✅ 已含 `/api/analysis/run`、`/api/report/generate` + auth/rag 鉴权矩阵 |
| `docs/VISION.md` | Vision 设计（基本准确，待补 TokenHub 多模态细节） |
| `docs/CONVERSATION_API.md` | 会话 API（准确） |
| `docs/TESTING.md` | 测试体系（准确） |

---

## 三、上游产品设计文档（仓库外 `BOIP_AI_Documents/`）

- `BOIP_PROJECT_TASK_TREE.md` — 任务树（⚠️ 停 Phase 0 视角，需升级为实时任务树）
- `technical_debt.md` — 技术债册（⚠️ 历史档案；TD-013/TD-014 仍 minimax/DashScope 语境，有效分类视图见 `BOIP/.ai/technical_debt/README.md`）
- 其余 20 份产品 / 架构 / 路线图 md

---

## 四、根文档与交付物

- `README.md` — 仓库入口（已补「Current Architecture Status」实时架构状态）
- `deliverables/software-company/*.md` — 前序会话交付文档（⚠️ 处于 untracked，待归档进文档体系）

---

## 五、读取建议

1. 先读 `.ai/project_status.json`（SSOT），再按需读对应 `.ai/*.md` 人读报告。
2. 手写 `docs/*` 与 `BOIP_AI_Documents/*` 可能滞后，凡与 `.ai/*` 冲突以 `.ai/*` + 人类主理人决策为准。

**END**
