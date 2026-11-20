import asyncio
import logging
import random

from job_queue.domain import Task, TaskStatus, utcnow
from job_queue.observability import Metrics
from job_queue.services.handlers import HandlerRegistry

logger = logging.getLogger(__name__)


class WorkerPool:
    """Fixed set of worker coroutines consuming one shared queue.

    A task is handed to exactly one worker by `queue.get()`. Status changes
    happen under the shared store lock, so a claim and a cancel cannot both win.
    """

    def __init__(
        self,
        *,
        queue: asyncio.Queue[Task],
        lock: asyncio.Lock,
        handlers: HandlerRegistry,
        metrics: Metrics,
        num_workers: int,
        backoff_base_seconds: float,
        backoff_max_seconds: float,
    ) -> None:
        self._queue = queue
        self._lock = lock
        self._handlers = handlers
        self._metrics = metrics
        self._num_workers = num_workers
        self._backoff_base = backoff_base_seconds
        self._backoff_max = backoff_max_seconds
        self._workers: list[asyncio.Task[None]] = []
        self._retries: dict[str, asyncio.Task[None]] = {}
        self._active = 0

    @property
    def total_workers(self) -> int:
        return self._num_workers

    @property
    def active_workers(self) -> int:
        return self._active

    def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"worker-{i}")
            for i in range(self._num_workers)
        ]

    async def drain(self) -> None:
        """Return once the queue is empty, nothing is running, and no retry is pending."""
        while True:
            await self._queue.join()
            pending = [t for t in self._retries.values() if not t.done()]
            if not pending:
                return
            await asyncio.wait(pending)

    async def stop(self) -> None:
        tasks = [*self._workers, *self._retries.values()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._workers = []

    def cancel_pending_retry(self, task_id: str) -> None:
        """Drop the backoff timer of a task that was cancelled while waiting to retry."""
        retry = self._retries.get(task_id)
        if retry is not None:
            retry.cancel()

    async def _worker(self, worker_id: int) -> None:
        while True:
            task = await self._queue.get()
            try:
                await self._process(task)
            except Exception:
                # _process isolates handler errors itself; this guards the loop
                # against bugs in the bookkeeping so one task cannot kill a worker.
                logger.exception("worker-%d: unexpected error on task %s", worker_id, task.id)
            finally:
                self._queue.task_done()

    async def _process(self, task: Task) -> None:
        async with self._lock:
            if task.status is not TaskStatus.QUEUED:
                return  # cancelled while it sat in the queue
            task.status = TaskStatus.RUNNING
            task.started_at = utcnow()

        self._active += 1
        try:
            await self._execute(task)
        finally:
            self._active -= 1

    async def _execute(self, task: Task) -> None:
        try:
            async with asyncio.timeout(task.timeout_seconds) as scope:
                handler = self._handlers.get(task.task_type)
                result = await handler(task.payload)
        except TimeoutError as exc:
            if scope.expired():
                await self._fail(task, "TIMEOUT")
            else:
                # Raised by the handler itself, not by our deadline.
                await self._fail_or_retry(task, exc)
        except Exception as exc:
            await self._fail_or_retry(task, exc)
        else:
            async with self._lock:
                task.status = TaskStatus.COMPLETED
                task.result = result
                task.error = None
                task.completed_at = utcnow()
            self._metrics.tasks_completed_total += 1

    async def _fail(self, task: Task, error: str) -> None:
        async with self._lock:
            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = utcnow()
        self._metrics.tasks_failed_total += 1

    async def _fail_or_retry(self, task: Task, exc: BaseException) -> None:
        error = f"{type(exc).__name__}: {exc}"
        if task.retry_count >= task.max_retries:
            await self._fail(task, error)
            return

        async with self._lock:
            delay = self._backoff(task.retry_count)
            task.retry_count += 1
            task.status = TaskStatus.QUEUED
            task.error = error
        self._metrics.tasks_retried_total += 1

        # The backoff runs outside the worker so the worker is free for other
        # tasks, and so a full queue cannot deadlock workers waiting to re-enqueue.
        retry = asyncio.create_task(self._requeue_after(task, delay), name=f"retry-{task.id}")
        self._retries[task.id] = retry
        retry.add_done_callback(lambda done: self._forget_retry(task.id, done))

    def _forget_retry(self, task_id: str, retry: asyncio.Task[None]) -> None:
        # A re-enqueued task can fail again and register a new timer before this
        # callback runs, so only remove the entry if it is still this timer.
        if self._retries.get(task_id) is retry:
            del self._retries[task_id]

    def _backoff(self, retry: int) -> float:
        jitter = random.uniform(0, self._backoff_base)
        return min(self._backoff_max, self._backoff_base * 2**retry + jitter)

    async def _requeue_after(self, task: Task, delay: float) -> None:
        await asyncio.sleep(delay)
        # An accepted task is never rejected on retry: wait for a free slot.
        await self._queue.put(task)
