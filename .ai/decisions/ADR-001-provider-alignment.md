# ADR-001：LLM Provider 统一决策

- **状态**：Accepted（已采纳，2026-07-26）
- **提出**：BOIP AI 架构治理工程师（架构收敛阶段）
- **关联**：`.ai/architecture_sync_report.md` 第五部分 C1；`.ai/project_status.json` `config_conflicts[C1]`
- **范围**：仅确立配置 / 文档单一事实源，**不修改 `agents/` 运行时代码**。

---

## 背景（Context）

架构同步阶段发现 LLM provider 身份在 **5 处互相矛盾**：

1. `agents/config.yaml` 注释："DashScope qwen-max"（T07 语境）
2. `docs/LLM.md` §4：`model: gpt-4o / claude-3-5-sonnet`、`是否启用: false`
3. `docs/PHASE0_LOG.md` T07："track_a：DashScope qwen-max"
4. `deliverables/...phase2-delivery`："track_a 指向 minimax"
5. **`.env` 当前事实**：`track_a = 腾讯混元 TokenHub HY-Vision-2.0-Instruct`

三代漂移：**DashScope → minimax → TokenHub**。代码机制本身健康（`config.yaml::track_a.provider=openai_compat` + `${LLM_A_*}` 插值），问题纯粹在注释 / 文档层。

---

## 决策（Decision）

1. **确立唯一事实源**：`.env::LLM_A_BASE_URL / LLM_A_API_KEY / LLM_A_MODEL` 是 LLM provider 的**唯一事实源**。所有文档、注释、对话提及 provider 时，一律引用「经 `agents/config.yaml` 从 `.env` 解析」，**不再硬编码任何 provider 品牌名**（DashScope / qwen-max / minimax / gpt-4o / claude-*）。
2. **当前真实身份**：`track_a = 腾讯混元 TokenHub HY-Vision-2.0-Instruct`（openai_compat），`llm.enabled = true`。
3. **`track_b` 维持 mock**：`config.yaml::llm.track_b.provider = mock`（容灾 / 离线兜底）；`.env` 中的 `LLM_B_*` 为无效死配置，后续择一清理（删除 或 显式启用 track_b 并填真实 key）。
4. **清理历史注释**：删除 `config.yaml` 注释中的 "DashScope qwen-max" 字样，改注「`track_a` 由 `.env::LLM_A_*` 注入，当前 TokenHub HY-Vision；`track_b` 维持 mock」。
5. **修复遗留键冲突**：`config.yaml` 顶层 `llm_enabled: false` / `llm_provider: ""`（Phase 1 占位）已被 `llm.enabled: true` 取代，属配置漂移，后续统一到 `llm.enabled` 单一开关。
6. **Vision 与 Text 共用 `track_a`**：当前 `HY-Vision` 为多模态模型，文本与视觉 Agent 共用同一端点。**本轮暂不改架构**，但登记为架构债（C4 / TD-013），Phase 3 前引入 `vision_provider` 与 `text_provider` 分离配置。

---

## 后果（Consequences）

**正面**
- 任何读档人可通过 `.env::LLM_A_*` → `config.yaml` 一条链路确认真实 provider，消除五源矛盾。
- 切换 provider 只需改 `.env`，无需动代码或文档。

**负面 / 待办（不在本轮，需授权）**
- 刷新 `docs/CHANGELOG.md` / `docs/LLM.md` / `docs/PHASE0_LOG.md` / `docs/AGENTS.md` / `docs/API.md` 中过时的 provider 描述（属文档同步，不改业务代码）。
- 处理 `LLM_B_*` 死配置（C3）。
- 单 `track_a` 多模态混用仍是架构隐患，列入 Phase 3 偿还。

---

## 遵循（Compliance）

- 本 ADR 与 `.ai/project_status.json` 的 `llm_config` 段保持一致。
- 后续 AI 会话读取 `.ai/project_status.json` 即视为已采纳本决策，无需重复判断 provider 身份。
- 关联文档：`.ai/provider_status.md`、`.ai/architecture_sync_report.md` 第五部分。

**END**
