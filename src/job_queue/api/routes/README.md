# `job_queue.api.routes`

The endpoint functions. Each one validates input through a schema, calls one
`TaskService` method, and returns a response model. Errors are raised as
exceptions and converted to HTTP responses by `api/errors.py`.

## Files

| File | Contains |
| :--- | :--- |
| `tasks.py` | Router for `/v1/tasks`: `submit_task`, `get_task`, `cancel_task`. |
| `health.py` | Router for `/v1/health`: `health`. |
| `__init__.py` | Package marker. |

## Endpoints

| Method and path | Function | Success | Errors |
| :--- | :--- | :--- | :--- |
| `POST /v1/tasks` | `submit_task` | `202` with `task_id`, `status`, `submitted_at`, `poll_url` | `400`, `429`, `503` |
| `GET /v1/tasks/{task_id}` | `get_task` | `200` with status, timings, result or error | `404` |
| `DELETE /v1/tasks/{task_id}` | `cancel_task` | `200` with the task, now `CANCELLED` | `404`, `409` if the task is not `QUEUED` |
| `GET /v1/health` | `health` | `200` with `HEALTHY` and queue and worker counts | `503` with `SHUTTING_DOWN` once shutdown starts |

`submit_task` returns as soon as the task is on the queue. It does not wait for
the task to run.
