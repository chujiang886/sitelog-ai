# BOIP Phase 3.2 Sprint 3.2.5-H1 — G6 发布授权模板（EngineeringReleaseApproval）

- **用途**：首次 `wind_pressure` 灰度放行的**主理人单独书面授权**记录模板（G6 门禁）。
- **红线**：**禁止 AI 自动创建 `EngineeringReleaseApproval`**；本模板仅由主理人线下确认后，由人工（或经主理人显式指令）写入授权库。AI 不代签、不自动生成 `authorized_by` / `approval_document_ref`。
- **SoD（职责分离）**：`authorized_by`（授权人 / 主理人）**必须 ≠** `rollback_owner`（回滚负责人）；且与 3.2.4 双签主体（阈值提供方 + 专家）相互独立。
- **当前状态（2026-08-01 实测）**：`EngineeringReleaseApproval` 库不存在，`approval_present=false`，count=0（G6 缺位）。本模板字段为空，待主理人填写。

---

## EngineeringReleaseApproval（七字段）

| 字段 | 说明 | 填写人 | 人工填写 |
|---|---|---|---|
| approval_id | 授权记录唯一 ID（建议 `ENG-REL-<日期>-<序号>`） | 主理人 | ________________________ |
| interface | 授权启用的接口（首期仅 `wind_pressure`） | 主理人 | `wind_pressure` |
| scope | 授权范围（如：仅风压、灰度比例、有效期） | 主理人 | ________________________ |
| authorized_by | 授权人（主理人）姓名 / 标识 | 主理人 | ________________________ |
| effective_time | 授权生效时间（ISO 8601） | 主理人 | ________________________ |
| rollback_owner | 回滚负责人（须 ≠ authorized_by） | 主理人 | ________________________ |
| approval_document_ref | 授权文书引用（线下签字件路径 / 编号） | 主理人 | ________________________ |

---

## 签字与生效

- [ ] `authorized_by` 已填且为真实主理人
- [ ] `rollback_owner` 已填且 **≠ authorized_by**（SoD 合规）
- [ ] `scope` 明确（仅 wind_pressure，不含其他接口）
- [ ] `approval_document_ref` 指向真实线下签字件
- [ ] `effective_time` 已到（不追溯生效）

**主理人签字（authorized_by）**：________________ 日期：__________

**回滚负责人确认（rollback_owner）**：________________ 日期：__________

---

## 写入方式（人工执行，非 AI 自动）

授权经主理人线下确认后，由人工触发写入（示例命令，须主理人显式授权后执行）：

```bash
# 仅示例；实际写入须经主理人书面授权，且脚本会校验 authorized_by ≠ rollback_owner
scripts/release/gray_release_ctl.py enable wind_pressure
# 脚本在 enable 前会：① 快照 verified.json ② 校验 EngineeringReleaseApproval 在场且生效 ③ 重跑 G1-G6 ④ 全过才翻接口级开关
```

> 注意：`enable` 仅翻接口级灰度开关；全局 `engineering_enabled=true` 仍须主理人经 G6 后于 config **显式**置位。两项独立，缺一不可。

> 最终硬约束：G1–G6 未全绿，任何情况下不得进入 enable（见主报告 任务5）。
