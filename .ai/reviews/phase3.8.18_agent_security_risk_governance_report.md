# Phase 3.8.18 收口报告 —— Enterprise Agent Security & Risk Governance Layer（企业智能体安全与风险治理层）

| 项 | 值 |
| --- | --- |
| Phase | 3.8.18 |
| 身份 | BOIP AI Chief Architect |
| 状态 | `ENTERPRISE_AGENT_SECURITY_RISK_BUILT_NO_GO` |
| 收口日期 | 2026-08-06 |
| 激活态 | `engineering_enabled = false`（未变更） |
| 全量测试 | `tests/agents` **1558 passed**（1518 基线 + 40 新增，零回归） |
| 审计类别 | 44 → **47**（+3） |

---

## 1. 概述

本 Phase 交付企业智能体**安全与风险治理层**：把 Agent 运行过程中产生的安全事实（访问 /
权限 / 执行 / 认证 / 数据流转）以**只记录事实**的方式沉淀，由检测器**只发现不处理**地产出
风险候选，汇总为**强可溯源**的安全报告，最终由**真实人工**完成风险处置。

本层的定位是**发现与记录**，不是**处置与执法**：

- AI 可以：登记安全事件、发现异常、产出风险候选、生成报告；
- AI 不可以：封禁 Agent、修改权限、处置风险、代替安全责任人下结论。

上述边界不是靠约定，而是通过 `_RedLineForbiddenMixin` 的 `__getattr__` 拦截、模型
`__post_init__` 强校验、以及 `require_human_actor(USER)` 守卫在**结构上**不可达。

---

## 2. 交付物清单

| # | 交付物 | 路径 / 位置 | 说明 |
| --- | --- | --- | --- |
| 1 | `AgentSecurityEvent` + `AgentSecurityEventType` + `AgentSecuritySeverity` | `agents/enterprise/agent_security_risk.py` | 安全事实事件（event_id / agent_id / event_type / severity / source / timestamp）；**只记录事实**，`source` 为空即拒绝落库 |
| 2 | `AgentRiskCandidate` | 同上 | 风险候选（risk_id / agent_id / pattern / evidence / requires_human_review）；`requires_human_review` **恒为 True**，无 pattern / 无 evidence 即拒绝构造 |
| 3 | `AgentSecurityDetector` | 同上 | 三类检测 `detect_access_anomaly` / `detect_permission_anomaly` / `detect_execution_anomaly`；**只发现不处理** |
| 4 | `AgentSecurityReport` + `SourceTrace` | 同上 | 安全事实 + 风险候选 + **来源链**；无来源链即拒绝构造/生成 |
| 5 | `AgentRiskReview` + `AgentRiskReviewStatus` | 同上 | 风险人工处置；构造期禁止落 `reviewed`，处置强制真实 USER |
| 6 | 审计增强（+3 类别 / +3 方法） | `agents/enterprise/audit.py` | `AGENT_SECURITY_EVENT` / `AGENT_RISK` / `AGENT_RISK_REVIEW`；累计 **47** |
| 7 | 权限接入与装配 | `agents/enterprise/service.py`、`agents/enterprise/__init__.py` | `AgentSecurityRiskService` 接入 `IdentityService` + `AgentPermissionPolicy`，安全数据读取**默认拒绝** |
| 8 | 八类测试（40 用例） | `tests/agents/test_enterprise_agent_security_risk.py` | security_event / risk_candidate / detector / report / review / permission / audit / red_line |
| 9 | 收口报告 | `.ai/reviews/phase3.8.18_agent_security_risk_governance_report.md` | 本文件 |
| 10 | 状态更新 | `.ai/project_status.json`、`.ai/roadmap_v8.md` §21 | `phase_3_8_18 = ENTERPRISE_AGENT_SECURITY_RISK_BUILT_NO_GO` |

新增代码规模：`agent_security_risk.py` **1032 行**；测试 **605 行**。

---

## 3. 红线守约（fail-closed，6 条）

| # | 红线 | 落地机制 | 结果 |
| --- | --- | --- | --- |
| ① | 禁开 `engineering_enabled` | 所有服务/检测器构造与全部写路径断言 `safety_invariants_ok()`；磁盘 `agents/config.yaml:102` 恒为 `false` | ✅ 未开启 |
| ② | 禁输出 `engineering_approved` | `approve` / `engineering_approved` / `sign` / `authorize` 列入 `_SECURITY_FORBIDDEN`，`__getattr__` 命中即抛 | ✅ 无任何赋值/输出 |
| ③ | 禁 AI 自动封禁 Agent | 拦截 `auto_disable_agent` / `disable_agent` / `block_agent` / `kill_agent` / `ban_agent` / `suspend_agent` / `terminate_agent` / `shutdown_agent` / `quarantine_agent` 及 `auto_*` 同族；检测器只产出候选，不触碰任何 Agent 状态 | ✅ 结构不可达 |
| ④ | 禁 AI 自动修改权限 | 拦截 `auto_change_permission` / `auto_grant_permission` / `auto_revoke_permission` / `modify_permission` / `update_permission` / `escalate_permission` / `elevate_permission` / `reset_permission` 及同族；本层对权限**只读校验**（`check_agent_access`），无任何写权限路径 | ✅ 结构不可达 |
| ⑤ | 禁 AI 自动处置安全风险 | 拦截 `auto_resolve_risk` / `resolve_risk` / `auto_fix_risk` / `fix_risk` / `auto_mitigate_risk` / `auto_close_risk` / `auto_dismiss_risk` / `auto_remediate` / `handle_incident` 等；`AgentRiskCandidate.requires_human_review` 恒为 True（置 False 即抛）；`AgentRiskReview` 构造期禁止落 `reviewed` | ✅ 结构不可达 |
| ⑥ | 禁 AI 代替安全责任 | 审计禁 `record_human_approval`；`human_review_risk` 强制 `require_human_actor(USER)` + 非空 `actor_id` + 非空人工 `decision`；事件/候选/报告缺来源即拒绝；拦截 `auto_secure` / `take_security_ownership` / `act_as_security_officer` / `assume_security_responsibility` / `auto_govern_security` | ✅ 强制人工 |

