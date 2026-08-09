# BOIP Phase 3.2 Sprint 3.2.5-A 工程审核闭环灰度策略设计

**身份**：BOIP AI 工程治理负责人
**日期**：2026-07-31
**性质**：`engineering_enabled` 开启前置的灰度上线方案设计；**非开启 `engineering_enabled`、非填写真实阈值、非输出 `engineering_approved`**。全部保持 `pending_verification`。

---

## 1. 为什么需要灰度

真实 `engineering_approved` 具有工程合规与法律责任（建筑开口涉及结构安全，风压/壁厚/使用寿命/防腐等级等结论一旦"已验证"将进入客户交付 PDF）。当前真实审核闭环尚未闭合：

- `verified.json` 全部 `value=null`、`verified=false`，治理态为 `DRAFT`（Sprint 3.2.4-A 已落地 `governance_status` 判定，当前全部 `GOV_REASON_NOT_VERIFIED`）；
- `engineering_enabled` 全局为 `false`（红线未破）；
- 真实专家双签尚未发生（3.2.3 / 3.2.4-A 仅为 `principal-001` / `expert-001` 占位演练）。

若一次性全量把五接口 `engineering_enabled` 置 `true`，任一阈值/签字/链路异常都将导致错误 `approved` 流入报告，**爆炸半径覆盖全部五接口 + 全部项目**。灰度（Gray Release）把爆炸半径限制为**单接口 + 受控项目白名单**，并提供端到端演练场：在真实 `enabled=true` + 真实双签阈值就位后，先用一个接口验证 `校验器 → 审核链 → 报告 → 监控 → 回滚` 全链路，再逐步放大。

> 灰度是"治理闭环"的验证手段，不是绕开红线。本阶段仅设计灰度方案，不写代码、不改 `config.yaml`、不填 `verified.json`。

---

## 2. 首个灰度接口选择分析

基于 `agents/engineering/threshold_loader.py::INTERFACE_THRESHOLD_MAP` 与跨模块降级链路（Sprint 3.1 五模块实证）：

| 候选接口 | 所需阈值 | 上游工程依赖 | 灰度适配度 | 说明 |
|---|---|---|---|---|
| **wind_pressure** | E-TH-01、E-TH-02、E-TH-03（Engineering 侧，治理可控） | 仅 项目/Environment/Design 输入，**不消费其他工程模块输出** | ★★★★★ | 公式确定性高（w_k = β·μ_s·μ_z·w_0，变量关系明确）；下游 glass_safety / profile 消费其 w_k，但下游自身阈值未齐仍 pending，灰度 wind_pressure 不会造成下游误 approved；**无上游降级传导**。 |
| glass_safety | D-TH-02（Design 侧） | 消费 wind_pressure 的 w_k | ★★☆☆☆ | D-TH-02 当前仅主理人单签，治理态缺专家签（`GOV_REASON_EXPERT_MISSING`），须先解决 D-TH 双签路径（3.2.4 open_decisions 待定）；不适合首批。 （pending_verification）|
| profile | D-TH-01（Design 侧） | 消费 wind_pressure 的 w_k | ★★☆☆☆ | 同 D-TH-02 单签缺口；不适合首批。 |
| hardware | E-TH-04（Engineering 侧） | 消费 profile_result 上游态 | ★★★☆☆ | 阈值治理可控，但消费 profile 上游审核态（profile 未 approved → hardware 强制 pending，降级传导）；作首批会被上游闸门稀释灰度价值；**可第二批**。 |
| installation_risk | E-TH-05、E-TH-06（Engineering 侧） | 末端聚合消费 glass_safety / profile / hardware 三上游 | ★☆☆☆☆ | 三上游全 pending → 强制 pending；**最后批**。 |

**关键区别**：wind_pressure 是唯一"上游无工程模块依赖"的接口（其输入来自项目元信息 + Environment 数据 + Design 三方案，均非 Engineering 计算结果），因此灰度它**不会触发任何跨模块降级传导**，且**下游不受其影响**（下游自身 pending）。其余四接口均依赖上游工程态，灰度价值被上游闸门稀释。

---

## 3. 推荐选择

**首个（且初期唯一）灰度接口：`wind_pressure`。**

