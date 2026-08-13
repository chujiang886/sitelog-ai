# Phase 3.9.6 现有工作取证（Existing Work Forensics）

- 生成时间：2026-08-13（Phase 3.9.6 启动）
- 取证原则：Git 为唯一事实源。本文件只记录**当前仓库工作树 / 引用中真实存在的 3.9.6 增量**，不假设、不重造。
- 执行命令：`git status` / `git branch -a` / `git log --oneline --all` / `git diff` / 新文件读取。

## 0. 当前位置

- 当前分支：`feat/phase3.9.4-r2-definitive-baseline-freeze`
- 当前 HEAD：`f7a2aba`（R2 真实收口终点）
- **无任何 `3.9.6` 提交**（`git log --oneline --all | grep 3.9.6` 无命中）。
- 所谓"Phase 3.9.6 增量"全部位于**工作树（未提交）**，共 6 个文件改动。

## 1. 工作树改动清单（T1 / T2 / T3 / T4 映射）

| 文件 | 状态 | 推定 Task | 功能 | 测试 | 文档 | 是否完整 |
|------|------|-----------|------|------|------|----------|
| `.ai/PHASE_BOUNDARY_LEDGER.md` | M | T2 | 修正 R2 冻结 HEAD（`ab1f7cd`→`f7a2aba`）+ 登记 3.9.6 行 | — | 是 | 部分（3.9.6 行含待纠正错误，见 §3） |
| `.github/workflows/baseline-freeze-gates.yml` | M | T1 | 分支覆盖策略对齐（main + 显式 + 通配） | 是（由 check_ci_release_gate_branches 间接覆盖） | 注释 | 完整 |
| `.github/workflows/release-gate.yml` | M | T1 | 同 T1 分支覆盖策略 | 是 | 注释 | 完整 |
| `scripts/check_ci_release_gate_branches.py` | ?? | T1 | CI 发布闸门分支覆盖门禁（R1–R8，fail-closed，stdlib，CWD 无关） | 待补（Task 28） | 注释 | 完整（逻辑独立） |
| `scripts/check_closure_commit_integrity.py` | ?? | T2 | 收口提交完整性门禁（ClosureCommitIntegrityResult，fail-closed） | 待补（Task 28） | 注释 | 完整（逻辑独立） |
| `agents/enterprise/production_release/activation_intake.py` | ?? | T3/T4 | 激活证据接收模型（ActivationEvidenceSubmission / EvidenceProvenance / ChainOfCustodyEvent） | 待补（Task 28） | 是 | 完整（模型层，AI 不可构造人工决策） |

## 2. T1 / T2 / T3 / T4 真实语义（来自 diff / 源码）

- **T1（CI 分支覆盖对齐）**：`baseline-freeze-gates.yml` 与 `release-gate.yml` 的 `on.push.branches`
  由"仅监听历史分支"改为"main + 真实 RC/基线集成分支（显式）+ 后续阶段通配
  （`feat/phase3.9.*` / `feat/phase*-release-*` / `release/**`）"。配套新增
  `scripts/check_ci_release_gate_branches.py`（R1 工作流可解析 / R2 主干占位 / R3 真实载体全覆盖 /
  R4 当前分支覆盖 / R5 通配 / R6 历史分支保留 / R7 既有 job 不破坏 / R8 PR 不收窄）。

- **T2（收口提交完整性）**：`PHASE_BOUNDARY_LEDGER.md` 将 R2 冻结 HEAD 由半途的 `ab1f7cd`
  修正为真实终点 `f7a2aba`；并登记 3.9.6 行。配套新增
  `scripts/check_closure_commit_integrity.py`（核验五类收口产物 tracked/committed/clean +
  working_tree_clean，fail-closed）。

- **T3/T4（激活证据接收 + 溯源/保管链）**：新增 `activation_intake.py`。定义
  `ActivationEvidenceSubmission`（状态上限 `STRUCTURALLY_VALIDATED`，绝不 `APPROVED`）、
  `EvidenceProvenance`（verifiable / missing_provenance_fields）、
  `ChainOfCustodyEvent`。工厂强制 `submitted_by_kind=='user'`，拒绝构造
  `APPROVED_BY_HUMAN` / `REJECTED_BY_HUMAN`（红线③/④/⑨）。只存引用与哈希，不存证据原文
  （T13 存储安全）。

## 3. 3.9.6 行中必须纠正的事实错误（Task 22 红线）

`PHASE_BOUNDARY_LEDGER.md` 当前 3.9.6 行写"审计 +4（100→104）"。
**经 `git status` + `git log` 核验：`agents/enterprise/audit.py` 未被本阶段任何提交或修改触碰，
AuditActionCategory 仍为 100。** 该"+4"属未落实的占位/臆测，违背 Task 22
"不要为阶段编号强行新增 Audit Category"。纠正为"审计不变（仍 100）"。

另：目标态应统一为授权书 §一 终态 `PRODUCTION_ACTIVATION_EVIDENCE_READY_BUILT_NO_GO`，
而非原行的 `PRODUCTION_ACTIVATION_EVIDENCE_SIGNOFF_GOVERNANCE_BUILT_AWAITING_HUMAN`。

## 4. 已存在、可复用的 3.9.5 提交模块（禁止重造）

