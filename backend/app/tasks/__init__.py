"""BOIP 异步任务包（Phase 1 / T08 占位）。

Phase 1 全部同步执行（便于本地/CI 演练与单测覆盖）；
Phase 2 引入 RQ + Redis broker 后再加入 ``enqueue`` 入口。
"""

__all__: list[str] = []