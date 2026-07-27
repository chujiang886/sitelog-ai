"""可扩展对象存储抽象（Phase 2.2 / 2.2.4 MinIO 切换）。

把 Phase 1 / T08 的硬编码本地路径升级为 ``StorageBackend`` 抽象，支持：
- ``LocalStorage``：开发/CI 默认（沿用 ``BOIP_STORAGE_ROOT`` 机制）；
- ``MinIOStorage``：生产可配置，密钥仅来自 .env；
- ``MemoryStorage``：测试 mock（对应外部服务 mock 模式，CI 不依赖真实 MinIO）。

设计同构 2.2.1 Provider 抽象：未知后端 / MinIO 未配置 → fail-fast 抛
``StorageConfigError``，不让错误静默降级成空存储。
"""

from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from pathlib import Path

from app.core import storage as storage_mod


class StorageConfigError(ValueError):
    """存储后端配置错误（未知后端 / MinIO 未配置 / SDK 缺失）。"""


class StorageBackend(ABC):
    """图片对象存储抽象（save / read / delete / 路径规划）。

    所有实现以**逻辑 key** 标识对象，格式统一为 ``{tenant_id}/{sha256}.{ext}``，
    保证跨后端迁移无需改 DB 的 ``storage_path``。
    """

    @property
    @abstractmethod
    def backend_name(self) -> str:
        """后端标识：local / minio / memory。"""

    @abstractmethod
    def save(self, *, key: str, content: bytes, tenant_id: str | None = None) -> str:
        """保存对象，返回逻辑 key（通常等于传入 key）。"""

    @abstractmethod
    def read(self, *, key: str) -> bytes:
        """按 key 读取字节；不存在抛 ``FileNotFoundError``。"""

    @abstractmethod
    def delete(self, *, key: str) -> None:
        """删除对象；不存在静默忽略。"""

    def resolve_key(self, *, tenant_id: str, sha256: str, extension: str) -> str:
        """路径规划：``{tenant_id}/{sha256}.{ext}``（租户隔离 + 内容 hash 去重）。"""

        safe_tenant: str = (tenant_id or "unknown").strip() or "unknown"
        safe_ext: str = (extension or "bin").lstrip(".")
        return f"{safe_tenant}/{sha256}.{safe_ext}"


class LocalStorage(StorageBackend):
    """本地文件系统后端（开发/CI 默认）。

    沿用 ``storage.resolve_storage_root()`` 与 ``storage.build_image_path``，
    保证既有 ``test_uploads.py`` 的 ``resolve_storage_root`` monkeypatch 生效。
    """

    @property
    def backend_name(self) -> str:
        return "local"

    def _path_for(self, key: str) -> Path:
        """逻辑 key → 绝对路径；兼容旧数据（key 为绝对路径且存在时直接用）。"""

        p = Path(key)
        if p.is_absolute() and p.exists():
            return p
        return storage_mod.resolve_storage_root() / key

    def save(self, *, key: str, content: bytes, tenant_id: str | None = None) -> str:
        path = storage_mod.resolve_storage_root() / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return key

    def read(self, *, key: str) -> bytes:
        path = self._path_for(key)
        if not path.exists():
            raise FileNotFoundError(f"local object not found: {key}")
        return path.read_bytes()

    def delete(self, *, key: str) -> None:
        path = self._path_for(key)
        if path.exists():
            path.unlink()

    def _list_keys(self) -> list[str]:
        """列举本地所有对象 key（相对 root），供 migrate 使用。"""

        root = storage_mod.resolve_storage_root()
        keys: list[str] = []
        if not root.exists():
            return keys
        for p in root.rglob("*"):
            if p.is_file():
                keys.append(str(p.relative_to(root)))
        return keys


class MemoryStorage(StorageBackend):
    """内存后端（测试 mock，对应外部服务 mock 模式）。

    CI / 单测使用，不触碰文件系统，不依赖真实 MinIO。
    """

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    @property
    def backend_name(self) -> str:
        return "memory"

    def save(self, *, key: str, content: bytes, tenant_id: str | None = None) -> str:
        self._store[key] = content
        return key

    def read(self, *, key: str) -> bytes:
        if key not in self._store:
            raise FileNotFoundError(f"memory object not found: {key}")
        return self._store[key]

    def delete(self, *, key: str) -> None:
        self._store.pop(key, None)

    def _list_keys(self) -> list[str]:
        """列举内存中所有 key，供 migrate 使用。"""

        return list(self._store.keys())


