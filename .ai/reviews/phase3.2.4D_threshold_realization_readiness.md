# BOIP Phase 3.2 Sprint 3.2.4-D — 真实阈值接入实施方案就绪报告

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：进入真实阈值接入（3.2.4 实施）前的「实施方案就绪」评估——**本阶段不填写真实工程参数、不修改 verified.json 真实 value、不设置 verified=true、不开 engineering_enabled、不输出 engineering_approved**，全部保持 `pending_verification`。

---

## 0. 就绪结论

| 项 | 状态 |
|---|---|
| 阈值迁移方案（schema_version 1 → 2） | ✅ 设计就绪（见 `phase3.2.4D_threshold_migration_plan.md`） |
| D-TH 双签决策 | ✅ 推荐方案 A（补专家双签），待主理人书面确认 |
| source_ref validator 设计 | ✅ 六项检查（standard/clause/edition/url/hash）就绪 |
| 真实录入流程 | ✅ 专家提供 → 主理人审核 → 专家复核 → verified，全 review_log |
| 实施安全检查（G1~G6） | ✅ 进入真实化前门禁清单就绪 |
| 代码改动 | 无（纯设计，零落库） |
| 防编造扫描 | 0 命中（待复扫） |

**全部阈值保持 pending_verification**；本阶段为"实施方案设计"，不进入 3.2.4 实施（verified.json 真实化）与 3.2.5 实施（engineering_enabled 开启灰度）——二者均须主理人**单独书面授权**。

---

## 1. 任务映射

| 用户任务 | 交付物 |
|---|---|
| 任务1 阈值迁移方案 | `phase3.2.4D_threshold_migration_plan.md` §1~§7 |
| 任务2 D-TH 双签决策 | `phase3.2.4D_dth_double_sign_decision.md` |
| 任务3 source_ref 验证设计 | 迁移方案 §4（validator C1~C6） |
| 任务4 真实录入流程 | 本报告 §2 |
| 任务5 实施安全检查 | 本报告 §3（G1~G6） |

---

## 2. 任务4：真实录入流程（专家提供 → 主理人审核 → 专家复核 → verified）

> 设计未来 3.2.4 实施（须书面授权、仍 `engineering_enabled=false`）的录入闭环；**本阶段不执行任何落库**。

### 2.1 四步闭环

```
① 专家提供(submit)         —— 专家提交人填 value/unit/source_ref（draft）
        │  review_log action=submit（prev_event_id=链尾）
        ▼
② 主理人审核(review_approve) —— 主理人核准位（verified_by/at，mgmt_signed）
        │  review_log action=review_approve
        ▼
③ 专家复核(expert_recheck)    —— 专家签字位（expert_verified_by/at，expert_signed）
        │  review_log action=expert_recheck
        ▼
④ 阈值验证(threshold_verified) —— 门禁 B.1 全满足 → threshold_status=verified, verified=true
           review_log action=threshold_verified
```

### 2.2 每一步的 review_log 事件

| 步骤 | action | signer_role | 链式约束 |
|---|---|---|---|
| ① | `submit` | submitter | prev_event_id = 当前链尾（或 null 起链） |
| ② | `review_approve` | principal | prev_event_id = submit.event_id |
| ③ | `expert_recheck` | expert | prev_event_id = review_approve.event_id |
| ④ | `threshold_verified` | principal + expert | prev_event_id = expert_recheck.event_id；双签位已齐 |

### 2.3 不变量

- **append-only**：`review_log.jsonl` 仅追加，回滚仅追加 `deprecated` 事件，绝不物理删除（复用 3.2.4 §7 / 3.2.5-C §4）；
- **SoD**：步骤②主理人 ≠ 步骤③专家签署人（角色标识符层面 `verified_by ≠ expert_verified_by`），否则 `is_fully_verified=False`；
- **门禁前置**：步骤④仅在 B.1 九项（值非空 / 单位枚举 / source_ref 完整 / 双签齐 / version 声明 / applies_to 无悬空 / 审核链完整 / CI 绿）全满足时置 `verified=true`；
- **不碰 enabled**：本流程只改变阈值治理态（draft→verified），绝不翻转 `engineering_enabled`（须 3.2.5 实施 + G1~G6 全绿 + 主理人授权）。

---

## 3. 任务5：实施安全检查（进入真实化前必须检查 G1~G6）

