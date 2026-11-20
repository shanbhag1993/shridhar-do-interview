import asyncio
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

from job_queue.config import Settings
from job_queue.domain import Task, TaskStatus, utcnow
from job_queue.domain.errors import (
    QueueFullError,
    ServiceShuttingDownError,
    TaskNotCancellableError,
    TaskNotFoundError,
    UnknownTaskTypeError,
)
from job_queue.observability import Metrics
from job_queue.services.cleaner import Cleaner
from job_queue.services.handlers import HandlerRegistry, default_registry
from job_queue.services.worker_pool import WorkerPool

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ServiceStats:
    accepting: bool
    queue_depth: int
    queue_capacity: int
    active_workers: int
    total_workers: int
    stored_tasks: int
    uptime_seconds: int


class TaskService:
    """Owns the bounded queue, the task store, the worker pool, and the TTL cleaner.

    Everything runs on one event loop. The store lock makes each status
    transition (submit, claim, finish, cancel, evict) a single critical section.
    """

    def __init__(self, settings: Settings, handlers: HandlerRegistry | None = None) -> None:
        self._settings = settings
        self._handlers = handlers or default_registry()
        self._queue: asyncio.Queue[Task] = asyncio.Queue(maxsize=settings.queue_capacity)
        self._store: dict[str, Task] = {}
        self._lock = asyncio.Lock()
        self._accepting = False
        self._started_at = time.monotonic()
        self.metrics = Metrics()
        self._pool = WorkerPool(
            queue=self._queue,
            lock=self._lock,
            handlers=self._handlers,
            metrics=self.metrics,
            num_workers=settings.num_workers,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
            backoff_max_seconds=settings.retry_backoff_max_seconds,
        )
        self._cleaner = Cleaner(
            store=self._store,
            lock=self._lock,
            ttl_seconds=settings.retention_ttl_seconds,
            interval_seconds=settings.cleaner_interval_seconds,
        )

    async def start(self) -> None:
        self._started_at = time.monotonic()
        self._pool.start()
        self._cleaner.start()
        self._accepting = True
        logger.info(
            "task service started: capacity=%d workers=%d",
            self._settings.queue_capacity,
            self._settings.num_workers,
        )

    async def submit(
        self,
        *,
        task_type: str,
        payload: dict[str, Any],
        priority: int = 0,
        max_retries: int = 0,
        timeout_seconds: float = 30.0,
    ) -> Task:
        """Enqueue without waiting. Raises QueueFullError when at capacity."""
        if not self._accepting:
            raise ServiceShuttingDownError()
        if task_type not in self._handlers:
            raise UnknownTaskTypeError(task_type)

        task = Task(
            id=str(uuid.uuid4()),
            task_type=task_type,
            payload=payload,
            priority=priority,
            max_retries=max_retries,
            timeout_seconds=timeout_seconds,
        )
        async with self._lock:
            try:
                self._queue.put_nowait(task)
            except asyncio.QueueFull:
                self.metrics.tasks_rejected_total += 1
                raise QueueFullError(self._settings.retry_after_seconds) from None
            self._store[task.id] = task
        self.metrics.tasks_enqueued_total += 1
        return task

    async def get(self, task_id: str) -> Task:
        async with self._lock:
            task = self._store.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    async def cancel(self, task_id: str) -> Task:
        """Cancel a task that has not started.

        asyncio.Queue cannot remove an arbitrary item, so the task stays in the
        queue and the worker that eventually pops it skips it.
        """
        async with self._lock:
            task = self._store.get(task_id)
            if task is None:
                raise TaskNotFoundError(task_id)
            if task.status is not TaskStatus.QUEUED:
                raise TaskNotCancellableError(task_id, task.status)
            task.status = TaskStatus.CANCELLED
            task.completed_at = utcnow()
        self._pool.cancel_pending_retry(task_id)
        self.metrics.tasks_cancelled_total += 1
        return task

    def stats(self) -> ServiceStats:
        return ServiceStats(
            accepting=self._accepting,
            queue_depth=self._queue.qsize(),
            queue_capacity=self._settings.queue_capacity,
            active_workers=self._pool.active_workers,
            total_workers=self._pool.total_workers,
            stored_tasks=len(self._store),
            uptime_seconds=int(time.monotonic() - self._started_at),
        )

    async def shutdown(self) -> None:
        """Stop intake, let workers drain within the grace period, then stop them."""
        self._accepting = False
        timeout = self._settings.drain_timeout_seconds
        logger.info(
            "shutdown: draining %d queued and %d running tasks (grace %.1fs)",
            self._queue.qsize(),
            self._pool.active_workers,
            timeout,
        )
        try:
            await asyncio.wait_for(self._pool.drain(), timeout=timeout)
        except TimeoutError:
            unfinished = sum(1 for t in self._store.values() if not t.status.is_terminal)
            logger.warning(
                "drain timed out after %.1fs; abandoning %d unfinished tasks", timeout, unfinished
            )
        else:
            logger.info("shutdown: drain complete")
        await self._pool.stop()
        await self._cleaner.stop()
        logger.info("task service stopped")
