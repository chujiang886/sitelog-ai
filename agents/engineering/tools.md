# Engineering Agent 工具声明（Phase 2.1.5 骨架）

> 骨架阶段：**仅声明，不连接**。所有工具调用能力等待真实服务接入评审。

## 已声明工具

| 工具标识 | 用途 | 状态 |
|---------|------|------|
| `structural_calc_mcp` | 结构计算服务（风压 / 玻璃 / 型材计算） | 仅声明，未连接（pending_verification） |
| `engineering_rules_mcp` | 工程规范 / 规则库检索 | 仅声明，未连接（pending_verification） |

## 声明与实现的对应关系

- 代码事实源：`agents/engineering/agent.py` 中 `EngineeringAgent.tools`
  返回 `("structural_calc_mcp", "engineering_rules_mcp")`。
- 本文件与代码不一致时以代码为准，并须同步修订本文件。

## 接入前置条件（Phase 3+）

1. 真实规范库 / 计算服务选型经主理人评审。
2. 每个工具的输出必须携带来源与时间戳，进入 `Evidence` 链。
3. 工具不可用时按「不编造」原则降级：`result` 空串 +
   `verification_status=pending_verification`，并在 `gaps` 中登记。
