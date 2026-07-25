# Core Agent 测试契约

## Phase 0 实现状态

- **已实现最小骨架**（T04）。
- `tests/agents/test_core.py`：2 项（身份 + invoke 信封）。
- `tests/agents/test_orchestrator.py`：4 项（pipeline / missing agent / context 入口）。
- `backend/tests/test_agent_routes.py`：Core invoke 路由 1 项。

## 单元测试（合同）

- 接受有效 `AgentContext`。
- 拒绝空请求标识（在 `AgentContext.__post_init__` 处抛 `ValueError`）。
- 仅调用注册表中存在的 Agent。
- 对重复或缺失 Agent 返回可诊断错误。
- 汇总结果保持 `success`、`data` 和证据链。

## 集成测试（合同）

- `GET /api/agents/core/invoke` 返回标准信封 `{"success": true, "data": {"agent": "core", ...}}`。
- `python -m agents.loader list` 输出 4 个 Agent 名称。

## 评测测试（未来）

未来评测集必须覆盖正常编排、输入缺失、专业 Agent 失败、证据冲突和无可靠数据等场景；具体样例在对应实施任务中建立，且任何工程数值必须 `pending_verification`。