"""Engineering Knowledge Connector 测试（Phase 3.3 Sprint 3.3.7）。

覆盖：
1. KnowledgeItem mapping（KnowledgeItemExtractor 抽取 + 13 字段 + 七态映射）；
2. SourceRef validation（SourceRefBinder C1-C6 通过 / 各类失败）；
3. Expert binding（ExpertBinder 资格 / 范围 / SoD）；
4. 单向同步编排（ObsidianToBoipConnector）；
5. 安全护栏（任务5）：不修改 verified.json value、不开启 engineering_enabled、不建 ReleaseApproval。

红线：本测试不写入任何真实 verified=true、不填真实 value、不出现真实专家姓名、
不输出 engineering_approved；仅用内存夹具与纯标识符（SRC-1 / EXP-1 / E-TH-01）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.config_loader import load_engineering_enabled
from agents.engineering.knowledge.connector import (
    ExpertBinder,
    ExpertBindResult,
    KnowledgeItem,
    KnowledgeItemExtractor,
    KnowledgeItemState,
    ObsidianToBoipConnector,
    SourceRefBinder,
    SourceRefBindResult,
)
from agents.engineering.thresholds.source_ref_validator import compute_content_hash

REPO_ROOT = Path(__file__).resolve().parents[2]
VERIFIED_JSON = REPO_ROOT / "agents" / "engineering" / "thresholds" / "verified.json"
RELEASE_APPROVALS = REPO_ROOT / "agents" / "engineering" / "release" / "release_approvals.jsonl"


# ---------------------------------------------------------------------------
# 任务1：KnowledgeItem mapping
# ---------------------------------------------------------------------------

SAMPLE_NOTE = """---
source: SRC-1
author: EXP-1
domain: wind_pressure
knowledge_type: spec
upstream: KI-parent
linked_threshold: E-TH-01
verification_status: draft
---
# 基本风压来源摘录

正文内容：本笔记记录一项规范来源摘录。
"""

SAMPLE_NOTE_VERIFIED = """---
source: SRC-2
author: EXP-2
domain: structure
knowledge_type: expert_opinion
linked_threshold: E-TH-02
verification_status: verified_source
---
# 已校验来源

正文内容：已通过人工来源校验的规范来源。
"""

SAMPLE_NOTE_NO_FRONTMATTER = """# 纯正文笔记

