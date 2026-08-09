# Phase 3.8.27 企业治理基础设施收敛层 — 收口报告

- **阶段名称**：Enterprise Governance Infrastructure Consolidation Layer
- **分支**：`feat/phase3.8.27-governance-infrastructure`
- **收口时间**：2026-08-09
- **收口状态**：`BUILT_NO_GO`（已构建，未放行）
- **提交数**：9 个（`1275a1b` → `572eecc`）
- **总变更量**：491 files changed, 108,552 insertions(+), 333 deletions(-)
- **工作区状态**：clean，0 未跟踪文件（除 `.gitignore` 明示的运行时产物）
- **红线开关**：`agents/config.yaml:102 engineering_enabled: false`（本阶段未触碰）

---

## 一、阶段目标

本阶段不新增治理语义，只做**基础设施收敛**——把前几个阶段（3.8.21 ~ 3.8.26）快速演进期间累积的架构债一次性还清，为后续企业级接入（真实认证、真实存储、CI 门禁）腾出干净的落脚点。

五项任务：

| 任务 | 目标 | 状态 |
|---|---|---|
| T1 统一 GovernanceWorkflow 实现 | 消除 `orchestrator.py` / `service.py` 双实现，5 条导入路径收敛到唯一类对象 | ✅ 完成 |
| T2 工作流持久化 | 内存 dict 升级为可替换的持久化层，进程重启后治理事实不蒸发 | ✅ 完成 |
| T3 企业身份认证接入准备 | 消除前端硬编码责任人，抽出 Identity Provider 适配层（本阶段只做接口抽象） | ✅ 完成 |
| T4 Git 仓库治理 | 修复 `agents/`、`tests/`、`.ai/` 大面积未追踪；建立追踪策略、CODEOWNERS、治理规范 | ✅ 完成 |
| T5 测试增强 | 覆盖唯一实现 / Repository / 权限 / 审计 / 迁移兼容五维度 | ✅ 完成（69 用例全绿） |

**边界声明**：本阶段是「搬存储、抽接口、补追踪、加测试」，**不改变任何 AI 治理边界**。所有 Human-in-the-loop 守卫的位置与强度与 3.8.26 完全一致，无一处放宽。

---

## 二、架构变化

### 2.1 变化前（3.8.26 结束态）

```
agents/enterprise/governance_workflow/
  ├── orchestrator.py     ← 实现 A（编排器全量实现）
  ├── service.py          ← 实现 B（另一份编排器，语义漂移风险）
  ├── models.py
  └── forbidden.py
        状态存储：Orchestrator 内 5 个私有 dict，进程级内存，重启即失

frontend/src/app/governance-dashboard/page.tsx
  └── const ACTOR_HEADERS = { "x-actor-id": "governor-1", ... }   ← 硬编码责任人
```

三处结构性问题：

1. **双实现**：同名类两份定义，异常类也是两份 —— `except` 分支可能静默漏捕（捕的是 A 的异常，抛的是 B 的）。
2. **存储与编排耦合**：治理事实直接躺在编排器的私有 dict 里，无法替换、无法落盘、无法验证完整性。
3. **身份硬编码**：责任人是一个前端常量。任何人打开页面都是 `governor-1`，「人工责任」在技术上不成立。

### 2.2 变化后

```
agents/enterprise/governance_workflow/
  ├── orchestrator.py   (1394 行)  ← 唯一实现，通过端口访问存储
  ├── repository.py     (1067 行)  ← 【新增】持久化端口 + 2 个适配器 + 历史留痕
  ├── service.py        (  39 行)  ← 退化为纯 re-export 垫片，零 class/def 定义
  ├── models.py         ( 624 行)
  ├── forbidden.py      ( 145 行)
  └── __init__.py       (  84 行)

frontend/src/lib/identity/          ← 【新增】依赖倒置的身份适配层
  ├── types.ts        (175)  端口契约 + 权限联合类型（无 auto_* 成员）
  ├── errors.ts       ( 80)  7 类 fail-closed 异常
  ├── guards.ts       (192)  assertHumanIdentity / 禁语拒绝 / 权限判定
  ├── registry.ts     (128)  唯一装配点
  ├── index.ts        ( 60)
  └── providers/
      ├── static-dev.ts      ( 83)  3.8.26 硬编码身份的合法归宿（生产环境抛错）
      ├── jwt.ts             (154)  骨架，未启用
      └── gateway-header.ts  ( 85)  骨架，需显式 gatewayVerified
```

