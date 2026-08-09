# Phase 3.8.11 收口报告 —— Enterprise Knowledge Conversation & Memory Layer（企业知识对话上下文与记忆层）

- **状态**：`ENTERPRISE_KNOWLEDGE_CONVERSATION_MEMORY_BUILT_NO_GO`（已构建，未进入启用态）
- **工程开关**：`engineering_enabled = false`（fail-closed，红线①）
- **收口结论**：✅ 全部 10 项任务交付；✅ 全量 agents 测试 **1353 passed**（基线 1335 + 18 新增），零回归；✅ 六条最高红线守约。
- **下一步**：**STOP，不进入 Phase 3.8.12；等待主理人审核。**

---

## 1. 概览与目标

Phase 3.8.11 在 3.8.0~3.8.10 企业知识层基座之上，新增「企业知识对话上下文与记忆层」，把分散的知识检索 / 引用 / 回答能力收敛到一条可审计、可隔离、可人工兜底的**会话主线**上。

设计主线（用户 → 会话 → 上下文 → 知识引用 → 回答草稿 → 人工使用）：

1. 用户发起一次知识会话（`KnowledgeConversation`）。
2. 会话内逐条追加消息（`KnowledgeMessage`），AI 消息**必须引用来源**。
3. 会话上下文（`KnowledgeConversationContext`）只暂存活跃主题 / 引用知识 / 未决问题 / 溯源，**绝不回写知识库**。
4. 记忆策略（`MemoryPolicyService`）管理短期上下文与长期记忆候选；长期记忆候选 `requires_human_review=True`，**唯一纳入路径须真实 USER**（红线⑥）。
5. 所有写路径如实接入 `AuditService`（新增 `KNOWLEDGE_CONVERSATION` / `KNOWLEDGE_MESSAGE` / `KNOWLEDGE_MEMORY` 三类）。
6. 不同用户只能访问自己的会话与授权知识（任务6：接入 `IdentityService` + `KnowledgeVisibilityPolicy`）。

---

## 2. 交付资产

### 2.1 新建文件

| 文件 | 内容 |
| --- | --- |
| `agents/enterprise/knowledge_conversation.py` | 任务1：`ConversationStatus` / `KnowledgeConversation` / `KnowledgeConversationService`（创建 / 读取 / 列举本人 / 归档；组织隔离；访问隔离） |
| `agents/enterprise/knowledge_message.py` | 任务2：`MessageRole` / `KnowledgeMessage` / `KnowledgeMessageService`（追加 / 读取 / 列举；**AI 消息 references 非空强制**；`requires_human_review` 强制 True） |
| `agents/enterprise/knowledge_conversation_context.py` | 任务3：`KnowledgeConversationContext` / `KnowledgeConversationContextService`（上下文更新 / 读取 / 授权知识过滤；**只暂存会话上下文，禁写知识库**） |
| `agents/enterprise/knowledge_memory_policy.py` | 任务4：`MemoryCandidateStatus` / `MemoryCandidate` / `MemoryPolicyService`（提议 / 人工纳入 / 人工拒绝 / 读取 / 列举；长期记忆 `requires_human_review=True` + `require_human_actor` 守卫） |

### 2.2 修改文件

| 文件 | 变更 |
| --- | --- |
| `agents/enterprise/audit.py` | 任务5：新增 3 个审计类别 `KNOWLEDGE_CONVERSATION` / `KNOWLEDGE_MESSAGE` / `KNOWLEDGE_MEMORY`（累计 **26**）；新增 `record_knowledge_conversation_action` / `record_knowledge_message_action` / `record_knowledge_memory_action`（actor 真实，无 `record_human_approval`） |
| `agents/enterprise/service.py` | 任务6：在 `EnterpriseOperationLayer.__init__` 装配 4 个新服务，共享 `self.audit` / `self.identity` / `self.knowledge_visibility`，上下文服务与消息服务注入 `self.knowledge_conversations` 以满足访问隔离 |
| `agents/enterprise/__init__.py` | 任务6：新增 3.8.11 import 段与 `__all__` 导出 |
| `tests/agents/test_enterprise_knowledge_conversation_memory.py` | 任务7：7 类共 **15** 个用例 |
| `tests/agents/test_enterprise_knowledge_governance_audit.py` | 同步 `EXPECTED_CATEGORIES` 至 26 + 新增 3 个 record 测试 |
| `tests/agents/test_enterprise_knowledge_intelligence_audit.py` | 同步总数断言 23 → 26 |

---

## 3. 架构与数据流

```
用户(USER)
   │  create(conversation_id, user_id)                 [USER 审计]
   ▼
KnowledgeConversationService  ── org_id 绑定 / 访问隔离(本人|ADMIN)
   │  append(message: USER提问 / AI回答草稿)
   ▼
KnowledgeMessageService
   │  • AI 消息 references 非空（否则 ValueError，禁无来源回答）
   │  • AI 消息 requires_human_review=True 强制
   ▼
KnowledgeConversationContextService.update_context()
   │  • 只暂存 active_topics / referenced_knowledge / unresolved_questions / trace
   │  • filter_visible_references() 按 KnowledgeVisibilityPolicy 过滤「授权知识」(默认拒绝)
   │  • 绝不写知识库
   ▼
MemoryPolicyService (长期记忆候选)
   │  • propose_long_term_memory()  [AI 提议, 默认 AI 审计]
   │  • commit_long_term_memory()   [必须真实 USER, require_human_actor 守卫]
   │  • 候选 requires_human_review=True（AI 不代责）
   ▼
AuditService: KNOWLEDGE_CONVERSATION / KNOWLEDGE_MESSAGE / KNOWLEDGE_MEMORY
   │  • actor_kind 真实（USER 发起记 USER；AI 起草记 AI）
   │  • 无 record_human_approval（绝不伪造人工审批）
   ▼
人工使用（最终采用须经真实 USER；红线⑥）
```

