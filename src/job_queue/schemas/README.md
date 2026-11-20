# `job_queue.schemas`

The JSON shapes of the API, as Pydantic models. Request models validate what
clients send; response models define what the API returns. They are separate
from `domain.Task` so the wire format can change without touching the runtime.

## Files

| File | Contains |
| :--- | :--- |
| `tasks.py` | `SubmitTaskRequest`, `SubmitTaskResponse`, and `TaskStatusResponse`. |
| `health.py` | `HealthResponse`. |
| `__init__.py` | Re-exports the four models. |

## Models

| Model | Used by | Fields |
| :--- | :--- | :--- |
| `SubmitTaskRequest` | Body of `POST /v1/tasks` | `task_type`, `priority`, `payload`, `max_retries`, `timeout_seconds` |
| `SubmitTaskResponse` | `202` reply to `POST /v1/tasks` | `task_id`, `status`, `submitted_at`, `poll_url` |
| `TaskStatusResponse` | Replies to `GET` and `DELETE /v1/tasks/{id}` | `task_id`, `status`, `task_type`, `priority`, timestamps, `duration_ms`, `retry_count`, `result`, `error` |
| `HealthResponse` | Reply to `GET /v1/health` | `status`, `queue_depth`, `queue_capacity`, `active_workers`, `total_workers`, `uptime_seconds` |

`TaskStatusResponse.from_task(task)` builds the response from a `domain.Task`.

## Request limits

| Field | Rule | Default |
| :--- | :--- | :--- |
| `task_type` | Required, 1 to 64 characters | none |
| `priority` | Integer, 0 or more | `0` |
| `payload` | JSON object | `{}` |
| `max_retries` | 0 to 10 | `0` |
| `timeout_seconds` | Greater than 0, at most 3600 | `30` |

A body that breaks these rules is rejected with `400 INVALID_REQUEST`.
