# BOIP Phase 3.2 Sprint 3.2.5-A engineering_enabled 门禁设计

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：定义 `engineering_enabled=true` 开启前必须满足的门禁条件；**本阶段不开启 `engineering_enabled`、不填写真实阈值、不输出 `engineering_approved`**。全部保持 `pending_verification`。

---

## 0. 门禁总览

`engineering_enabled` 是 `ExpertBackedEngineeringValidation` 四签闸门的最后一签（全局开关）。它**只能在所有前置条件就位后**由主理人单独书面授权开启。本设计定义开启前的五项强制门禁 + 一项授权门禁：

```
can_enable_engineering(interface):
    ok = verified_governance_ok(interface)
       AND dual_sign_ok(interface)
       AND ci_green()
       AND audit_chain_intact()
       AND rollback_ready()
       AND principal_written_authorization()
    return ok, blocking_reasons
```

任一条件不满足 → `blocking_reasons` 列出缺口，禁止开启。

---

## 1. Verified 治理完备（verified governance）

目标接口所需阈值必须全部通过 `governance_status()`（Sprint 3.2.4-A 已落地）：

- `threshold_status = verified`（非 `draft` / `review` / `deprecated`）；
- 结构化 `source_ref` 完整（`standard` + `clause` 双要素，非仅自由文本）；
- 双签齐全（`verified_by` / `verified_at` + `expert_verified_by` / `expert_verified_at`）；
- `version` 一致（无版本冲突，非 `deprecated` 取代态）。

**首个灰度接口 wind_pressure 的具体要求**：E-TH-01、E-TH-02、E-TH-03 三条阈值均须 `governance_ok`。当前三者治理态为 `DRAFT`（`GOV_REASON_NOT_VERIFIED`），故**当前不满足**——须先走 3.2.4 实施（verified.json 真实化 + 双签填充 + source_ref 结构化 + version 管理）方可。（pending_verification）

> 与 3.2.4 open_decisions 的关系：wind_pressure 仅依赖 Engineering 侧 E-TH-01~03，不依赖 Design 侧 D-TH 双签路径决策；glass_safety / profile 的开启则须先解决 D-TH 双签（路径一补 expert_verified_by/at 推荐 / 路径二放宽复用接口双签 不推荐）。（pending_verification）

---

## 2. 双签齐备（dual sign）

- **主理人核准**：`verified=true` 且 `verified_by` / `verified_at` 俱全（真实身份，非占位符）；
- **行业专家签字**：`expert_verified_by` / `expert_verified_at` 俱全（真实身份，非 3.2.3 / 3.2.4-A 演练用的 `principal-001` / `expert-001` 占位符）；
- 签字人身份须真实可溯（主理人 + 行业专家双轨，一票否决）；
- 签字动作须落入 `review_log.jsonl`（append-only，含 `event_id` / `prev_event_id` 链）。

可由 `threshold_loader.is_fully_verified(entry)`（主理人 + 专家双签五字段）判定，并额外校验 `expert_verified_by/at` 非占位标识符。

---

## 3. CI 全绿（continuous integration）

`bash scripts/ci/local_ci.sh` 必须 **8/8 PASS**：

- Backend pytest 通过，覆盖率 ≥ 当前基线 **88.57%**（Sprint 3.2.4-A 权威值）；
- Ruff / ESLint 零违规；
- Alembic 双向、Seed 通过；
- **编造业务数字扫描 0 命中**、**硬编码业务配置扫描 0 命中**；
- 新增灰度判定逻辑须有对应测试：四签矩阵 / 灰度 allowlist 收窄 / 回滚翻转 / 监控记录写入。

> 覆盖率门槛是"不低于当前基线"的滑动门槛，确保灰度相关代码新增不拉低整体质量水位。

---

## 4. 审计链完整（audit chain integrity）

首次 `engineering_approved` 产出前，须跑一次 `review_log` 链完整性校验：

- `event_id` 链连续无断裂（每条 `prev_event_id` 指向上一条 `event_id`）；
- `sign_off_id` 可由同一签字元数据重算并与落库一致（`review_log.compute_sign_off_id` 可复核性）；
- 无篡改迹象（损坏行可被跳过，但链尾须闭合）；
- 阈值签字事件（action=sign / verify）齐全，覆盖目标接口全部所需阈值。

**不变量**：`review_log.jsonl` 为 append-only 真相源，门禁只"读"不"写"历史。

---

## 5. 回滚就绪（rollback readiness）

灰度回滚流程（详见 `phase3.2.5A_gray_release_design.md` §6 / §8）须：

- 已文档化（本 Sprint 产出）；
- 已演练：配置翻转（`engineering_gray_release.*.enabled=false` 或全局 `engineering_enabled=false`）→ 下一请求结果自动回落 `pending_verification`，无数据丢失；
- 有熔断开关（全局 `engineering_enabled` 一键 false）；
- 监控告警已接入（sign_off 复核失败 / 链断裂 / error 非空 → 触发回滚评估）。

回滚就绪 = "能在一分钟内把任意接口/全局恢复到 pending_verification，且历史审计不可篡改"。

---

## 6. 主理人单独书面授权（written authorization）

延续 3.2.4 / 3.2.4-A 的红线：

- `engineering_enabled=true` 的真实开启（含灰度 `wind_pressure.enabled=true`）须**主理人单独书面授权**；
- C 系列（3.2.4 verified.json 真实化 + 3.2.5 enabled 开启灰度）的授权**不可与 A/B 系列 Sprint（Result 抽象 / 报告章节）混同**；
- 授权须明确：开启接口范围、受控项目白名单、签署人、生效时间、回滚责任人。

---

## 7. 门禁检查清单（checklist）

| # | 门禁 | 检查手段 | 当前状态（2026-07-31） |
|---|---|---|---|
| G1 | Verified 治理完备 | `governance_status()` 全 ok | ❌ 未满足（E-TH-01~03 仍 DRAFT） |
| G2 | 双签齐备 | `is_fully_verified()` + 非占位符 | ❌ 未满足（仅演练占位符） |
| G3 | CI 全绿 | `local_ci.sh` 8/8 + 覆盖 ≥88.57% | ✅ 基础设施就绪（388 passed@88.57%，但需含灰度测试） |
| G4 | 审计链完整 | `review_log` 链校验脚本 | ⚠️ 设施就绪（待真实签字事件） |
| G5 | 回滚就绪 | 回滚演练 + 熔断开关 | ✅ 方案就绪（本 Sprint 产出） |
| G6 | 书面授权 | 主理人签署 | ❌ 未授权（红线未破） |

> G3 / G5 为"能力就绪"，G1 / G2 / G6 为"真实数据 + 授权"缺口——须先完成 3.2.4 实施（verified.json 真实化）与真实双签，再获 G6 授权，方能开启。

---

## 8. 门禁与灰度的关系

- 门禁（本设计）是"能否开启 `engineering_enabled`"的准入；
- 灰度（见 `phase3.2.5A_gray_release_design.md`）是"开启后如何收窄爆炸半径"的策略；
- 二者顺序：**门禁全过 → 授权 → 灰度开关打开（单接口白名单）→ 监控 → 回滚预案待命**。
- 即使门禁全过，灰度仍默认 `enabled=false`（全局 false 双重保险），须再次显式开启灰度接口白名单。
