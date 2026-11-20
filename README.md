# REST API with Message Queue Backend

In-memory asynchronous job processing service: a FastAPI REST API, a bounded
`asyncio.Queue`, and a pool of worker coroutines, all in one process and one
container. Design: [`docs/design.md`](docs/design.md).

## Run in Docker

```bash
docker compose up --build        # serves http://localhost:8000
```

Or run the image from the registry:

```bash
docker run -d --name job-queue --restart unless-stopped --stop-timeout 40 \
  -p 8000:8000 -e QUEUE_CAPACITY=10000 -e NUM_WORKERS=16 \
  registry.digitalocean.com/shridhar-job-queue/job-queue:latest
```

Keep the stop timeout above `DRAIN_TIMEOUT_SECONDS`. Docker's default is 10
seconds, after which it kills the container while it is still draining.

Run only one instance. The queue and task store live in process memory, so a
restart drops queued and running tasks, and a second replica would not share state.

## API

| Method | Path | Result |
| :--- | :--- | :--- |
| `POST` | `/v1/tasks` | `202` with `task_id`; `400` invalid body or unknown `task_type`; `429` queue full; `503` shutting down |
| `GET` | `/v1/tasks/{id}` | `200` status, timings, result or error; `404` |
| `DELETE` | `/v1/tasks/{id}` | `200` cancelled; `409` if not `QUEUED`; `404` |
| `GET` | `/v1/health` | `200` queue and worker metrics; `503` shutting down |

```bash
curl -X POST localhost:8000/v1/tasks -H 'content-type: application/json' \
  -d '{"task_type":"DATA_AGGREGATION","payload":{"dataset_id":"ds-9982"},"max_retries":3}'
curl localhost:8000/v1/tasks/<task_id>
```

`DATA_AGGREGATION` is the only registered task type and its handler is a
simulation. Add real work in `src/job_queue/services/handlers.py`.

## Configuration

| Variable | Default | Meaning |
| :--- | :--- | :--- |
| `PORT` | `8000` | Listen port |
| `QUEUE_CAPACITY` | `10000` | Max queued tasks before `429` |
| `NUM_WORKERS` | `16` | Concurrent worker coroutines |
| `RETENTION_TTL_SECONDS` | `3600` | How long finished tasks stay queryable (`RETENTION_TTL` also accepted) |
| `CLEANER_INTERVAL_SECONDS` | `60` | How often finished tasks are swept |
| `DRAIN_TIMEOUT_SECONDS` | `30` | Grace period for queued work on `SIGTERM` |
| `RETRY_BACKOFF_BASE_SECONDS` | `0.5` | Base of the exponential retry backoff |
| `RETRY_BACKOFF_MAX_SECONDS` | `30` | Backoff ceiling |
| `RETRY_AFTER_SECONDS` | `3` | Retry hint returned with `429` |
| `LOG_LEVEL` | `INFO` | Log level |

## Build, test, and release

Everything goes through `make`. Run `make help` for the full list.

| Command | What it does |
| :--- | :--- |
| `make venv` | Create the project virtualenv `.venv` and install dependencies |
| `make compile` | Byte-compile `src` and `tests`; fails on a syntax error |
| `make test` | Run the unit tests |
| `make run` | Run the service locally on port 8000 |
| `make build` | Build the `linux/amd64` image, tagged with the git SHA and `latest` |
| `make smoke` | Build, then run the end-to-end smoke test against the image |
| `make push` | Build, log in to the registry, and push both tags |
| `make release` | `compile`, `test`, `smoke`, then `push`; stops at the first failure |
| `make clean` | Remove `.venv` and caches |

### Virtualenv

`make venv` needs Python 3.11+ to create `.venv`. If your `python3` is older,
point it at a newer one once: `make venv PYTHON=/path/to/python3.12`.

Every `make` target uses `.venv` automatically. For commands you type yourself,
activate it once per terminal:

```bash
source .venv/bin/activate
pytest -k cancel
```

### Registry

Images go to `registry.digitalocean.com/shridhar-job-queue/job-queue`.

```bash
export DIGITALOCEAN_TOKEN=...   # API token with registry write access
make release
```

- **Tags:** each push sets `<git-short-sha>` and `latest`. The SHA tag gets a
  `-dirty` suffix when built from uncommitted changes, so commit first for a
  tag you can roll back to.
- **Platform:** the image is built for `linux/amd64` to match the Droplet,
  whatever machine builds it.
- **Overrides:** `make push REGISTRY=<host>/<name> TAG=<tag>`.
