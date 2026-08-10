# Phase 3.8.31 治理仓库完整性与发布基线收敛层 — 收口报告

| 项 | 值 |
| --- | --- |
| 阶段编号 | Phase 3.8.31 |
| 阶段名 | Governance Repository Integrity & Release Baseline Convergence Layer（治理仓库完整性与发布基线收敛层） |
| 阶段性质 | **仓库治理 / SSOT 对齐 / Git 完整性 / 测试基线收敛**，非新业务功能开发 |
| 执行身份 | BOIP AI Chief Architect + Repository Governance Auditor + Release Baseline Custodian |
| 收口时间 | 2026-08-10 |
| HEAD | `1377e8b`（Phase 3.8.29 企业生产安全与部署强化层），**全程未变** |
| 状态 | `GOVERNANCE_REPOSITORY_INTEGRITY_RELEASE_BASELINE_BUILT_NO_GO` |
| Roadmap | `.ai/roadmap_v8.md` §34 |
| 放行结论 | **未放行**。`engineering_enabled=false`，未输出 `engineering_approved`，未触碰 `verified.json` |

---

## 一、阶段目标

3.8.27 → 3.8.30 连续四个阶段高速推进后，仓库出现了典型的「**跑得比账快**」问题：代码与报告是真的，但记账（SSOT）、事实基线、编号语义、测试统计四处漂移。本阶段不写新业务功能，只做四件事：

1. **对账**：把已产出收口报告却未在 SSOT 登记的阶段全部归位，不重编号、不覆盖历史。
2. **固化事实**：把「本次收敛点的仓库事实」冻结成一份机器可读的发布基线清单，让后续任何漂移都必须是显式改基线的动作，而不是悄悄发生。
3. **建门禁**：写一个只读的仓库完整性检查器，把上述不变量变成 CI 里能失败的硬约束。
4. **清债**：清理 threshold 系列历史 hygiene 债与审计枚举总数断言的脆性设计，把测试基线收敛到全绿。

核心判断：**治理层的真正风险不是功能缺失，是账实不符**。一个说自己 72 类审计、实际 72 类、但十几处测试各自硬编码总数的仓库，下一次加一类就会雪崩——这不是测试在保护代码，是测试在勒索代码。

---

## 二、任务分解与完成情况（18 Task）

| Task | 内容 | 状态 |
| --- | --- | --- |
| T1 | Reality Scan（仓库现状全量扫描 + Phase 登记表） | ✅ |
| T2 | SSOT Reconciliation（阶段登记对账回填） | ✅ |
| T3 | Artifact Integrity（产物完整性核验） | ✅ |
| T4 | Commit Boundary Plan（提交边界规划，**只规划不提交**） | ✅ |
| T5 | Threshold Hygiene（临时文件历史债清理） | ✅ |
| T6 | Test Baseline Authority（测试基线权威化） | ✅ |
| T7 | Audit Category Contract Cleanup（审计枚举契约去脆性） | ✅ |
| T8 | Release Baseline Manifest（发布基线清单） | ✅ |
| T9 | Repository Integrity Checker（完整性检查器 9 规则） | ✅ |
| T10 | CI Integration（挂载为 CI 步骤 11） | ✅ |
| T11 | Documentation Reconciliation（roadmap 补章 + 引用修正） | ✅ |
| T12 | Red-Line Verification（六道红线逐条复核） | ✅ |
| T13 | 完整测试（双套件全量实跑） | ✅ |
| T14 | 收口文档（本报告） | ✅ |
| T15 | SSOT 更新（3.8.31 档案与状态串登记） | ✅ |
| T16 | 交付 + STOP | ✅ |

---

## 三、六道最高红线守约核验（fail-closed）

红线复核不是「声明我没违规」，而是**逐条给出可复验的证据**。

### 红线①：`engineering_enabled` 恒 false

- 事实：`agents/config.yaml:102` 为 `engineering_enabled: false`，本阶段未修改。
- 常态化守卫：检查器**规则 7**（`rule_engineering_flag_false`）已挂 CI 步骤 11，此后任何人改成 true 都会红。

### 红线②：禁输出 `engineering_approved`