依赖方向：`orchestrator → WorkflowRepository（抽象）← InMemory / JsonFile（实现）`；
前端：`page.tsx → IdentityProvider（抽象）← StaticDev / Jwt / GatewayHeader（实现）`。

两处都是标准依赖倒置：**高层策略（治理编排、页面逻辑）不再依赖低层细节（内存 dict、硬编码常量）**。

---

## 三、双实现合并方案（T1）

### 3.1 合并判定

对比两份实现后确认：`orchestrator.py` 是语义完整的一份（含红线守卫、组织隔离、审计接线），`service.py` 是早期版本的残留。**合并方向：以 `orchestrator.py` 为准，`service.py` 退化为垫片。**

不采用「删除 `service.py`」的原因：历史代码与文档中存在 `from ...governance_workflow.service import GovernanceWorkflowOrchestrator` 的导入路径，直接删除会造成外部断裂。垫片是零成本的兼容层。

### 3.2 垫片契约

`service.py` 现为 39 行，**只有 import 与 `__all__`，零 `class` / 零 `def` 定义**。这一点被测试钉死（源码级断言），防止未来有人在垫片里「顺手加个方法」，双实现重新长回来。

### 3.3 唯一性验证

5 条导入路径全部解析到**同一个类对象**（用 `is` 判定，不是 `==`）：

```
agents.enterprise.governance_workflow.orchestrator.GovernanceWorkflowOrchestrator
agents.enterprise.governance_workflow.service.GovernanceWorkflowOrchestrator
agents.enterprise.governance_workflow.GovernanceWorkflowOrchestrator
（+ 异常类 GovernanceWorkflowAccessDenied / EnterpriseRedLineViolationError 同样唯一）
```

异常类唯一性是**必须验证项而非附赠项**：若异常类有两份，`except GovernanceWorkflowAccessDenied` 会漏捕另一份抛出的同名异常，表现为「权限拒绝变成 500」，而所有单元测试仍然全绿。

---

## 四、持久化设计（T2）

### 4.1 端口（`WorkflowRepository`，ABC）

16 项能力，覆盖工作流读写、状态索引、执行桶、归档、历史留痕。

**端口上刻意不存在的方法**：`delete_*`、`update_history`、`clear_history`。这不是遗漏，是设计——治理留痕是**只增不改**的责任事实，删改能力若存在于端口上，就迟早会被调用。`_REPOSITORY_FORBIDDEN` 禁名清单在运行时兜底：访问任何禁名属性直接抛错。

### 4.2 两个适配器

| 适配器 | 用途 | 关键机制 |
|---|---|---|
| `InMemoryWorkflowRepository` | 默认，测试与开发 | 五个原始视图返回**活字典**（不是拷贝），保证旧式直写 `orch._workflows[...]` 的迁移兼容 |
| `JsonFileWorkflowRepository` | 持久化 | 原子写（tempfile + `os.replace`）、版本号、**逐条记录 SHA-256 摘要**、fail-closed 严格加载 |

### 4.3 完整性保护

`JsonFileWorkflowRepository` 加载时逐项校验，以下情况**一律拒绝加载**（抛 `WorkflowStoreIntegrityError`）：

- 载荷被篡改（摘要不匹配）
- 摘要本身被改写
- 文件被截断
- 版本号不符
- 顶层非对象
- 出现未知字段
- 归档索引悬空（指向不存在的工作流）

`WorkflowStoreIntegrityError` **同时是** `EnterpriseRedLineViolationError` 的子类 —— 既有的红线捕获契约无需修改即成立。`strict=False` 模式仅用于取证（登记 `load_errors`），不用于生产恢复。

### 4.4 恢复期不变量

从磁盘恢复工作流时，逐项拒绝下列伪造：

- 缺标识
- `requires_human_confirmation` 被翻转为 false
- 低状态却带 `confirmed_by`（伪造人工确认）
- 高状态却缺研判人
- `completed` 缺 `completed_by` / `archived` 缺 `archived_by`
- 文本字段含「自动审批」等语义标记

**这一层是本阶段最关键的红线加固**：持久化引入了一个 3.8.26 不存在的新攻击面——「直接改磁盘文件伪造人工确认」。恢复期不变量把这个面封死了。

