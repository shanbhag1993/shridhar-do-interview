# `job_queue.api`

The HTTP layer. It turns HTTP requests into calls on `TaskService` and turns
the service's exceptions into JSON error responses. It holds no queue or worker
logic.

## Files

| File | Contains |
| :--- | :--- |
| `app.py` | `create_app(settings, handlers)`: the FastAPI application factory. Its lifespan creates the `TaskService`, stores it on `app.state.task_service`, starts the workers, and on exit calls `shutdown()` to drain the queue. Also registers the error handlers and routers. |
| `deps.py` | `get_task_service` and the `TaskServiceDep` annotation, which give route functions the running `TaskService`. |
| `errors.py` | `register_error_handlers(app)`: maps each exception to a status code and a JSON body (table below). |
| `__init__.py` | Re-exports `create_app`. |
| [`routes/`](routes/README.md) | The endpoint functions. |

## Error responses

Every error body has the shape `{"error": "<CODE>", "message": "<text>"}`.

| Exception | Status | `error` code |
| :--- | :--- | :--- |
| Request body fails validation | `400` | `INVALID_REQUEST` (adds a `details` list) |
| `UnknownTaskTypeError` | `400` | `UNKNOWN_TASK_TYPE` |
| `TaskNotFoundError` | `404` | `TASK_NOT_FOUND` |
| `TaskNotCancellableError` | `409` | `TASK_NOT_CANCELLABLE` |
| `QueueFullError` | `429` | `QUEUE_CAPACITY_EXCEEDED` (adds `retry_after_seconds` and a `Retry-After` header) |
| `ServiceShuttingDownError` | `503` | `SERVICE_UNAVAILABLE` |

## Shutdown

On `SIGTERM` or `SIGINT`, Uvicorn stops accepting requests and then leaves the
lifespan in `app.py`. That is where the queue is drained, for up to
`DRAIN_TIMEOUT_SECONDS`.
