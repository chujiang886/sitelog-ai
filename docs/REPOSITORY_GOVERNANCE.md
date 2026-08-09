# BOIP 仓库治理规范

> 建立于 Phase 3.8.27 T4（企业治理基础设施收敛层）。
> 本文件是仓库层面的**强制约定**，与 `.gitignore`、`.github/CODEOWNERS` 三者配套生效。

---

## 1. 为什么需要这份规范

Phase 3.8.27 架构自分析时对仓库做了一次完整体检，结果如下：

| 目录 | 磁盘上的文件 | 被 git 追踪 | 追踪率 |
|---|---|---|---|
| `agents/`（Python 源码） | 188 | 64 | **34%** |
| `tests/`（Python 测试） | 147 | 36 | **24%** |
| `.ai/`（阶段与评审文档） | 224 | 45 | **20%** |

也就是说：**平台三分之二的源码、四分之三的测试从未进入版本库**。

这不是"还没提交"，而是一类结构性风险：

1. **不可回溯** —— 治理红线代码（`red_line.py` 之外的大量实现）没有历史，改坏了无法 `git revert`；
2. **不可评审** —— 未追踪文件不进 diff，CODEOWNERS 与分支保护对它们完全失效；
3. **不可复制** —— 换一台机器 clone 下来的仓库跑不起来，"仓库"不等于"系统"；
4. **审计断链** —— 企业治理平台自身的代码变更无法自证，这与平台宣称的治理能力自相矛盾。

同时存在反向问题：`frontend/tsconfig.tsbuildinfo`（构建缓存）被追踪，
`tests/_tmp_*`（测试临时产物，历史上曾堆积数百个）散落在工作区。
即"**该进的没进，不该进的进了**"。

T4 的目标就是把这两件事同时纠正，并把判定标准写死，避免复发。

---

## 2. 追踪判定标准（唯一口径）

一个文件**不入库**，必须同时满足以下三条：

1. 由程序运行 / 测试执行**自动生成**；
2. 删除后可通过重跑**完全复现**，不含任何唯一的人工输入；
3. 内容随机（哈希名 / 时间戳）或体量**持续膨胀**。

**不满足以上三条的一律必须追踪。** 尤其是：

- 所有 `agents/**/*.py`、`backend/**/*.py`、`frontend/src/**`、`scripts/**`
- 所有 `tests/**/*.py`（红线测试是治理资产，不是临时脚本）
- 所有 `.ai/**/*.md` 阶段设计与收口报告（是决策留痕）
- 所有结构性配置：`agents/config.yaml`、`alembic/versions/*`、CI 配置

### 已明确排除的运行时产物

| 模式 | 理由 |
|---|---|
| `tests/_tmp_*`、`tests/intake_snapshots/` | 测试临时产物；历史上堆积导致 threshold 系列测试雪崩式失败 |
| `*.tsbuildinfo` | tsc 增量缓存，每次构建都变，入库只制造无意义 diff |
| `agents/engineering/knowledge/*_sessions.json` | 会话运行时状态 |
| `agents/engineering/thresholds/verified.json` | 阈值签署运行时产物 |
| `agents/engineering/**/*.jsonl` | 审计/评审流水，应落审计系统与数据库，不属版本库 |
| `release_freeze_record.json`、`release_candidate_record.json` | 发布流程运行时记录 |
| `.workbuddy/` | 本地 AI 工作台数据，属个人环境而非项目资产 |

> **注意**：审计流水不入库 ≠ 审计可丢。
> 审计的权威载体是 `AuditService` 与数据库，版本库只承载**代码与决策**。

---

## 3. 提交纪律（硬性）

### 3.1 禁止 `git add -A` / `git add .`

BOIP 工作区长期混有运行时产物与跨阶段草稿，`git add -A` 会：

- 把临时文件、缓存、本地记忆一次性灌进历史，事后只能靠改写历史清理；
- 把多个阶段的改动混进一次提交，破坏「一阶段一收口」的可回溯性。

**唯一允许的方式是精确路径 add**：

```bash
git add agents/enterprise/governance_workflow/repository.py
git add tests/agents/test_enterprise_governance_infrastructure.py
```

批量场景使用受控 glob，并在 add 后用 `git status --short` 逐条核对：

```bash
git add 'agents/**/*.py'
git status --short   # 必须人工确认清单
```

### 3.2 一个阶段一组语义提交

每个 Phase 的提交按**域**切分，不按时间切分。典型顺序：

1. `chore(repo)` 仓库治理基建（.gitignore / CODEOWNERS / 规范文档）
2. `feat(<域>)` 源码
3. `test(<域>)` 测试
4. `docs(<域>)` 阶段文档与收口报告

### 3.3 提交信息格式

```
<type>(<scope>): <中文摘要>

<正文：为什么改、影响面、红线验证结论>
```

`type` 取值：`feat` / `fix` / `refactor` / `test` / `docs` / `chore` / `perf`。

治理相关提交**必须**在正文中显式声明红线状态，例如：

```
红线验证：engineering_enabled 保持 false；未产出 engineering_approved；
AI 无自动审批/自动执行路径；require_human_actor(USER) 全链路生效。
```

---

## 4. 分支策略

| 分支 | 用途 | 约束 |
|---|---|---|
| `master` | 已验收基线 | 只接受经主理人审核的合并 |
| `feat/phaseX.Y.Z-<主题>` | 阶段开发 | 一阶段一分支，收口后停等审核 |
| `fix/<主题>` | 缺陷修复 | 允许直接从 master 切出 |

阶段分支在收口报告产出后**立即停止**，不得自行进入下一阶段。
这是治理纪律，不是流程建议。

---

## 5. 评审责任矩阵

见 `.github/CODEOWNERS`。要点：

- **治理红线区**（`red_line.py`、`audit.py`、`governance_workflow/`、`config.yaml`）
  必须由 `@boip/governance-owners` 评审；
- **工程激活闸门**（`gate/`、`approved_monitor.py`、`config_loader.py`）
  需治理 + 工程双签；
- **前端身份适配层**（`frontend/src/lib/identity/`）视为治理红线延伸区，需双签
  —— 因为它决定"谁能代表人做治理动作"；
- **红线测试**（`tests/agents/test_enterprise_*`）由治理负责人把关，
  防止通过放宽断言绕过红线；
- `CODEOWNERS` 自身也在治理管辖内，防止绕过评审结构。

---

## 6. 落地状态（Phase 3.8.27 T4）

- [x] `.gitignore` 补全运行时产物排除规则，并写入判定标准
- [x] `frontend/tsconfig.tsbuildinfo` 从索引移除（保留本地文件）
- [x] 新建 `.github/CODEOWNERS` 责任矩阵
- [x] 新建本规范文档
- [x] `agents/` 与 `tests/` 源码按域精确补追踪
- [ ] GitHub 组织团队创建与分支保护规则绑定（需远端仓库，属部署侧动作）

---

## 7. 后续维护

新增排除规则时，必须在 `.gitignore` 中同时说明其满足第 2 节三条判定标准中的哪几条；
无法自证的一律追踪。规范本身的修改走 `@boip/governance-owners` 评审。
