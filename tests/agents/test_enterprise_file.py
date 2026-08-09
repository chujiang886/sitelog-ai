"""Enterprise Operation Layer —— 测试4：文件资产管理（任务4，Phase 3.8.0）。

覆盖：
- compute_sha256 与标准库一致。
- upload：version=1、content_hash 计算、source/permission/owner。
- add_version：version 递增 + 重算 hash。
- verify_hash：内容溯源校验。
- list_assets / get 按 org_id 作用域过滤，跨域抛 EnterpriseIsolationError。
"""

from __future__ import annotations

import hashlib

import pytest

from agents.enterprise.file_asset import FileAsset, FileAssetService, compute_sha256
from agents.enterprise.identity import Permission
from agents.enterprise.organization import EnterpriseIsolationError


def test_compute_sha256_matches_hashlib() -> None:
    data = b"hello boip"
    assert compute_sha256(data) == hashlib.sha256(data).hexdigest()


def test_upload_sets_version_one_and_hash() -> None:
    svc = FileAssetService(org_id="org-1")
    asset = svc.upload(file_id="f1", name="a.pdf", data=b"data", owner_id="u1")
    assert asset.version == 1
    assert asset.content_hash == compute_sha256(b"data")
    assert asset.org_id == "org-1"
    assert asset.source == "upload"


def test_add_version_increments_and_rehashes() -> None:
    svc = FileAssetService(org_id="org-1")
    svc.upload(file_id="f1", name="a.pdf", data=b"v1")
    asset = svc.add_version(file_id="f1", data=b"v2-content")
    assert asset.version == 2
    assert asset.content_hash == compute_sha256(b"v2-content")


def test_verify_hash() -> None:
    svc = FileAssetService(org_id="org-1")
    svc.upload(file_id="f1", name="a.pdf", data=b"data")
    assert svc.verify_hash(file_id="f1", data=b"data")
    assert not svc.verify_hash(file_id="f1", data=b"tampered")


def test_list_assets_scoped_to_org() -> None:
    svc = FileAssetService(org_id="org-1")
    svc.upload(file_id="f1", name="a.pdf", data=b"x")
    svc._assets["f2"] = FileAsset(file_id="f2", org_id="org-2", name="b.pdf", content_hash="z")
    ids = {a.file_id for a in svc.list_assets()}
    assert ids == {"f1"}


def test_get_cross_org_raises_isolation() -> None:
    svc = FileAssetService(org_id="org-1")
    svc._assets["f2"] = FileAsset(file_id="f2", org_id="org-2", name="b.pdf", content_hash="z")
    with pytest.raises(EnterpriseIsolationError):
        svc.get(file_id="f2")


def test_default_permission_is_manage_files() -> None:
    svc = FileAssetService(org_id="org-1")
    asset = svc.upload(file_id="f1", name="a.pdf", data=b"x")
    assert asset.permission == Permission.MANAGE_FILES.value
