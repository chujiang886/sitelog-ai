"""回归测试：``app.tasks.vision_tasks._run_agent_coroutine``。

守护点：传入的协程必须**恰好被 await 一次**并返回其结果，无论调用方
当前线程是否已有"运行中的 event loop"。任一分支若未消费协程，GC 时会
触发 ``RuntimeWarning: coroutine ... was never awaited``——本测试会捕获该警告。

不依赖数据库 / 网络：直接对 helper 喂真实协程，验证其契约。
"""
from __future__ import annotations

import asyncio
import warnings

from app.tasks.vision_tasks import _run_agent_coroutine


def _assert_no_never_awaited(caught) -> None:
    for w in caught:
        assert "never awaited" not in str(w.message), f"unexpected warning: {w.message!r}"


def test_run_without_running_loop_runs_once():
    calls: list[int] = []

    async def f():
        calls.append(1)
        return "SENTINEL_A"

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = _run_agent_coroutine(f())

    assert result == "SENTINEL_A"
    assert calls == [1], "协程应恰好执行一次"
    _assert_no_never_awaited(caught)


def test_run_with_running_loop_runs_once():
    calls: list[int] = []

    async def f():
        calls.append(1)
        return "SENTINEL_B"

    def driver():
        async def _run():
            return _run_agent_coroutine(f())

        return asyncio.run(_run())

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = driver()

    assert result == "SENTINEL_B"
    assert calls == [1], "运行 loop 分支下协程也应恰好执行一次"
    _assert_no_never_awaited(caught)
