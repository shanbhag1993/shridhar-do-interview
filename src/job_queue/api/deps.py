from typing import Annotated

from fastapi import Depends, Request

from job_queue.services import TaskService


def get_task_service(request: Request) -> TaskService:
    return request.app.state.task_service


TaskServiceDep = Annotated[TaskService, Depends(get_task_service)]
