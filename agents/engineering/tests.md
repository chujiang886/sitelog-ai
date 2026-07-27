# Engineering Agent 测试说明（Phase 2.1.5 骨架）

## 测试位置

- `tests/agents/test_engineering.py`

## 运行方式

```bash
backend/.venv/bin/python -m pytest tests/agents/test_engineering.py -q
```

## 覆盖矩阵

| 分组 | 断言内容 |
|------|---------|
| 身份 / 协议 | name=`engineering`、版本前缀、tools 声明、BaseAgent 继承 |
| 统一输出结构 | 五个接口各自返回且仅返回 `result` / `confidence` / `evidence` / `verification_status` 四字段；`verification_status` 恒为 `pending_verification` |
| 防编造红线 | 骨架输出的 `result` / `confidence` / `evidence` 必须为空串（任何非空即视为编造） |
| invoke 契约 | 缺省执行全部五接口；`analyses` 子集只执行子集；未知接口名 → `success=false` + `ENGINEERING_UNKNOWN_INTERFACE` |
| 审核链 | 每个接口一条 `review_chain` 记录；`structure_valid=true`；`validator=PendingEngineeringValidation` |
| 验证机制 | `PendingEngineeringValidation` 对缺字段 payload 返回 `invalid_structure`；自定义 `EngineeringValidation` 可注入替换 |
| 注册 / 配置 | `agents/config.yaml` 登记 `engineering` 条目但 `enabled: false`；loader 不注册、编排管道不含 engineering |
| envelope | `AgentResult.to_envelope()` 携带 `success` / `data` / `evidence` |

## 约束

- 测试不得引入任何真实工程数值（风压、楼层阈值、玻璃厚度、评分权重）。
- 测试不得连接网络或外部服务。
