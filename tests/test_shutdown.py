import asyncio

import pytest
from conftest import make_settings
from helpers import echo, registry

from job_queue.domain import TaskStatus
from job_queue.domain.errors import ServiceShuttingDownError
from job_queue.services import TaskService


async def test_shutdown_drains_queued_and_running_tasks():
    async def work(payload):
        await asyncio.sleep(0.02)
        return {"n": payload["n"]}

    service = TaskService(make_settings(num_workers=2), registry(WORK=work))
    await service.start()
    tasks = [await service.submit(task_type="WORK", payload={"n": n}) for n in range(10)]

    await service.shutdown()

    assert [t.status for t in tasks] == [TaskStatus.COMPLETED] * 10
    assert [t.result for t in tasks] == [{"n": n} for n in range(10)]
    assert service.stats().queue_depth == 0
    assert service.stats().active_workers == 0


async def test_shutdown_waits_for_a_pending_retry():
    attempts = 0

    async def fail_once(payload):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("first attempt failed")
        return {"attempts": attempts}

    service = TaskService(
        make_settings(retry_backoff_base_seconds=0.05, retry_backoff_max_seconds=0.2),
        registry(FLAKY=fail_once),
    )
    await service.start()
    task = await service.submit(task_type="FLAKY", payload={}, max_retries=1)

    await service.shutdown()

    assert task.status is TaskStatus.COMPLETED
    assert task.retry_count == 1
    assert task.result == {"attempts": 2}


async def test_shutdown_gives_up_after_drain_timeout_and_stops_workers():
    cancelled = asyncio.Event()

    async def stuck(payload):
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    service = TaskService(make_settings(drain_timeout_seconds=0.1), registry(STUCK=stuck))
    await service.start()
    task = await service.submit(task_type="STUCK", payload={}, timeout_seconds=3600)

    loop = asyncio.get_running_loop()
    started = loop.time()
    await service.shutdown()
    elapsed = loop.time() - started

    assert 0.1 <= elapsed < 1
    assert cancelled.is_set()  # the worker was cancelled, not left running
    assert task.status is TaskStatus.RUNNING  # never finished; lost with the process
    leftover = [t for t in asyncio.all_tasks() if t.get_name().startswith(("worker-", "ttl-"))]
    assert leftover == []


async def test_submit_is_rejected_after_shutdown_starts():
    service = TaskService(make_settings(), registry(ECHO=echo))
    await service.start()
    await service.shutdown()

    with pytest.raises(ServiceShuttingDownError):
        await service.submit(task_type="ECHO", payload={})


async def test_post_returns_503_after_shutdown_starts(start_app):
    client, service = await start_app(registry(ECHO=echo))
    await service.shutdown()

    resp = await client.post("/v1/tasks", json={"task_type": "ECHO"})

    assert resp.status_code == 503
    assert resp.json()["error"] == "SERVICE_UNAVAILABLE"


async def test_lifespan_exit_drains_accepted_tasks():
    """The path Uvicorn takes on SIGTERM: leaving the lifespan drains the queue."""
    from job_queue.api import create_app

    async def work(payload):
        await asyncio.sleep(0.02)

    app = create_app(settings=make_settings(num_workers=1), handlers=registry(WORK=work))
    async with app.router.lifespan_context(app):
        service: TaskService = app.state.task_service
        tasks = [await service.submit(task_type="WORK", payload={}) for _ in range(5)]
        assert tasks[-1].status is TaskStatus.QUEUED

    assert all(t.status is TaskStatus.COMPLETED for t in tasks)
