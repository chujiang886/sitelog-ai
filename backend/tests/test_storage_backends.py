"""Phase 2.2 / 2.2.4 MinIO 图片存储切换测试。

覆盖：上传(save)/读取(read)/删除(delete)/迁移(migrate) + 租户隔离 + hash 去重 +
MinIO 未配置 fail-fast。CI 不依赖真实 MinIO（local / memory 后端）。
"""

from __future__ import annotations

import pytest

from app.core import storage as storage_module
from app.core.storage_backends import (
    LocalStorage,
    MemoryStorage,
    StorageConfigError,
    get_storage_backend,
    migrate_storage,
)


# --------------------------------------------------------------------------- #
# save / read                                                                  #
# --------------------------------------------------------------------------- #


def test_local_save_read_roundtrip() -> None:
    backend = LocalStorage()
    key = backend.resolve_key(tenant_id="t1", sha256="a" * 64, extension="jpg")
    backend.save(key=key, content=b"hello", tenant_id="t1")
    assert backend.read(key=key) == b"hello"


def test_memory_save_read_roundtrip() -> None:
    backend = MemoryStorage()
    key = backend.resolve_key(tenant_id="t1", sha256="b" * 64, extension="png")
    backend.save(key=key, content=b"world", tenant_id="t1")
    assert backend.read(key=key) == b"world"


def test_read_missing_raises() -> None:
    backend = MemoryStorage()
    with pytest.raises(FileNotFoundError):
        backend.read(key="nope/abc.jpg")


# --------------------------------------------------------------------------- #
# delete                                                                       #
# --------------------------------------------------------------------------- #


def test_delete_removes_object() -> None:
    backend = MemoryStorage()
    key = backend.resolve_key(tenant_id="t1", sha256="c" * 64, extension="jpg")
    backend.save(key=key, content=b"x", tenant_id="t1")
    backend.delete(key=key)
    with pytest.raises(FileNotFoundError):
        backend.read(key=key)


# --------------------------------------------------------------------------- #
# 租户隔离 + hash 去重                                                          #
# --------------------------------------------------------------------------- #


def test_tenant_isolation_in_key() -> None:
    backend = LocalStorage()
    k1 = backend.resolve_key(tenant_id="tenantA", sha256="d" * 64, extension="jpg")
    k2 = backend.resolve_key(tenant_id="tenantB", sha256="d" * 64, extension="jpg")
    assert k1.startswith("tenantA/")
    assert k2.startswith("tenantB/")
    assert k1 != k2  # 租户前缀隔离


def test_hash_dedup_same_content_same_key() -> None:
    backend = MemoryStorage()
    k1 = backend.resolve_key(tenant_id="t1", sha256="e" * 64, extension="jpg")
    k2 = backend.resolve_key(tenant_id="t1", sha256="e" * 64, extension="jpg")
    assert k1 == k2  # 相同 sha256 → 相同 key（幂等去重）
    backend.save(key=k1, content=b"same", tenant_id="t1")
    backend.save(key=k2, content=b"same", tenant_id="t1")
    assert backend.read(key=k1) == b"same"


# --------------------------------------------------------------------------- #
# MinIO 未配置 fail-fast                                                        #
# --------------------------------------------------------------------------- #


def test_minio_missing_config_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOIP_STORAGE_BACKEND", "minio")
    for var in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(StorageConfigError):
        get_storage_backend()


def test_get_storage_backend_default_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BOIP_STORAGE_BACKEND", raising=False)
    assert get_storage_backend().backend_name == "local"


def test_get_storage_backend_memory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOIP_STORAGE_BACKEND", "memory")
    assert get_storage_backend().backend_name == "memory"


def test_get_storage_backend_unknown_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BOIP_STORAGE_BACKEND", "s3")
    with pytest.raises(StorageConfigError):
        get_storage_backend()


# --------------------------------------------------------------------------- #
# 迁移                                                                          #
# --------------------------------------------------------------------------- #


