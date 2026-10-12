import asyncio
from collections.abc import Coroutine
from typing import Any


class BackgroundTaskRegistry:
    """Tracks fire-and-forget asyncio tasks so they can be awaited on shutdown or in tests."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[None]] = set()

    def schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def wait(self) -> None:
        if not self._tasks:
            return
        await asyncio.gather(*list(self._tasks), return_exceptions=True)
