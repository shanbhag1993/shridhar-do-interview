from dataclasses import dataclass


@dataclass(slots=True)
class Metrics:
    """In-process counters. Not exported yet; a /metrics endpoint can read these."""

    tasks_enqueued_total: int = 0
    tasks_rejected_total: int = 0
    tasks_completed_total: int = 0
    tasks_failed_total: int = 0
    tasks_cancelled_total: int = 0
    tasks_retried_total: int = 0
