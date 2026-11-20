import asyncio
from typing import Any

from httpx import AsyncClient

from job_queue.services import HandlerRegistry
from job_queue.services.handlers import Handler


def registry(**handlers: Handler) -> HandlerRegistry:
    reg = HandlerRegistry()
    for task_type, handler in handlers.items():
        reg.register(task_type, handler)
    return reg


async def echo(payload: dict[str, Any]) -> dict[str, Any]:
    return {"echo": payload}


async def submit(client: AsyncClient, task_type: str, **body: Any) -> str:
    resp = await client.post("/v1/tasks", json={"task_type": task_type, **body})
    assert resp.status_code == 202, resp.text
    return resp.json()["task_id"]


async def wait_for_status(
    client: AsyncClient, task_id: str, *statuses: str, timeout: float = 3.0
) -> dict[str, Any]:
    """Poll GET /v1/tasks/{id} until the task reaches one of `statuses`."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        resp = await client.get(f"/v1/tasks/{task_id}")
        body = resp.json()
        if resp.status_code == 200 and body["status"] in statuses:
            return body
        if loop.time() > deadline:
            raise AssertionError(f"task {task_id} never reached {statuses}; last response: {body}")
        await asyncio.sleep(0.005)
