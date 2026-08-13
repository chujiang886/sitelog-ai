# 生产变更管控平面 · 人工操作清单（Phase 3.9.7-change）

> 本文件是**主理人 / 四角色（production-owner / release-manager / security-owner / auditor）**在真实生产变更场景下的操作清单。
> 它由 `agents/enterprise/production_change/` 变更管控平面支撑，但该平面**只起草、只仿真、只留痕、只校验结构**——
> **绝不执行、绝不部署、绝不回滚、绝不迁移、绝不应用、绝不激活、绝不宣布 GO**。任何真实动作都只能在**人类终端**由真人完成。

---

## 0. 一句话红线

本平面处于 **`PRODUCTION_CHANGE_CONTROL_BUILT_NO_GO`** 态：`engineering_enabled = False`。
AI 产出的一切（变更请求草稿、预检、仿真、证据包、裁决草稿）**均不表示批准、放行或激活**。
真实生产变更 / 真实部署 / 真实回滚 / 真实数据覆盖 / 真实密钥注入 / 真实 GO，一律由主理人在人类终端执行，
且须经四角色真人签署。

---

## 1. 哪些事 AI（本平面）**做**，哪些**不做**

| AI 做（只读 / 起草 / 仿真 / 留痕） | AI 绝不做（红线③/⑩） |
|---|---|
| 起草 `HUMAN_DRAFTED` / `AWAITING_HUMAN_REVIEW` 变更请求 | 执行变更（execute） |
| 生成变更计划、预约受控窗口（只登记，不开启） | 部署（deploy） |
| 跑**受控仿真**（`is_simulation` 恒 True，绝不触碰真实系统） | 回滚（rollback） |
| 校验变更前预检（只出 READY / BLOCKED / PENDING，不含 APPROVED） | 应用（apply）/ 迁移（migrate） |
| 生成仿真专用变更包（`simulated_only` 恒 True） | 激活（activate）/ 翻转 `engineering_enabled` |
| 记录真实 USER 已发生的行为（审计留痕） | 宣布变更 GO（trigger-go）/ 自动执行（auto-execute） |
| 输出裁决**草稿**（不输出 GO_LIVE_APPROVED） | 代四角色签署 / 代主理人拍板 |

---

## 2. 人工变更流程清单（主理人 + 四角色）

1. **[真人]** 在主理人人类终端提出变更意图；本平面仅以 `HUMAN_DRAFTED` 态承载草稿。
2. **[真人]** 填写变更计划与回滚引用（last-known-good 版本 / commit / DB revision / 配置基线）。
3. **[真人]** 在受控窗口登记：本平面只做 `reserve_change_window` 留痕，不自动开启任何窗口。
4. **[真人]** 触发**受控仿真**：确认 `is_simulation=true`、无任何真实系统被调用；阅读仿真结果。
5. **[真人]** 完成变更前预检：本平面只给 `READY_FOR_HUMAN_REVIEW` / `BLOCKED` / `PENDING_VERIFICATION`，**不**给 `APPROVED`。
6. **[四角色]** 各自以真实 USER 身份在终端登记签署（`HUMAN_SIGNOFF_REGISTERED` / `CHANGE_HUMAN_DECISION_RECORDED`）。
7. **[主理人]** 在确认四角色签署齐备、仿真通过、回滚引用完整后，**在人类终端**执行真实变更 / 部署 / 回滚。
8. **[主理人]** 如需真正启用生产，唯一动作：在人类终端将 `engineering_enabled` 置 `true`（**AI 不代执行**）。
9. **[真人]** 变更后验证：本平面只做 `register_post_change_verification` 留痕，不自动判定成功。

---

## 3. 平面不提供的端点（CI 闸门强制校验）

以下端点**明确不存在**；若任一真实出现，即违反红线③/⑩，`check_production_change_control_gate.py` 须失败：

```
POST /governance/change/execute
POST /governance/change/deploy
POST /governance/change/rollback
POST /governance/change/apply
POST /governance/change/migrate
POST /governance/change/activate
POST /governance/change/trigger-go
POST /governance/change/auto-execute
```

平面仅提供：`/governance/change/*` 的 **13 个只读 GET** + **13 个真实 USER 登记 POST**（`RELEASE_READ`）+ `/signoff`、`/decision`（`RELEASE_SIGNOFF`）。

---

## 4. 只读控制台（前端）

`frontend/src/app/governance-change/page.tsx` 为**只读**面板：
- 展示 13 项只读材料（readiness / contract / plan / window / preflight / checkpoint / abort-policy /
  rollback-reference / post-verification / evidence / simulation / failure-scenarios / package / decision-ledger）；
- 顶部恒显示 `engineering_enabled=false`；
- **不含任何 Deploy / Execute / Rollback Now 按钮**——真实动作只能发生在人类终端。

---

## 5. CI 闸门

`scripts/check_production_change_control_gate.py`（fail-closed）：

- 断言 `engineering_enabled=False`（红线①）；
- 断言变更管控不变量（`check_change_control_invariants`）：结构禁名齐全、状态机无 AI 自动态、
  `ChangeExecutionMode` 无 `ai_automatic`、13 个 `CHANGE_*` 审计类目齐全；
- 断言真实路由不含任何 absent_route（结构不可达）；
- 断言审计总数一致（ledger == baseline == 实时枚举 = 121）。

任一检查失败即整条流水线失败。

---

## 6. 责任边界（红线⑥/⑧）

- AI 不代替生产负责人；所有审计入口强制 `actor=USER`。
- AI 不代填真实人工证据；证据缺失时只标 `pending_verification`。
- AI 不翻转 `engineering_enabled`；唯一启用动作由主理人在人类终端执行。