### 4.5 append-only 历史

`WorkflowHistoryEntry`（frozen dataclass）+ `WorkflowHistoryEvent`（枚举）。

- 枚举**无任何 `AUTO_*` / `AI_*` 成员**——测试中成员名从枚举自身 `__members__` 程序化派生，不手抄（规避 `KNOWLEDGE→KNOWEDGE` 这类形近污染，项目历史上踩过）
- `detail` 字段过语义扫描
- 历史条数单调递增
- `list_history()` 返回副本，外部无法就地改写

---

## 五、权限设计（T3）

### 5.1 依赖倒置

前端页面不再知道「责任人是谁」这件事从哪来，只向 `IdentityProvider` 端口要。端口五项契约：`id` / `scheme` / `isConfigured` / `getIdentity()` / `getAuthHeaders()`（+ 可选 `signOut()`）。

### 5.2 三重红线保护

**① 类型级** — `GovernanceIdentity.actorKind` 被收窄为字面量类型 `"user"`。这意味着 agent / system / service 身份**在编译期就无法构造**为治理身份（红线⑥：禁 AI 代替人工责任）。

**② 联合类型级** — `GovernancePermission` 是一个显式联合类型，**刻意不包含任何 `auto_*` 成员**。「AI 自动审批」这个权限在类型系统里根本不存在，写不出来。

**③ 运行时级** — `FORBIDDEN_PERMISSION_PATTERNS` 拦截 `auto_approve` / `bypass_human` / `engineering_approved` 等禁语（大小写不敏感）。

关键设计决策：命中禁语时**拒绝整份凭证**（抛 `IdentityRedLineViolationError`），而不是静默过滤掉那一条权限。理由——一份声明了 `auto_approve` 的凭证，本身就是签发方出了问题的信号；静默剔除会让错误配置以「看起来正常」的降级形态继续运行。

### 5.3 三个 Provider

| Provider | 状态 | 说明 |
|---|---|---|
| `StaticDevIdentityProvider` | 可用（开发） | 3.8.26 硬编码身份的**合法归宿**：默认 `governor-1` / `governance-reviewer`，行为与旧版等价，但 `nodeEnv === "production"` 时直接抛 `IdentityInsecureEnvironmentError` |
| `JwtIdentityProvider` | 骨架，未启用 | 浏览器**无法安全验签**，本层只解析 payload 供 UI 展示并透传 `Authorization`；真正的验签属于后端，留给 3.8.28+ |
| `GatewayHeaderIdentityProvider` | 骨架，未启用 | 要求 `claimsSource` **且** 显式 `gatewayVerified: true` —— 把「后端不可被绕过直连」这个隐含前提抬成一次自觉确认 |

### 5.4 装配点

`registry.ts` 是**唯一**装配点。未知 provider id → 抛错；生产环境未配置 → 抛错。不存在「找不到就退回默认」的静默降级路径。

### 5.5 页面行为变化

`governance-dashboard/page.tsx`：

- 删除 `const ACTOR_HEADERS = {...}`
- 加载时 `getIdentityProvider().getIdentity()` → `requirePermission(me, "governance:workflow:read")`
- 确认操作前 `requirePermission(me, "governance:review:confirm")`
- 取不到身份时页面显示「未取得责任人身份，治理动作已全部禁用」，确认按钮 `disabled`
- 请求头由 `provider.getAuthHeaders()` 产出，`toActorHeaders()` 恒定输出 `x-actor-kind: "user"`

**与后端契约一致**：`backend/app/api/governance_dashboard.py` 上游 `require_user` 校验 `x-actor-kind === "user"`，前后端在同一条红线上闭合。

---

## 六、Git 治理结果（T4）

### 6.1 问题诊断

审计发现**双向漂移**——该追踪的没追踪，不该追踪的进了索引：

| 目录 | 阶段前追踪 | 磁盘实存 | 追踪率 |
|---|---|---|---|
| `agents/` | 64 | 188 | 34% |
| `tests/` | 36 | 147 | 24% |
| `.ai/` | 45 | 224 | 20% |

即：**三分之二的智能体源码、四分之三的测试、五分之四的阶段决策留痕，从未进入版本控制**。这是比任何代码缺陷都严重的问题——治理平台自身的责任事实无法追溯。

反向问题：`tsconfig.tsbuildinfo`（构建缓存）被误追踪。

### 6.2 落地结果