理由：
1. **治理自洽**：所需 E-TH-01、E-TH-02、E-TH-03 均为 Engineering 侧阈值，可由工程治理流程独立双签转正，不依赖 Design 侧 D-TH 双签路径决策（与 3.2.4 open_decisions 解耦）；
2. **无上游工程依赖**：不消费任何 Engineering 模块输出，灰度判定不受上游 pending 传导干扰；
3. **下游安全**：glass_safety / profile 消费其 w_k，但二者自身阈值未齐仍 pending，不会因 wind_pressure 灰度而误 approved；
4. **公式清晰易复核**：荷载计算链确定性高，便于首次真实 approved 的人工复核与监控断言；
5. **爆炸半径最小**：单接口 + 受控项目白名单，任何异常可秒级回滚。

后续批次建议顺序（待各自门禁满足后）：hardware（E-TH-04，第二批）→ glass_safety / profile（须先解决 D-TH 双签路径，第三批）→ installation_risk（末端聚合，最后批）。

---

## 4. 灰度范围

**接口范围**：仅 `wind_pressure`（单接口灰度）。

**项目范围**：仅标记灰度标签的受控项目集合（白名单，默认空）；生产全量项目仍走 `pending_verification`。避免"全量误开"。

**配置形态（设计，不改动 `config.yaml`）**：

```yaml
# agents/config.yaml —— 设计草案，本阶段不落地
orchestrator:
  engineering_enabled: false            # 全局闸门，仍 false（红线）
  engineering_gray_release:             # 独立 per-interface 灰度覆盖层
    wind_pressure:
      enabled: false                    # 灰度开关，默认 false；真实开启须单独书面授权
      allowed_project_tags: []          # 受控项目白名单，默认空
      rollout_pct: 100                  # 同标签内流量比例（未来可细分）
```

**灰度判定逻辑（设计级伪码）**：在 `ExpertBackedEngineeringValidation.validate()` 的现有四签闸门之外，新增 per-interface 灰度覆盖：

```
approved = structure_valid
          AND threshold_verified        # 阈值主理人核准
          AND expert_signed             # 阈值专家签字
          AND engineering_enabled        # 全局闸门（仍 false 直到真实开启）
          AND interface IN gray_allowlist          # 灰度接口白名单
          AND project_tag IN allowed_project_tags  # 受控项目白名单
```

> 全局 `engineering_enabled=false` 时，即使灰度配置 `enabled=true` 也恒 pending（双重保险，与既有红线闸门一致）。灰度开关是"全局 true 之后的进一步收窄"，不是绕过全局闸门。

---

## 5. 观察指标

灰度期间须可观测（指标源：校验器返回 + 监控记录，见 §7）：

| 指标 | 定义 | 告警阈值（建议） |
|---|---|---|
| 通过量 | wind_pressure 接口 `engineering_approved` 计数（按日 / 按项目） | — |
| 端到端延迟 | 分析请求 → approved 的 P50 / P95 | P95 > 阈值（按部署 SLA 定） |
| 降级率 | 因上游 pending / 治理不通过 / 灰度未覆盖而回落 `pending_verification` 的比例 | 异常突增即告警 |
| sign_off_id 可复核率 | 由签字元数据重算与落库一致的比例 | 必须 100% |
| review_log 完整性 | event_id 链无断裂、sign_off_id 复核通过率 | 必须 100% |
| 错误率 | 参数异常 / 链路异常 / 校验器异常计数 | > 0 即评估回滚 |
| 回退次数 | 灰度期间触发回滚的事件数 | > 0 即复盘 |

---

## 6. 失败回滚方案（概要）

- **一键回滚**：将 `engineering_gray_release.wind_pressure.enabled` 置 `false`（或移除接口于白名单）；下一请求起该接口结果自动回落 `pending_verification`。
- **全局熔断**：置全局 `engineering_enabled=false` → 所有接口（含已灰度）立即回归 pending。
- **数据零丢失**：`verified.json` / `review_log.jsonl` / `sign_off_id` 均不回滚（append-only 真相）；回滚仅改变"未来判定闸门"，历史 approved 记录保留供审计。
- 详述见 §8 回滚设计。

---

## 7. 监控设计（任务3）

