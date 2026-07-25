# Environment Agent 工具契约

## Phase 0 工具状态

不连接任何真实工具或服务。

## 声明工具（占位）

| 工具 ID | 用途 | Phase 0 状态 | 备注 |
|---|---|---|---|
| `weather_mcp` | 获取风压 / 湿度 / 温度等气象数据 | 声明未实现 | `08_MCP_INTERFACE_DESIGN.md` |
| `gis_mcp` | 获取地理编码、海拔、灾害区等 | 声明未实现 | `08_MCP_INTERFACE_DESIGN.md` |

## 未来接入规则

- 仅当用户提供授权位置时调用天气/地理服务。
- 风压等级、楼层阈值等数值必须显式标注 `pending_verification`，不得直接代入计算。
- 工具失败时保留错误上下文，写入 `gaps` 字段，不补造数据。
- 禁止把模型推断当作工具观测（TD-002）。