| 目录 | 阶段前 | 阶段后 | 说明 |
|---|---|---|---|
| `agents/` | 64 | **215** | 磁盘 221，差额 6 为 `.gitignore` 明示的运行时产物 |
| `tests/` | 36 | **152** | 磁盘 212，差额为 `_tmp_intake_*` / `_tmp_drill_*` / `__pycache__` 等再生文件 |
| `.ai/` | 45 | **224** | 100% |
| `frontend/src/` | — | **41** | 100% |
| `scripts/` | — | **5** | 100% |

### 6.3 三项治理产物

**`.gitignore`（增强）** — 引入「运行时产物」三条判定准则（可再生 / 与提交无关 / 含机器本地路径或时间戳），据此排除 `tests/_tmp_*`、`tests/intake_snapshots/`、`*.tsbuildinfo`、`agents/engineering/**/*.jsonl`、`*_sessions.json`、`release_*_record.json`、`.workbuddy/` 等。

**`.github/CODEOWNERS`（新增）** — 责任矩阵，关键条目：

- 治理红线区（`red_line.py` / `audit.py` / `governance_workflow/` / `config.yaml` / CODEOWNERS 自身 / CI 配置）→ `@boip/governance-owners`
- 工程闸门 → governance + engineering **双签**
- 前端身份层 + 治理驾驶舱 → frontend + governance **双签**
- `tests/agents/test_enterprise_*` → `@boip/governance-owners`

**`docs/REPOSITORY_GOVERNANCE.md`（新增）** — 追踪判定准则、提交纪律（**明令禁止 `git add -A`**）、语义化提交格式（含红线声明段）、分支策略、评审矩阵。

### 6.4 提交纪律执行情况

全程**精确路径暂存**，无一次 `git add -A`。执行中两次纠偏：

1. `git add 'agents/**/*.py'` 通配符误吞 T1/T2 的三个文件 → `git restore --staged` 剔出，确保该批提交语义纯粹为「补追踪存量」（149 A，零 M）
2. `tests/**/*.py` 通配符捎带 10 个既有改动（审计枚举断言 68→69）→ 剔出后单独作为 `fix(test)` 提交

---

## 七、新增文件

### 7.1 核心交付（本阶段编写）

| 文件 | 行数 | 任务 | 说明 |
|---|---|---|---|
| `agents/enterprise/governance_workflow/repository.py` | 1067 | T2 | 持久化端口 + InMemory/JsonFile 适配器 + 历史留痕 + 恢复期不变量 |
| `tests/agents/test_enterprise_governance_infrastructure.py` | 1064 | T5 | 五维度基础设施测试，69 用例 |
| `frontend/src/lib/identity/types.ts` | 175 | T3 | 端口契约、权限联合类型、禁语清单 |
| `frontend/src/lib/identity/guards.ts` | 192 | T3 | `assertHumanIdentity` / 禁语拒绝 / 权限判定 / 请求头生成 |
| `frontend/src/lib/identity/registry.ts` | 128 | T3 | 唯一装配点 |
| `frontend/src/lib/identity/errors.ts` | 80 | T3 | 7 类 fail-closed 异常 |
| `frontend/src/lib/identity/index.ts` | 60 | T3 | 桶导出 |
| `frontend/src/lib/identity/providers/jwt.ts` | 154 | T3 | JWT 适配器骨架 |
| `frontend/src/lib/identity/providers/gateway-header.ts` | 85 | T3 | 网关头适配器骨架 |
| `frontend/src/lib/identity/providers/static-dev.ts` | 83 | T3 | 开发态静态身份 |
| `frontend/src/lib/identity/__tests__/identity.test.ts` | 392 | T3 | 45 个前端身份测试 |
| `.github/CODEOWNERS` | — | T4 | 责任矩阵 |
| `docs/REPOSITORY_GOVERNANCE.md` | — | T4 | 仓库治理规范 |
| `.ai/reviews/phase3.8.27_governance_infrastructure_closure_report.md` | — | 收口 | 本文档 |

**本阶段新写代码合计约 3,480 行**（其中测试 1,456 行，占 42%）。

### 7.2 补追踪存量（T4，非本阶段编写）

443 个既有文件首次进入版本控制：`agents/` 149、`tests/` 115、`.ai/` 179、backend/scripts 若干。这些是历史产物，本阶段只做纳管，未修改内容。

