"""Knowledge Repository & Governance Layer 测试（Phase 3.3 Sprint 3.3.8）。

覆盖（用户要求）：
1. repository CRUD：save / get / exists / query / item_count；
2. version tracking：created_at / updated_at / content_hash / parent_knowledge_id、
   版本递增与幂等、版本快照与历史；
3. audit logging：KnowledgeEventLog 仅记录 create / update / verify / deprecated，
   **明确拒绝 approved**（红线：AI 不代签 / 不代授权 / 不自动 approved）；
4. connector integration：Obsidian→KnowledgeItem→Validation→Repository 落库，
   且 verified.json 字节级不变、不建 release_approvals.jsonl、engineering_enabled=False。

红线约束（任务5）：
- 禁止修改 verified.json value（Repository 仅读写自身 store）；
- 禁止开启 engineering_enabled（safety_invariants_ok 只读断言）；
- 禁止创建 ReleaseApproval（不写 release_approvals.jsonl）；
- 禁止 AI 代替专家审核 / 自动 approved（审计事件白名单拒 approved）。

夹具一律使用纯标识符（SRC-1 / EXP-1 / E-TH-01），不写入任何真实 value 或
真实专家姓名，不出现 engineering_approved。
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.connector import (
    KnowledgeItem,
    KnowledgeItemState,
    ObsidianToBoipConnector,
)
from agents.engineering.knowledge.repository import (
    EVENT_TYPES,
    FORBIDDEN_EVENT_TYPE,
    KnowledgeEvent,
    KnowledgeEventLog,
    KnowledgeRepository,
    _canonical_core,
)
from agents.engineering.thresholds.source_ref_validator import compute_content_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIED_JSON = REPO_ROOT / "agents" / "engineering" / "thresholds" / "verified.json"
RELEASE_APPROVALS = (
    REPO_ROOT / "agents" / "engineering" / "release" / "release_approvals.jsonl"
)


# ---------------------------------------------------------------------------
# 夹具构造
# ---------------------------------------------------------------------------
def make_item(**overrides: Any) -> KnowledgeItem:
    """构造一个确定性 KnowledgeItem（纯标识符，无真实 value）。"""
    base = dict(
        knowledge_id="KI-TEST-0001",
        knowledge_type="spec",
        parent_knowledge_id="",
        title="Example Threshold Note",
        content="This is a placeholder knowledge content body.",
        source="SRC-1",
        author="EXP-1",
        domain="wind_pressure",
        content_hash="",
        validation_status=KnowledgeItemState.PENDING_VERIFICATION.value,
        linked_entities=["E-TH-01"],
        created_at="2026-08-01T00:00:00+00:00",
        updated_at="2026-08-01T00:00:00+00:00",
    )
    base.update(overrides)
    return KnowledgeItem(**base)


# ---------------------------------------------------------------------------
# 任务1：repository CRUD
# ---------------------------------------------------------------------------
class TestRepositoryCRUD:
    def test_save_and_get_roundtrip(self, tmp_path: Path) -> None:
        store = tmp_path / "knowledge_repository.json"
        repo = KnowledgeRepository(store_path=store)
        item = make_item()
        version = repo.save(item, actor="tester", detail="create fixture")
        assert version == 1

        got = repo.get(item.knowledge_id)
        assert got is not None
        assert got.knowledge_id == item.knowledge_id
        assert got.title == item.title
        assert got.domain == item.domain
        assert got.content == item.content

    def test_get_missing_returns_none(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        assert repo.get("KI-NOPE") is None
        assert repo.exists("KI-NOPE") is False

    def test_exists_true_after_save(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(), actor="tester")
        assert repo.exists("KI-TEST-0001") is True
        assert repo.item_count() == 1

    def test_query_by_domain(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-A", domain="wind_pressure"), actor="t")
        repo.save(make_item(knowledge_id="KI-B", domain="structure"), actor="t")
        wind = repo.query(domain="wind_pressure")
        assert {i.knowledge_id for i in wind} == {"KI-A"}

    def test_query_by_validation_status(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(knowledge_id="KI-A"), actor="t")
        repo.save(
            make_item(knowledge_id="KI-B", validation_status="Source_Verified"),
            actor="t",
        )
        verified = repo.query(validation_status="Source_Verified")
        assert {i.knowledge_id for i in verified} == {"KI-B"}

    def test_query_by_knowledge_type_and_author(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(
            make_item(knowledge_id="KI-A", knowledge_type="spec", author="EXP-1"),
            actor="t",
        )
        repo.save(
            make_item(
                knowledge_id="KI-B", knowledge_type="expert_opinion", author="EXP-2"
            ),
            actor="t",
        )
        res = repo.query(knowledge_type="spec", author="EXP-1")
        assert {i.knowledge_id for i in res} == {"KI-A"}

    def test_query_by_parent_and_title_and_prefix(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(
            make_item(knowledge_id="KI-A", parent_knowledge_id="KI-P", title="Alpha"),
            actor="t",
        )
        repo.save(
            make_item(knowledge_id="KI-B", parent_knowledge_id="KI-Q", title="Beta"),
            actor="t",
        )
        by_parent = repo.query(parent_knowledge_id="KI-P")
        assert {i.knowledge_id for i in by_parent} == {"KI-A"}
        by_title = repo.query(title_contains="Bet")
        assert {i.knowledge_id for i in by_title} == {"KI-B"}
        by_prefix = repo.query(knowledge_id_prefix="KI-A")
        assert {i.knowledge_id for i in by_prefix} == {"KI-A"}

    def test_persist_reload_roundtrip(self, tmp_path: Path) -> None:
        store = tmp_path / "knowledge_repository.json"
        repo1 = KnowledgeRepository(store_path=store)
        repo1.save(make_item(knowledge_id="KI-A"), actor="t")
        # 重新打开，应能从磁盘恢复。
        repo2 = KnowledgeRepository(store_path=store)
        assert repo2.item_count() == 1
        assert repo2.exists("KI-A") is True
        assert repo2.get("KI-A").title == "Example Threshold Note"


# ---------------------------------------------------------------------------
# 任务2：version tracking
# ---------------------------------------------------------------------------
class TestVersionTracking:
    def test_content_hash_ignores_timestamps(self) -> None:
        a = make_item(created_at="2026-08-01T00:00:00+00:00")
        b = make_item(created_at="2026-08-02T00:00:00+00:00")  # 仅时间戳不同
        repo = KnowledgeRepository(store_path=None)
        repo.save(a, actor="t")
        repo.save(b, actor="t")
        # 时间戳变化不应产生新版本（内容相同 → 幂等）。
        assert len(repo.version("KI-TEST-0001")) == 1
        # 两种时间戳的规范化核心哈希应一致（哈希排除时间戳）。
        assert compute_content_hash(_canonical_core(a)) == compute_content_hash(
            _canonical_core(b)
        )

    def test_version_increments_on_content_change(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        v1 = repo.save(make_item(content="body v1"), actor="t")
        assert v1 == 1
        v2 = repo.save(make_item(content="body v2"), actor="t")
        assert v2 == 2
        snapshots = repo.version("KI-TEST-0001")
        assert len(snapshots) == 2
        assert snapshots[0]["_version"] == 1
        assert snapshots[1]["_version"] == 2
        assert snapshots[1]["content"] == "body v2"

    def test_idempotent_save_returns_current_version(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        v1 = repo.save(make_item(), actor="t")
        # 完全相同的 item 再次 save（无显式事件）→ 幂等，不新增版本。
        v2 = repo.save(make_item(), actor="t")
        assert v1 == 1
        assert v2 == 1
        assert len(repo.version("KI-TEST-0001")) == 1
        assert len(repo.history("KI-TEST-0001")) == 1

    def test_created_at_preserved_updated_at_changes(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        item = make_item(created_at="2026-08-01T00:00:00+00:00")
        repo.save(item, actor="t")
        item.content = "changed body"
        repo.save(item, actor="t")
        got = repo.get("KI-TEST-0001")
        assert got.created_at == "2026-08-01T00:00:00+00:00"
        assert got.updated_at != got.created_at  # 更新后时间戳应不同

    def test_parent_knowledge_id_tracked(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(parent_knowledge_id="KI-PARENT"), actor="t")
        got = repo.get("KI-TEST-0001")
        assert got.parent_knowledge_id == "KI-PARENT"
        # 谱系演化：新版本改 parent 指向 successor。
        item = repo.get("KI-TEST-0001")
        item.parent_knowledge_id = "KI-SUCCESSOR"
        repo.save(item, actor="t")
        assert repo.get("KI-TEST-0001").parent_knowledge_id == "KI-SUCCESSOR"

    def test_content_hash_set_on_save(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(content_hash=""), actor="t")
        got = repo.get("KI-TEST-0001")
        # content_hash 必为 64 位十六进制 sha256 摘要。
        assert len(got.content_hash) == 64
        assert all(c in "0123456789abcdef" for c in got.content_hash)

    def test_verify_and_deprecate_produce_new_versions(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(), actor="t")  # v1 create
        v2 = repo.verify("KI-TEST-0001", actor="expert", new_status="Source_Verified")
        v3 = repo.deprecate("KI-TEST-0001", actor="governance", successor="KI-NEW")
        assert v2 == 2
        assert v3 == 3
        assert repo.get("KI-TEST-0001").validation_status == "Deprecated"
        assert repo.get("KI-TEST-0001").parent_knowledge_id == "KI-NEW"


# ---------------------------------------------------------------------------
# 任务3：audit logging
# ---------------------------------------------------------------------------
class TestAuditLogging:
    def test_valid_event_types(self) -> None:
        log = KnowledgeEventLog()
        for etype in EVENT_TYPES:
            ev = log.record("KI-X", etype, actor="t", version=1)
            assert ev.event_type == etype
        assert len(log.all_events()) == len(EVENT_TYPES)

    def test_record_approved_is_rejected(self) -> None:
        log = KnowledgeEventLog()
        try:
            log.record("KI-X", FORBIDDEN_EVENT_TYPE, actor="ai")
        except ValueError as exc:
            assert "approved" in str(exc).lower()
        else:
            raise AssertionError("approved 事件应被拒绝（红线）")
        # 日志中不得出现 approved 事件。
        assert all(e.event_type != FORBIDDEN_EVENT_TYPE for e in log.all_events())

    def test_repository_record_event_approved_rejected(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(), actor="t")
        try:
            repo.record_event("KI-TEST-0001", "approved", actor="ai")
        except ValueError:
            pass
        else:
            raise AssertionError("Repository 不应允许 approved 事件")
        assert all(
            e.event_type != FORBIDDEN_EVENT_TYPE
            for e in repo.history("KI-TEST-0001")
        )

    def test_event_log_from_dict_roundtrip(self) -> None:
        raw = [
            {
                "event_id": "EVT-1",
                "knowledge_id": "KI-Y",
                "event_type": "create",
                "actor": "tester",
                "timestamp": "2026-08-01T00:00:00+00:00",
                "detail": "created",
                "version": 1,
            }
        ]
        log = KnowledgeEventLog(raw)
        assert len(log.events_for("KI-Y")) == 1
        assert log.to_list()[0]["event_id"] == "EVT-1"
        ev = KnowledgeEvent.from_dict(raw[0])
        assert ev.knowledge_id == "KI-Y"

    def test_history_records_lifecycle(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(), actor="creator")  # create
        repo.verify("KI-TEST-0001", actor="expert")  # verify
        repo.deprecate("KI-TEST-0001", actor="gov")  # deprecated
        types = [e.event_type for e in repo.history("KI-TEST-0001")]
        assert types == ["create", "verify", "deprecated"]
        assert FORBIDDEN_EVENT_TYPE not in types


# ---------------------------------------------------------------------------
# 任务4：connector integration（Obsidian→KnowledgeItem→Validation→Repository）
# ---------------------------------------------------------------------------
class TestConnectorIntegration:
    def test_process_note_without_repository_backward_compat(self) -> None:
        connector = ObsidianToBoipConnector()
        note = _SAMPLE_NOTE
        result = connector.process_note(note, note_path="vault/note.md")
        assert result.repository_info is None
        assert result.item is not None

    def test_process_note_with_repository_persists(self, tmp_path: Path) -> None:
        store = tmp_path / "knowledge_repository.json"
        repo = KnowledgeRepository(store_path=store)
        connector = ObsidianToBoipConnector()
        verified_before = VERIFIED_JSON.read_bytes() if VERIFIED_JSON.is_file() else b""

        result = connector.process_note(
            _SAMPLE_NOTE, note_path="vault/note.md", repository=repo
        )

        assert result.repository_info is not None
        assert result.repository_info["saved"] is True
        assert result.repository_info["version"] == 1
        assert repo.item_count() == 1
        # 红线：verified.json 字节级不变。
        if VERIFIED_JSON.is_file():
            assert VERIFIED_JSON.read_bytes() == verified_before
        # 红线：不创建 release_approvals.jsonl。
        assert not RELEASE_APPROVALS.exists()
        # 红线：engineering_enabled 保持 False。
        assert load_engineering_enabled() is False
        assert KnowledgeRepository.safety_invariants_ok() is True

    def test_connector_source_verified_records_verify_event(self, tmp_path: Path) -> None:
        """source_ref C1-C6 通过时，Connector 应补记 verify 事件。"""
        sha = hashlib.sha256(b"reference-content").hexdigest()
        spec_sources = {
            "sources": [
                {
                    "source_id": "SRC-1",
                    "source_status": "verified_source",
                    "standard": "GB 50009",
                    "clause_index": ["8.1.1"],
                    "edition": "2012",
                    "official_url": "https://example.com/gb50009",
                    "source_hash": sha,
                    "retrieved_at": "2026-01-01",
                }
            ]
        }
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        connector = ObsidianToBoipConnector(spec_sources=spec_sources)
        result = connector.process_note(
            _SAMPLE_NOTE, note_path="vault/note.md", repository=repo
        )
        assert result.source_ref_result.ok is True
        assert result.repository_info.get("verify_event") is True
        kid = result.item.knowledge_id
        types = [e.event_type for e in repo.history(kid)]
        assert "verify" in types
        assert FORBIDDEN_EVENT_TYPE not in types

    def test_verify_never_sets_engineering_approved(self, tmp_path: Path) -> None:
        repo = KnowledgeRepository(store_path=tmp_path / "store.json")
        repo.save(make_item(), actor="t")
        repo.verify("KI-TEST-0001", actor="expert")  # default Source_Verified
        status = repo.get("KI-TEST-0001").validation_status
        assert status == "Source_Verified"
        assert status != "Engineering_Approved"
        # 审计事件中绝无 approved。
        assert all(
            e.event_type != FORBIDDEN_EVENT_TYPE
            for e in repo.history("KI-TEST-0001")
        )


# ---------------------------------------------------------------------------
# 测试夹具笔记（纯标识符，无真实 value）
# ---------------------------------------------------------------------------
_SAMPLE_NOTE = """---
source: SRC-1
author: EXP-1
domain: wind_pressure
knowledge_type: spec
upstream: KI-parent
linked_threshold: E-TH-01
verification_status: draft
---
# Example Threshold Note

This is a placeholder knowledge content body used only for testing.
"""
