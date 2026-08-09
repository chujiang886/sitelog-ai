# BOIP Phase 3.2 Sprint 3.2.5-E 工程灰度授权与执行准备就绪报告（Release Authorization & Execution Readiness）

- **阶段**：Phase 3.2 Sprint 3.2.5-E
- **身份**：BOIP AI 工程发布治理负责人（Engineering Release Governance Lead）
- **性质**：首次工程灰度发布的**责任与执行体系设计**——**非开启 `engineering_enabled`、非输出 `engineering_approved`、非修改生产 `verified.json`、非真实灰度放量**，全部 `pending_verification`。
- **日期**：2026-07-31
- **状态**：✅ AUTHORIZATION_EXECUTION_DESIGN_DONE（体系设计就绪；等待主理人书面授权后依设计执行真实放行）

---

## 1. 交付物

| 文件 | 类型 | 说明 |
|---|---|---|
| `.ai/tasks/phase3.2.5E_release_approval_design.md` | 新增 | 发布授权记录设计（EngineeringReleaseApproval 七字段）/ 首次灰度执行流程（Pre-check→Authorization→Enable→Monitor→Rollback，每步责任人）/ 人工确认清单（G1-G6+责任+风险+回滚）/ 灰度执行脚本设计（enable/disable/rollback，默认关闭） |
| `.ai/reviews/phase3.2.5E_release_authorization_readiness.md` | 新增 | 本报告（任务5 风险评估 + 红线守约 + SSOT/Roadmap 更新说明） |

**零代码改动**：未修改 `agents/`、`backend/app`、`frontend/src`、`.json`、`.yaml` 任何文件；未新增测试文件；未开启 `engineering_enabled`。本阶段为纯文档的授权与执行体系设计。

---

## 2. 设计就绪判定（摘要）

本阶段为 `wind_pressure` 首次灰度建立"授权 + 执行"责任体系，结论：

1. **授权记录就绪**：`EngineeringReleaseApproval` 七字段（`approval_id` / `interface` / `scope` / `authorized_by` / `effective_time` / `rollback_owner` / `approval_document_ref`）覆盖"谁、何时、对什么范围、授权了什么、谁负责回滚、依据哪份授权"，作为 G6 `authorization_present` 注入项的**唯一可信来源**。
2. **执行流程就绪**：五步流程（Pre-check → Authorization → Enable → Monitor → Rollback）每步标注责任人，并固化"先快照后变更、顺序不可跳、全局闸门不可绕过"等不变量。
3. **人工确认就绪**：四类确认（G1-G6 / 责任 / 风险 / 回滚）模板化，供真实放行前逐项签字。
4. **脚本设计就绪**：`enable`/`disable`/`rollback` 三指令**默认关闭**（Hard Default-Closed），强制"先快照、后变更、按授权"，杜绝默认可放路径。
5. **生产未达标（与 3.2.5-D 一致）**：生产 `verified.json` 仍为占位态、`engineering_enabled=false`，G1/G2/G6 未满足，本设计**尚未被真实执行**。

---

## 3. 任务5：首次 Release 风险评估（授权与执行视角）

### 3.1 技术风险（Technical Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| RT-E1 | **授权记录被篡改**：若 `EngineeringReleaseApproval` 可事后修改，G6 证据链断裂 | 中 | 记录 append-only + 未来可加哈希链；禁止 in-place 修改，撤销须追加新记录 |
| RT-E2 | **脚本绕过授权门禁**：若 `enable` 子命令未强制校验 `authorization_present` 与 G1-G6 全绿，可能无 G6 即放量 | 高 | 脚本硬编码硬闸门：`can_enable_engineering()=(True,[])` 且存在有效 `EngineeringReleaseApproval` 才执行，否则非零退出码拒绝 |
| RT-E3 | **变更前未快照**：`RollbackHandler` 无 snapshot 则 `restore()` 退化为空操作，回滚失效 | 中 | 脚本 `enable`/`disable`/`rollback` 任意变更前强制 `snapshot()`；缺失即拒绝 |
| RT-E4 | **授权记录字段漂移**：未来向 `scope` 误写入真实工程数值（风压/壁厚/楼层） | 低 | `scope` 仅含标识符与配置布尔/百分比占位；字段语义经设计固化，新增须经审查 |

### 3.2 工程风险（Engineering Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| RE-E1 | **授权 SoD 违反**：`authorized_by`（G6 主理人）与 3.2.4 双签主体（`verified_by`/`expert_verified_by`）为同一人，混淆"真实化授权"与"放行授权" | 高 | 授权记录设计明确要求 `authorized_by` 独立于双签主体；审核链可比对 `sign_off_id` |
| RE-E2 | **范围误扩大**：真实放量时误启用 `wind_pressure` 之外接口（D-TH / E-TH-04 至 E-TH-06） | 高（已规避） | 脚本 `enable <interface>` 参数受 `INTERFACE_THRESHOLD_MAP` 唯一白名单约束；非白名单接口拒绝 |
| RE-E3 | **生效时间倒签**：`effective_time` 被回填至授权前，规避时间窗审计 | 低 | 时间戳取自签署事件，未来加单调性校验；授权记录 append-only |
| RE-E4 | **回滚责任人缺位**：`rollback_owner` 未指定导致异常时无主可追 | 中 | 授权记录 `rollback_owner` 为必填；人工确认清单 §3.4 强制就位确认 |