- `agents/enterprise/production_release/activation_evidence.py` → `ActivationEvidenceBundle`（Task 5 基础）
- `agents/enterprise/production_release/activation_gate.py` → `ControlledActivationGate`（Task 8/15 复用，永不 APPROVED）
- `agents/enterprise/production_release/human_signoff.py` → `HumanSignoffRegistry` / `HumanSignoffRecord`（Task 6/7 基础）
- `agents/enterprise/production_release/human_approval.py` → 3.9.2 最终人工批准契约
- `agents/enterprise/red_line.py` → `EnterpriseRedLineViolationError` / `_RedLineForbiddenMixin`（Task 15 复用，不复制第二套 RedLineViolation）

## 5. 本阶段施工范围（基于真实 Git 定义）

保留并收口：T1 / T2 / T3 / T4（现有未提交增量，全部保留）。
新建（补齐至正式收口）：Tasks 5,6,7（完善/复用）、8（门禁 facade 复用已有 gate）、
9–15、16–21、23、25–28、29–30、收口报告。
新分支：`feat/phase3.9.6-production-activation-evidence-readiness`（自 `f7a2aba` 切出，保留真实 ancestry，不 reset --hard / 不重写历史）。

## 6. 施工后修订（Addendum，2026-08-13 施工中回填）

本节**不改写 §1–§5**——那是启动时刻的真实快照，改写快照等于伪造取证。以下为快照之后
发生的真实变化：

### 6.1 §3 的结论已被后续真实施工推翻（+4 现在成立）

§3 当时的判定是正确的：在写下该节的时刻，`agents/enterprise/audit.py` 确实未被触碰，
`AuditActionCategory` 仍为 100，因此台账里那句"审计 +4（100→104）"当时属于**未落实的占位**。

此后 T5–T10 落地了四条**真实的人工行为通道**，每一条都必须留痕，否则整条链路不可审计：

| 新增类目 | 由哪个真实行为触发 | 若不新增会怎样 |
|----------|--------------------|----------------|
| `ACTIVATION_EVIDENCE_SUBMITTED` | 真实 USER 提交一份激活证据 | 谁在什么时候交了什么，无留痕 |
| `ACTIVATION_EVIDENCE_VALIDATED` | 对已提交证据做结构/哈希/溯源校验 | 校验发生过与否不可证 |
| `HUMAN_SIGNOFF_REGISTERED` | 真实 USER 以某角色登记签署 | 四角色签署无法追责 |
| `ACTIVATION_REVIEW_PACKAGE_GENERATED` | 生成供人裁决的材料包 | 人是"看着哪一版材料"拍的板，不可回溯 |

判据方向与 Task 22 一致：**先有真实行为，后有审计类目**；不是为了让阶段号看起来有产出而
凑数。故 `PHASE_BOUNDARY_LEDGER.md` 3.9.6 行已由"审计不变（仍 100）"更正为
"审计 +4（100→104）"，并同步基线契约、权威测试、JSON Ledger（由 Git 真实提交重建）。

### 6.2 §1 之外新增的模块（Layer A / Layer B 分层）

`agents/enterprise/production_release/activation_readiness.py`（Layer A，仓库派生就绪档案）
与 T3–T10 的 `activation_intake` / `human_signoff` / `intake_service` / `review_package` /
`final_decision`（Layer B，人工提交证据链）**职责正交**，分层契约写在
`agents/enterprise/production_release/__init__.py` 模块 docstring 中：Layer A 回答"仓库客观
就绪前置态"，Layer B 回答"人到底交了/签了/拍了什么"。两层都不得产出放行结论，且不得互相
顶替（Layer A 不能"视为已签署"，Layer B 不能覆盖仓库客观事实）。

## 7. 最终权威结论（2026-08-13 收口复核，覆盖 §3 与 §6.1）

- **§3 的"+4 属臆测/未落实"在**写下该节的那一刻**成立（当时 audit.py 确未被触碰，基线仍为 100）；
  但随着 T5–T10 真实施工，4 类审计事件已真实落地，该结论已被推翻。请勿孤立引用 §3。**
- **权威事实（经枚举定义 + `AuditService` 方法 + 调用点三重核验）**：
  - `AuditActionCategory` 成员数 = **104**（基线 100 + 3.9.6 真实 +4 = 104）；
  - 4 类 = `ACTIVATION_EVIDENCE_SUBMITTED` / `ACTIVATION_EVIDENCE_VALIDATED` /
    `HUMAN_SIGNOFF_REGISTERED` / `ACTIVATION_REVIEW_PACKAGE_GENERATED`，定义在 `audit.py:278-281`；
  - 对应 `AuditService` 记录方法 4 个（`audit.py:3397/3424/3451/3478`）；
  - 真实调用点 **7 处**：`intake_service.py` ×6 + `backend/app/api/governance_activation.py` ×1。
- **JSON Ledger SSOT** `.ai/baselines/audit_action_category_ledger.json` `total=104`，与枚举一致。
- **结论**：3.9.6 的"审计 +4（100→104）"为**真实、可溯源、非凑数**，`PHASE_BOUNDARY_LEDGER.md`
  3.9.6 行与 `roadmap_v8.md` §35.10 已据此登记。本阶段无审计类目造假。
