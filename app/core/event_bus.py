from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import Any

QUEUE_MAX = 200


class EventBus:
    """进程内 pub/sub，连接 TCP 写入侧与 SSE 推送侧（单例）。"""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def publish(self, topic: str, payload: dict[str, Any]) -> None:
        async with self._lock:
            queues = list(self._subscribers.get(topic, []))
        for q in queues:
            if q.full():
                try:
                    q.get_nowait()  # 丢弃最旧消息
                except asyncio.QueueEmpty:
                    pass
            await q.put(payload)

    @asynccontextmanager
    async def subscribe(self, topics: list[str]):
        q: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)
        async with self._lock:
            for topic in topics:
                self._subscribers[topic].append(q)
        try:
            yield q
        finally:
            async with self._lock:
                for topic in topics:
                    try:
                        self._subscribers[topic].remove(q)
                    except ValueError:
                        pass


event_bus = EventBus()