def test_migrate_memory_to_local(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: tmp_path, raising=False)
    src = MemoryStorage()
    dst = LocalStorage()
    keys = [
        src.resolve_key(tenant_id="t1", sha256="f" * 64, extension="jpg"),
        src.resolve_key(tenant_id="t2", sha256="1" * 64, extension="png"),
    ]
    for i, k in enumerate(keys):
        src.save(key=k, content=f"data-{i}".encode(), tenant_id="t1")
    migrated = migrate_storage(src, dst)
    assert set(migrated) == set(keys)
    for i, k in enumerate(keys):
        assert dst.read(key=k) == f"data-{i}".encode()


def test_migrate_local_to_memory(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: tmp_path, raising=False)
    src = LocalStorage()
    dst = MemoryStorage()
    keys = [
        src.resolve_key(tenant_id="t1", sha256="a" * 64, extension="jpg"),
    ]
    for k in keys:
        src.save(key=k, content=b"local-data", tenant_id="t1")
    migrated = migrate_storage(src, dst)
    assert migrated == keys
    assert dst.read(key=keys[0]) == b"local-data"


# --------------------------------------------------------------------------- #
# 兼容性 + 历史路径 + MinIO 逻辑（用 fake client，不依赖真实 MinIO）            #
# --------------------------------------------------------------------------- #


def test_local_read_absolute_path_fallback(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LocalStorage.read 兼容旧数据（storage_path 为绝对路径时直接读）。"""

    monkeypatch.setattr(storage_module, "resolve_storage_root", lambda: tmp_path, raising=False)
    direct = tmp_path / "direct.bin"
    direct.write_bytes(b"abs-data")
    backend = LocalStorage()
    assert backend.read(key=str(direct)) == b"abs-data"


def test_build_image_path_format_and_validation() -> None:
    """历史 build_image_path 仍然可用且校验 sha256。"""

    from app.core.storage import build_image_path

    p = build_image_path(tenant_id="t1", sha256="a" * 64, extension="jpg")
    assert p.name == ("a" * 64) + ".jpg"
    assert "t1" in str(p)
    with pytest.raises(ValueError):
        build_image_path(tenant_id="t1", sha256="bad", extension="jpg")


def _install_fake_minio(monkeypatch: pytest.MonkeyPatch) -> None:
    """注入 fake minio 模块，使 MinIOStorage 可在无真实服务下被测。"""

    import sys
    import types

    fake = types.ModuleType("minio")

    class _FakeResp:
        def __init__(self, data: bytes) -> None:
            self._d = data

        def read(self) -> bytes:
            return self._d

        def close(self) -> None:
            pass

        def release_conn(self) -> None:
            pass

    class _FakeMinio:
        def __init__(self, endpoint, access_key, secret_key, secure) -> None:  # noqa: ANN001
            self._store: dict[str, bytes] = {}

        def bucket_exists(self, bucket: str) -> bool:  # noqa: ARG002
            return False

        def make_bucket(self, bucket: str) -> None:  # noqa: ARG002
            pass

        def put_object(self, bucket, key, data, length) -> None:  # noqa: ANN001, ARG002
            self._store[key] = data.read()

        def get_object(self, bucket, key):  # noqa: ANN001, ARG002
            return _FakeResp(self._store[key])

        def remove_object(self, bucket, key) -> None:  # noqa: ANN001, ARG002
            self._store.pop(key, None)

    fake.Minio = _FakeMinio
    monkeypatch.setitem(sys.modules, "minio", fake)


def test_minio_save_read_delete_with_fake_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MinIOStorage 逻辑路径（save/read/delete/backend_name）用 fake client 覆盖。"""

    for var, val in (
        ("BOIP_STORAGE_BACKEND", "minio"),
        ("MINIO_ENDPOINT", "localhost:9000"),
        ("MINIO_ACCESS_KEY", "fake-access"),
        ("MINIO_SECRET_KEY", "fake-secret"),
        ("MINIO_BUCKET", "boip"),
    ):
        monkeypatch.setenv(var, val)
    _install_fake_minio(monkeypatch)
    backend = get_storage_backend()  # backend=minio（env 已配）
    assert backend.backend_name == "minio"
    key = backend.resolve_key(tenant_id="t1", sha256="9" * 64, extension="jpg")
    backend.save(key=key, content=b"minio-data", tenant_id="t1")
    assert backend.read(key=key) == b"minio-data"
    backend.delete(key=key)
    with pytest.raises(FileNotFoundError):
        backend.read(key=key)


__all__: list[str] = []
