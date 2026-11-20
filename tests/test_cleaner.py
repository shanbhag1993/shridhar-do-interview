import asyncio
from datetime import timedelta

from helpers import echo, registry, submit, wait_for_status

from job_queue.domain import Task, TaskStatus, utcnow
from job_queue.services.cleaner import Cleaner


def _task(task_id: str, status: TaskStatus, finished_seconds_ago: float | None) -> Task:
    task = Task(id=task_id, task_type="ECHO", payload={}, status=status)
    if finished_seconds_ago is not None:
        task.completed_at = utcnow() - timedelta(seconds=finished_seconds_ago)
    return task


async def test_sweep_evicts_only_terminal_tasks_older_than_ttl():
    store = {
        t.id: t
        for t in (
            _task("old-completed", TaskStatus.COMPLETED, 120),
            _task("old-failed", TaskStatus.FAILED, 120),
            _task("old-cancelled", TaskStatus.CANCELLED, 120),
            _task("fresh-completed", TaskStatus.COMPLETED, 10),
            _task("queued", TaskStatus.QUEUED, None),
            _task("running", TaskStatus.RUNNING, None),
        )
    }
    cleaner = Cleaner(store=store, lock=asyncio.Lock(), ttl_seconds=60, interval_seconds=60)

    evicted = await cleaner.sweep()

    assert evicted == 3
    assert set(store) == {"fresh-completed", "queued", "running"}


async def test_finished_task_is_evicted_after_ttl(start_app):
    client, service = await start_app(
        registry(ECHO=echo), retention_ttl_seconds=0.05, cleaner_interval_seconds=0.02
    )

    task_id = await submit(client, "ECHO")
    await wait_for_status(client, task_id, "COMPLETED")
    assert service.stats().stored_tasks == 1

    for _ in range(200):
        if (await client.get(f"/v1/tasks/{task_id}")).status_code == 404:
            break
        await asyncio.sleep(0.01)

    assert (await client.get(f"/v1/tasks/{task_id}")).status_code == 404
    assert service.stats().stored_tasks == 0


async def test_unfinished_task_is_never_evicted(start_app):
    gate = asyncio.Event()

    async def blocked(payload):
        await gate.wait()

    client, _ = await start_app(
        registry(BLOCK=blocked), retention_ttl_seconds=0.01, cleaner_interval_seconds=0.01
    )

    task_id = await submit(client, "BLOCK")
    await wait_for_status(client, task_id, "RUNNING")
    await asyncio.sleep(0.1)  # many sweep intervals and TTLs

    assert (await client.get(f"/v1/tasks/{task_id}")).json()["status"] == "RUNNING"
    gate.set()
