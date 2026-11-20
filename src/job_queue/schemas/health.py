from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["HEALTHY", "SHUTTING_DOWN"]
    queue_depth: int
    queue_capacity: int
    active_workers: int
    total_workers: int
    uptime_seconds: int
