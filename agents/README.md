# BOIP Agent 骨架

`agents/` 保存独立于 Web 框架的 Agent 合同和注册机制。Phase 0 / T01 只建立基础抽象与文档契约，不实现行业判断、不调用真实 LLM、不注册不存在的外部工具。

## 注册机制

1. 具体 Agent 继承 `BaseAgent`，提供唯一 `name`、说明 `description`、契约 `version`、工具声明 `tools` 和异步 `invoke`。
2. 启动装配层显式创建具体 Agent，并调用 `AgentRegistry().register(agent)`。
3. 调用方使用 `AgentRegistry().get(name)` 获取实例，或用 `list_all()` 获取按名称排序的快照。
4. 重复名称会被拒绝，避免运行时悄然覆盖。

`AgentContext` 保存请求输入、上下文元数据和证据；`AgentResult` 采用 `success` 与 `data` 作为标准结果字段，并保留证据链入口。所有映射与序列均在边界处冻结，便于追踪与测试。

## Agent 文档四件套

每个 Agent 目录必须包含：

- `agent.md`：职责、输入、输出与限制
- `prompt.md`：系统提示词边界和结构化响应要求
- `tools.md`：允许工具、权限与失败策略
- `tests.md`：合同测试与评测要求

Phase 0 的四个业务 Agent 骨架为 Core、Environment、Vision、Design；扩展范围受现有技术债登记约束。