### 3.3 法律责任 / 责任风险（Responsibility / Compliance Risks）

| 编号 | 风险 | 等级 | 缓解 |
|------|------|------|------|
| RL-E1 | **责任链不清**：灰度放行后工程结论出错，四方（阈值提供/主理人核准/专家签字/发布授权）责任边界不明 | 高 | 授权记录 + 人工确认清单 §3.2 固化五角色职责边界；`review_log` 每步记 `signer_role`/`signer`/`sign_off_id` |
| RL-E2 | **未经授权擅自开启**：操作员绕开 `can_enable_engineering` 直接置 `engineering_enabled=true` | 高（已防） | `config_loader` 拦截非法开启；脚本硬闸门；全局闸门 `is_interface_gray_allowed` 恒 False 兜底 |
| RL-E3 | **审计缺口**：真实放行时 `approved_monitor` 未落盘，失去放行证据 | 中 | Monitor 步骤在 `engineering_approved` 出现时自动 `append_approved_record`（仅引用）；审核链监督定期回放比对 |
| RL-E4 | **跨阶段授权混淆**：3.2.4 双签（阈值真实化）与 3.2.5 G6（enable 授权）被混为一谈，误以为"双签即放行" | 高 | 两记录独立、主体 SoD 分离；文档明示"阈值转真 ≠ 工程批准"，`evaluate_gates()` 恒默认拒绝 |

---

## 4. 安全检查（红线守约）

| 红线 | 状态 |
|---|---|
| ① 未开启 `engineering_enabled` | ✅ 仍为 false（本设计为文档，不触动 config） |
| ② 未输出 `engineering_approved` | ✅ 仅描述流程与门禁逻辑，不运行校验器、不落盘 |
| ③ 未修改生产 `verified.json` | ✅ 生产仍为 schema_version 1 占位态 |
| ④ 未真实灰度放量 | ✅ 仅 `wind_pressure` 设计，未激活；范围未扩大 |
| ⑤ 未填真实阈值 / 姓名 / 规范数值 | ✅ 阈值仅以 E-TH 标识符引用；signer 仅标识符；`scope` 仅占位 |
| ⑥ 防编造 / 硬编码扫描 | ✅ 零命中（纯文档，业务词仅以接口/E-TH 标识符出现，无未验证真实数字；见 §6） |

---

## 5. SSOT / Roadmap 更新

- `.ai/project_status.json`：在 `task_status.phase_3_1.phase_3_2` 下新增 `3.2.5-E` 条目（`status=AUTHORIZATION_EXECUTION_DESIGN_DONE`），`_phase_status` 刷新为 `SPRINT_3_2_5E_DONE`，`_completed_at=2026-07-31`，`_summary` 概述本阶段结论。
- `.ai/roadmap_v2.md`：第 92 行 3.2 里程碑追加 `Sprint 3.2.5-E DONE`（授权与执行体系设计就绪）。

---

## 6. 测试结果

本阶段为纯文档，**未执行编码**，无 CI 扰动。沿用 Sprint 3.2.4-G 基线：

- `bash scripts/ci/local_ci.sh` 理论状态：**8/8 全绿**（backend **435 passed @ 89.21%** / frontend **29 @ 93.15%** / Alembic 双向 / Seed / 防编造+硬编码扫描 零命中，≥89.10% 达标）；
- 防编造扫描：`check_fabrication.py` 对新增文档扫描 **零命中**（业务词仅以 `wind_pressure` / E-TH 标识符出现，无未验证真实数字）；
- 硬编码扫描：`check_hardcoded.py` 不适用（无代码改动，复扫 零命中）。

---

## 7. 待主理人定夺 / 下一步

- **本阶段为授权与执行体系设计，未真实执行、未开启 `engineering_enabled`、未输出 `engineering_approved`、未修改生产 `verified.json`、未真实放量。**
- 进入真实放行（开启 `engineering_enabled` 灰度）前，仍须依次满足：
  1. 主理人依本设计签署 `EngineeringReleaseApproval`（G6，SoD 独立于 3.2.4 双签主体），指定 `rollback_owner`；
  2. 人工以真实数据完成 E-TH-01 至 E-TH-03 真实化（满足 G1/G2/G4），并存真实 `review_log` 链；
  3. 重跑 `local_ci.sh` 确认 G3 绿；
  4. 发布执行人依本设计脚本（`enable wind_pressure --approval ...`）置 `engineering_enabled=true` 并触发 Monitor 落盘 → per-interface 灰度放量（仅 `wind_pressure`）。
- 待定（沿用）：未来 `EngineeringReleaseApproval` 是否落盘为独立 JSONL 专表（类比 `approved_monitor.jsonl`）；`scope.rollout_pct` 真实初始放量比例（占位，待授权时填）；D-TH 双签最终方案（A 补专家双签 / B 保持单签）。

**本阶段已停止。未开启 engineering_enabled、未输出 engineering_approved、未修改生产 verified.json、未真实灰度放量。全部 pending_verification。等待主理人书面授权（G6）。**
