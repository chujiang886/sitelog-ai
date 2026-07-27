# BOIP Phase 2.1 Sprint 1 执行状态

- **执行人**：BOIP AI 高级工程负责人
- **依据**：`.ai/roadmap_v2.md`（任务 2.1.1 / 2.1.4 / 2.1.6 / 2.1.7）
- **原则**：禁止开发新业务功能；提升稳定性、一致性、可维护性
- **每任务交付**：更新任务状态 + 更新文档 + 运行测试 + 输出完成报告

## 任务状态总览

| 任务 | 标题 | 状态 | 测试 |
|---|---|---|---|
| 2.1.1 | 文档/配置全面对齐收尾 | ✅ 完成 | ✅ backend 71 + agents 72 + 前端 11 全绿（见报告） |
| 2.1.4 | AsyncSession 引入（TD-012） | ⏳ 待开始 | — |
| 2.1.6 | Provider 架构解耦（C4/TD-013） | ✅ 编码完成 | agents 83 + backend 64 + 前端 29 = 176 passed（见完成报告） |
| 2.1.7 | 测试基线刷新与 collection 冲突修复 | ⏳ 待开始 | — |

## 各任务记录

### 2.1.1 文档/配置全面对齐收尾
- 状态：✅ 完成（2026-07-26）
- 范围说明：**纯文档/注释对齐，未引入任何行为变更**（符合 Sprint 1 原则）。
- 已完成子项：
  - `docs/CHANGELOG.md`：追加 Phase 2 早期（T12-T15）+ 2.1.1 两段事实记录。
  - `docs/LLM.md`：标题段改 Phase 2 TokenHub 事实；Mermaid 架构图 TrackA=TokenHub、TrackB=Mock 容灾；§2 切换指南去掉 `sk-ant-...` 误导，改为 `track_b=mock`；§4 成本表删 gpt-4o/claude 占位、标 `是否启用: true`、补 vision/text 解耦说明；§5 技术债 TD-014 标 RESOLVED。
  - `docs/PHASE0_LOG.md`：T07 段加"演进注释"——DashScope qwen-max(401)→minimax→TokenHub。
  - `docs/AGENTS.md`：Agent 表 Vision/Environment/Design 改"已真实接入"；§4 编排管道去 pending；§6 补多模态 provider + modality 解耦；新增 §8 分析/报告编排（`/api/analysis/run`、`/api/report/generate`、`ReportGenerator`）。
  - `docs/API.md`：新增"分析与报告（Phase 2）"章，含两条路由契约骨架。
  - `agents/config.yaml`：顶层注释改 Phase 2；`llm_enabled`/`llm_provider` 标"弃用"；T07 注释块改 TokenHub 演进；行为零变化（lint/loader 仍兼容）。
  - `.gitignore`：补 `frontend/.next.trash/`、`deliverables/`（后者即"归档"语义，不再纳入版本控制）。
- **刻意推迟到 2.1.6**：`llm.vision` 配置段 + `build_router_from_config(modality=...)` + Vision Agent 接线。理由：这三件属于"provider 解耦"功能整体，放在 2.1.6 一并落地并由测试验证，避免在 2.1.1 埋下未被消费的悬挂配置。

### 2.1.4 AsyncSession 引入（TD-012）
- 状态：⏳ 待开始

### 2.1.6 Provider 架构解耦（C4/TD-013）
- 状态：✅ 编码完成（2026-07-26）
- 设计文档：`.ai/tasks/2.1.6_provider_decoupling_design.md`（审核通过）；完成报告：`.ai/tasks/2.1.6_provider_decoupling_completion.md`。
- 执行约束（审核确认，比设计更保守）：① 严格按设计；② 不扩大范围；③ 不改 Agent prompt；④ 不改前端；⑤ 保留 `modality=` deprecated 别名；⑥ 保留 `track_a/track_b` 兼容解析（不作为新入口）；⑦ embedding 仅 disabled 占位。
- 两步演进：先落 `modality` 软开关（text/vision 选块），再经设计阶段升级为 `ProviderRole` 语义化架构（本完成记录即第二步全量落地）。
- 改动清单：
  - `agents/llm/router.py`：新增 `ProviderRole`（TEXT/VISION/EMBEDDING/FALLBACK）；`build_router_from_config` 加 `role=` 参数（保留 `modality=` deprecated 别名→`_modality_to_role`）；新增 `resolve_provider(config, role)`（vision→text 回落 / 旧键兼容回落 / embedding→None）+ `build_embedding_provider`。
  - `agents/config.yaml`：`track_a/track_b/vision` → `llm.providers:{text,vision,embedding,fallback}`（text/vision 同源 TokenHub、fallback=mock、embedding=disabled）；注释保留"router.py 仍兼容旧键"。
  - `agents/vision/agent.py`：`role=ProviderRole.VISION`（原 modality="vision"）；移除未用 import json。
  - `agents/environment/agent.py` / `agents/design/agent.py`：`role=ProviderRole.TEXT`。
  - `agents/core/orchestrator_chat_integration.py`（修 P2 既有 bug）：`_ensure_initialized` 先 `load_llm_config(config_path)` 再 `build_router_from_config(llm_cfg, role=ProviderRole.TEXT)`；原误传 `config_path`(str) 当 Mapping 致 `router=None`、聊天 LLM 增强失效。占位文案去 `LLM_B_API_KEY` 误导。
  - 测试：`test_router.py` 重写 10 项；`test_orchestrator_chat_integration.py` 新增（验证 P2 修复）；`test_environment.py`/`test_design.py` 共 5 处 monkeypatch 桩改 `lambda _cfg, **_kw: fake_router`。
  - `scripts/lint/check_fabrication.py`（修 2.1.7 遗留扫描倒退）：`OUTLINE_SECTION_RE` 改行首前缀判定，避免含数值示例串误当大纲编号放行；表格 `|` 与字母紧邻编号（P0/R4/D1）跳过。
  - `docs/LLM.md` / `docs/AGENTS.md`：同步 ProviderRole + resolve_provider、Agent 状态、`modality=` deprecated 标注。
- 验证（2026-07-26 实测）：agents **83** + backend **64** + 前端 **29** = **176 passed**；`bash scripts/ci/local_ci.sh` 8 步全绿（"Local CI passed"）。
- 保留兼容层：modality= 别名 / track_a/track_b 解析 / embedding disabled 占位——均不删，仅不作新入口。
- 待跟进（不属本任务范围）：`orchestrator_chat_integration.chat()` 独立元组解包 bug（`route()` 返回 `(response, results)` 赋给 `response` 后 `.finish_reason` 抛 AttributeError），已单列待修。

### 2.1.7 测试基线刷新与 collection 冲突修复
- 状态：⏳ 待开始
