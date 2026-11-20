import asyncio
from datetime import datetime

from helpers import echo, registry, submit, wait_for_status

DESIGN_EXAMPLE = {
    "task_type": "DATA_AGGREGATION",
    "priority": 1,
    "payload": {
        "dataset_id": "ds-9982",
        "operations": ["FILTER", "SUMMARIZE"],
        "destination": "s3://output-bucket/report.csv",
    },
    "max_retries": 3,
    "timeout_seconds": 30,
}


async def test_submit_returns_202_with_task_id_and_poll_url(start_app):
    client, _ = await start_app()

    resp = await client.post("/v1/tasks", json=DESIGN_EXAMPLE)

    assert resp.status_code == 202
    body = resp.json()
    assert set(body) == {"task_id", "status", "submitted_at", "poll_url"}
    assert body["status"] == "QUEUED"
    assert body["poll_url"] == f"/v1/tasks/{body['task_id']}"
    assert datetime.fromisoformat(body["submitted_at"]).utcoffset().total_seconds() == 0


async def test_submit_returns_before_the_task_runs(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, _ = await start_app(registry(BLOCK=blocked))

    task_id = await submit(client, "BLOCK")  # would hang here if submit waited for execution

    assert (await wait_for_status(client, task_id, "RUNNING"))["completed_at"] is None
    gate.set()
    await wait_for_status(client, task_id, "COMPLETED")


async def test_submit_applies_defaults_for_optional_fields(start_app):
    client, _ = await start_app(registry(ECHO=echo))

    task_id = await submit(client, "ECHO")

    body = await wait_for_status(client, task_id, "COMPLETED")
    assert body["priority"] == 0
    assert body["result"] == {"echo": {}}


async def test_submit_rejects_missing_task_type_with_400(start_app):
    client, service = await start_app()

    resp = await client.post("/v1/tasks", json={"payload": {}})

    assert resp.status_code == 400
    body = resp.json()
    assert body["error"] == "INVALID_REQUEST"
    assert body["details"][0]["field"] == "body.task_type"
    assert service.stats().stored_tasks == 0


async def test_submit_rejects_invalid_field_values_with_400(start_app):
    client, _ = await start_app()

    for bad in (
        {"task_type": "DATA_AGGREGATION", "max_retries": -1},
        {"task_type": "DATA_AGGREGATION", "timeout_seconds": 0},
        {"task_type": "DATA_AGGREGATION", "payload": "not-an-object"},
        {"task_type": ""},
    ):
        resp = await client.post("/v1/tasks", json=bad)
        assert resp.status_code == 400, bad
        assert resp.json()["error"] == "INVALID_REQUEST"


async def test_submit_rejects_malformed_json_with_400(start_app):
    client, _ = await start_app()

    resp = await client.post(
        "/v1/tasks", content=b"{not json", headers={"content-type": "application/json"}
    )

    assert resp.status_code == 400
    assert resp.json()["error"] == "INVALID_REQUEST"


async def test_submit_rejects_unknown_task_type_with_400(start_app):
    client, service = await start_app()

    resp = await client.post("/v1/tasks", json={"task_type": "NOPE"})

    assert resp.status_code == 400
    assert resp.json()["error"] == "UNKNOWN_TASK_TYPE"
    assert service.stats().stored_tasks == 0


async def test_submit_returns_429_when_queue_is_full(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, service = await start_app(registry(BLOCK=blocked), queue_capacity=2, num_workers=1)

    # One task occupies the only worker, two more fill the queue.
    running = await submit(client, "BLOCK")
    await wait_for_status(client, running, "RUNNING")
    queued = [await submit(client, "BLOCK") for _ in range(2)]
    assert service.stats().queue_depth == 2

    resp = await client.post("/v1/tasks", json={"task_type": "BLOCK"})

    assert resp.status_code == 429
    assert resp.json() == {
        "error": "QUEUE_CAPACITY_EXCEEDED",
        "message": "In-memory queue is currently at capacity. Please retry shortly.",
        "retry_after_seconds": 3,
    }
    assert resp.headers["retry-after"] == "3"
    # The rejected submission leaves no record behind.
    assert service.stats().stored_tasks == 3
    assert service.metrics.tasks_rejected_total == 1

    # Once workers catch up, submissions are accepted again.
    gate.set()
    for task_id in (running, *queued):
        await wait_for_status(client, task_id, "COMPLETED")
    await submit(client, "BLOCK")