- 事实：全仓 Grep 复核，`agents/` 与 `backend/app/` 中该标识**仅出现在否定式声明与 fail-closed 闸门**（forbidden 名单、负向断言），**无任何正向产出路径**。
- 常态化守卫：检查器**规则 8**（`rule_no_engineering_approved_emission`）。

### 红线③：禁覆盖历史 commit

- HEAD 全程恒为 `1377e8b`，未 rebase / 未 amend / 未 force。
- `git reflog` 无 rebase、amend 记录；无进行中的 rebase / merge 状态。
- 本阶段**未执行任何提交**，30 项改动全部留在工作区（详见 §7）。

### 红线④：禁重编号已占用 Phase

- `7384b00`（3.8.27 治理基础设施收敛层）、`f10c5dc`（3.8.28 企业身份认证）、`1377e8b`（3.8.29 生产安全）三个 commit 均经 `git merge-base --is-ancestor` 验证在册且为 HEAD 祖先。
- 三者编号语义**未被覆盖、未被挪用**。追踪层按主理人裁决记为 **3.8.30**，该裁决未被重改。
- 常态化守卫：检查器**规则 9**（`rule_phase_numbering_unique`）。

### 红线⑤：禁删测试 / 跳失败 / 改逻辑掩盖失败

这是本阶段改动量最大、最需要自证的一条。

- 17 个测试文件被修改，函数级统计：**删除 19 个 / 新增 19 个**，一一对应，全部为重命名或签名变更，**零测试丢失**。
- `test_threshold_migration.py`：13 删 = 13 增，同样一一对应。
- **无任何新增 `skip` / `xfail`**。
- 14 条 `== 69` 形式的脆性总数断言被替换为**存在性契约**（子集断言）——这是断言语义的收敛，不是断言的删除：原断言保护的是「这些类别在册」，新断言保护的仍是「这些类别在册」，只是不再顺带绑架总数。

### 红线⑥：禁伪造任何 commit / 测试 / 文件 / SSOT / release 状态

- 所有引用的 commit 均经 `git merge-base --is-ancestor` 实证，非凭记忆书写。
- 所有测试数字均为**当日实跑**，非估算、非沿用（详见 §5，并因此修正了一处失真，见 §6）。
- `verified.json` **未触碰**。
- release 状态维持 `BUILT_NO_GO`，未做任何放行性表述。

---

## 四、核心交付物

### 4.1 发布基线清单 `.ai/baselines/phase3.8_governance_release_baseline.json`（17.2 KB）

机器可读的单一事实源，冻结六类事实：

- `git`：HEAD、head_phase、未提交说明；
- `release_gate`：`BUILT_NO_GO` / `engineering_enabled=false` / `engineering_approved_emitted=false` / `verified_json_modified=false`；
- `audit_category_contract`：总数 72、权威文件、唯一性策略、演进史（68 → +1 VIEW = 69 → +3 TRACE/TIMELINE/REPLAY = 72）、6 个必需审计族；
- `test_baseline`：双套件实跑数字；
- `ssot`：回填清单与理由；
- `phase_registry`：3.8.0 → 3.8.31 共 32 个阶段的编号、名称、状态、状态键、报告路径。

另含 `integrity_invariants`（8 条不变量）、`known_notes`（4 条歧义备忘）、`pending_verification`（4 项存疑保留）。

### 4.2 仓库完整性检查器 `scripts/check_governance_repository_integrity.py`（565 行）

只读、不修改任何文件。9 条规则：

| # | 规则 | 防的是什么 |
| --- | --- | --- |
| 1 | 基线清单可解析 | 基线本身损坏 |
| 2 | 阶段登记完整（报告 ⇒ SSOT） | 干了活不记账 |
| 3 | SSOT 报告路径真实存在 | 记了账没有活 |
| 4 | 审计总数断言全仓唯一 | 总数断言四处扩散导致脆性 |
| 5 | 审计总数与基线一致 | 枚举实际数与基线漂移 |
| 6 | 必需审计族齐备 | 关键审计大类被误删 |
| 7 | 红线①`engineering_enabled=false` | 越权放行 |
| 8 | 红线②不产出 `engineering_approved` | 越权批准 |
| 9 | 阶段编号唯一无冲突 | 编号覆盖 / 重号 |

**当前结果：9/9 全绿。**

### 4.3 检查器双向自检 `tests/agents/test_governance_repository_integrity_checker.py`（434 行，40 例）

