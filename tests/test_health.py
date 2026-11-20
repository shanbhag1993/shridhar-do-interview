import asyncio

from helpers import registry, submit, wait_for_status


async def test_health_returns_200_with_queue_metrics(start_app):
    client, _ = await start_app(queue_capacity=50, num_workers=4)

    resp = await client.get("/v1/health")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "HEALTHY",
        "queue_depth": 0,
        "queue_capacity": 50,
        "active_workers": 0,
        "total_workers": 4,
        "uptime_seconds": 0,
    }


async def test_health_reports_queue_depth_and_active_workers(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, _ = await start_app(registry(BLOCK=blocked), num_workers=2)

    ids = [await submit(client, "BLOCK") for _ in range(5)]
    await wait_for_status(client, ids[0], "RUNNING")
    await wait_for_status(client, ids[1], "RUNNING")

    busy = (await client.get("/v1/health")).json()
    assert busy["active_workers"] == 2
    assert busy["queue_depth"] == 3

    gate.set()
    for task_id in ids:
        await wait_for_status(client, task_id, "COMPLETED")

    idle = (await client.get("/v1/health")).json()
    assert idle["active_workers"] == 0
    assert idle["queue_depth"] == 0


async def test_health_returns_503_once_shutdown_has_started(start_app):
    client, service = await start_app()

    await service.shutdown()
    resp = await client.get("/v1/health")

    assert resp.status_code == 503
    assert resp.json()["status"] == "SHUTTING_DOWN"