没有 frontmatter 的个人经验笔记。
"""


def test_extractor_maps_thirteen_fields() -> None:
    """抽取的 KnowledgeItem 必须具备 13 核心字段且值正确映射。"""
    item = KnowledgeItemExtractor().extract(SAMPLE_NOTE, "note.md")

    assert item.knowledge_id.startswith("KI-")
    assert item.knowledge_type == "spec"
    assert item.parent_knowledge_id == "KI-parent"
    assert item.title == "基本风压来源摘录"
    assert item.content.startswith("正文内容")
    assert item.source == "SRC-1"
    assert item.author == "EXP-1"
    assert item.domain == "wind_pressure"
    assert item.content_hash and len(item.content_hash) == 64
    assert item.validation_status == KnowledgeItemState.PENDING_VERIFICATION.value
    assert item.linked_entities == ["E-TH-01"]
    assert item.created_at and item.updated_at

    # 13 字段核心契约计数 + 序列化键完整。
    assert KnowledgeItem.CORE_FIELD_COUNT == 13
    payload = item.to_dict()
    core_keys = list(payload.keys())[:13]
    assert core_keys == [
        "knowledge_id",
        "knowledge_type",
        "parent_knowledge_id",
        "title",
        "content",
        "source",
        "author",
        "domain",
        "content_hash",
        "validation_status",
        "linked_entities",
        "created_at",
        "updated_at",
    ]


def test_extractor_verification_status_mapping() -> None:
    """Obsidian verification_status 三态 → 七态映射正确。"""
    draft = KnowledgeItemExtractor().extract(SAMPLE_NOTE)
    assert draft.validation_status == KnowledgeItemState.PENDING_VERIFICATION.value

    verified = KnowledgeItemExtractor().extract(SAMPLE_NOTE_VERIFIED)
    assert verified.validation_status == KnowledgeItemState.SOURCE_VERIFIED.value


def test_extractor_no_frontmatter_is_captured() -> None:
    """无 frontmatter 的笔记：title 取自 H1，状态为 Captured（原始抽取态）。"""
    item = KnowledgeItemExtractor().extract(SAMPLE_NOTE_NO_FRONTMATTER, "exp.md")
    assert item.title == "纯正文笔记"
    assert item.validation_status == KnowledgeItemState.CAPTURED.value
    assert item.source == "pending_verification"
    assert item.author == "pending_verification"


def test_extractor_id_and_hash_deterministic() -> None:
    """同一笔记知识 id 与 content_hash 稳定（去重依据）。"""
    a = KnowledgeItemExtractor().extract(SAMPLE_NOTE)
    b = KnowledgeItemExtractor().extract(SAMPLE_NOTE)
    assert a.knowledge_id == b.knowledge_id
    assert a.content_hash == b.content_hash


def test_extractor_from_dict_roundtrip() -> None:
    """from_dict 容错恢复，缺失字段补 pending_verification。"""
    raw: dict[str, Any] = {"title": "x", "domain": "wind_pressure"}
    item = KnowledgeItem.from_dict(raw)
    assert item.title == "x"
    assert item.knowledge_id == "pending_verification"
    assert item.validation_status == KnowledgeItemState.PENDING_VERIFICATION.value
    assert item.to_dict()["title"] == "x"


# ---------------------------------------------------------------------------
# 任务2：SourceRef validation（C1-C6）
# ---------------------------------------------------------------------------

def _passing_source(clause: str = "8.1.1") -> dict[str, Any]:
    """构造一条通过 C1-C6 的 spec source 夹具（含匹配 hash）。"""
    content = f"GB 50009 clause {clause}"
    return {
        "source_id": "SRC-1",
        "standard": "GB 50009",
        "edition": "2012",
        "official_url": "https://example.com/gb50009",
        "clause_index": [clause],
        "source_status": "verified_source",
        "source_hash": compute_content_hash(content),
    }


def _item_with_source(source_id: str = "SRC-1", domain: str = "wind_pressure") -> KnowledgeItem:
    return KnowledgeItem(
        knowledge_id="KI-x",
        knowledge_type="spec",
        parent_knowledge_id="pending_verification",
        title="t",
        content="c",
        source=source_id,
        author="pending_verification",
        domain=domain,
        content_hash="h",
        validation_status=KnowledgeItemState.PENDING_VERIFICATION.value,
        linked_entities=["E-TH-01"],
        created_at="now",
        updated_at="now",
    )


def test_source_ref_binder_pass_c1_c6() -> None:
    """source 通过 C1-C6 → Source_Verified。"""
    binder = SourceRefBinder({"sources": [_passing_source()]})
    item = _item_with_source()
    result = binder.bind(item, content_provider=lambda sid: "GB 50009 clause 8.1.1")
    assert isinstance(result, SourceRefBindResult)
    assert result.ok is True
    assert result.new_status == KnowledgeItemState.SOURCE_VERIFIED.value
    assert result.source_ref.standard == "GB 50009"
    assert result.source_ref.clause == "8.1.1"


def test_source_ref_binder_source_pending() -> None:
    """source 仍为 pending_verification → 失败，停留 Pending_Verification。"""
    binder = SourceRefBinder({"sources": [_passing_source()]})
    item = _item_with_source(source_id="pending_verification")
    result = binder.bind(item)
    assert result.ok is False
    assert result.new_status == KnowledgeItemState.PENDING_VERIFICATION.value


def test_source_ref_binder_source_not_found() -> None:
    """source_id 未登记 → 失败。"""
    binder = SourceRefBinder({"sources": [_passing_source()]})
    result = binder.bind(_item_with_source(source_id="SRC-missing"))
    assert result.ok is False
    assert "未在 spec_sources 登记" in result.reason


def test_source_ref_binder_source_not_verified() -> None:
    """source_status 非 verified_source → 失败（拒绝引用 draft）。"""
    src = _passing_source()
    src["source_status"] = "draft"
    binder = SourceRefBinder({"sources": [src]})
    result = binder.bind(_item_with_source(), content_provider=lambda s: "GB 50009 clause 8.1.1")
    assert result.ok is False


def test_source_ref_binder_c5_hash_mismatch() -> None:
    """C5 内容哈希不一致 → 失败。"""
    binder = SourceRefBinder({"sources": [_passing_source()]})
    result = binder.bind(
        _item_with_source(),
        content_provider=lambda sid: "篡改后的内容与被登记 hash 不符",
    )
    assert result.ok is False
    assert "hash" in result.reason


# ---------------------------------------------------------------------------
# 任务3：Expert binding（资格 / 范围 / SoD）
# ---------------------------------------------------------------------------

def _verified_expert(expert_id: str = "EXP-1", domain: str = "wind_pressure") -> dict[str, Any]:
    return {
        "expert_id": expert_id,
        "domains": [domain],
        "qualification_status": "verified",
        "sign_scope": [domain],
        "sod_role": "expert",
    }


def _item_with_author(author: str = "EXP-1", domain: str = "wind_pressure") -> KnowledgeItem:
    item = _item_with_source(domain=domain)
    item.author = author
    return item


def test_expert_binder_pass() -> None:
    """已 verified 且 sign_scope 覆盖 domain 的专家 → 关联成功。"""
    binder = ExpertBinder({"experts": [_verified_expert()]})
    result = binder.bind(_item_with_author())
    assert isinstance(result, ExpertBindResult)
    assert result.ok is True
    assert result.qualification_ok and result.scope_ok and result.sod_ok


def test_expert_binder_author_pending() -> None:
    """author 仍为 pending_verification → 失败。"""
    binder = ExpertBinder({"experts": [_verified_expert()]})
    result = binder.bind(_item_with_author(author="pending_verification"))
    assert result.ok is False
    assert "author 未解析" in result.reason


def test_expert_binder_not_registered() -> None:
    """专家未登记 → 失败。"""
    binder = ExpertBinder({"experts": [_verified_expert()]})
    result = binder.bind(_item_with_author(author="EXP-unknown"))
    assert result.ok is False
    assert "未在 experts.json 登记" in result.reason


def test_expert_binder_qualification_not_verified() -> None:
    """qualification_status 非 verified → 失败（R5）。"""
    expert = _verified_expert()
    expert["qualification_status"] = "pending"
    binder = ExpertBinder({"experts": [expert]})
    result = binder.bind(_item_with_author())
    assert result.ok is False
    assert "qualification_status 非 verified" in result.reason
    assert result.qualification_ok is False


def test_expert_binder_scope_not_covered() -> None:
    """sign_scope 不覆盖 domain → 失败（R4）。"""
    expert = _verified_expert(domain="structure")
    binder = ExpertBinder({"experts": [expert]})
    result = binder.bind(_item_with_author(domain="wind_pressure"))
    assert result.ok is False
    assert "sign_scope 不覆盖 domain" in result.reason
    assert result.scope_ok is False


# ---------------------------------------------------------------------------
# 任务4：单向同步编排
# ---------------------------------------------------------------------------

def test_connector_pipeline_pass() -> None:
    """完整流水线：抽取 → source_ref 绑定 → 专家关联。"""
    connector = ObsidianToBoipConnector(
        spec_sources={"sources": [_passing_source()]},
        experts={"experts": [_verified_expert()]},
    )
    result = connector.process_note(SAMPLE_NOTE, "note.md")
    assert result.item.validation_status == KnowledgeItemState.SOURCE_VERIFIED.value
    assert result.source_ref_result.ok is True
    assert result.expert_result.ok is True


def test_connector_sync_direction_one_way() -> None:
    """同步方向为单向 Obsidian→BOIP。"""
    assert ObsidianToBoipConnector.sync_direction() == "obsidian_to_boip"


# ---------------------------------------------------------------------------
# 任务5：安全保护确认
# ---------------------------------------------------------------------------

def test_connector_does_not_mutate_verified_json() -> None:
    """Connector 运行后，真实 verified.json 字节级不变（从不写 value）。"""
    before = VERIFIED_JSON.read_bytes()
    connector = ObsidianToBoipConnector(
        spec_sources={"sources": [_passing_source()]},
        experts={"experts": [_verified_expert()]},
    )
    connector.process_note(SAMPLE_NOTE, "note.md")
    after = VERIFIED_JSON.read_bytes()
    assert before == after


def test_connector_does_not_create_release_approval() -> None:
    """Connector 运行后，release_approvals.jsonl 不被创建。"""
    connector = ObsidianToBoipConnector(
        spec_sources={"sources": [_passing_source()]},
        experts={"experts": [_verified_expert()]},
    )
    connector.process_note(SAMPLE_NOTE, "note.md")
    assert not RELEASE_APPROVALS.exists()


def test_connector_engineering_enabled_stays_false() -> None:
    """engineering_enabled 保持 False（默认闸门关闭，Connector 不开启）。"""
    assert load_engineering_enabled() is False
    assert ObsidianToBoipConnector.safety_invariants_ok() is True
