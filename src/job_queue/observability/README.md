# `job_queue.observability`

In-process counters describing what the service has done since it started.

## Files

| File | Contains |
| :--- | :--- |
| `metrics.py` | `Metrics`: a dataclass of integer counters (table below). |
| `__init__.py` | Re-exports `Metrics`. |

## Counters

| Counter | Incremented by | When |
| :--- | :--- | :--- |
| `tasks_enqueued_total` | `TaskService.submit` | A task is accepted |
| `tasks_rejected_total` | `TaskService.submit` | A submission is refused because the queue is full |
| `tasks_cancelled_total` | `TaskService.cancel` | A queued task is cancelled |
| `tasks_completed_total` | `WorkerPool` | A handler returns successfully |
| `tasks_failed_total` | `WorkerPool` | A task ends as `FAILED` |
| `tasks_retried_total` | `WorkerPool` | A failed attempt is scheduled for retry |

One `Metrics` instance lives on the service as `TaskService.metrics`.

The counters are not exported yet: there is no `/metrics` endpoint. The
`/v1/health` endpoint does not read them either; it reports live queue depth
and worker counts from `TaskService.stats()`.