`EnterpriseOperationLayer` 聚合 `knowledge_conversations` / `knowledge_messages` / `knowledge_conversation_context` / `knowledge_memory_policy`，与相关企业层服务共享同一 `audit` / `identity` / `knowledge_visibility` 实例，保证审计与隔离语义一致。

---

## 4. 红线守约核验（fail-closed）

| # | 红线 | 本层落实 | 核验结果 |
| --- | --- | --- | --- |
| ① | 保持 `engineering_enabled=false` | 所有服务构造/写路径断言 `safety_invariants_ok()`；配置保持 `false` | ✅ `load_engineering_enabled()=False` |
| ② | 不输出 `engineering_approved` | 4 个新服务 `_FORBIDDEN` 含 `engineering_approved`；访问该属性抛 `EnterpriseRedLineViolationError` | ✅ 无输出路径 |
| ③ | 禁止 AI 自动修改/合并/发布/应用知识 | 上下文服务 / 记忆服务 `_FORBIDDEN` 含 `auto_update_knowledge` / `auto_merge_knowledge` / `auto_publish_knowledge` / `auto_apply_knowledge` / `commit` / `write` 等 | ✅ 无自动写知识路径 |
| ④ | 禁止 AI 自动学习用户信息写知识库 | `_FORBIDDEN` 含 `auto_learn_user` / `auto_save_user_to_knowledge` / `auto_learn` / `auto_save` | ✅ 无自动学习路径 |
| ⑤ | 无自动工程决策 | 写路径守卫 `safety_invariants_ok()`；无 `generate_engineering_conclusion` / `decide` 等 | ✅ |
| ⑥ | AI 不代替人工责任 | 长期记忆 `commit`/`reject` 必经 `require_human_actor(USER)`；AI 消息 `requires_human_review=True`；审计 actor 真实、无 `record_human_approval` | ✅ |

- **审计枚举数量**：`len(AuditActionCategory) == 26`（3.8.10 为 23，本层 +3）。
- **无 `record_human_approval` 方法**：`"record_human_approval" not in AuditService.__dict__` ✅。
- **组织隔离**：跨域访问抛 `EnterpriseIsolationError`；越权访问抛 `EnterpriseRedLineViolationError`。

---

## 5. 测试结果

- **全量 agents 套件**：`1353 passed`（基线 1335 + 18 新增），0 失败，34.53s。
- **本层新增用例分布（7 类）**：
  - 会话模型：`test_conversation_create_get_list_archive`、`test_conversation_org_isolation`
  - 消息模型：`test_message_user_and_ai_append`、`test_message_ai_requires_references`
  - 会话上下文：`test_conversation_context_update_and_read`、`test_conversation_context_only_session_no_knowledge_write`
  - 记忆策略：`test_memory_propose_requires_human_review`、`test_memory_commit_requires_real_user`、`test_memory_no_auto_save_knowledge`
  - 权限接入（任务6）：`test_permission_cross_user_denied_but_admin_allowed`、`test_memory_candidate_owner_isolation`、`test_context_visible_knowledge_filter_by_role`
  - 会话审计（任务5）：`test_audit_conversation_message_memory_actors`
  - 红线（任务8 验证）：`test_red_line_forbidden_methods_blocked`、`test_safety_invariants_ok_and_no_engineering_approved`
- **审计计数测试修正**：治理审计 `assert len(members)==26` + `EXPECTED_CATEGORIES` 同步；智能审计 `assert len(list(AuditActionCategory))==26`。

---

## 6. 已知限制与待主理人动作

1. **未启用（NO_GO）**：`engineering_enabled=false`，所有真实工程参数 / 尺寸确认 / 报价 / 代签路径保持 fail-closed；激活须经主理人 + 专家线下提交真实证据后由人类终端显式置 `enabled=true`。
2. **本层只承载「会话上下文与记忆候选」**：长期记忆候选 `commit` 后仅纳入本层候选库，**不**回写底层知识库（红线③/④）；如需沉淀为企业知识，须走既有知识治理层（3.8.8）的人类审核发布流程。
3. **可见性策略为检索展示层细化**：`KnowledgeVisibilityPolicy` 与 `IdentityService.check` 互补，不替代真实权限校验。
4. **待主理人审核**：审阅本报告与代码，确认是否进入 Phase 3.8.12。

---

## 7. 状态与下一步

- `agents/config.yaml`：`engineering_enabled = false`（未变更）。
- `AuditActionCategory`：累计 26（3.8.11 +3）。
- `project_status.json`：新增 `phase_3_8_11_status = ENTERPRISE_KNOWLEDGE_CONVERSATION_MEMORY_BUILT_NO_GO`；`phase` 推进至 `3.8.11`（更新见 `roadmap_v8.md` §14）。
- **下一步**：**STOP。不进入 Phase 3.8.12。等待主理人审核。**

---

*报告生成：BOIP AI Chief Architect · 2026-08-06*
