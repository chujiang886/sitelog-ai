"""图片预处理工具（Phase 1 / T08）。

最小正确实现：
- 校验 MIME 类型（jpg/jpeg/png/webp）；
- 校验大小（≤ 10 MB，pending_verification）；
- base64 编码（Phase 1 暂不做像素级压缩，保留原始字节）；
- 输出统一结构化元数据，便于 Vision Agent 与前端复用。

不在此处做 LLM 调用；本模块仅做"图 → 结构化 dict"。
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import dataclass
from typing import Final


# 允许的 MIME 白名单；Phase 1 暂不做 HEIC/AVIF，避免解码层依赖。
ALLOWED_MIME_TYPES: Final[tuple[str, ...]] = (
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
)

# 单文件体积上限（10 MB）；主理人确认前一律 pending_verification。
MAX_SIZE_BYTES: Final[int] = 10 * 1024 * 1024

# MIME → 扩展名映射（落盘文件名后缀）。
MIME_TO_EXT: Final[dict[str, str]] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}


class ImageValidationError(ValueError):
    """图片校验失败时抛出，由上层路由转为 400/422。"""


@dataclass(frozen=True, slots=True)
class ProcessedImage:
    """图片预处理结果：原始二进制 + 派生元数据。"""

    content: bytes
    filename: str
    mime_type: str
    size_bytes: int
    sha256: str
    base64: str
    extension: str
    pending_verification: bool = True

    def to_metadata(self) -> dict[str, object]:
        """返回不含 ``content`` 的元数据（便于日志 / DB 持久化）。"""

        return {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "extension": self.extension,
            "pending_verification": self.pending_verification,
        }


def validate_mime(mime_type: str) -> str:
    """校验 MIME 是否在白名单；返回标准化后的小写 MIME。"""

    normalized: str = (mime_type or "").strip().lower()
    if normalized not in ALLOWED_MIME_TYPES:
        raise ImageValidationError(
            f"Unsupported mime_type: {mime_type!r}; "
            f"allowed={list(ALLOWED_MIME_TYPES)}"
        )
    return normalized


def validate_size(content: bytes) -> int:
    """校验大小是否 ≤ 上限；返回字节数。"""

    size: int = len(content)
    if size <= 0:
        raise ImageValidationError("Empty file")
    if size > MAX_SIZE_BYTES:
        raise ImageValidationError(
            f"File too large: {size} bytes > {MAX_SIZE_BYTES} bytes (pending_verification)"
        )
    return size


def compute_sha256(content: bytes) -> str:
    """计算 sha256（小写 hex），便于去重与审计。"""

    return hashlib.sha256(content).hexdigest()


def encode_base64(content: bytes) -> str:
    """把二进制编码为 base64 字符串（不带前缀），供多模态 LLM 调用。"""

    return base64.b64encode(content).decode("ascii")


def process_image(
    *,
    content: bytes,
    filename: str,
    mime_type: str,
) -> ProcessedImage:
    """图片预处理：MIME / 大小校验 + sha256 + base64。

    - 校验失败抛 ``ImageValidationError``；
    - 所有工程数值（压缩阈值、像素上限）保持 ``pending_verification``，
      Phase 2 引入 PIL/Pillow 后再细化。
    """

    normalized_mime: str = validate_mime(mime_type)
    size: int = validate_size(content)
    digest: str = compute_sha256(content)
    b64: str = encode_base64(content)
    extension: str = MIME_TO_EXT.get(normalized_mime, "bin")
    return ProcessedImage(
        content=content,
        filename=filename or "upload.bin",
        mime_type=normalized_mime,
        size_bytes=size,
        sha256=digest,
        base64=b64,
        extension=extension,
        pending_verification=True,
    )


__all__ = [
    "ALLOWED_MIME_TYPES",
    "MAX_SIZE_BYTES",
    "MIME_TO_EXT",
    "ImageValidationError",
    "ProcessedImage",
    "compute_sha256",
    "encode_base64",
    "process_image",
    "validate_mime",
    "validate_size",
]