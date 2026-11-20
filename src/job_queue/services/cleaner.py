import asyncio
import logging
from datetime import datetime

from job_queue.domain import Task, utcnow

logger = logging.getLogger(__name__)


class Cleaner:
    """Periodically evicts finished tasks older than the retention TTL."""

    def __init__(
        self,
        *,
        store: dict[str, Task],
        lock: asyncio.Lock,
        ttl_seconds: float,
        interval_seconds: float,
    ) -> None:
        self._store = store
        self._lock = lock
        self._ttl = ttl_seconds
        self._interval = interval_seconds
        self._runner: asyncio.Task[None] | None = None

    def start(self) -> None:
        self._runner = asyncio.create_task(self._run(), name="ttl-cleaner")

    async def stop(self) -> None:
        if self._runner is None:
            return
        self._runner.cancel()
        await asyncio.gather(self._runner, return_exceptions=True)
        self._runner = None

    async def sweep(self, now: datetime | None = None) -> int:
        """Remove expired terminal tasks. Returns how many were evicted."""
        now = now or utcnow()
        async with self._lock:
            expired = [
                task_id
                for task_id, task in self._store.items()
                if task.status.is_terminal
                and task.completed_at is not None
                and (now - task.completed_at).total_seconds() > self._ttl
            ]
            for task_id in expired:
                del self._store[task_id]
        return len(expired)

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(self._interval)
            try:
                evicted = await self.sweep()
            except Exception:
                logger.exception("ttl-cleaner: sweep failed")
            else:
                if evicted:
                    logger.info("ttl-cleaner: evicted %d finished tasks", evicted)
