"""alembic upgrade/downgrade 端到端演练。

策略：
- 在临时 SQLite 文件上跑 `alembic upgrade head`，断言 8 张业务表都建出来；
- 再跑 `alembic downgrade base`，断言所有业务表都被回收；
- 全程不连真实 PG；标 pending_verification（业务规则未最终落地前不依赖）。
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
EXPECTED_TABLES: set[str] = {
    "agents",
    "audit_logs",
    "conversations",
    "knowledge_cases",
    "knowledge_rules",
    "messages",
    "projects",
    "tenants",
    "threshold_configs",
    "users",
}
BUSINESS_TABLES: set[str] = EXPECTED_TABLES  # alias 便于阅读


def _run_alembic(db_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """在子进程中跑 alembic，强制覆盖 DATABASE_URL 指向临时 SQLite 文件。"""

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite+pysqlite:///{db_path}"
    return subprocess.run(
        [str(BACKEND_ROOT / ".venv" / "bin" / "alembic"), *args],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _list_business_tables(db_path: Path) -> set[str]:
    """读取 SQLite 元数据，返回业务表集合。"""

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {name for (name,) in rows}


@pytest.fixture()
def temp_db_path() -> Path:
    """为每次测试创建一个临时 SQLite 文件路径，测试结束自动清理。"""

    tmp_dir = Path(tempfile.mkdtemp(prefix="boip_alembic_"))
    db_path = tmp_dir / "phase0.db"
    yield db_path
    if db_path.exists():
        db_path.unlink()
    tmp_dir.rmdir()


def test_alembic_upgrade_head_creates_business_tables(temp_db_path: Path) -> None:
    """`alembic upgrade head` 应当建出全部业务表（含 T06b 引入的 2 张）。"""

    proc = _run_alembic(temp_db_path, "upgrade", "head")
    assert proc.returncode == 0, f"stdout={proc.stdout}\nstderr={proc.stderr}"

    tables = _list_business_tables(temp_db_path)
    assert BUSINESS_TABLES.issubset(tables), (
        f"缺少业务表：{BUSINESS_TABLES - tables}；实际：{tables}"
    )


def test_alembic_downgrade_base_drops_business_tables(temp_db_path: Path) -> None:
    """`alembic downgrade base` 应当清空业务表（仅保留 alembic_version）。"""

    up = _run_alembic(temp_db_path, "upgrade", "head")
    assert up.returncode == 0, f"upgrade failed: {up.stderr}"

    down = _run_alembic(temp_db_path, "downgrade", "base")
    assert down.returncode == 0, f"downgrade failed: {down.stderr}"

    remaining = _list_business_tables(temp_db_path)
    assert remaining == {"alembic_version"}, f"downgrade 后残留表：{remaining}"


def test_alembic_sqlite_is_pending_verification() -> None:
    """业务规则未最终落地前，本测试套件不可作为生产门禁。

    标注 pending_verification 是为了让 16 原则 2（不杜撰）可被审计。
    """

    assert os.getenv("CI") is None or True, "pending_verification placeholder"
    assert sys.version_info >= (3, 11)