设计原则：**门禁抓不住违规，等于没门禁**。因此每条规则都配「正例放行 + 反例拦截」双向自检——不仅验证合规仓库能过，更验证违规仓库会被精确拦下（含违规位置定位）。

**当前结果：40/40 全过。**

### 4.4 CI 集成 `scripts/ci/local_ci.sh`

检查器挂载为**步骤 11**（总步骤数 7 → 11 中的静态门禁段）。设计考量已写入脚本注释：静态门禁虽然最先失败最省时间，但仍排在最后，是为了让「代码到底能不能跑」先有结论。

### 4.5 文档与 SSOT

- `.ai/roadmap_v8.md`：补 §32/§33/§34 三章并重编号，§34 为本阶段。
- `.ai/project_status.json`：修正 4 处编号引用错误，补登 3.8.25/3.8.26 档案，新增 `phase_3_8_31_status` 与 `phase_3_8_31` 档案。

---

## 五、测试基线（当日实跑，`backend/.venv/bin/python` 3.11）

| 套件 | 命令 | passed | failed | 耗时 |
| --- | --- | --- | --- | --- |
| `tests/agents` | `backend/.venv/bin/python -m pytest tests/agents -q` | **2230** | 0 | 14.0 s |
| `backend/tests` | `cd backend && .venv/bin/python -m pytest tests -q` | **292** | 0 | 21.2 s |
| **合计** | — | **2522** | **0** | — |

两笔历史债在本阶段清零：

1. 3.8.29 收口时记录的 backend「291 passed / **1 failed**（继承债）」——已修复，现 292 全绿。
2. threshold 系列历史 hygiene 债（`_tmp_drill_*` 临时文件堆积导致的雪崩式失败）——已清理，残留临时文件 **0**。

**全绿、零跳过、零 xfail。**

---

## 六、实战发现的两处真实缺陷（本阶段最有价值的产出）

红线复核如果只是照着清单打钩，就没有价值。本阶段的复核实际抓出了两处真实缺陷，均已修复。

### 缺陷一：检查器规则 4 存在别名漏网（门禁失效）

**现象**：扫描发现 `tests/agents/test_enterprise_governance_workflow_orchestration.py:605` 存在第二处总数硬断言 `assert len(cats) == 72`（非权威文件），而检查器却报规则 4 通过。门禁没抓住它。

**根因**：规则 4 的参数识别只认裸变量白名单（`members`、`list(AuditActionCategory)` 等）。而该处写法是**局部别名**：

```python
cats = {c.value for c in AuditActionCategory}
...
assert len(cats) == 72
```

`cats` 不在白名单里，整条断言直接从门禁下漏过去。

**附带发现**：该用例名为 `test_audit_category_count_still_68`，实际断言 `== 72`，注释还写着「计数 68」——**函数名在撒谎**。历史上多次加类别只改了数字、没改名字。

**双修方案**：

1. **改被测方**：该处改为存在性契约，只断言本层真正依赖的三类工作流审计大类在册，并更名为 `test_workflow_audit_categories_registered`，消除名字撒谎。断言强度不减、脆性归零。
2. **改门禁**：检查器新增 `_enum_full_set_aliases()`，通过 `_ENUM_ALIAS_BINDING_RE` + `_ENUM_ALIAS_RHS_RE` 识别「枚举全集别名」绑定，`_find_total_assertions()` 改为 `if not is_whitelisted and arg not in aliases: continue`，使别名形式也被捕获。

**加固自证**：新增 7 条双向自检（33 → 40），其中：

- `test_enum_full_set_alias_total_assertion_is_rejected`：直接复现本次漏网场景，断言违规位置精确定位到 `tests/aliased_layer.py:4`；
- `test_enum_alias_variants_are_all_caught`：parametrize 覆盖 `list()` / `sorted()` / 列表推导 / `__members__` 四种别名变体；
- `test_non_enum_alias_is_not_flagged` 与 `test_single_member_reference_is_not_an_alias`：两条**误报守卫**，确保 `team.categories()`、单成员引用 `GOVERNANCE_TRACE` 不被误判。

加固的价值不在于修了一处断言，而在于**证明了修完之后这类违规真的抓得住**。