---

## 八、修改文件

| 文件 | 任务 | 修改内容 |
|---|---|---|
| `agents/enterprise/governance_workflow/orchestrator.py` | T1+T2 | 接入 Repository 端口，5 个存储改为代理属性；保留全部红线守卫 |
| `agents/enterprise/governance_workflow/service.py` | T1 | 全量实现 → 39 行 re-export 垫片 |
| `agents/enterprise/governance_workflow/__init__.py` | T1 | 统一导出面 |
| `frontend/src/app/governance-dashboard/page.tsx` | T3 | 删除硬编码 `ACTOR_HEADERS`，接入身份端口与权限判定，无身份时禁用治理动作 |
| `backend/app/api/governance_dashboard.py` | T5 | 新增 `reset_dashboard_service()` 复位缝；**未改动任何红线校验** |
| `backend/tests/test_governance_dashboard.py` | T5 | 夹具 setup/teardown 两侧复位，消除用例间顺序依赖 |
| `.gitignore` | T4 | 新增运行时产物排除规则 |
| 10 个 `tests/agents/test_*.py` | T4 | 审计枚举总数断言 `68` → `69`（既有漂移，非本阶段引入） |

---

## 九、Commit 列表

分支 `feat/phase3.8.27-governance-infrastructure`，9 个提交，全部含红线声明段。

| # | Hash | 提交信息 | 变更量 |
|---|---|---|---|
| 1 | `1275a1b` | `chore(repo)`: T4 建立仓库治理基线（.gitignore/CODEOWNERS/规范） | 4 files, +248 −1 |
| 2 | `4aa23fb` | `chore(repo)`: T4 补追踪 agents/ 存量源码 149 个文件 | 149 files, +46,123 |
| 3 | `140d1cf` | `chore(repo)`: T4 补追踪 tests/ 存量测试 115 个文件 | 115 files, +23,915 |
| 4 | `93464a3` | `fix(test)`: 对齐审计枚举总数断言 68 → 69（AuditActionCategory） | 10 files, +12 −10 |
| 5 | `0b11e84` | `chore(repo)`: T4 补追踪 backend/scripts 存量与历史遗留改动 | 16 files, +2,289 −20 |
| 6 | `cdf6eb4` | `docs(governance)`: T4 补追踪 .ai/ 阶段决策与评审留痕 179 份 | 181 files, +31,319 −70 |
| 7 | `2f9a075` | `refactor(governance)`: T1+T2 统一治理工作流实现并抽出持久化端口 | 3 files, +2,147 −217 |
| 8 | `51a0dc6` | `feat(identity)`: T3 前端企业身份适配层（接口抽象，fail-closed） | 10 files, +1,404 −15 |
| 9 | `572eecc` | `test(governance)`: T5 基础设施测试增强（69 用例）+ 修复驾驶舱装配泄漏 | 3 files, +1,095 |

**合计**：491 files changed, +108,552 −333。其中补追踪存量占 ~103,600 行，本阶段实际新写 ~3,480 行 + 修改 ~330 行。

---

## 十、测试结果

### 10.1 三套件全绿

| 套件 | 阶段前 | 阶段后 | 增量 |
|---|---|---|---|
| `tests/agents`（智能体运行时） | 2085 passed | **2154 passed** | +69，零回归 |
| `backend/tests`（FastAPI） | 127 passed + **5 errors** | **132 passed** | +5 修复，0 error |
| `frontend` jest | 29 passed | **74 passed**（7 suites） | +45 |

**总计 2,360 个测试全部通过。**

复现命令：

```bash
# 先清理历史遗留临时文件（已知技术债，见第十三节）
find tests -name '_tmp_drill_*' -delete; rm -rf tests/intake_snapshots

backend/.venv/bin/python -m pytest tests/agents -q      # 2154 passed
backend/.venv/bin/python -m pytest backend/tests -q     # 132 passed
node_modules/.bin/jest --config frontend/jest.config.js # 74 passed
```

### 10.2 T5 新增 69 用例分布

