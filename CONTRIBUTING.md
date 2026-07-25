# BOIP 贡献指南

## 分支策略

仓库采用 Git Flow：

- `main`：稳定发布分支，禁止直接修改。
- `develop`：日常集成分支。
- `feature/*`：从 `develop` 创建的功能分支。
- `bugfix/*`：从 `develop` 创建的问题修复分支。

所有变更必须通过合并请求进入 `develop` 或 `main`。

## 提交规范

提交信息采用 `<type>(<scope>): <summary>`：

- `feat`：新增功能
- `fix`：问题修复
- `test`：测试变更
- `docs`：文档变更
- `refactor`：不改变行为的重构
- `chore`：工程配置或依赖维护

示例：`chore(repo): initialize phase zero workspace`

提交应聚焦单一目的，说明修改内容，不得混入密钥、真实业务数据或未经验证的行业参数。

## 开发流程

1. 阅读 `BOIP_AI_Documents/` 中与任务相关的设计文档。
2. 从 `develop` 创建 `feature/*` 或 `bugfix/*` 分支。
3. 完成最小正确实现和对应测试。
4. 执行 `bash scripts/ci/local_ci.sh`。
5. 同步工程实施记录；涉及架构、API 或数据库时同步对应设计文档。
6. 创建合并请求并填写影响范围、测试证据、回滚方案与技术债。

## 评审要求

- 至少一名代码评审者批准。
- CI 必须通过；不得跳过失败测试。
- API 返回结构统一为 `{success, data}`。
- 新 Agent 必须具备 `agent.md`、`prompt.md`、`tools.md`、`tests.md`。
- 未经可靠来源确认的行业数值必须标记 `pending_verification`，禁止进入业务判断。
- 数据库结构变更必须同时提交迁移脚本与数据库文档更新。

## 合并前检查

- [ ] 代码和配置符合任务范围
- [ ] 测试已新增且通过
- [ ] 架构、API、数据库文档已按影响同步
- [ ] CHANGELOG 和阶段日志已更新
- [ ] 技术债已披露或明确无新增
- [ ] 未提交敏感信息
