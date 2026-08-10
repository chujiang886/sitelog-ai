"""Phase 3.8.27 企业治理基础设施收敛层 —— 基础设施测试（Task 5）。

本文件是 3.8.27 的**基础设施回归网**，与 3.8.25 的
``test_enterprise_governance_workflow_orchestration.py``（编排语义）互补：那份测
的是「治理流程是否守红线」，这份测的是「承载治理流程的基础设施是否可靠、是否
在收敛过程中改变了任何既有语义」。

五个维度（对应 Task 5 要求）：

===========================  ================================================
维度                         关注点
===========================  ================================================
① Orchestrator 唯一实现      五条 import 路径解析为**同一个类对象**（T1）
② Repository 端口与适配器    端口契约 / 内存 / JSON 文件 / 完整性 / 恢复不变量
③ 权限                       换持久化后访问控制与组织隔离**不被削弱**
④ 审计                       换持久化后审计事件**不缺失**，历史与审计互补
⑤ 迁移兼容                   默认装配与 3.8.25 逐字节等价，旧属性契约不破
===========================  ================================================

红线复核（本层不新增权力，只搬运存储）：
① 全程 ``engineering_enabled=false``；② 不产生 ``engineering_approved``；
③/④ 仓储层在**结构上**不提供自动审批 / 自动执行入口；
⑤ 存储被篡改即拒绝加载，绝不带病提供治理事实；
⑥ 变更历史 append-only，端口无任何改/删历史的方法。

启用态一律通过 monkeypatch ``load_engineering_enabled`` 注入，
**不修改** verified.json / config.yaml / engineering_enabled 任何磁盘文件。
"""

from __future__ import annotations

import importlib
import json

import pytest

from agents.enterprise.agent_permission_policy import AgentPermissionPolicy
from agents.enterprise.audit import (
    AuditActionCategory,
    AuditActorKind,
    AuditService,
)
from agents.enterprise.governance_workflow import (
    GovernanceExecutionRecord,
    GovernanceWorkflow,
    GovernanceWorkflowOrchestrator,
    GovernanceWorkflowReview,
    GovernanceWorkflowSourceType,
    GovernanceWorkflowStatus,
    WorkflowReviewDecision,
)
from agents.enterprise.governance_workflow.repository import (
    InMemoryWorkflowRepository,
    JsonFileWorkflowRepository,
    WorkflowHistoryEntry,
    WorkflowHistoryEvent,
    WorkflowRepository,
    WorkflowRepositoryError,
    WorkflowStoreIntegrityError,
    _REPOSITORY_FORBIDDEN,
    _restore_workflow,
)
from agents.enterprise.identity import IdentityService, RoleKind
from agents.enterprise.organization import EnterpriseIsolationError
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


# ---------------------------------------------------------------------------
# 共享夹具与构造器
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _force_disabled(monkeypatch) -> None:
    """确保测试全程 engineering_enabled=false（红线①），不触碰磁盘配置。"""
    monkeypatch.setattr(
        "agents.enterprise.red_line.load_engineering_enabled", lambda: False
    )


def _forbidden_access(obj: object, name: str) -> bool:
    """访问 ``obj.name`` 是否被红线结构性拦截。

    ``hasattr`` 只吞 ``AttributeError``，而禁名会抛
    ``EnterpriseRedLineViolationError``，因此不能用 ``hasattr`` 判定。
    """
    try:
        getattr(obj, name)
    except EnterpriseRedLineViolationError:
        return True
    except AttributeError:
        return False
    return False


def _audit(org_id: str = "org-1") -> AuditService:
    return AuditService(org_id=org_id)


def _identity(org_id: str = "org-1") -> IdentityService:
    return IdentityService(org_id=org_id)


def _policy(org_id: str = "org-1") -> AgentPermissionPolicy:
    return AgentPermissionPolicy(org_id=org_id, identity=_identity(org_id))


def _reviewer(org_id: str = "org-1"):
    return _identity(org_id).make_user(
        user_id="rev", name="R", role_kind=RoleKind.REVIEWER
    )


def _admin(org_id: str = "org-1"):
    """在 ``data`` 资源类别上被放行的角色（与 3.8.25 权限口径一致）。"""
    return _identity(org_id).make_user(
        user_id="zhuguan", name="Z", role_kind=RoleKind.ADMIN
    )


def _orch(
    *,
    org_id: str = "org-1",
    audit=None,
    permission_policy=None,
    repository=None,
) -> GovernanceWorkflowOrchestrator:
    return GovernanceWorkflowOrchestrator(
        org_id=org_id,
        audit=audit,
        permission_policy=permission_policy,
        repository=repository,
    )


def _seed(
    orch: GovernanceWorkflowOrchestrator,
    workflow_id: str = "wf-1",
    source_id: str = "gt-1",
) -> GovernanceWorkflow:
    """登记一条 CREATED 候选工作流（AI 可发起，只落候选态）。"""
    return orch.create_workflow(
        workflow_id=workflow_id,
        source_type=GovernanceWorkflowSourceType.GOVERNANCE_TASK,
        source_id=source_id,
        title="治理线索候选",
        description="一条来自治理任务的待研判线索",
        source_facts=["事实1：x 指标异常", "事实2：y 偏离基线"],
        created_at="2026-08-09T10:00:00Z",
    )