| 维度 | 测试类 | 用例数 |
|---|---|---|
| ① 唯一实现 | `TestOrchestratorSingleImplementation` | 5 |
| ② Repository 端口 | `TestRepositoryPortContract` | 6 |
| ② 内存适配器 | `TestInMemoryRepository` | 6 |
| ② append-only 历史 | `TestAppendOnlyHistory` | 7 |
| ② JSON 持久化 | `TestJsonFilePersistence` | 6 |
| ② 完整性拒绝 | `TestStoreIntegrity` | 10 |
| ② 恢复期不变量 | `TestRestoreInvariants` | 10 |
| ③ 权限 | `TestPermissionUnchangedAfterPersistence` | 4 |
| ④ 审计 | `TestAuditPreservedAfterPersistence` | 4 |
| ⑤ 迁移兼容 | `TestMigrationCompatibility` | 11 |
| **合计** | | **69** |

与 3.8.25 的编排语义测试**互补而非重复**：那份测「流程守不守红线」，这份测「承载流程的基础设施可不可靠、收敛有没有悄悄改变既有语义」。

### 10.3 T5 期间发现并修复的真实缺陷

`backend/tests/test_governance_dashboard.py` 6 个用例中 5 个在 setup 阶段报错。

**根因**：`_DEMO_SERVICE` 是进程级单例，而测试夹具是函数级——每个用例都向同一实例登记 `gw-1`，编排器依红线⑥ 拒绝重复 `workflow_id`（禁止覆盖既有治理事实），第二个用例起必然失败。

**处理原则：复位装配，不放宽红线。**

- 新增 `reset_dashboard_service()`，只丢弃服务实例引用，**不删除、不改写任何治理事实**（被丢弃实例连同内存态一并 GC，不存在「抹除留痕」语义）；生产路径不调用（服务由 `EnterpriseOperationLayer` 注入且长期存活）
- 夹具在 setup/teardown 两侧复位，用例间彻底无顺序依赖
- 额外补 `test_duplicate_workflow_id_rejected_on_both_entry_points`，把 `create_workflow` 与 `register_candidate` 共用同一道重复守卫**钉死** —— 未来若有人为让夹具跑通而拆掉这道守卫，该用例立刻变红

这是本阶段唯一一处「测试反过来暴露产品代码缺陷」的案例，且缺陷在装配层而非治理层。

---

## 十一、安全红线验证

### 11.1 六条最高红线逐条核验

| # | 红线 | 本阶段状态 | 验证方式 |
|---|---|---|---|
| ① | 禁开 `engineering_enabled` | ✅ 保持 `false` | `agents/config.yaml:102`；本阶段对该文件的提交数 = **0** |
| ② | 禁输出 `engineering_approved` | ✅ 无输出面 | 落盘产物扫描无该字样（T5 ④ 维度用例）；代码中仅出现在禁语声明与注释 |
| ③ | 禁 AI 自动评级 / 自动确认 | ✅ 未新增 | `def auto_approve/auto_confirm/ai_approve/auto_execute` 全仓扫描 = **0** |
| ④ | 禁 AI 自动禁用/弃用 Agent | ✅ 未新增 | 同上；Repository 端口刻意无 `delete_*` |
| ⑤ | 禁 AI 自动修改 Agent / 自动修改知识 | ✅ 未新增 | 历史 append-only，`WorkflowHistoryEvent` 无 `AUTO_*`/`AI_*` 成员 |
| ⑥ | 禁 AI 代替人工责任 | ✅ 强度未变，且**新增两层加固** | `governance_workflow/` 内 `require_human_actor` / `AuditActorKind.USER` 守卫 **29 处**；前端 `actorKind: "user"` 字面量类型 |

### 11.2 本阶段对红线的净影响：只增不减

本阶段**未放宽任何一条红线**，且新增三处加固：

1. **恢复期不变量（T2）** — 持久化引入了新攻击面「改磁盘文件伪造人工确认」，恢复期不变量逐项封死：翻转 `requires_human_confirmation`、低状态伪造 `confirmed_by`、高状态缺研判人、含「自动审批」语义标记，一律拒绝加载。
2. **类型级人工身份约束（T3）** — `actorKind` 收窄为 `"user"` 字面量，AI 身份在 TypeScript 编译期即无法构造为治理身份。
3. **重复守卫钉死用例（T5）** — `create_workflow` 与 `register_candidate` 共用的重复 `workflow_id` 拒绝守卫被测试固定，防止后人为「让测试跑通」而拆除。

### 11.3 Human-in-the-loop 完整性