补充事实约束（红线⑥的可溯源要求）：

- `AgentSecurityEvent.source` 为空 → 拒绝落库；
- `AgentRiskCandidate.evidence` 为空 → 拒绝构造（无证据不指控）；
- `AgentSecurityReport.source_trace` 缺失/为空 → 拒绝构造；
- `generate_security_report` 在零事实时直接抛错，不生成空报告。

---

## 4. 测试（八类，40 用例）

| 类别 | 用例数 | 覆盖要点 |
| --- | --- | --- |
| 1. security_event | 3 | 只记录事实、无源拒绝、枚举强制转换 |
| 2. risk_candidate | 4 | `requires_human_review` 恒 True、置 False 抛错、pattern/evidence 必填、无处置方法 |
| 3. detector | 5 | 三类检测产出候选、严重度触发、不臆造风险、检测器无改权限能力 |
| 4. report | 4 | 来源链清洗、无来源链拒绝、报告汇总事实、零事实拒绝生成 |
| 5. review | 5 | 构造期禁 reviewed、自动生成 pending 复核单、AI/system/None 拒绝、USER 处置成功且终态、actor_id/decision 必填 |
| 6. permission | 3 | REVIEWER 默认拒绝、ADMIN 可读且组织隔离、服务层无写权限能力 |
| 7. audit | 4 | 3 类别齐备且累计 47、AI 动作记 AI、人工处置记 USER、禁 `record_human_approval` |
| 8. red_line | 9 | 6 条红线逐条断言 + 启用态阻断构造/写入 + 伪造候选被服务层拒绝 + 聚合层装配校验 |

单文件运行：`40 passed in 0.10s`（一次通过，无返工）。

---

## 5. 最终验证

```
$ find tests -name '_tmp_drill_*' -delete
$ backend/.venv/bin/python -m pytest tests/agents -q
1558 passed in 36.64s
```

- 基线 1518（3.8.17 收口）→ 现 1558，**+40 全部为本 Phase 新增**，**零回归**。
- `AuditActionCategory` 实测 **47**。
- 历史累计断言同步刷新（属既定范式，非功能变更）：
  - `test_enterprise_agent_cost_resource.py`：44 → 47
  - `test_enterprise_agent_runtime_policy.py`：44 → 47
  - `test_enterprise_knowledge_intelligence_audit.py`：44 → 47
  - `test_enterprise_agent_quality_governance.py`：44 → 47
  - `test_enterprise_knowledge_governance_audit.py`：全集 `EXPECTED_CATEGORIES` 补 3 个值，计数 44 → 47
- 未修改 `verified.json`；未修改 `engineering_enabled`；测试通过 monkeypatch 注入启用态，不触碰磁盘配置。

---

## 6. 状态与激活态

| 项 | 值 |
| --- | --- |
| `phase_3_8_18` | `ENTERPRISE_AGENT_SECURITY_RISK_BUILT_NO_GO` |
| `engineering_enabled` | `false`（`agents/config.yaml:102`，未变更） |
| ESW 窗口 | 维持 `OPEN_EMPTY` |
| 工程放行 | **无**。本层不产出任何工程结论、不放行任何运行、不改变任何 Agent 可用状态 |

**BUILT_NO_GO 含义**：能力已建成并通过测试，但**未获工程放行**。安全事实与风险候选仅供
真实安全责任人参考，任何封禁、权限调整、风险处置动作，均须由人工在本系统之外依据自身
职责作出并回填事实。

---

## 7. STOP 声明（等待主理人审核）

Phase 3.8.18 全部 11 项任务已按主理人授权完成并自检通过。依授权原话
「完成后停止。不要进入 Phase 3.8.19。等待主理人审核」，现**主动 STOP**：

- ❌ 不进入 Phase 3.8.19；
- ❌ 不开启 `engineering_enabled`；
- ❌ 不输出 `engineering_approved`；
- ❌ 不自行封禁任何 Agent、不自行修改任何权限、不自行处置任何安全风险；
- ✅ 等待主理人审核本报告后再行授权。

—— BOIP AI Chief Architect，2026-08-06
