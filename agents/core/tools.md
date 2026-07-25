# Core Agent 工具契约

## Phase 0 工具状态

当前不启用任何真实工具或服务调用（`llm_enabled: false`）。

## 声明工具（仅占位）

| 工具 ID | 用途 | Phase 0 状态 | 备注 |
|---|---|---|---|
| `registry.lookup` | 通过 `AgentRegistry` 解析已注册 Agent | 已实现 | `agents/registry.py` |
| `orchestrator.placeholder` | 编排骨架返回结构化占位 | 已实现 | `agents/core/orchestrator.py` |

## 未来接入规则

- 仅通过注册表发现和调度专业 Agent。
- 每个工具必须声明输入、输出、超时、错误和权限边界。
- 工具返回必须附带来源、观测时间和可信度。
- 调用失败时保留错误上下文，不用模型猜测补齐。
- 密钥只能从环境或受管密钥服务读取，不进入提示词或日志。
- Phase 1+ 接入 LLM 时需先在 `technical_debt.md` 关闭 TD-006 / TD-008 后再做。