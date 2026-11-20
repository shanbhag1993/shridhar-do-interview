import asyncio
from datetime import datetime

from helpers import echo, registry, submit, wait_for_status


async def test_get_unknown_task_returns_404(start_app):
    client, _ = await start_app()

    resp = await client.get("/v1/tasks/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["error"] == "TASK_NOT_FOUND"


async def test_task_runs_to_completed_with_result_and_timings(start_app):
    client, _ = await start_app()  # default registry: simulated DATA_AGGREGATION

    task_id = await submit(
        client,
        "DATA_AGGREGATION",
        priority=1,
        payload={
            "dataset_id": "ds-9982",
            "operations": ["FILTER", "SUMMARIZE"],
            "destination": "s3://output-bucket/report.csv",
        },
    )
    body = await wait_for_status(client, task_id, "COMPLETED")

    assert body["task_id"] == task_id
    assert body["task_type"] == "DATA_AGGREGATION"
    assert body["priority"] == 1
    assert body["retry_count"] == 0
    assert body["error"] is None
    assert body["result"] == {
        "dataset_id": "ds-9982",
        "operations_applied": ["FILTER", "SUMMARIZE"],
        "summary_url": "s3://output-bucket/report.csv",
    }
    submitted, started, completed = (
        datetime.fromisoformat(body[key]) for key in ("submitted_at", "started_at", "completed_at")
    )
    assert submitted <= started <= completed
    assert body["duration_ms"] >= 190  # the simulated handler sleeps 200 ms


async def test_status_shows_queued_then_running(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, _ = await start_app(registry(BLOCK=blocked), num_workers=1)

    first = await submit(client, "BLOCK")
    second = await submit(client, "BLOCK")

    running = await wait_for_status(client, first, "RUNNING")
    assert running["started_at"] is not None
    assert running["completed_at"] is None and running["duration_ms"] is None

    waiting = (await client.get(f"/v1/tasks/{second}")).json()
    assert waiting["status"] == "QUEUED"
    assert waiting["started_at"] is None

    gate.set()
    await wait_for_status(client, second, "COMPLETED")


async def test_handler_exception_marks_task_failed_and_worker_survives(start_app):
    async def boom(payload):
        raise ValueError("bad dataset")

    client, service = await start_app(registry(BOOM=boom, ECHO=echo), num_workers=1)

    failed_id = await submit(client, "BOOM")
    failed = await wait_for_status(client, failed_id, "FAILED")

    assert failed["error"] == "ValueError: bad dataset"
    assert failed["result"] is None
    assert failed["completed_at"] is not None

    # The single worker is still alive and processes the next task.
    ok_id = await submit(client, "ECHO", payload={"n": 1})
    ok = await wait_for_status(client, ok_id, "COMPLETED")
    assert ok["result"] == {"echo": {"n": 1}}
    assert service.stats().total_workers == 1


async def test_task_exceeding_timeout_is_failed_with_timeout(start_app):
    async def slow(payload):
        await asyncio.sleep(30)

    client, _ = await start_app(registry(SLOW=slow))

    task_id = await submit(client, "SLOW", timeout_seconds=0.05, max_retries=3)
    body = await wait_for_status(client, task_id, "FAILED")

    assert body["error"] == "TIMEOUT"
    assert body["retry_count"] == 0  # timeouts are not retried
    assert body["duration_ms"] < 1000


async def test_failed_task_is_retried_until_it_succeeds(start_app):
    attempts = 0

    async def flaky(payload):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RuntimeError(f"attempt {attempts} failed")
        return {"attempts": attempts}

    client, service = await start_app(registry(FLAKY=flaky))

    task_id = await submit(client, "FLAKY", max_retries=3)
    body = await wait_for_status(client, task_id, "COMPLETED")

    assert attempts == 3
    assert body["retry_count"] == 2
    assert body["result"] == {"attempts": 3}
    assert body["error"] is None
    assert service.metrics.tasks_retried_total == 2


async def test_task_is_failed_once_retries_are_exhausted(start_app):
    attempts = 0

    async def boom(payload):
        nonlocal attempts
        attempts += 1
        raise RuntimeError(f"attempt {attempts} failed")

    client, _ = await start_app(registry(BOOM=boom))

    task_id = await submit(client, "BOOM", max_retries=2)
    body = await wait_for_status(client, task_id, "FAILED")

    assert attempts == 3  # first attempt + 2 retries
    assert body["retry_count"] == 2
    assert body["error"] == "RuntimeError: attempt 3 failed"


async def test_retry_waits_for_backoff_before_running_again(start_app):
    loop = asyncio.get_running_loop()
    attempt_times: list[float] = []

    async def fail_once(payload):
        attempt_times.append(loop.time())
        if len(attempt_times) == 1:
            raise RuntimeError("first attempt failed")

    client, _ = await start_app(
        registry(FLAKY=fail_once), retry_backoff_base_seconds=0.1, retry_backoff_max_seconds=1
    )

    task_id = await submit(client, "FLAKY", max_retries=1)
    await wait_for_status(client, task_id, "COMPLETED")

    # backoff = base * 2^0 + jitter in [0, base]  ->  between 0.1 s and 0.2 s
    assert 0.09 <= attempt_times[1] - attempt_times[0] < 0.5


async def test_single_worker_processes_tasks_in_fifo_order(start_app):
    order: list[int] = []

    async def record(payload):
        order.append(payload["n"])

    client, _ = await start_app(registry(RECORD=record), num_workers=1)

    ids = [await submit(client, "RECORD", payload={"n": n}) for n in range(20)]
    for task_id in ids:
        await wait_for_status(client, task_id, "COMPLETED")

    assert order == list(range(20))


async def test_concurrent_workers_run_each_task_exactly_once(start_app):
    seen: list[int] = []
    in_flight = 0
    peak = 0

    async def record(payload):
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.01)
        seen.append(payload["n"])
        in_flight -= 1

    client, service = await start_app(registry(RECORD=record), queue_capacity=200, num_workers=8)

    ids = await asyncio.gather(*(submit(client, "RECORD", payload={"n": n}) for n in range(200)))
    for task_id in ids:
        await wait_for_status(client, task_id, "COMPLETED")

    assert sorted(seen) == list(range(200))  # nothing lost, nothing run twice
    assert peak == 8  # all workers consumed the queue at the same time
    assert service.metrics.tasks_completed_total == 200
