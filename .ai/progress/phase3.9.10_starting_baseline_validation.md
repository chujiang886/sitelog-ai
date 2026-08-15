# Phase 3.9.10 — Starting Baseline Validation / 起始基线核验

**生成时间**：2026-08-15（GMT+8）
**生成主体**：BOIP AI Chief Architect（治理协议 v2.0 安全边界内自主执行，Phase 3.9.10 External Staging Qualification & Evidence Integration Layer 起始核验层）
**分支**：`feat/phase3.9.10-external-staging-qualification`
**阶段性质**：**外部预生产资格认定与证据集成层（External Staging Qualification & Evidence Integration Layer）** —— **不是 Production 激活、不是 Production Handoff**。
**终端态目标**：`PHASE_3_9_10_EXTERNAL_STAGING_QUALIFICATION_EVIDENCE_INTEGRATION_BUILT_NO_GO`（禁 `PRODUCTION_READY` / `APPROVED` / `GO`）。

---

## 1. 分支建立与锚定核验（Task 0 · Branch Integrity Guard）

| 项 | 结果 |
|---|---|
| 施工起点指令 | 严格锁定 `base=2f4a983`、`audit.py=d03a7f1f`、Audit canonical baseline=129 |
| 当前分支 | `feat/phase3.9.10-external-staging-qualification` ✓ |
| 当前 HEAD | `2f4a9838bcfc7105bc561f74fb2658906801e011` ✓（= base，本阶段尚未产生新 commit；交付物均为未跟踪文件） |
| ancestry 正确性 | `2f4a983` 是有效 commit，为 3.9.9 Real Staging 收口线之后的合法演进起点 |
| `git status --porcelain` | 10 个未跟踪交付项（见 §6），无已跟踪文件修改、无错分支污染 ✓ |
| Branch Integrity Guard | 每关键写操作前 `git checkout -qf 2f4a983` + `git branch --show-current` 复验；本会话首动作已复验 HEAD/branch 一致 ✓ |

**结论**：分支锚定正确，HEAD=base，工作树仅含本阶段合法未跟踪交付物，未使用 `git reset --hard` / `git add -A`。

---

## 2. 红线守约核验（全程红线①–⑥）

| 检查 | 位置 / 命令 | 结果 |
|---|---|---|
| `engineering_enabled` | `agents/config.yaml:102` | `engineering_enabled: false` ✓（红线①保持，全程未改） |
| `engineering_approved` | 本分支 | 本分支无 `engineering_approved` 输出；所有构造/写路径经 `safety_invariants_ok()` 前置断言 |
| 真实 Production 动作 | — | 不执行真实部署 / DB migration / 配置修改 / 写 Secret / 改 DB / 回滚 / 输出 GO / 代四角色签署 / 改 `engineering_enabled` / 跑 Runbook / 自动关 Incident |
| Production Handoff 吸收 | 见 T1 文档 | 旧 `production_handoff/` WIP 隔离于 stash，未 pop / 未 merge / 未 cherry-pick / 未拷贝进本阶段 |

---

## 3. Audit Ledger（SSOT）基线

- 当前机器可读 SSOT：`.ai/baselines/audit_action_category_ledger.json` → **`"total": 129`**。
- 人类可读镜像：`.ai/AUDIT_ACTION_CATEGORY_LEDGER.md`。
- 本阶段**审计 0 新增**（External Staging Qualification 为资格认定 + 证据集成层，不引入新 `AuditActionCategory`），仍维持 129 分支基线。
- 校验器：`scripts/audit_category_ledger_validator.py` 由 `scripts/build_audit_category_ledger.py` 从 Git 真实提交重建，0 orphan/ghost/dup。

---

## 4. Phase Boundary Ledger 基线

- `.ai/PHASE_BOUNDARY_LEDGER.md` §1 总表当前覆盖至 **3.9.9（Real Staging）**。
- 本阶段收口时**追加** Phase 3.9.10 External Staging Qualification 独立行（不改写既有 3.9.9 及以前行、不覆盖另一条 3.9.9 记录），并以 JSON Ledger `129` 维持 §5 计数一致。

---

## 5. 旧 WIP 溯源冲突裁决（治理 §4 · 真实来源校正）

