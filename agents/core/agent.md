# Core Agent 定义

## 标识

- 名称：Core Agent
- 版本：`0.1.0-phase0`
- 实现状态：**已实现最小骨架**（T04）
- 实现位置：`agents/core/agent.py` + `agents/core/orchestrator.py`

## 职责

接收统一上下文、拆分可追踪任务、调度已注册专业 Agent，并在保留证据来源的前提下汇总结构化结果。

## 输入

- `AgentContext.request_id`
- 经验证的用户输入映射
- 可用证据列表
- 调用链元数据

## 输出

`AgentResult`：通过 `to_envelope()` 转写为标准 API 信封 `{success, data, error?}`。

## 限制

- 不直接执行专业行业判断。
- 不调用未注册的 Agent 或未声明工具。
- 缺少可靠证据时明确返回需确认状态，不补造数据。
- Phase 0 不连接真实 LLM（`agents/config.yaml::llm_enabled=false`）。
- 真实编排走 `agents.core.orchestrator.CoreOrchestrator`；`CoreAgent.invoke` 仅返回标准占位信封。
