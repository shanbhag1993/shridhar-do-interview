# `job_queue.domain`

The core types shared by the rest of the package: what a task is, which states
it can be in, and which errors the service raises. Nothing here depends on
FastAPI or on any other part of the package.

## Files

| File | Contains |
| :--- | :--- |
| `status.py` | `TaskStatus`: the enum `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, with `is_terminal` true for the last three. |
| `task.py` | `Task`: the dataclass held in the task store and passed through the queue. Also `utcnow()`, the timezone-aware clock used for all timestamps. |
| `errors.py` | `JobQueueError` and its subclasses, which the API layer maps to HTTP responses (table below). |
| `__init__.py` | Re-exports `Task`, `TaskStatus`, and `utcnow`. |

## `Task` fields

| Field | Meaning |
| :--- | :--- |
| `id` | UUID assigned at submission |
| `task_type`, `payload` | Which handler runs, and its input |
| `priority` | Stored and returned; it does not affect ordering, which is FIFO |
| `max_retries`, `timeout_seconds` | Per-task limits from the request |
| `status`, `retry_count` | Current state and how many retries have been used |
| `result`, `error` | Handler output, or the failure text |
| `submitted_at`, `started_at`, `completed_at` | Timestamps in UTC. `started_at` is the start of the most recent attempt. |
| `duration_ms` (property) | `completed_at - started_at`, or `None` until the task finishes |

## State transitions

```text
QUEUED  -> RUNNING     a worker claims the task
RUNNING -> COMPLETED   the handler returned
RUNNING -> QUEUED      the handler raised and retries remain; re-enqueued after a backoff
RUNNING -> FAILED      the handler raised with no retries left, or it timed out
QUEUED  -> CANCELLED   DELETE /v1/tasks/{id}
```

## Errors

| Exception | Raised when |
| :--- | :--- |
| `QueueFullError` | The queue is at capacity on submit |
| `ServiceShuttingDownError` | A task is submitted after shutdown has started |
| `UnknownTaskTypeError` | No handler is registered for the `task_type` |
| `TaskNotFoundError` | The task id is not in the store |
| `TaskNotCancellableError` | Cancel is requested for a task that is not `QUEUED` |
