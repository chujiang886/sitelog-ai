# BOIP LLM Provider 真实状态（provider_status.md）

**生成日期**：2026-07-26
**生成身份**：BOIP AI 架构治理工程师（架构收敛阶段）
**动作性质**：只读核对 `.env` / `agents/config.yaml`；**不修改任何业务代码**
**权威来源**：`.ai/project_status.json` 的 `llm_config` 段（本文件为其人读镜像）

---

## 1. 当前真实 LLM Provider（唯一事实）

| 项 | 值 |
|---|---|
| 机制 | `DualTrackRouter`，策略 `fastest` |
| `track_a`（真实链路） | `provider=openai_compat`，经 `${LLM_A_*}` 插值 |
| **当前真实身份** | **腾讯混元 TokenHub `HY-Vision-2.0-Instruct`**（多模态，文本+视觉共用） |
| 启用开关 | `agents/config.yaml::llm.enabled = true` |
| `track_b` | `provider=mock`（容灾/离线兜底） |
| 遗留键冲突 | `config.yaml` 顶层 `llm_enabled: false` / `llm_provider: ""`（Phase 1 占位，已被 `llm.enabled` 取代，属配置漂移，见 ADR-001） |

> ⚠️ 任何文档/注释中硬编码的 provider 品牌名（DashScope / qwen-max / minimax / gpt-4o / claude-3-5-sonnet）均为历史漂移，**当前事实一律以 `.env::LLM_A_*` 为准**。

---

## 2. Vision 模型（视觉）

- **名称**：`HY-Vision-2.0-Instruct`
- **来源**：`track_a`（与文本 Agent 共用同一端点）
- **多模态**：是（图像 + 文本）
- **降级行为**：无图 / 无网 / LLM 异常 → 捕获 `LLMRouterError` → 返回 `success=True` 且 `pending_verification` 占位（契约合规，不杜撰）
- **接入 commit**：`f53b4be`（Vision 接入 TokenHub 多模态）

---

## 3. Text 模型（文本）

- **当前文本 Agent**（Environment / Design / Core NLU）同样走 `track_a = HY-Vision-2.0-Instruct`。
- 即：**文本与视觉共用同一多模态模型的同一端点**。
- **架构局限**：未区分 `text_provider` 与 `vision_provider`；若未来 `track_a` 切为纯文本模型，Vision 将失效（登记为架构债 C4 / TD-013，Phase 3 前偿还）。
- **历史漂移**：`DashScope qwen-max`（T07 注释）→ `minimax`（phase2-delivery）→ `TokenHub`（当前）。

---

## 4. Mock 链路

- **`track_b`**：`provider=mock` → 恒返回 `MockProvider`（与 `.env` 无关）。
- **行为**：`MockProvider.complete` 现抛 `LLMProviderError`，避免污染 `fastest` 真实链路（Phase 2 修复）。
- **`.env` 中的 `LLM_B_*`**：存在但值为 `pending_verification`，因 `track_b.provider=mock` 而**无效（死配置）**。
- **用途**：离线 / 测试 / 容灾降级。

---

## 5. 环境变量来源（env var provenance）

| 变量 | 作用 | 是否在 `.env` | 是否进 git | 解析位置 |
|---|---|---|---|---|
| `LLM_A_BASE_URL` | track_a 端点 | ✅ 已设（`tokenhub.tencentmaas.com`，path 含 token，已隐去） | ❌ 已 gitignore | `config.yaml::llm.track_a.base_url: ${LLM_A_BASE_URL:pending_verification}` |
| `LLM_A_API_KEY` | track_a 密钥 | ✅ 已设（值不打印） | ❌ 已 gitignore | `OpenAICompatProvider` 读取 |
| `LLM_A_MODEL` | track_a 模型名 | ✅ 已设（`HY-Vision-2.0-Instruct`） | ❌ 已 gitignore | `config.yaml::llm.track_a.model: ${LLM_A_MODEL:pending_verification}` |
| `LLM_B_BASE_URL` | track_b 端点（死） | ✅（`pending_verification`） | ❌ 已 gitignore | `config.yaml`，但 `provider=mock` 不读 |
| `LLM_B_API_KEY` | track_b 密钥（死） | ✅（`pending_verification`） | ❌ 已 gitignore | 同上 |
| `LLM_B_MODEL` | track_b 模型（死） | ✅（`pending_verification`） | ❌ 已 gitignore | 同上 |

---

## 6. 结论（单一事实源）

- **唯一事实源**：`.env::LLM_A_*` → 经 `agents/config.yaml` 插值 → 当前 = **腾讯混元 TokenHub `HY-Vision-2.0-Instruct`**。
- 所有 provider 品牌名的硬编码描述均为历史漂移，不作为事实。
- 决策留痕见 [`.ai/decisions/ADR-001-provider-alignment.md`](.ai/decisions/ADR-001-provider-alignment.md)。
- 机器可读镜像见 [`.ai/project_status.json`](.ai/project_status.json) 的 `llm_config` 段。

**END**