- 治理动作全链路仍要求人工 actor，无任何 AI 旁路
- 前端无身份时**禁用**全部治理动作（不是降级为只读提示，是按钮 `disabled` + 明示原因）
- 前后端 `x-actor-kind === "user"` 契约闭合
- `reset_dashboard_service()` 只复位实例引用，不触碰治理事实，且生产路径不调用

### 11.4 未触碰清单

以下红线相关文件本阶段**零改动**：`agents/config.yaml`、`agents/enterprise/red_line.py`、`agents/enterprise/governance_workflow/forbidden.py`、`agents/enterprise/governance_workflow/models.py` 的守卫段。

---

## 十二、当前系统能力

### 12.1 本阶段后新具备的能力

| 能力 | 状态 | 说明 |
|---|---|---|
| 治理工作流跨进程持久化 | ✅ 可用 | 切换到 `JsonFileWorkflowRepository` 即生效，进程重启后责任事实不蒸发 |
| 存储篡改检测 | ✅ 可用 | 逐条 SHA-256 摘要 + 版本号 + fail-closed 严格加载 |
| 治理动作 append-only 留痕 | ✅ 可用 | frozen entry，只增不改不删 |
| 存储后端可替换 | ✅ 可用 | 端口化，接 DB/对象存储只需新增适配器，编排层零改动 |
| 前端身份可插拔 | ✅ 接口就绪 | `StaticDev` 可用；`Jwt` / `GatewayHeader` 骨架待后端配套 |
| 权限判定与按钮级管控 | ✅ 可用 | `requirePermission` + `canConfirm` 驱动 UI |
| 仓库责任可追溯 | ✅ 可用 | 追踪率 agents 34%→97%、tests 24%→100%（净源码）、.ai 20%→100% |
| 变更评审矩阵 | ✅ 就绪 | CODEOWNERS 双签规则已落地（生效待 GitHub 侧团队配置） |

### 12.2 仍未具备（明确不在本阶段范围）

- **真实企业认证**：JWT 验签、SSO/OIDC 对接、RBAC 落库 —— 本阶段只交付接口抽象，实现属 3.8.28+
- **数据库持久化**：当前持久化适配器为 JSON 文件，适合单机与中小规模；DB 适配器待需求明确
- **CI 强制门禁**：CODEOWNERS 已写，但分支保护规则、必需检查项需在 GitHub 仓库设置侧配置
- **工程放行**：`engineering_enabled` 恒 `false`，ESW 窗口维持 `OPEN_EMPTY`，等主理人与专家线下提交真实证据后由人类终端显式置位

### 12.3 阶段结论

**`BUILT_NO_GO`** — 基础设施已收敛并通过全量验证，但工程放行开关保持关闭，等待主理人审核。

---

## 十三、剩余技术债

按严重度排序。**本阶段新引入的债标注为「新增」，其余为存量。**

### D-1｜测试临时文件污染（存量，高优先级）

- **现象**：`tests/_tmp_drill_*.json` / `tests/_tmp_intake_*.json` 历史堆积数百个；threshold 系列测试会扫描 `tests/` 目录读取这些文件，导致雪崩式失败（与被测代码无关）。每次运行再生 ~14 个。
- **本阶段处置**：已在 `.gitignore` 排除，不再污染版本库；跑测试前需手动 `find tests -name '_tmp_drill_*' -delete; rm -rf tests/intake_snapshots`。
- **未偿部分**：测试本身仍会写入仓库目录。**根治方案**：改用 `tmp_path` fixture，让临时产物落在 pytest 隔离目录。建议单独开一个 hygiene 任务。

### D-2｜前端存量 TS 类型错误（存量，中优先级）

- `tsc --noEmit` 在 `consult/page.tsx`、`consult.test.tsx`、`result.test.tsx`、`upload.test.tsx`、`lib/api.test.ts`、`lib/chat.ts` 报错。
- **与本阶段无关**：`frontend/src/lib/identity/**` 与 `governance-dashboard/page.tsx` 过滤后**零错误**（已验证）。
- 建议后续单独清理，并在 CI 加 `tsc --noEmit` 门禁防回潮。

### D-3｜JSON 文件持久化的规模上限（新增，中优先级）

- `JsonFileWorkflowRepository` 每次写全量文件，工作流量级上万后 IO 与内存会成为瓶颈；无并发写锁，多进程部署会互相覆盖。
- **当前不构成风险**：默认适配器仍是内存版，文件版用于单机场景。
- 端口化设计已使替换成本可控 —— 接 DB 只需新增一个适配器，编排层零改动。