- **被确认的「独立历史 WIP」事实**（上一轮 user_query 确认）：旧分支 `feat/phase3.9.10-production-handoff-human-activation-ceremony` 被陈述为 tip=`e97d5361`、Audit=155、+14 HANDOFF categories、相对 base +15 commits。
- **本会话实测真实来源（冲突）**：
  - `git cat-file -t e97d5361` → **NOT_FOUND**（该 commit 对象在本仓库本地对象库不存在）；
  - 旧分支当前 tip = **`2f4a983`**（= base），`git rev-list --count 2f4a983..<old_tip>` = **0**（0 个额外 commit）；
  - 真实「Production Handoff & Human Activation Ceremony」WIP 实际**隔离于 `stash@{4}` / `stash@{5}`**（位于该旧分支），内容为 `agents/enterprise/audit.py`（修改）+ `agents/enterprise/production_handoff/`（5 文件：`__init__.py` / `forbidden.py` / `gate.py` / `models.py` / `service.py`），**未提交、未丢失、未并入**。
- **裁决（不破坏历史、选真实来源）**：
  - 旧 WIP 的 provenance = stash 引用 `stash@{4}` / `stash@{5}` + 分支名，独立登记；
  - **不 pop / 不 merge / 不 cherry-pick / 不拷贝**该 `production_handoff/` 进本阶段；
  - 不删除 stash、不重写其历史；
  - 因此「+14 HANDOFF 审计类目 / Audit 155」属**未持久化的误述**，本阶段以 SSOT JSON Ledger `129` 为权威，不吸收、不伪造该类目。
- **Pending Human Item**：主理人审核时确认「旧 WIP 以 stash 隔离形态存在（非 commit tip e97d5361）」符合预期；如须将该 `production_handoff/` 模块正式立项，由主理人线下裁定新 Phase 编号与 stash 处置方式。

---

## 6. 本阶段起始交付物清单（未跟踪，待收口 commit）

```
.ai/baselines/external_staging_api_contract.json          # 8 routes 机器可读契约
.ai/runbooks/staging/EXTERNAL_STAGING_OPERATIONS_RUNBOOK.md
.ai/runbooks/staging/HUMAN_EXTERNAL_STAGING_QUALIFICATION_CHECKLIST.md
.ai/staging/external_staging_qualification_package.json   # 确定性资格包（SHA-256 稳定）
agents/external_staging_qualification/                    # 16 文件包（models/gate/denylist/probes/...）
backend/app/api/external_staging_qualification.py         # 8 只读端点
scripts/generate_external_staging_qualification_package.py
script/validate_external_staging_qualification_package.py
tests/agents/test_external_staging_qualification.py       # 50 fail-closed 测试（已 PASS）
```

> 注：CI gate 脚本 / workflow、SSOT 三处、T0/T1 文档、收口报告均于本会话后续步骤补齐（此前 summary 高估进度，本次以实际工作树为准重建）。

---

## 7. 起始基线结论

| 维度 | 状态 |
|---|---|
| 分支 / HEAD / ancestry | ✓ 正确（HEAD=base `2f4a983`） |
| working tree | ✓ 仅本阶段合法未跟踪交付物 |
| 红线① `engineering_enabled=false` | ✓ 保持 |
| `engineering_approved` | ✓ 未输出 |
| Audit Ledger SSOT | ✓ `129`（本阶段 0 新增） |
| Phase Boundary Ledger | ⚠ 待收口追加 §7 行 |
| 旧 WIP 冲突 | ⚠ 已裁决（stash 隔离，不吸收，见 §5） |
| 3.9.11 内容残留 | ✓ 工作树 0 命中（Grep 定向扫描确认） |

**判定**：起始基线**有效**，可进入后续 Tasks（External Staging Qualification 包 / Gate / API·Contract / UI / 机器包 / Validator / Scanner / Checklist / CI / 安全 / 审计 / SSOT / Phase Boundary / 文档 / 收口报告）。不等待人工确认（基线核验属自动执行权限 C 类文档同步 + 自动判断规则；唯一需人工裁决的冲突已按 §4 就地裁决并记录 Pending Human Item）。
