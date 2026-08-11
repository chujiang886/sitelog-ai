# Phase 3.9.0 生产就绪与受控激活准备层 —— 收口报告

> 身份：BOIP AI Chief Architect + Production Readiness Auditor
> 阶段定位：**生产上线准备体系的构建阶段**——只检查、只规划、不激活、不写真实密钥、
> 不自动授权、不输出 `engineering_approved`、不代替生产负责人。
> 分支：`feat/phase3.9.0-production-readiness-preparation`（自 `49afca9` 分出）
> 收口结论：**BUILT_NO_GO**——准备体系已建成并通过验证，但**未开启生产、未进入自动激活**，
> 等待主理人线下审核与决策。

---

## 1. 目标与范围

- **目标**：把「生产上线前该检查什么 / 该准备什么 / 该由谁线下决策」沉淀为一套
  **只读**的准备体系（检查清单 + 部署清单 + 环境校验 + 权限计划 + 回滚计划 + 激活评审包），
  外加对应的审计留痕与红线结构拦截。
- **范围**：T1–T11 共 11 个 Task。全部产物为「只读检查 + 计划文档 / 结构」，无副作用写入、
  无密钥、无真实授权、无真实激活。
- **不在范围**：真实生产激活、真实企业数据修改、真实密钥写入、真实权限授予、任何
  `engineering_approved` 输出——这些只能源于主理人在人类终端的线下决策。
- **新增产物**：
  - `agents/enterprise/production_readiness/` 包（`forbidden.py` / `models.py` / `service.py` / `__init__.py`）
  - `agents/enterprise/audit.py`：+3 审计枚举与 +3 record 方法（T7）
  - `agents/enterprise/service.py`：运营层门面接线 `self.agent_production_readiness`（T1–T6 入口）
  - `tests/agents/test_production_readiness_preparation.py`：T8 测试（13 例）
  - `.ai/baselines/phase3.8_governance_release_baseline.json`：审计契约总数 72→75 同步

---

## 2. 准备层检查结果（T1–T6）

| Task | 产物 | 关键不变量 | 状态 |
|------|------|-----------|------|
| T1 | `ProductionReadinessChecklist` | 六域（environment/database/security/permission/backup/rollback）；`auto_passed` **恒 False**（只检查、不自动放行） | ✅ |
| T2 | `ProductionDeploymentManifest` | `secret_policy=NO_REAL_SECRET_WRITTEN`；仅密钥**键名**占位，值一律不出现 | ✅ |
| T3 | `EnvironmentValidationReport` | Python/依赖/数据库(配置存在性)/存储(目录存在性)/网络(可配置受控探测) 事实收集；`all_ok` 仅聚合、**不用于放行** | ✅ |
| T4 | `PermissionInitializationPlan` | `policy=NO_REAL_GRANT`；`grant_required` 仅标记、**绝不执行** | ✅ |
| T5 | `RollbackPlan` | `version_from/to` + db/config/recovery 步骤；可逆优先 | ✅ |
| T6 | `ActivationReviewPackage` | 聚合 T1–T5 + 测试结果引用 + 安全检查 + 风险列表；`approved` **恒 False**；`signature_required=HUMAN_PRODUCTION_OWNER` | ✅ |

服务入口 `ProductionReadinessPreparationService` 构造即断言 `safety_invariants_ok()`
（`engineering_enabled` 必须为 False），并通过 `_RedLineForbiddenMixin` 结构拦截所有
开生产 / 出 approved / 真激活 / 改真实数据 / 写真实密钥 / 自动授权 / 代生产负责人 的调用。

---

## 3. 部署准备（T2 manifest）

- 三服务清单：`boip-agents` / `boip-backend` / `boip-frontend`，各含版本、依赖、配置**键名**、
  环境要求。
- 真实密钥仅以**键名**占位列出：`LLM_A_API_KEY` / `DATABASE_PASSWORD` / `SESSION_SECRET` /
  `IDP_CLIENT_SECRET`。**真实值由主理人线下注入，准备层不持有任何密钥明文**。

