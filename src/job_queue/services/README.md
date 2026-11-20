# `job_queue.services`

The runtime of the service: the bounded queue, the in-memory task store, the
workers that consume the queue, the cleaner that evicts old results, and the
handlers that do the actual work. Nothing here knows about HTTP.

## Files

| File | Contains |
| :--- | :--- |
| `task_service.py` | `TaskService`: owns the `asyncio.Queue`, the task store, and the lock that guards status changes. Its methods are what the API calls: `start`, `submit`, `get`, `cancel`, `stats`, `shutdown`. Also `ServiceStats`, the snapshot returned by `stats()`. |
| `worker_pool.py` | `WorkerPool`: the worker coroutines. Each takes a task from the queue, runs its handler under the task's timeout, and records the outcome. Also handles retries, `drain()`, and `stop()`. |
| `cleaner.py` | `Cleaner`: a background task that removes finished tasks older than the retention TTL. `sweep()` does one pass. |
| `handlers.py` | `HandlerRegistry`, which maps a `task_type` to an async function, the `Handler` type, the simulated `data_aggregation` handler, and `default_registry()`. |
| `__init__.py` | Re-exports `TaskService`, `ServiceStats`, `HandlerRegistry`, and `default_registry`. |

## How the pieces work together

- **Submit:** `TaskService.submit` puts the task on the queue with
  `put_nowait`. A full queue raises `QueueFullError` at once, and nothing is
  stored for the rejected task.
- **Consume:** every worker waits on the same queue, and the queue hands each
  task to exactly one of them. The worker sets `RUNNING`, then `COMPLETED` or
  `FAILED`.
- **Failure isolation:** an exception in a handler fails only that task. The
  worker carries on with the next one.
- **Timeout:** a task that exceeds its `timeout_seconds` becomes `FAILED` with
  the error `TIMEOUT`. Timeouts are not retried.
- **Retry:** if a handler raises and retries remain, the task goes back to
  `QUEUED` and is re-enqueued after
  `min(max, base * 2^retry + jitter)` seconds. The wait runs on a separate
  timer, so the worker is free for other tasks in the meantime.
- **Cancel:** `asyncio.Queue` cannot remove an item from the middle, so a
  cancelled task stays in the queue marked `CANCELLED`, and the worker that
  takes it skips it.
- **Eviction:** the cleaner runs every `CLEANER_INTERVAL_SECONDS` and deletes
  `COMPLETED`, `FAILED`, and `CANCELLED` tasks older than
  `RETENTION_TTL_SECONDS`. Unfinished tasks are never evicted.
- **Shutdown:** `TaskService.shutdown` refuses new submissions, waits up to
  `DRAIN_TIMEOUT_SECONDS` for queued work, running work, and pending retries to
  finish, then cancels the workers and the cleaner.

## Adding a task type

Write an async function that takes the payload and returns a JSON-serialisable
result, then register it in `default_registry()` in `handlers.py`:

```python
async def send_report(payload: dict[str, Any]) -> dict[str, Any]:
    ...
    return {"sent": True}

registry.register("SEND_REPORT", send_report)
```

Raise an exception to fail the task; it will be retried if the request allowed
retries. `DATA_AGGREGATION` is the only type registered today, and its handler
is a simulation.
