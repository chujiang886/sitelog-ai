# Engineering Agent 定义

## 标识

- 名称：Engineering Agent
- 版本：`0.1.0-phase2.1.5-skeleton`
- 实现状态：**骨架已建立**（Phase 2.1.5 —— 结构 / 契约 / 审核链 / 验证机制，无真实工程计算）
- 实现位置：`agents/engineering/agent.py`（验证机制：`agents/engineering/validation.py`）
- 注册状态：`agents/config.yaml` 中登记但 `enabled: false`（未进编排管道，TD-005 偿还时启用）

## 职责

为建筑开口方案提供工程分析能力框架，定义五个分析接口的稳定契约：

| 接口标识 | 职责 |
|---------|------|
| `wind_pressure` | 风压分析接口：评估开口部位风荷载工况（骨架，不产出数值） |
| `glass_safety` | 玻璃安全接口：评估玻璃配置安全性（骨架，不产出配置结论） |
| `profile` | 型材分析接口：评估型材选型合理性（骨架，不产出选型结论） |
| `hardware` | 五金分析接口：评估五金配置合理性（骨架，不产出选型结论） |
| `installation_risk` | 安装风险接口：评估安装工况风险（骨架，不产出风险等级） |

## 输入

- `AgentContext.request_id`
- `input_data.analyses`（可选）：要执行的接口子集，缺省执行全部五个接口
- `input_data.vision_result` / `environment_result` / `design_candidate`（可选）：
  上游 Agent 产物，骨架阶段仅声明透传、不消费

## 输出

`AgentResult`，其中 `data` 包含：

- `analyses`：每个接口一个**统一输出结构**：

```json
{
  "result": "",
  "confidence": "",
  "evidence": "",
  "verification_status": "pending_verification"
}
```

- `review_chain`：审核链记录列表（每个接口输出经 `EngineeringValidation.validate` 产出一条）
- `pending_verification`：恒为 `true`（骨架阶段）
- `gaps`：逐接口显式声明缺口（`<interface>_analysis: pending_verification`）

未知接口名 → `success=false` + `error.code=ENGINEERING_UNKNOWN_INTERFACE`。

## 审核链与验证机制

- 抽象契约：`EngineeringValidation`（`validation.py`），每个分析输出必须经
  `validate(interface, payload)` 产出审核记录后才能进入 `AgentResult`。
- 骨架默认实现：`PendingEngineeringValidation` —— 只做结构校验
  （统一四字段齐备性），工程结论一律 `pending_verification`。
- 演进：Phase 3+ 注入接真实规范库 / 规则引擎的实现类，Agent 侧无需改动。

## 限制（防编造红线）

- 不编造风压参数（无真实规范数据来源时 `result` 保持空串）。
- 不编造楼层阈值。
- 不编造玻璃厚度。
- 不编造评分权重。
- 不连接任何外部计算服务（`structural_calc_mcp` / `engineering_rules_mcp` 仅声明）。
- 不越权输出最终设计结论；只提供工程分析视角，最终决策留给编排层与主理人。
