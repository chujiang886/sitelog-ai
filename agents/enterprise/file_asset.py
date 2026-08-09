"""Enterprise Operation Layer —— 文件资产管理（任务4，Phase 3.8.0）。

新增：``FileAsset``，支持上传 / ``content_hash``(sha256) / ``version``(递增) /
``source`` / ``permission``。

隔离与红线：
- 所有资源按 ``org_id`` 作用域过滤；跨域访问由 ``FileAssetService`` 统一拦截。
- ``FileAssetService`` 构造/写路径断言 ``safety_invariants_ok()``（红线①/⑤）。
- 本模块不持有批准/报价方法（红线②/③/④）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from agents.enterprise.identity import Permission
from agents.enterprise.red_line import (
    EnterpriseRedLineViolationError,
    safety_invariants_ok,
)


def compute_sha256(data: bytes) -> str:
    """计算内容 sha256（hex 字符串）。"""
    return hashlib.sha256(data).hexdigest()


@dataclass
class FileAsset:
    """文件资产（任务4）。

    - ``content_hash``：内容 sha256，保证不可变溯源。
    - ``version``：版本号（>=1，递增）。
    - ``source``：来源（upload / import / generated）。
    - ``permission``：访问权限（以 ``Permission`` 字符串值表达，如 ``manage_files``）。
    """

    file_id: str
    org_id: str
    name: str
    content_hash: str
    version: int = 1
    source: str = "upload"     # upload / import / generated
    permission: str = "manage_files"
    owner_id: str = ""
    created_at: str = ""
    updated_at: str = ""


class FileAssetService:
    """文件资产服务（任务4）。"""

    def __init__(self, org_id: str) -> None:
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下构造 FileAssetService（红线①/⑤）"
            )
        self._org_id = org_id
        self._assets: dict[str, FileAsset] = {}
        self._versions: dict[str, int] = {}

    def upload(
        self,
        *,
        file_id: str,
        name: str,
        data: bytes,
        source: str = "upload",
        permission: str = Permission.MANAGE_FILES.value,
        owner_id: str = "",
        created_at: str = "",
    ) -> FileAsset:
        """上传文件资产，计算 sha256 并登记版本 1。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下上传文件（红线①/⑤）"
            )
        digest = compute_sha256(data)
        asset = FileAsset(
            file_id=file_id,
            org_id=self._org_id,
            name=name,
            content_hash=digest,
            version=1,
            source=source,
            permission=permission,
            owner_id=owner_id,
            created_at=created_at,
            updated_at=created_at,
        )
        self._assets[file_id] = asset
        self._versions[file_id] = 1
        return asset

    def add_version(
        self,
        *,
        file_id: str,
        data: bytes,
        updated_at: str = "",
    ) -> FileAsset:
        """基于新内容新增一个版本（version 递增，重算 hash）。"""
        if not safety_invariants_ok():
            raise EnterpriseRedLineViolationError(
                "safety_invariants_ok() 失败：禁止在启用态下追加版本（红线①/⑤）"
            )
        asset = self._get_scoped(file_id)
        new_version = (self._versions.get(file_id, asset.version) or asset.version) + 1
        asset.content_hash = compute_sha256(data)
        asset.version = new_version
        asset.updated_at = updated_at
        self._versions[file_id] = new_version
        return asset

    def get(self, *, file_id: str) -> FileAsset:
        """按组织作用域读取文件资产（跨域访问抛隔离错误）。"""
        return self._get_scoped(file_id)

    def verify_hash(self, *, file_id: str, data: bytes) -> bool:
        """验证给定内容是否与已登记资产 hash 一致（只读溯源）。"""
        asset = self._get_scoped(file_id)
        return compute_sha256(data) == asset.content_hash

    def list_assets(self) -> list[FileAsset]:
        """列出当前组织下全部文件资产（作用域过滤）。"""
        return [a for a in self._assets.values() if a.org_id == self._org_id]

    def _get_scoped(self, file_id: str) -> FileAsset:
        from agents.enterprise.organization import EnterpriseIsolationError

        asset = self._assets.get(file_id)
        if asset is None:
            raise EnterpriseIsolationError(f"文件资产 {file_id!r} 不存在")
        if asset.org_id != self._org_id:
            raise EnterpriseIsolationError(
                f"文件资产 {file_id!r} 归属组织 {asset.org_id!r} 与当前组织 "
                f"{self._org_id!r} 不一致，禁止跨域访问"
            )
        return asset


__all__ = ["FileAsset", "FileAssetService", "compute_sha256"]
