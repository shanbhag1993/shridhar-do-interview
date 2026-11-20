from fastapi import APIRouter, Response

from job_queue.api.deps import TaskServiceDep
from job_queue.schemas import HealthResponse

router = APIRouter(prefix="/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
async def health(service: TaskServiceDep, response: Response) -> HealthResponse:
    stats = service.stats()
    if not stats.accepting:
        response.status_code = 503
    return HealthResponse(
        status="HEALTHY" if stats.accepting else "SHUTTING_DOWN",
        queue_depth=stats.queue_depth,
        queue_capacity=stats.queue_capacity,
        active_workers=stats.active_workers,
        total_workers=stats.total_workers,
        uptime_seconds=stats.uptime_seconds,
    )