**触发**：每次 `ExpertBackedEngineeringValidation.validate()` 产出 `verification_status = engineering_approved` 时，写入一条监控记录（首次出现即重点观测）。

**记录字段**（与既有 `review_log` 范式对齐，独立专表）：

| 字段 | 来源 |
|---|---|
| `interface` | 被审核接口（首个灰度恒为 `wind_pressure`） |
| `threshold_version` | 由该接口所需阈值（E-TH-01、E-TH-02、E-TH-03）的 `version` 聚合（多阈值取最小/联合版本，设计待定） |
| `sign_off_id` | `review_log.compute_sign_off_id()` 派生的十六位标识 |
| `review_log` | 最新 `event_id` 与 `prev_event_id` 链尾引用（指向签字链） |
| `error` | `None` 或异常摘要（参数异常 / 链路异常） |

**落点（设计）**：新增 append-only `agents/engineering/approved_monitor.jsonl`（与 `review_log.jsonl` 同 append-only 范式，但职责专一：仅记录"已 approved"事件，避免与签字链混淆）。每条记录含确定性 `monitor_id`（内容哈希）。

**告警**：
- `sign_off_id` 复核失败（重算与落库不一致）→ 即时告警 + 触发回滚评估；
- `review_log` event_id 链断裂 / 缺 `prev_event_id` → 即时告警；
- `error` 非空 → 即时告警。

> 监控不消费任何真实工程数值，仅记录"谁在何时被批准、依据哪条签字链、版本几何"，供审计回溯。

---

## 8. 回滚设计（任务4，详述）

**触发条件**：

| 类别 | 具体信号 |
|---|---|
| 审核错误 | `sign_off_id` 由同一签字元数据重算与落库不一致（篡改 / 派生逻辑偏移） |
| 参数错误 | 中间量 `value` 越界 / `NaN` / 量纲异常（如风压中间量出现非物理量） |
| 链路异常 | `review_log.jsonl` event_id 链断裂 / 缺 `prev_event_id` / 损坏行无法跳过 |

**回滚动作（两级）**：
1. **接口级**（优先）：将该接口移出灰度白名单（`engineering_gray_release.wind_pressure.enabled=false`）；下一请求起该接口自动回落 `pending_verification`，不影响其他接口（当前仅 wind_pressure，故等价单接口关闭）。
2. **全局熔断**（根因不明或影响面广）：置全局 `engineering_enabled=false`；所有接口立即回归 pending。

**恢复流程**：
1. 定位根因（阈值补签 / 链路修复 / 公式复核 / 配置修正）；
2. 重新走 §门禁（见 `phase3.2.5A_enable_gate_design.md` 五项）；
3. 重新灰度（可先小流量 `rollout_pct` 放大，再全量）。

**不变量**：回滚不改变已落盘数据——`verified.json` 仍是双签真实态、`review_log.jsonl` 仍是 append-only 真相、`approved_monitor.jsonl` 仍是历史记录。回滚仅改变"后续判定闸门"，符合不可篡改审计原则。

---

## 9. 与既有红线的关系

- 本方案全程 `pending_verification`：不填真实阈值、不置 `verified=true`、不置 `engineering_enabled=true`、不输出真实 `engineering_approved`；
- 灰度开关 `enabled` 默认 `false`，真实开启须**单独书面授权**（延续 3.2.4 / 3.2.4-A 的 C 系列红线——不可与 A/B 系列混同）；
- 首个灰度接口 wind_pressure 不依赖 D-TH 双签路径决策，可独立于 3.2.4 open_decisions 推进；（pending_verification）
- 监控 / 回滚设施均为 append-only / 配置翻转，不触碰 `verified.json` 真实数值。

---

## 10. 待主理人定夺的开放项

- 灰度监控落点：`approved_monitor.jsonl` 独立专表 vs 复用 `review_log` 的 `action=engineering_approved` 事件（本设计推荐独立专表）；
- `threshold_version` 多阈值聚合策略（取最小版本 / 联合版本字符串）；
- `rollout_pct` 是否纳入首版（当前建议先 `100%` 白名单内全量，后续再细分）；
- 真实开启 engineering_enabled 的书面授权流程与签署人（须独立于 A/B 系列 Sprint）。