def _drive_to_confirmed(
    orch: GovernanceWorkflowOrchestrator, workflow_id: str = "wf-1"
) -> GovernanceWorkflowReview:
    """把工作流经真实人工推进到 human_confirmed 态。"""
    orch.submit_for_review(workflow_id=workflow_id, timestamp="2026-08-09T10:01:00Z")
    return orch.human_confirm(
        workflow_id=workflow_id,
        reason="人工复核事实成立，进入治理执行",
        reviewer_id="rev",
        reviewer_kind=AuditActorKind.USER,
        decision=WorkflowReviewDecision.CONFIRMED,
        review_id="gwr-1",
        reviewed_at="2026-08-09T10:02:00Z",
    )


def _make_workflow_payload(**overrides) -> dict:
    """构造一份「合法可恢复」的工作流载荷，供恢复期不变量测试逐项破坏。"""
    payload = {
        "workflow_id": "wf-restore",
        "source_type": GovernanceWorkflowSourceType.GOVERNANCE_TASK.value,
        "source_id": "gt-restore",
        "status": GovernanceWorkflowStatus.CREATED.value,
        "org_id": "org-1",
        "title": "恢复用例",
        "description": "从磁盘恢复的治理工作流",
        "source_facts": ["事实：指标异常"],
        "references": [],
        "created_at": "2026-08-09T09:00:00Z",
        "created_by": "ai",
        "confirmed_by": "",
        "confirmed_at": "",
        "completed_by": "",
        "completed_at": "",
        "archived": False,
        "archived_by": "",
        "archived_at": "",
        "draft_id": "",
        "task_id": "",
        "human_notes": [],
        "requires_human_confirmation": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 维度①：Orchestrator 唯一实现（Task 1 的回归网）
# ---------------------------------------------------------------------------

class TestOrchestratorSingleImplementation:
    """3.8.25 曾在 ``orchestrator.py`` 与 ``service.py`` 各写一份同名类，
    导致 ``isinstance`` / ``except`` 在不同 import 路径上行为不一致。
    这组测试把「唯一实现」钉成可回归的断言，防止未来任何人再分叉一份。
    """

    #: 历史上出现过的全部 import 路径（合并后必须全部指向同一个类对象）。
    _IMPORT_PATHS = (
        "agents.enterprise.governance_workflow",
        "agents.enterprise.governance_workflow.orchestrator",
        "agents.enterprise.governance_workflow.service",
    )

    def test_all_import_paths_resolve_to_same_class_object(self) -> None:
        classes = [
            getattr(importlib.import_module(path), "GovernanceWorkflowOrchestrator")
            for path in self._IMPORT_PATHS
        ]
        first = classes[0]
        for path, cls in zip(self._IMPORT_PATHS, classes):
            # 用 `is` 而不是 `==`：两份不同的类对象也可能名字相同、字段相同，
            # 只有对象同一性才能证明「合并成一份」。
            assert cls is first, f"{path} 解析出了不同的类对象（双实现回潮）"

    def test_access_denied_exception_is_also_unique(self) -> None:
        """异常类同样必须唯一 —— 否则 ``except`` 分支会静默漏捕。"""
        from agents.enterprise.governance_workflow import orchestrator as orch_mod
        from agents.enterprise.governance_workflow import service as svc_mod

        assert (
            svc_mod.GovernanceWorkflowAccessDenied
            is orch_mod.GovernanceWorkflowAccessDenied
        )

    def test_service_module_is_a_pure_shim(self) -> None:
        """``service.py`` 降级为再导出垫片：**不得**含任何类/函数定义。"""
        from agents.enterprise.governance_workflow import service as svc_mod

        source = importlib.util.find_spec(svc_mod.__name__).origin
        assert source is not None
        text = open(source, encoding="utf-8").read()
        for marker in ("\nclass ", "\ndef ", "\n    def "):
            assert marker not in text, (
                f"service.py 中出现 {marker.strip()!r} 定义：垫片必须零实现，"
                f"否则双实现会再次分叉"
            )

    def test_instance_from_shim_path_is_instance_of_canonical_class(self) -> None:
        from agents.enterprise.governance_workflow import orchestrator as orch_mod
        from agents.enterprise.governance_workflow import service as svc_mod

        inst = svc_mod.GovernanceWorkflowOrchestrator(org_id="org-1")
        assert isinstance(inst, orch_mod.GovernanceWorkflowOrchestrator)

    def test_orchestrator_exposes_repository_port(self) -> None:
        orch = _orch()
        assert isinstance(orch.repository, WorkflowRepository)
        # 不传 repository 时默认落到内存适配器（迁移兼容的前提）。
        assert isinstance(orch.repository, InMemoryWorkflowRepository)


# ---------------------------------------------------------------------------
# 维度②-A：Repository 端口契约
# ---------------------------------------------------------------------------

class TestRepositoryPortContract:
    def test_port_is_abstract_and_cannot_be_instantiated(self) -> None:
        with pytest.raises(TypeError):
            WorkflowRepository()  # type: ignore[abstract]

    def test_port_declares_crud_and_history_capabilities(self) -> None:
        for name in (
            "put_workflow",
            "get_workflow",
            "has_workflow",
            "list_workflows",
            "put_review",
            "get_review",
            "has_review",
            "list_reviews",
            "put_execution",
            "get_execution",
            "has_execution",
            "list_executions",
            "put_archived",
            "list_archived",
            "append_history",
            "list_history",
        ):
            assert hasattr(WorkflowRepository, name), f"端口缺少能力 {name}"

    def test_port_has_no_delete_or_history_mutation_method(self) -> None:
        """红线⑥：治理事实与留痕在**结构上**不可删改。"""
        for name in (
            "delete_workflow",
            "remove_workflow",
            "delete_review",
            "delete_execution",
            "delete_history",
            "update_history",
            "purge_history",
            "clear_all",
        ):
            assert name not in vars(WorkflowRepository), (
                f"端口暴露了 {name}：治理留痕必须 append-only"
            )

    def test_forbidden_names_are_structurally_blocked(self) -> None:
        """红线③/④/⑥：禁名不仅「没实现」，而且访问即抛错。"""
        repo = InMemoryWorkflowRepository()
        for name in _REPOSITORY_FORBIDDEN:
            assert _forbidden_access(repo, name), f"禁名 {name} 未被结构性拦截"

    def test_forbidden_list_covers_auto_and_erase_families(self) -> None:
        for name in (
            "auto_approve",
            "auto_confirm",
            "auto_execute",
            "auto_close_workflow",
            "bypass_human_review",
            "force_status",
            "delete_workflow",
            "purge_history",
            "rewrite_history",
        ):
            assert name in _REPOSITORY_FORBIDDEN, f"禁名清单遗漏 {name}"

    def test_constructing_repository_rejected_when_enabled(self, monkeypatch) -> None:
        """红线①：启用态下连仓储都不许构造。"""
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        assert safety_invariants_ok() is False
        with pytest.raises(EnterpriseRedLineViolationError):
            InMemoryWorkflowRepository()


# ---------------------------------------------------------------------------
# 维度②-B：内存适配器（默认实现）
# ---------------------------------------------------------------------------

class TestInMemoryRepository:
    def test_put_and_get_workflow_round_trip(self) -> None:
        repo = InMemoryWorkflowRepository()
        wf = GovernanceWorkflow(
            workflow_id="wf-a",
            source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
            source_id="src-a",
            org_id="org-1",
            title="线索 A",
        )
        repo.put_workflow(wf, event=WorkflowHistoryEvent.CREATED, actor_id="ai")
        assert repo.has_workflow("wf-a") is True
        assert repo.get_workflow("wf-a") is wf
        assert repo.get_workflow("  wf-a  ") is wf  # id 规范化
        assert repo.get_workflow("wf-missing") is None
        assert repo.has_workflow("wf-missing") is False

    def test_list_workflows_filters_by_org_and_status(self) -> None:
        repo = InMemoryWorkflowRepository()
        for wid, org in (("wf-1", "org-1"), ("wf-2", "org-2")):
            repo.put_workflow(
                GovernanceWorkflow(
                    workflow_id=wid,
                    source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                    source_id=f"src-{wid}",
                    org_id=org,
                ),
                event=WorkflowHistoryEvent.CREATED,
            )
        assert len(repo.list_workflows()) == 2
        assert [w.workflow_id for w in repo.list_workflows(org_id="org-2")] == ["wf-2"]
        assert (
            len(repo.list_workflows(status=GovernanceWorkflowStatus.CREATED)) == 2
        )
        assert repo.list_workflows(status=GovernanceWorkflowStatus.COMPLETED) == []

    def test_put_workflow_always_leaves_history(self) -> None:
        """红线⑥：接口设计上「写事实却不留痕」写不出来（event 是必填 kw）。"""
        repo = InMemoryWorkflowRepository()
        wf = GovernanceWorkflow(
            workflow_id="wf-h",
            source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
            source_id="src-h",
            org_id="org-1",
        )
        with pytest.raises(TypeError):
            repo.put_workflow(wf)  # type: ignore[call-arg]
        repo.put_workflow(wf, event=WorkflowHistoryEvent.CREATED)
        assert len(repo.list_history(workflow_id="wf-h")) == 1

    def test_execution_bucket_keeps_order_and_dedupes_index(self) -> None:
        repo = InMemoryWorkflowRepository()
        for rid in ("ex-1", "ex-2", "ex-3"):
            repo.put_execution(
                GovernanceExecutionRecord(
                    record_id=rid,
                    workflow_id="wf-e",
                    action="人工执行治理动作",
                    actor="rev",
                    actor_kind="user",
                    source="workflow:wf-e",
                )
            )
        assert [r.record_id for r in repo.list_executions(workflow_id="wf-e")] == [
            "ex-1",
            "ex-2",
            "ex-3",
        ]
        # 同 id 重复登记按 upsert 处理，桶内不重复追加。
        repo.put_execution(
            GovernanceExecutionRecord(
                record_id="ex-2",
                workflow_id="wf-e",
                action="人工执行治理动作（更新）",
                actor="rev",
                actor_kind="user",
                source="workflow:wf-e",
            )
        )
        assert len(repo.list_executions(workflow_id="wf-e")) == 3
        assert repo.get_execution("ex-2").action.endswith("（更新）")

    def test_archive_does_not_delete_original_record(self) -> None:
        """归档是**增加封存索引**，不是删除（红线⑥）。"""
        repo = InMemoryWorkflowRepository()
        wf = GovernanceWorkflow(
            workflow_id="wf-arc",
            source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
            source_id="src-arc",
            org_id="org-1",
        )
        repo.put_workflow(wf, event=WorkflowHistoryEvent.CREATED)
        repo.put_archived(wf, actor_id="rev", actor_kind="user")
        assert repo.has_workflow("wf-arc") is True
        assert [w.workflow_id for w in repo.list_archived()] == ["wf-arc"]

    def test_raw_dict_views_are_live(self) -> None:
        """向后兼容视图必须是**同一个字典对象**，而不是拷贝。"""
        repo = InMemoryWorkflowRepository()
        assert repo.workflows is repo._workflows
        assert repo.reviews is repo._reviews
        assert repo.executions is repo._executions
        assert repo.execution_index is repo._execution_index
        assert repo.archived is repo._archived


# ---------------------------------------------------------------------------
# 维度②-C：变更历史 append-only（红线⑥）
# ---------------------------------------------------------------------------

class TestAppendOnlyHistory:
    def test_history_event_enum_has_no_auto_members(self) -> None:
        """红线③/④：AI 自动推进的历史事件在**类型层面**不可表达。

        成员名从枚举自身派生（不手抄），避免形近污染。
        """
        names = set(WorkflowHistoryEvent.__members__)
        for banned in ("AUTO_APPROVED", "AUTO_CLOSED", "AUTO_EXECUTED", "AI_CONFIRMED"):
            assert banned not in names
        assert not any(n.startswith("AUTO_") for n in names)
        assert not any("AI_" in n for n in names)

    def test_history_entry_is_frozen(self) -> None:
        entry = WorkflowHistoryEntry(
            entry_id="wfh-1", workflow_id="wf-1", event=WorkflowHistoryEvent.CREATED
        )
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            entry.event = WorkflowHistoryEvent.COMPLETED  # type: ignore[misc]

    def test_history_entry_requires_identity_and_workflow(self) -> None:
        with pytest.raises(EnterpriseRedLineViolationError):
            WorkflowHistoryEntry(entry_id="", workflow_id="wf-1")
        with pytest.raises(EnterpriseRedLineViolationError):
            WorkflowHistoryEntry(entry_id="wfh-1", workflow_id="")

    def test_history_entry_detail_passes_semantic_scan(self) -> None:
        """红线③：即便有人往留痕里塞「自动审批」措辞，构造期就被拒。"""
        with pytest.raises(EnterpriseRedLineViolationError):
            WorkflowHistoryEntry(
                entry_id="wfh-x",
                workflow_id="wf-1",
                detail="系统已自动审批该治理工作流",
            )

    def test_history_only_grows(self) -> None:
        repo = InMemoryWorkflowRepository()
        wf = GovernanceWorkflow(
            workflow_id="wf-g",
            source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
            source_id="src-g",
            org_id="org-1",
        )
        counts = []
        for event in (
            WorkflowHistoryEvent.CREATED,
            WorkflowHistoryEvent.SUBMITTED_FOR_REVIEW,
            WorkflowHistoryEvent.NOTE_APPENDED,
        ):
            repo.put_workflow(wf, event=event)
            counts.append(len(repo.list_history()))
        assert counts == [1, 2, 3]
        # 同一条工作流被反复 upsert，历史条数只增不减。
        assert all(b > a for a, b in zip(counts, counts[1:]))

    def test_adapters_expose_no_history_mutation_api(self) -> None:
        repo = InMemoryWorkflowRepository()
        for name in ("update_history", "delete_history", "purge_history", "clear_all"):
            assert _forbidden_access(repo, name)

    def test_history_returned_list_is_a_copy(self) -> None:
        """外部拿到的历史列表被改动不得污染仓储内部留痕。"""
        repo = InMemoryWorkflowRepository()
        repo.append_history(
            WorkflowHistoryEntry(entry_id="wfh-1", workflow_id="wf-c")
        )
        got = repo.list_history()
        got.clear()
        assert len(repo.list_history()) == 1


# ---------------------------------------------------------------------------
# 维度②-D：JSON 文件适配器（持久化 / 原子写 / 完整性）
# ---------------------------------------------------------------------------

class TestJsonFilePersistence:
    def test_round_trip_across_instances(self, tmp_path) -> None:
        """核心价值验证：进程重启后治理责任事实**不蒸发**。"""
        store = tmp_path / "governance.json"
        repo = JsonFileWorkflowRepository(store)
        orch = _orch(repository=repo)
        _seed(orch, "wf-1")
        _drive_to_confirmed(orch, "wf-1")

        assert store.exists()

        repo2 = JsonFileWorkflowRepository(store)
        wf = repo2.get_workflow("wf-1")
        assert wf is not None
        assert wf.status is GovernanceWorkflowStatus.HUMAN_CONFIRMED
        assert wf.confirmed_by == "rev"
        assert repo2.has_review("gwr-1") is True
        assert repo2.get_review("gwr-1").decision is WorkflowReviewDecision.CONFIRMED
        # 历史一并恢复，生命周期可回放。
        events = [e.event for e in repo2.list_history(workflow_id="wf-1")]
        assert WorkflowHistoryEvent.CREATED in events
        assert WorkflowHistoryEvent.SUBMITTED_FOR_REVIEW in events
        assert WorkflowHistoryEvent.HUMAN_CONFIRMED in events

    def test_snapshot_has_version_and_per_record_digest(self, tmp_path) -> None:
        repo = JsonFileWorkflowRepository(tmp_path / "s.json")
        _seed(_orch(repository=repo), "wf-1")
        doc = json.loads((tmp_path / "s.json").read_text(encoding="utf-8"))
        assert doc["version"] == 1
        assert doc["workflows"] and "digest" in doc["workflows"][0]
        assert doc["history"] and "digest" in doc["history"][0]

    def test_atomic_write_leaves_no_temp_file(self, tmp_path) -> None:
        repo = JsonFileWorkflowRepository(tmp_path / "s.json")
        orch = _orch(repository=repo)
        _seed(orch, "wf-1")
        _drive_to_confirmed(orch, "wf-1")
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != "s.json"]
        assert leftovers == [], f"原子写留下了残留文件：{leftovers}"

    def test_empty_and_missing_file_are_tolerated(self, tmp_path) -> None:
        missing = tmp_path / "nope.json"
        assert JsonFileWorkflowRepository(missing).list_workflows() == []
        empty = tmp_path / "empty.json"
        empty.write_text("   \n", encoding="utf-8")
        assert JsonFileWorkflowRepository(empty).list_workflows() == []

    def test_execution_order_survives_reload(self, tmp_path) -> None:
        store = tmp_path / "s.json"
        repo = JsonFileWorkflowRepository(store)
        for rid in ("ex-1", "ex-2", "ex-3"):
            repo.put_execution(
                GovernanceExecutionRecord(
                    record_id=rid,
                    workflow_id="wf-e",
                    action="人工执行治理动作",
                    actor="rev",
                    actor_kind="user",
                    source="workflow:wf-e",
                )
            )
        reloaded = JsonFileWorkflowRepository(store)
        assert [
            r.record_id for r in reloaded.list_executions(workflow_id="wf-e")
        ] == ["ex-1", "ex-2", "ex-3"]

    def test_entry_id_does_not_collide_after_reload(self, tmp_path) -> None:
        """恢复后序号游标须推进，否则新历史会与旧历史撞号。"""
        store = tmp_path / "s.json"
        _seed(_orch(repository=JsonFileWorkflowRepository(store)), "wf-1")
        repo2 = JsonFileWorkflowRepository(store)
        before = {e.entry_id for e in repo2.list_history()}
        repo2.append_history(
            WorkflowHistoryEntry(
                entry_id=repo2._next_entry_id("wf-1"), workflow_id="wf-1"
            )
        )
        after = [e.entry_id for e in repo2.list_history()]
        assert len(set(after)) == len(after), "恢复后 entry_id 撞号"
        assert set(after) - before


