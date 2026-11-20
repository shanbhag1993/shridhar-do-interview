import asyncio

from helpers import echo, registry, submit, wait_for_status


async def test_cancel_unknown_task_returns_404(start_app):
    client, _ = await start_app()

    resp = await client.delete("/v1/tasks/does-not-exist")

    assert resp.status_code == 404
    assert resp.json()["error"] == "TASK_NOT_FOUND"


async def test_cancel_queued_task_returns_200_and_task_never_runs(start_app):
    gate = asyncio.Event()
    executed: list[str] = []

    async def blocked(payload):
        executed.append(payload["name"])
        await gate.wait()

    client, service = await start_app(registry(BLOCK=blocked), num_workers=1)

    running = await submit(client, "BLOCK", payload={"name": "running"})
    await wait_for_status(client, running, "RUNNING")
    victim = await submit(client, "BLOCK", payload={"name": "victim"})
    after = await submit(client, "BLOCK", payload={"name": "after"})

    resp = await client.delete(f"/v1/tasks/{victim}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "CANCELLED"
    assert body["completed_at"] is not None
    assert body["started_at"] is None

    # Let the worker go past the cancelled task and finish the one behind it.
    gate.set()
    await wait_for_status(client, after, "COMPLETED")

    assert executed == ["running", "after"]
    assert (await client.get(f"/v1/tasks/{victim}")).json()["status"] == "CANCELLED"
    assert service.metrics.tasks_cancelled_total == 1


async def test_cancel_running_task_returns_409(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()
        return {"done": True}

    client, _ = await start_app(registry(BLOCK=blocked))

    task_id = await submit(client, "BLOCK")
    await wait_for_status(client, task_id, "RUNNING")

    resp = await client.delete(f"/v1/tasks/{task_id}")

    assert resp.status_code == 409
    assert resp.json()["error"] == "TASK_NOT_CANCELLABLE"

    # The running task is unaffected.
    gate.set()
    body = await wait_for_status(client, task_id, "COMPLETED")
    assert body["result"] == {"done": True}


async def test_cancel_finished_or_already_cancelled_task_returns_409(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, _ = await start_app(registry(ECHO=echo, BLOCK=blocked), num_workers=1)

    completed = await submit(client, "ECHO")
    await wait_for_status(client, completed, "COMPLETED")
    assert (await client.delete(f"/v1/tasks/{completed}")).status_code == 409

    running = await submit(client, "BLOCK")
    await wait_for_status(client, running, "RUNNING")
    queued = await submit(client, "BLOCK")
    assert (await client.delete(f"/v1/tasks/{queued}")).status_code == 200
    assert (await client.delete(f"/v1/tasks/{queued}")).status_code == 409
    gate.set()


async def test_cancel_during_retry_backoff_stops_the_retry(start_app):
    attempts = 0

    async def boom(payload):
        nonlocal attempts
        attempts += 1
        raise RuntimeError("always fails")

    client, service = await start_app(
        registry(BOOM=boom), retry_backoff_base_seconds=5, retry_backoff_max_seconds=5
    )

    task_id = await submit(client, "BOOM", max_retries=3)
    # After the first failure the task is QUEUED again, waiting out its backoff.
    while (await client.get(f"/v1/tasks/{task_id}")).json()["retry_count"] != 1:
        await asyncio.sleep(0.005)

    resp = await client.delete(f"/v1/tasks/{task_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "CANCELLED"

    # Shutdown must not wait 5 s for the cancelled task's backoff timer.
    loop = asyncio.get_running_loop()
    started = loop.time()
    await service.shutdown()
    assert loop.time() - started < 1
    assert attempts == 1
