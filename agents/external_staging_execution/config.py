"""Phase 3.9.11 —— External Staging Identity Loader（Tasks 4, 8）。

复用 3.9.10 资格层的身份加载器（production=false + 结构指纹），避免重造。
"""

from __future__ import annotations

from agents.external_staging_qualification.config import (
    fingerprint_collision_with_production,
    load_external_staging_identity,
)

__all__ = ["load_external_staging_identity", "fingerprint_collision_with_production"]
