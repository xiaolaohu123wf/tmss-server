from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger()


class TaskRegistry:
    """统一管理后台 asyncio 任务。所有后台协程必须通过此类创建。"""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[Any]] = set()

    def spawn(self, coro: Coroutine[Any, Any, Any], *, name: str) -> asyncio.Task[Any]:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        task.add_done_callback(self._log_exception)
        return task

    def _log_exception(self, task: asyncio.Task[Any]) -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error("background_task_failed", task=task.get_name(), exc_info=exc)

    async def shutdown(self, timeout: float = 5.0) -> None:
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.wait(list(self._tasks), timeout=timeout)


task_registry = TaskRegistry()
