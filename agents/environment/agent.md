# Environment Agent 定义

## 标识

- 名称：Environment Agent
- 版本：`0.1.0-phase0`
- 实现状态：**已实现最小骨架**（T04）
- 实现位置：`agents/environment/agent.py`

## 职责

将经授权、可追踪的环境数据整理为结构化环境事实与风险输入，供后续专业 Agent 使用。

## 输入

- `AgentContext.request_id`
- 用户明确提供的位置和建筑上下文
- 具有来源、时间和可信度的环境证据

## 输出

`AgentResult`：`data` 只包含可追踪环境事实、数据缺口和确认状态，`evidence` 指向使用过的来源。

## 限制

- 不杜撰天气、地理或行业标准数据。
- 不以未验证阈值作工程结论。
- 不越权输出设计方案。
- Phase 0 不连接天气、地图或其他真实服务（`weather_mcp` / `gis_mcp` 仅声明）。
- `facts` 字段保持空对象；`gaps` 显式列出每个缺口并标注 `pending_verification`。