# Environment Agent 测试契约

## Phase 0 实现状态

- **已实现最小骨架**（T04）。
- `tests/agents/test_environment.py`：2 项（身份 + invoke 信封）。

## 单元测试（合同）

- `name == "environment"`，`version` 以 `phase0` 结尾。
- 声明工具包含 `weather_mcp` 与 `gis_mcp`。
- `invoke()` 在 `AgentContext.request_id` 为空字符串时拒绝执行（`AgentContext.__post_init__`）。
- `invoke()` 返回 `AgentResult`：
  - `data["agent"] == "environment"`
  - `data["pending_verification"] is True`
  - `data["gaps"]` 至少包含 `weather_data` 与 `gis_data` 两个缺口
  - `data["facts"]` 为空对象
- 信封形态满足 `to_envelope()` 标准格式。

## 集成测试（合同）

- `GET /api/agents/environment/invoke` 返回 `success: true`、`data.agent == "environment"`、`data.gaps` 存在。

## 评测测试（未来）

未来评测集必须覆盖：缺位置信息、缺授权、天气/地理工具失败、行业阈值缺失等场景；具体样例在 Phase 1 评估中建立。