### D-4｜JWT / GatewayHeader Provider 未实装（新增，已知缺口）

- 两者为骨架，`isConfigured` 默认 false，未接入 registry 生产路径。
- **安全前提必须写清**：浏览器无法安全验签，`JwtIdentityProvider` 的解析结果**仅供 UI 展示，不是安全边界**。真正的身份裁决必须在后端。这一点已在代码注释与本报告中双重声明，防止后人误当作认证实现。

### D-5｜CODEOWNERS 未实际生效（新增，配置缺口）

- 文件已落地，但 `@boip/governance-owners` 等团队在 GitHub 侧尚未创建，分支保护规则未配置。
- 当前仓库无 origin 远程，规则处于「已声明未强制」状态。属组织侧配置事项。

### D-6｜`.ai/` 目录体量（存量，低优先级）

- 补追踪后 `.ai/` 224 个文件、约 31,000 行进入版本库。内容是阶段决策与评审留痕，有长期价值，但缺少索引与归档策略。
- 建议后续建立 `.ai/INDEX.md` 与按阶段归档规则。

### 已在本阶段解决、不再计入债务

- ~~审计枚举总数断言 `== 68` 硬编码于 10 个测试文件~~ → 已于 `93464a3` 对齐为 69，并在 T5 ⑤ 维度加了稳定性用例
- ~~`GovernanceWorkflowOrchestrator` 双实现~~ → T1 已收敛，测试钉死
- ~~前端硬编码 `ACTOR_HEADERS`~~ → T3 已消除
- ~~`backend/tests/test_governance_dashboard.py` 5 errors~~ → T5 已修复装配泄漏
- ~~`tsconfig.tsbuildinfo` 误入版本库~~ → T4 已从索引移除

---

## 十四、下一阶段建议

### 建议一：Phase 3.8.28 定为「企业身份认证实装层」（推荐优先）

T3 只交付了接口，价值尚未兑现。真正消除「责任人是个前端常量」这个问题，需要后端配套：

1. 后端 JWT 验签中间件（签发方、过期、audience 校验），把身份裁决收到服务端
2. RBAC 权限落库，替换 `guards.ts` 里的 `ROLE_PERMISSIONS` 硬编码映射
3. 前端 `JwtIdentityProvider` 实装并在 registry 生产路径启用
4. `StaticDevIdentityProvider` 加入 CI 检查，确保永不出现在生产构建

**理由**：这是当前唯一一处「红线在设计上成立、但在部署上尚未闭合」的位置。任何人打开驾驶舱都是 `governor-1`，人工责任在生产环境仍不可追溯。基础设施已就位，此时实装成本最低。

### 建议二：仓库卫生专项（小、可并行）

- D-1 测试临时文件根治（改 `tmp_path` fixture）
- D-2 前端存量 TS 错误清理
- CI 接入：`pytest tests/agents` + `pytest backend/tests` + `jest` + `tsc --noEmit` 四项必需检查
- GitHub 侧创建 CODEOWNERS 涉及的团队并开启分支保护

建议作为独立 hygiene 分支处理，不与治理语义演进混在同一阶段。

### 建议三：暂缓引入 DB 持久化

端口已抽出，替换成本可控。在真实规模需求出现前引入 DB，会带来 schema 迁移、事务边界、连接池等一整套复杂度，而当前收益为零。**建议等到有明确的并发或量级诉求再做。**

### 建议四：不要在下一阶段扩治理语义

3.8.21 ~ 3.8.26 连续六个阶段都在加治理语义，本阶段才把架构债还清。建议下一阶段专注「让已有能力真正可用」（认证实装 + CI 门禁），而非继续加层。

---

## 收口声明

- Phase 3.8.27 五项任务（T1 ~ T5）**全部完成**，2,360 个测试全绿，零回归。
- 六条最高红线**逐条核验通过**，本阶段未放宽任何一条，另新增三处加固。
- `engineering_enabled` 保持 `false`，ESW 窗口维持 `OPEN_EMPTY`。
- 阶段状态：**`BUILT_NO_GO`**。
- 按纪律要求，**在此停止，不进入 Phase 3.8.28，等待主理人审核。**

---

*报告生成：2026-08-09 ｜ 分支 `feat/phase3.8.27-governance-infrastructure` ｜ HEAD `572eecc`*
