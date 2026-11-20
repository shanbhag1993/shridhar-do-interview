from fastapi import APIRouter

from job_queue.api.deps import TaskServiceDep
from job_queue.schemas import SubmitTaskRequest, SubmitTaskResponse, TaskStatusResponse

router = APIRouter(prefix="/v1/tasks", tags=["tasks"])


@router.post("", status_code=202, response_model=SubmitTaskResponse)
async def submit_task(body: SubmitTaskRequest, service: TaskServiceDep) -> SubmitTaskResponse:
    task = await service.submit(
        task_type=body.task_type,
        payload=body.payload,
        priority=body.priority,
        max_retries=body.max_retries,
        timeout_seconds=body.timeout_seconds,
    )
    return SubmitTaskResponse(
        task_id=task.id,
        status=task.status,
        submitted_at=task.submitted_at,
        poll_url=f"/v1/tasks/{task.id}",
    )


@router.get("/{task_id}", response_model=TaskStatusResponse)
async def get_task(task_id: str, service: TaskServiceDep) -> TaskStatusResponse:
    return TaskStatusResponse.from_task(await service.get(task_id))


@router.delete("/{task_id}", response_model=TaskStatusResponse)
async def cancel_task(task_id: str, service: TaskServiceDep) -> TaskStatusResponse:
    return TaskStatusResponse.from_task(await service.cancel(task_id))