> 真实化动作（3.2.4 实施 verified.json 真实化）执行前，须逐项确认以下六项门禁，任何一项未满足即**中止真实化、保持 pending_verification**。门禁语义继承 3.2.5-B `can_enable_engineering()`，此处聚焦"真实化前"而非"开启 enabled 前"。

| 门禁 | 检查项 | 真实化前判定 | 失败处置 |
|---|---|---|---|
| **G1 阈值治理完备** | 目标阈值 `governance_status` 返回 ok（status=verified + 结构化 source_ref 完整 + 双签齐） | 所有待真实化阈值须 ok | 拒绝真实化，回退 draft |
| **G2 双签齐全** | `is_fully_verified` 对所有目标阈值为真（主理人 + 行业专家双签） | 全 True | 拒绝真实化 |
| **G3 CI 全绿** | `local_ci.sh` 8/8 通过，覆盖率不低于当前基线 | 全绿 | 拒绝合入 |
| **G4 审核链完整** | `review_log` 链式无断裂/无损坏行（prev_event_id 连续、event_id 重算一致） | 连续 | 拒绝真实化，修复链 |
| **G5 回滚就绪** | 快照机制 + `rollback.py` 就绪，可恢复上一可信快照 | 就绪 | 拒绝真实化 |
| **G6 授权到位** | 主理人**单独书面授权**真实化的签署记录存在（独立于 enabled 授权） | 授权 present | 拒绝真实化 |

**说明**：
- G1/G2 是"阈值能否转正"的硬前提；G3/G4/G5 是"真实化过程可审计、可回滚"的工程保障；G6 是治理授权（不与 3.2.5 的 enabled 授权混同，须两次独立书面授权）。
- 本阶段 G1/G2/G6 默认未满足（全 `pending_verification`、无授权），故真实化不会、也未被触发。
- 真实化完成后仍须经 3.2.5-B 完整 G1~G6（含 enabled 授权）方可 `engineering_approved`。

---

## 4. 红线守约声明

- ✅ 未填写真实工程阈值（所有 value 仍为 null，占位 pending_verification）；
- ✅ 未修改 verified.json 真实 value（本阶段零文件改动）；
- ✅ 未设置 verified=true（全部 threshold_status=draft）；
- ✅ 未开启 engineering_enabled（config 恒 false，门禁 G1~G6 默认拒绝）；
- ✅ 未输出 engineering_approved（四签状态机因 enabled=false 恒 pending）；
- ✅ 防编造 / 硬编码扫描目标 0 命中（E-TH/D-TH 标识符为机制键名，非业务数值；含业务词的行均带 pending_verification 标记 pending_verification）。

---

## 5. 待主理人定夺的开放项

1. **D-TH 双签路径**：采纳方案 A（补专家双签，推荐）或方案 B（保持单签），须书面确认；决策结果驱动 3.2.4 实施迁移 M6（见 `phase3.2.4D_dth_double_sign_decision.md`）。
2. **source_ref.hash 算法**：v2 新增 `hash` 字段的内容摘要算法（建议 sha256 文档内容摘要）待定。
3. **真实化授权与 enabled 授权分离**：两次书面授权的签署人是否须满足 SoD（不同人）待定。
4. **首个真实化范围**：建议先真实化 E-TH-01 至 E-TH-03（wind_pressure 接口），与 3.2.5 首发灰度对齐，不阻塞 D-TH 决策（pending_verification）。

---

## 6. 下一步

1. 主理人审核本报告 + 两份设计文档；
2. 主理人**书面授权** 3.2.4 实施（verified.json 真实化，仍 enabled=false）+ 单独**书面授权** 3.2.5 实施（engineering_enabled 开启灰度）；
3. 授权到位后，按 `phase3.2.4D_threshold_migration_plan.md` 步骤 M1~M8 落地真实化，并执行本报告 §3 的 G1~G6 检查；
4. 本阶段（3.2.4-D）已停止，不进入实施。

---

**本阶段交付边界**：本文档为真实阈值接入的实施方案就绪报告，未修改任何代码、未修改 verified.json、未新增测试、未开启 engineering_enabled，全部阈值保持 pending_verification。待主理人审核 + 单独书面授权后，方可进入 3.2.4 实施与 3.2.5 实施。
