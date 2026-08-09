# BOIP Phase 3.2 Sprint 3.2.4 — 工程阈值审计流程设计

> 身份：BOIP AI 工程治理负责人
> 阶段性质：阈值治理审计流程设计（仅设计，不落地代码、不执行真实签署、不修改 verified.json）。
> 红线：不填真实参数、不设置 verified=true、不开启 engineering_enabled、不填真实专家姓名 / 规范数值；全部 pending_verification。
> 本流程与 `agents/engineering/review_log.jsonl`（append-only 不可篡改审核链）对齐，并服务于 `ExpertBackedEngineeringValidation` 四签状态机。

---

## 1. 审计流程总览

```
专家提交(submit)
    │  工程师/起草人填入 param/value/unit/source_ref，threshold_status=draft→review
    ▼
主理人审核(review_approve)
    │  主理人核对 source_ref 与数值，填写 verified_by/verified_at（角色标识符），threshold_status=review
    ▼
专家复核(expert_recheck)
    │  行业专家独立复核，填写 expert_verified_by/expert_verified_at（角色标识符）
    ▼
verified（双签完整 + 主理人核准）
    │  is_fully_verified=True，threshold_status=verified，verified=true（镜像）
    ▼
可用于 engineering（release）
       仅当 engineering_enabled=true（config.yaml 显式授权）且接口所需阈值全 verified
       → ExpertBackedEngineeringValidation 四签齐备 → engineering_approved + sign_off_id
```

关键原则：**审核链每一步在 `review_log.jsonl` 追加一条 append-only 记录**，`event_id` 为内容哈希（确定性），`prev_event_id` 链接上一条记录，形成不可篡改溯源链。

---

## 2. 角色与签署凭据

| 角色 | 标识符形态（非真实姓名） | 职责 | 落库字段 |
|---|---|---|---|
| `submitter` | `submitter-001`（角色标识） | 起草阈值草拟 / 填数值 / 附 source_ref | `review_log.action=submit` |
| `principal` | `principal-001`（主理人角色） | 核对 source_ref 与数值，主理人核准 | `verified_by` / `verified_at` |
| `expert` | `expert-001`（行业专家角色） | 独立复核数值与规范引用，专家签字 | `expert_verified_by` / `expert_verified_at` |

红线：所有 `signer` 字段仅写角色标识符，禁止写入真实专家姓名、真实机构名、真实联系方式。

---

## 3. 逐步动作与审核链记录

每条动作向 `review_log.jsonl` 追加一条记录，字段对齐 `review_log.REQUIRED_FIELDS`：
`event_id / threshold_id / action / signer_role / signer / timestamp / source_ref / prev_event_id`。

### 3.1 专家提交（submit）
- 输入：`threshold_id`（E-TH-xx / D-TH-xx）、`param`、`value`（占位或待填）、`unit`、`source_ref`（结构化占位）；
- 前置条件：`threshold_status ∈ {draft}`；
- 动作：`append_review_event(action="submit", signer_role="submitter", ...)`；
- 状态迁移：`draft → review`。

### 3.2 主理人审核（review_approve）
- 输入：主理人角色标识符、`verified_at`（UTC ISO8601）；
- 前置条件：`source_ref.standard` 与 `source_ref.clause` 非空（否则驳回回 draft）；
- 动作：`append_review_event(action="review_approve", signer_role="principal", ...)`；
- 落库：`verified_by=principal-001`、`verified_at=<ts>`，`threshold_status` 保持 `review`（待专家复核）；
- 状态迁移：`review`（主理人侧完成，等待专家复核）。

### 3.3 专家复核（expert_recheck）
- 输入：行业专家角色标识符、`expert_verified_at`（UTC ISO8601）；
- 前置条件：主理人已 `review_approve`（即 `verified_by` / `verified_at` 非空）；
- 动作：`append_review_event(action="expert_recheck", signer_role="expert", ...)`；
- 落库：`expert_verified_by=expert-001`、`expert_verified_at=<ts>`；
- 状态迁移：`review → verified`（双签完整，`is_fully_verified=True`）。

### 3.4 verified（阈值转正）
- 门禁（见治理设计附录B.1）全绿后：`verified=true`（镜像）、`threshold_status=verified`、`version` 声明；
- `threshold_loader.is_fully_verified` 返回 `True`，该阈值可被 `ExpertBackedEngineeringValidation` 计入 `threshold_verified`。

### 3.5 可用于 engineering（release）
- 仅当 `engineering_enabled=true`（config.yaml 显式授权，独立书面授权，见治理设计附录B.2）；
- 目标接口的 `get_interface_thresholds` 全部 `verified=true` 且双签完整；
- `ExpertBackedEngineeringValidation.validate` 四签齐备 → `engineering_approved` + 派生 `sign_off_id`（十六位内容哈希）；
- 追加 `review_log` 系统放行事件（`action="release"`, `signer_role="system"`）。

---

## 4. 审核链完整性校验（审计可复核性）

复核一条阈值是否"干净转正"，需回放 `review_log.jsonl` 并断言：
1. 存在该 `threshold_id` 的 `submit` → `review_approve` → `expert_recheck` → `verified` 四段连续链路；
2. 每段 `event_id` 可由 `compute_event_id` 重新派生并比对一致（防篡改）；
3. 每段 `prev_event_id` 正确指向上一段 `event_id`（链式闭环）；
4. 主理人与专家签字时间戳逻辑有序（submit ≤ review_approve ≤ expert_recheck ≤ verified）；
5. `verified.json` 中该阈值 `is_fully_verified=True` 与审核链动作一致。

任何一段缺失 / 哈希不一致 / 链指针断裂 → 审计失败，强制 `pending_verification`。

---

## 5. 本阶段边界

- 本流程为**设计文档**，不执行任何真实提交 / 审核 / 复核 / 放行动作；
- 不修改 `verified.json`、不追加 `review_log.jsonl`、不开启 `engineering_enabled`；
- 所有 `value` / `source_ref` / `signer` 保持 `pending_verification` 占位；
- 待主理人审核通过后，本流程作为 3.2.4 实施（verified.json 真实化，须单独书面授权）与 3.2.5（engineering_enabled 开启灰度，须单独书面授权）的操作手册。