---

## 4. 安全验证（T3 / T4 / T7）

- **T3 环境校验**：只读取事实（Python 版本、依赖 availability、DB 配置存在性、存储目录存在性），
  无任何写库 / 写配置 / 写文件动作。
- **T4 权限计划**：`NO_REAL_GRANT`——所有 `grant_required=True` 仅表示「需要主理人线下授予」，
  准备层**不执行任何真实授权**。
- **T7 审计增强**：新增 `PRODUCTION_READINESS_CHECK` / `DEPLOYMENT_MANIFEST` / `ROLLBACK_PLAN`
  三个审计动作大类（审计枚举总数 72→75）。三个 `record_*` 方法强制 `actor_kind=USER`
  （**actor 真实**，红线⑥），不提供任何「AI 自动写审计」入口。

---

## 5. 测试结果（T8）

- **新增 `tests/agents/test_production_readiness_preparation.py`：13 例全绿**，覆盖：
  T1 六域不自动放行、T2 无真实密钥、T3 只输出事实、T4 不真实授权、T5 回滚可逆优先、
  T6 不自动批准、T7 枚举存在 + record 强制 USER + 空 actor 拒绝、红线结构拦截、
  `engineering_enabled` 全程不变、运营层门面接线。
- **既有回归（不受影响）**：
  - 审计权威测试（75 计数断言）：17 passed
  - 仓库完整性检查器（规则4 总数断言唯一性）：40 passed
  - 生产安全红线扫描（Phase 3.8.29）：7/7 通过
  - **agents 全量套件：2243 passed / 0 failed**（基线 2154 + 本阶段增量，无回归）

---

## 6. 红线验证（T9，六条最高红线全绿）

| # | 红线 | 验证方式 | 结果 |
|---|------|---------|------|
| ① | `engineering_enabled` 保持 false | `agents/config.yaml:102` 仍为 `false`；准备层构造断言 `safety_invariants_ok()` | ✅ |
| ② | 禁输出 `engineering_approved` | 生产安全 lint「engineering_enabled 保持 false / 测试密钥」等 7/7；评审包无 `engineering_approved` 键；全仓无正向产出 | ✅ |
| ③ | 禁执行真实生产激活 | 无任何 `activate/deploy_production` 调用；结构级禁名 `activate_production` / `deploy_production` 被 mixin 拦截 | ✅ |
| ④ | 禁修改真实企业数据 | 准备层全部为只读构造，无写库 / 写配置动作 | ✅ |
| ⑤ | 禁自动创建真实权限 | `NO_REAL_GRANT`；权限计划仅标记 `grant_required`，不执行 | ✅ |
| ⑥ | 禁代替生产负责人 | 所有审计入口强制 `actor=USER`；结构级禁名 `act_as_production_owner` / `approve_activation` 等 278 项拦截 | ✅ |

- **`verified.json` 未修改**：`git status` 未列任何 `verified.json`（T9 第三项满足）。

---

## 7. Pending Human Actions（主理人线下完成）

1. 审核本激活评审包，并在**人类终端**显式签署 `production.activate` 授权。
2. **线下注入真实密钥**（准备层仅留占位键名，绝不持有明文）。
3. 为 `production-owner` / `ops` / `auditor` **线下授予真实权限**。
4. 在确认所有真实证据后，于**人类终端**将 `engineering_enabled` 置 `True`（全仓唯一一处）。
5. （可选）如需在 `.ai/project_status.json` 补登 `phase_3_9_0` 状态：当前仓库完整性检查器
   仅治理 `3.8.x`（扫描 `phase3.8*` 报告与 `phase_3_8_*_status` 键），`phase3.9.0` 报告不在其
   扫描范围，故本阶段**未强制登记**；若需登记，请主理人确认后手工对齐，避免让 SSOT 描述
   不存在的事实。

---

## STOP

本阶段已收口：**未开启生产、未进入自动激活、未输出 engineering_approved**。
所有产物为只读准备体系， awaiting 主理人审核与线下决策。
