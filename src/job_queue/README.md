# `job_queue`

The whole service: an HTTP API, a bounded in-memory queue, and a pool of worker
coroutines, all running in one Python process on one `asyncio` event loop.
Design: [`docs/design.md`](../../docs/design.md).

## Sub-modules

| Folder | Purpose |
| :--- | :--- |
| [`api/`](api/README.md) | HTTP layer: FastAPI app, routes, and error responses |
| [`schemas/`](schemas/README.md) | JSON shapes of requests and responses |
| [`services/`](services/README.md) | Runtime: queue, task store, worker pool, TTL cleaner, task handlers |
| [`domain/`](domain/README.md) | Core types: `Task`, `TaskStatus`, and the service's exceptions |
| [`observability/`](observability/README.md) | In-process counters |

## Files in this folder

| File | Contains |
| :--- | :--- |
| `main.py` | Entry point. Builds the `app` object and `run()`, which configures logging and starts Uvicorn on `HOST`:`PORT`. The container runs `python -m job_queue.main`. |
| `config.py` | `Settings`: every runtime option, read from environment variables and validated at startup (queue capacity, worker count, TTL, drain timeout, retry backoff, port). |
| `__init__.py` | Package marker. |

## How a request flows

```text
POST /v1/tasks
  api/routes/tasks.py      validate body (schemas/), call the service
  services/task_service.py put the task on the queue, record it in the store, return 202
  services/worker_pool.py  a worker takes it, runs the handler, records the result

GET /v1/tasks/{id}
  api/routes/tasks.py      read the task from the store via the service
```

## Dependency direction

`api` → `services` → `domain`. `schemas` depends only on `domain`, and
`domain` and `observability` import nothing from the rest of the package.
`services` knows nothing about HTTP.