### 缺陷二：基线测试数字失真（统计口径缺口）

**现象**：基线记 `tests/agents = 2190`，当日实跑 `2230`，差 40。初判疑似伪造。

**核查**：2190 + 33（T9 检查器自检）+ 7（本次新增别名回归守卫）= 2230，完全吻合。**2190 是 T9 自检文件建立之前测得的数字，后续未同步**。属统计口径缺口，非伪造。

**处置**：据实更新基线为 2230 / 292 / 合计 2522，并在 `note` 中写明差额来源，保留可追溯性。

### 附：一处假阳性（已排除）

初见基线 `measured_at = 2026-08-10` 时，因上下文注入时间为 08-09，一度怀疑是未来日期（红线⑥）。执行 `date` 实测系统时间为 `2026-08-10 19:06 CST`，确认无误，排除伪造嫌疑。**存疑必查、查实必录**，这条也写进记录。

---

## 七、提交边界规划（T4，只规划、不执行）

本阶段**不执行任何 git 提交**。工作区当前 30 项改动，建议未来按语义拆为两个 commit：

**Commit A — Phase 3.8.30 追踪层产物**（5 项）

```
?? agents/enterprise/governance_traceability/
?? tests/agents/test_enterprise_governance_traceability.py
?? .ai/reviews/phase3.8.30_governance_traceability_audit_report.md
 M agents/enterprise/__init__.py / audit.py / service.py（+3 审计类别接入）
```

**Commit B — Phase 3.8.31 仓库完整性与基线收敛**（其余）

```
?? .ai/baselines/  ?? scripts/check_governance_repository_integrity.py
?? tests/agents/test_governance_repository_integrity_checker.py
 M .ai/project_status.json / .ai/roadmap_v8.md / .gitignore / scripts/ci/local_ci.sh
 M 17 个测试文件（脆性断言收敛 + threshold hygiene）
```

差异统计：24 个已跟踪文件，+918 / −131。

**提交动作留待主理人授权后执行**，AI 不自行提交，以免污染 3.8.30 与 3.8.31 的边界语义。

---

## 八、关键设计决策

1. **总数权威单点化**：全仓只允许一处硬编码枚举总数断言（`tests/agents/test_enterprise_knowledge_governance_audit.py` 的 `assert len(members) == 72`），其余各层一律降为存在性契约。理由：总数是全局事实，应当只有一个负责人；各层只应关心自己依赖的类别是否在册。
2. **基线即事实、漂移即显式**：不变量写进 JSON 而非文档散文，使「改基线」成为一个可 review 的动作，杜绝静默漂移。
3. **门禁必须双向自证**：只测「合规能过」是自欺，必须测「违规被拦」并校验拦截位置。本阶段正是靠这条原则抓出了规则 4 的漏网。
4. **存疑保留而非删除**：`pending_verification` 保留 4 项未证实事项，不做乐观清理。
5. **编号裁决不可回改**：3.8.30 归属由主理人裁决，写入基线 `known_notes` 固化，防止后续会话「自作聪明」重排。

---

## 九、遗留与 pending_verification

| 项 | 说明 |
| --- | --- |
| 真实生产部署与真实企业身份目录接入 | 未进行 |
| `verified.json` 真实化 | 本阶段未触碰 |
| `engineering_enabled` 开启 | **仅人类终端可执行**，AI 无权 |
| 3.8.30 / 3.8.31 产物提交边界 | 已规划，待主理人授权后执行 |

---

## 十、状态结论与 STOP 纪律

- **阶段状态**：`GOVERNANCE_REPOSITORY_INTEGRITY_RELEASE_BASELINE_BUILT_NO_GO`
- **放行结论**：**未放行**。本报告不构成任何放行依据；放行决策仅限主理人在人类终端执行。
- **STOP 声明**：
  - 已 STOP，**不进入 Phase 3.8.32**；
  - **未开启** `engineering_enabled`（恒 false）；
  - **未输出** `engineering_approved`；
  - **未自动放行**、未提交、未改 `verified.json`、未伪造任何专家签名；
  - 等待主理人审核授权。

---

*报告生成：2026-08-10 ｜ Phase 3.8.31 Task 14 ｜ 依据 `.ai/baselines/phase3.8_governance_release_baseline.json` 与当日实跑测试*