class TestStoreIntegrity:
    """红线⑤：绝不带病加载治理事实。"""

    def _seeded_store(self, tmp_path):
        store = tmp_path / "s.json"
        _seed(_orch(repository=JsonFileWorkflowRepository(store)), "wf-1")
        return store

    def test_tampered_payload_is_rejected(self, tmp_path) -> None:
        store = self._seeded_store(tmp_path)
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["workflows"][0]["payload"]["title"] = "被改过的标题"  # 摘要不再匹配
        store.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(WorkflowStoreIntegrityError):
            JsonFileWorkflowRepository(store)

    def test_integrity_error_is_also_a_red_line_error(self, tmp_path) -> None:
        """既有的红线捕获契约对「存储被篡改」同样成立，无需新增捕获点。"""
        store = self._seeded_store(tmp_path)
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["workflows"][0]["digest"] = "0" * 64
        store.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(EnterpriseRedLineViolationError):
            JsonFileWorkflowRepository(store)

    def test_truncated_json_is_rejected(self, tmp_path) -> None:
        store = self._seeded_store(tmp_path)
        raw = store.read_text(encoding="utf-8")
        store.write_text(raw[: len(raw) // 2], encoding="utf-8")
        with pytest.raises(WorkflowStoreIntegrityError):
            JsonFileWorkflowRepository(store)

    def test_unknown_version_is_rejected(self, tmp_path) -> None:
        store = self._seeded_store(tmp_path)
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["version"] = 99
        store.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(WorkflowStoreIntegrityError):
            JsonFileWorkflowRepository(store)

    def test_non_object_top_level_is_rejected(self, tmp_path) -> None:
        store = tmp_path / "s.json"
        store.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(WorkflowStoreIntegrityError):
            JsonFileWorkflowRepository(store)

    def test_unknown_field_in_payload_is_rejected(self, tmp_path) -> None:
        """来路不明的字段一律拒收（避免未来格式被悄悄注入语义）。"""
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(_make_workflow_payload(shadow_flag=True))

    def test_dangling_archive_index_is_rejected(self, tmp_path) -> None:
        store = self._seeded_store(tmp_path)
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["archived"] = ["wf-does-not-exist"]
        store.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        with pytest.raises(WorkflowStoreIntegrityError):
            JsonFileWorkflowRepository(store)

    def test_non_strict_mode_collects_errors_for_forensics(self, tmp_path) -> None:
        """``strict=False`` 只供离线取证：跳过坏记录并留下可追溯的原因。"""
        store = self._seeded_store(tmp_path)
        doc = json.loads(store.read_text(encoding="utf-8"))
        doc["workflows"][0]["digest"] = "0" * 64
        store.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        repo = JsonFileWorkflowRepository(store, strict=False)
        assert repo.get_workflow("wf-1") is None
        assert repo.load_errors, "非严格模式必须登记被跳过的坏记录"
        assert repo.load_errors[0][0] == "workflow"

    def test_default_mode_is_strict(self, tmp_path) -> None:
        repo = JsonFileWorkflowRepository(tmp_path / "s.json")
        assert repo._strict is True

    def test_unreadable_path_raises_repository_error(self, tmp_path) -> None:
        """目录冒充存储文件：读失败必须是明确的仓储异常，不是裸 OSError。"""
        bogus = tmp_path / "as_dir.json"
        bogus.mkdir()
        with pytest.raises(WorkflowRepositoryError):
            JsonFileWorkflowRepository(bogus)


class TestRestoreInvariants:
    """恢复期不变量 —— 不是放宽创建期守卫，而是换一组同样 fail-closed 的检查。"""

    def test_legitimate_payload_restores(self) -> None:
        wf = _restore_workflow(_make_workflow_payload())
        assert wf.workflow_id == "wf-restore"
        assert wf.status is GovernanceWorkflowStatus.CREATED
        assert wf.requires_human_confirmation is True

    def test_confirmed_workflow_restores_with_human_fact(self) -> None:
        """一条昨天被真人确认过的工作流，今天必须能带着确认事实读回来。"""
        wf = _restore_workflow(
            _make_workflow_payload(
                status=GovernanceWorkflowStatus.HUMAN_CONFIRMED.value,
                confirmed_by="rev",
                confirmed_at="2026-08-09T10:02:00Z",
            )
        )
        assert wf.status is GovernanceWorkflowStatus.HUMAN_CONFIRMED
        assert wf.confirmed_by == "rev"

    def test_missing_identity_fields_rejected(self) -> None:
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(_make_workflow_payload(workflow_id=""))
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(_make_workflow_payload(source_id=""))

    def test_requires_human_confirmation_cannot_be_flipped_by_storage(self) -> None:
        """红线⑥：存储层不得改写「必须人工确认」这一标志。"""
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(
                _make_workflow_payload(requires_human_confirmation=False)
            )

    def test_forged_confirmation_at_low_status_rejected(self) -> None:
        """红线③/⑥：created 态却带 confirmed_by = 伪造人工确认事实。"""
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(_make_workflow_payload(confirmed_by="rev"))

    def test_advanced_status_without_confirmation_rejected(self) -> None:
        """反向：已推进却无研判人 = 治理链断裂。"""
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(
                _make_workflow_payload(
                    status=GovernanceWorkflowStatus.IN_PROGRESS.value
                )
            )

    def test_completed_without_completed_by_rejected(self) -> None:
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(
                _make_workflow_payload(
                    status=GovernanceWorkflowStatus.COMPLETED.value,
                    confirmed_by="rev",
                    completed_by="",
                )
            )

    def test_archived_without_archiver_rejected(self) -> None:
        with pytest.raises(WorkflowStoreIntegrityError):
            _restore_workflow(
                _make_workflow_payload(
                    status=GovernanceWorkflowStatus.COMPLETED.value,
                    confirmed_by="rev",
                    completed_by="rev",
                    archived=True,
                    archived_by="",
                )
            )

    def test_semantic_markers_rejected_at_load_time(self) -> None:
        """红线③：手改 JSON 塞进「自动审批通过」，加载期即被拦下。"""
        with pytest.raises(EnterpriseRedLineViolationError):
            _restore_workflow(_make_workflow_payload(title="自动审批通过的治理事项"))
        with pytest.raises(EnterpriseRedLineViolationError):
            _restore_workflow(
                _make_workflow_payload(human_notes=["系统已自动执行整改"])
            )

    def test_restore_rejected_when_enabled(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "agents.enterprise.red_line.load_engineering_enabled", lambda: True
        )
        with pytest.raises(EnterpriseRedLineViolationError):
            _restore_workflow(_make_workflow_payload())


# ---------------------------------------------------------------------------
# 维度③：权限与隔离在换持久化后不被削弱
# ---------------------------------------------------------------------------

class TestPermissionUnchangedAfterPersistence:
    """基础设施收敛**不得**顺带放宽访问控制（取严不取宽）。"""

    def test_access_denied_before_touching_storage(self, tmp_path) -> None:
        """无权用户在读到任何治理事实**之前**就被拒。"""
        from agents.enterprise.governance_workflow import (
            GovernanceWorkflowAccessDenied,
        )

        store = tmp_path / "s.json"
        repo = JsonFileWorkflowRepository(store)
        orch = _orch(repository=repo, permission_policy=_policy())
        _seed(orch, "wf-1")

        class _Outsider:
            role = None

        with pytest.raises(GovernanceWorkflowAccessDenied):
            orch.list_workflows(user=_Outsider())

    def test_cross_org_isolation_still_enforced_with_file_store(
        self, tmp_path
    ) -> None:
        """跨组织隔离与存储介质无关：换成文件仓储照样拒绝。"""
        store = tmp_path / "s.json"
        repo = JsonFileWorkflowRepository(store)
        _seed(_orch(org_id="org-1", repository=repo), "wf-1")

        # 另一个组织的编排器共用同一份存储文件也读不到别人的治理事实。
        other = _orch(org_id="org-2", repository=JsonFileWorkflowRepository(store))
        with pytest.raises(EnterpriseIsolationError):
            other.get_workflow("wf-1")

    def test_history_readonly_and_access_checked(self, tmp_path) -> None:
        """``history()`` 是只读回放接口，同样走访问校验。"""
        from agents.enterprise.governance_workflow import (
            GovernanceWorkflowAccessDenied,
        )

        orch = _orch(
            repository=JsonFileWorkflowRepository(tmp_path / "s.json"),
            permission_policy=_policy(),
        )
        _seed(orch, "wf-1")

        class _Outsider:
            role = None

        with pytest.raises(GovernanceWorkflowAccessDenied):
            orch.history(workflow_id="wf-1", user=_Outsider())
        # ``data`` 类别上 REVIEWER 角色本就被拒（3.8.25 既有口径，不放宽）
        with pytest.raises(EnterpriseIsolationError):
            orch.history(workflow_id="wf-1", user=_reviewer())
        # 有权角色可读，且拿到的是留痕列表
        assert orch.history(workflow_id="wf-1", user=_admin())

    def test_repository_does_not_reimplement_human_guard(self, tmp_path) -> None:
        """红线⑥：人工身份判定只在编排器/模型，仓储不重复也不放宽。

        仓储可以忠实存下调用方给它的对象，但 AI 依然无法经**编排器**推进 ——
        守卫的位置没变，权力也就没变。
        """
        orch = _orch(repository=JsonFileWorkflowRepository(tmp_path / "s.json"))
        _seed(orch, "wf-1")
        orch.submit_for_review(workflow_id="wf-1")
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.human_confirm(
                workflow_id="wf-1",
                reason="AI 试图自行研判",
                reviewer_id="ai",
                reviewer_kind=AuditActorKind.AI,
            )
        # 状态未被推进，磁盘上也不会出现被伪造的确认事实。
        assert (
            orch.repository.get_workflow("wf-1").status
            is GovernanceWorkflowStatus.UNDER_REVIEW
        )


# ---------------------------------------------------------------------------
# 维度④：审计事件在换持久化后不缺失（历史与审计互补）
# ---------------------------------------------------------------------------

class TestAuditPreservedAfterPersistence:
    def _categories(self, audit: AuditService):
        return [r.category for r in audit._records]

    def test_audit_events_written_with_file_repository(self, tmp_path) -> None:
        audit = _audit()
        orch = _orch(
            audit=audit, repository=JsonFileWorkflowRepository(tmp_path / "s.json")
        )
        _seed(orch, "wf-1")
        _drive_to_confirmed(orch, "wf-1")
        cats = self._categories(audit)
        assert AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_CREATE in cats
        assert AuditActionCategory.AGENT_GOVERNANCE_WORKFLOW_REVIEW in cats

    def test_audit_count_identical_across_repositories(self, tmp_path) -> None:
        """同一串治理动作，内存仓储与文件仓储产生**完全相同**的审计事件。"""
        mem_audit, file_audit = _audit(), _audit()
        mem = _orch(audit=mem_audit, repository=InMemoryWorkflowRepository())
        fil = _orch(
            audit=file_audit,
            repository=JsonFileWorkflowRepository(tmp_path / "s.json"),
        )
        for orch in (mem, fil):
            _seed(orch, "wf-1")
            _drive_to_confirmed(orch, "wf-1")
        assert self._categories(mem_audit) == self._categories(file_audit)

    def test_history_supplements_audit_not_replaces_it(self, tmp_path) -> None:
        """历史面向单条工作流回放，审计面向全局合规 —— 两者都写，缺一不可。"""
        audit = _audit()
        orch = _orch(
            audit=audit, repository=JsonFileWorkflowRepository(tmp_path / "s.json")
        )
        _seed(orch, "wf-1")
        _drive_to_confirmed(orch, "wf-1")
        assert len(audit._records) > 0
        assert len(orch.history(workflow_id="wf-1")) > 0

    def test_no_engineering_approved_in_any_persisted_byte(self, tmp_path) -> None:
        """红线②：落盘产物中不得出现 ``engineering_approved`` 字样。"""
        store = tmp_path / "s.json"
        orch = _orch(repository=JsonFileWorkflowRepository(store))
        _seed(orch, "wf-1")
        _drive_to_confirmed(orch, "wf-1")
        raw = store.read_text(encoding="utf-8")
        assert "engineering_approved" not in raw
        assert "engineering_enabled" not in raw


# ---------------------------------------------------------------------------
# 维度⑤：迁移兼容（默认装配与 3.8.25 等价，旧契约不破）
# ---------------------------------------------------------------------------

class TestMigrationCompatibility:
    def test_default_construction_needs_no_repository_argument(self) -> None:
        """既有全部调用方**零改动**：不传 repository 依然工作。"""
        orch = GovernanceWorkflowOrchestrator(org_id="org-1")
        wf = _seed(orch, "wf-1")
        assert orch.get_workflow("wf-1") is wf

    def test_positional_org_id_still_accepted(self) -> None:
        """合并前两份实现签名不同，收敛后位置参数仍须兼容。"""
        orch = GovernanceWorkflowOrchestrator("org-1")
        assert _seed(orch, "wf-1").org_id == "org-1"

    def test_legacy_private_dict_attributes_still_dicts(self) -> None:
        orch = _orch()
        for attr in (
            "_workflows",
            "_reviews",
            "_executions",
            "_execution_index",
            "_archived",
        ):
            assert isinstance(getattr(orch, attr), dict), f"{attr} 不再是 dict"

    def test_legacy_direct_dict_write_still_visible(self) -> None:
        """3.8.25 既有测试会直接写 ``orch._workflows[...]``，该契约必须保留。"""
        orch = _orch()
        wf = GovernanceWorkflow(
            workflow_id="wf-legacy",
            source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
            source_id="src-legacy",
            org_id="org-1",
        )
        orch._workflows["wf-legacy"] = wf
        assert orch.get_workflow("wf-legacy") is wf
        assert orch.repository.has_workflow("wf-legacy") is True

    def test_dict_views_are_shared_with_repository(self) -> None:
        orch = _orch()
        assert orch._workflows is orch.repository.workflows
        assert orch._reviews is orch.repository.reviews
        assert orch._executions is orch.repository.executions
        assert orch._execution_index is orch.repository.execution_index
        assert orch._archived is orch.repository.archived

    def test_full_lifecycle_equivalent_between_adapters(self, tmp_path) -> None:
        """同一串动作在两种适配器上得到**相同的可观察结果**。"""
        results = []
        for repo in (
            InMemoryWorkflowRepository(),
            JsonFileWorkflowRepository(tmp_path / "s.json"),
        ):
            orch = _orch(repository=repo)
            _seed(orch, "wf-1")
            _drive_to_confirmed(orch, "wf-1")
            orch.start_execution(
                workflow_id="wf-1",
                actor_kind=AuditActorKind.USER,
                actor_id="rev",
                record_id="ex-1",
                source="workflow:wf-1",
            )
            wf = orch.get_workflow("wf-1")
            results.append(
                (
                    wf.status,
                    wf.confirmed_by,
                    len(orch.list_reviews(workflow_id="wf-1")),
                    len(orch.list_execution_records(workflow_id="wf-1")),
                    [e.event for e in orch.history(workflow_id="wf-1")],
                )
            )
        assert results[0] == results[1]

    def test_duplicate_workflow_id_rejected_on_both_entry_points(self) -> None:
        """红线⑥：``create_workflow`` 与 ``register_candidate`` 都不得覆盖既有事实。

        合并前 ``service.register_candidate`` 与 ``orchestrator.create_workflow``
        对「重复 id」的处置不一致，是双实现最危险的表现之一：同一个 id 在一条
        路径上被拒、在另一条路径上被**静默覆盖**。收敛后两个入口共用同一份守卫，
        本用例把这一点钉死 —— 未来若有人为了让某个夹具跑通而拆掉这道守卫，
        这里会立刻变红。
        """
        orch = _orch()
        _seed(orch, "wf-dup")
        with pytest.raises(EnterpriseRedLineViolationError):
            _seed(orch, "wf-dup")
        with pytest.raises(EnterpriseRedLineViolationError):
            orch.register_candidate(
                workflow_id="wf-dup",
                source_type=GovernanceWorkflowSourceType.HUMAN_REPORTED,
                source_id="other-src",
                title="试图覆盖既有治理事实",
            )
        # 原始事实完好，未被后来者改写。
        assert orch.get_workflow("wf-dup").source_id == "gt-1"

    def test_audit_category_contract_intact(self) -> None:
        """基础设施收敛不得**丢失**任何既有治理审计语义。

        Phase 3.8.31 Task 9：原断言硬编码总数（69 → 72 时被迫连带修改十余处
        历史测试），属结构性脆性；改为「治理审计族存在性契约」——它才是本层
        真正要守的东西（收敛不许丢语义）。审计大类**总数**的唯一权威断言保留
        在 ``tests/agents/test_enterprise_knowledge_governance_audit.py``
        （``EXPECTED_CATEGORIES`` 全量成员名集合 + 总数）。
        """
        names = set(AuditActionCategory.__members__)
        assert {
            # Phase 3.8.21 治理任务 / 行动 / 收口
            "AGENT_GOVERNANCE_TASK",
            "AGENT_GOVERNANCE_ACTION",
            "AGENT_GOVERNANCE_CLOSURE",
            # Phase 3.8.26 治理工作流查看（只读事实）
            "AGENT_GOVERNANCE_WORKFLOW_VIEW",
            # Phase 3.8.30 治理全链路追踪 / 时间线 / 重放（只读事实）
            "GOVERNANCE_TRACE",
            "GOVERNANCE_TIMELINE",
            "GOVERNANCE_REPLAY",
        } <= names

    def test_governance_workflow_audit_categories_intact(self) -> None:
        for name in (
            "AGENT_GOVERNANCE_WORKFLOW_CREATE",
            "AGENT_GOVERNANCE_WORKFLOW_REVIEW",
            "AGENT_GOVERNANCE_WORKFLOW_EXECUTION",
            "AGENT_GOVERNANCE_WORKFLOW_VIEW",
        ):
            assert name in AuditActionCategory.__members__

    def test_public_exports_unchanged(self) -> None:
        """包级导出面是既有调用方的契约，收敛不得删项。"""
        import agents.enterprise.governance_workflow as pkg

        for name in (
            "GovernanceWorkflow",
            "GovernanceWorkflowStatus",
            "GovernanceWorkflowSourceType",
            "GovernanceWorkflowReview",
            "WorkflowReviewDecision",
            "GovernanceExecutionRecord",
            "GovernanceWorkflowOrchestrator",
            "GovernanceWorkflowAccessDenied",
        ):
            assert name in pkg.__all__, f"包导出缺少 {name}"
            assert hasattr(pkg, name)

    def test_repository_module_exports_are_complete(self) -> None:
        from agents.enterprise.governance_workflow import repository as repo_mod

        for name in (
            "WorkflowRepository",
            "InMemoryWorkflowRepository",
            "JsonFileWorkflowRepository",
            "WorkflowHistoryEntry",
            "WorkflowHistoryEvent",
            "WorkflowRepositoryError",
            "WorkflowStoreIntegrityError",
        ):
            assert name in repo_mod.__all__
