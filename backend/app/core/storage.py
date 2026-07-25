"""本地文件存储 helper（Phase 1 / T08 占位实现）。

最小正确实现：
- 把图片按 tenant 隔离写到 ``backend/storage/uploads/{tenant_id}/{sha256}.{ext}``；
- 通过 ``STORAGE_ROOT`` 环境变量允许测试或生产覆盖根目录；
- 不引入文件系统锁，假设同一 sha256 不会并发写两次（上传接口走 dedup）。
"""

from __future__ import annotations

import os
from pathlib import Path

from app.db.models.tenant import GUID  # noqa: F401  - 复用跨方言 UUID 处理


DEFAULT_STORAGE_ROOT: Path = Path(
    os.getenv("BOIP_STORAGE_ROOT", "").strip()
    or (Path(__file__).resolve().parents[2] / "storage" / "uploads")
)


def resolve_storage_root() -> Path:
    """返回当前进程使用的 storage 根目录；目录会自动创建。"""

    root: Path = DEFAULT_STORAGE_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_image_path(*, tenant_id: str, sha256: str, extension: str) -> Path:
    """根据 tenant + sha256 + 扩展名构造绝对路径。"""

    safe_ext: str = extension.lstrip(".") or "bin"
    safe_tenant: str = tenant_id.strip() or "unknown"
    safe_sha: str = sha256.strip().lower()
    if len(safe_sha) != 64 or any(c not in "0123456789abcdef" for c in safe_sha):
        raise ValueError(f"Invalid sha256: {sha256!r}")
    root: Path = resolve_storage_root() / safe_tenant
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{safe_sha}.{safe_ext}"


__all__ = ["DEFAULT_STORAGE_ROOT", "build_image_path", "resolve_storage_root"]