class MinIOStorage(StorageBackend):
    """MinIO 对象存储后端（生产可配置，密钥仅来自 .env）。

    懒加载 minio SDK；构造时校验环境变量齐全，缺失即 fail-fast。
    """

    def __init__(self) -> None:
        endpoint = os.getenv("MINIO_ENDPOINT", "").strip()
        access_key = os.getenv("MINIO_ACCESS_KEY", "").strip()
        secret_key = os.getenv("MINIO_SECRET_KEY", "").strip()
        bucket = os.getenv("MINIO_BUCKET", "").strip()
        secure_env = os.getenv("MINIO_SECURE", "true").strip().lower()
        secure: bool = secure_env not in ("0", "false", "no")
        missing = [
            name
            for name, val in (
                ("MINIO_ENDPOINT", endpoint),
                ("MINIO_ACCESS_KEY", access_key),
                ("MINIO_SECRET_KEY", secret_key),
                ("MINIO_BUCKET", bucket),
            )
            if not val
        ]
        if missing:
            raise StorageConfigError(
                "MinIO backend 未配置（仅允许来自 .env）：缺少 "
                + ", ".join(missing)
            )
        try:
            from minio import Minio  # noqa: PLC0415 - 懒加载，未装时清晰报错
        except Exception as exc:  # noqa: BLE001 - SDK 缺失
            raise StorageConfigError(
                f"MinIO SDK 未安装（请 pip install minio）：{type(exc).__name__}: {exc}"
            ) from exc

        self._endpoint: str = endpoint
        self._bucket: str = bucket
        self._secure: bool = secure
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        # bucket 不存在则创建（已存在忽略）。
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    @property
    def backend_name(self) -> str:
        return "minio"

    def save(self, *, key: str, content: bytes, tenant_id: str | None = None) -> str:
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(content),
            length=len(content),
        )
        return key

    def read(self, *, key: str) -> bytes:
        try:
            resp = self._client.get_object(self._bucket, key)
        except Exception as exc:  # noqa: BLE001 - 缺失对象统一映射为 FileNotFoundError
            # 真实 minio 抛 S3Error(code="NoSuchKey")；fake 客户端测试抛 KeyError。
            raise FileNotFoundError(f"minio object not found: {key}") from exc
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    def delete(self, *, key: str) -> None:
        self._client.remove_object(self._bucket, key)


def get_storage_backend() -> StorageBackend:
    """按 ``BOIP_STORAGE_BACKEND`` 环境变量返回后端实例（默认 local）。

    未知后端 / MinIO 未配置 → 抛 ``StorageConfigError``（fail-fast）。
    """

    kind = (os.getenv("BOIP_STORAGE_BACKEND", "local") or "local").strip().lower()
    if kind == "local":
        return LocalStorage()
    if kind == "memory":
        return MemoryStorage()
    if kind == "minio":
        return MinIOStorage()  # 未配置会在此抛 StorageConfigError
    raise StorageConfigError(f"未知存储后端：{kind!r}（支持 local/minio/memory）")


def migrate_storage(src: StorageBackend, dst: StorageBackend) -> list[str]:
    """跨后端迁移：按 key 逐对象 copy。

    因 key 规划统一（``{tenant_id}/{sha256}.{ext}``），DB 的 ``storage_path``
    保持不变。返回已迁移的 key 列表（由调用方决定如何列举；本函数对给定 key 迁移）。
    """

    migrated: list[str] = []
    # src 需暴露可列举能力；Local/Memory 提供 _list_keys，MinIO 由调用方传入 key 列表。
    keys = getattr(src, "_list_keys", lambda: [])()
    for key in keys:
        data = src.read(key=key)
        dst.save(key=key, content=data)
        migrated.append(key)
    return migrated


__all__ = [
    "StorageConfigError",
    "StorageBackend",
    "LocalStorage",
    "MemoryStorage",
    "MinIOStorage",
    "get_storage_backend",
    "migrate_storage",
]
