import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

Handler = Callable[[dict[str, Any]], Awaitable[Any]]


class HandlerRegistry:
    """Maps a task_type to the coroutine that performs the work."""

    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, task_type: str, handler: Handler) -> None:
        self._handlers[task_type] = handler

    def get(self, task_type: str) -> Handler:
        return self._handlers[task_type]

    def __contains__(self, task_type: object) -> bool:
        return task_type in self._handlers


async def data_aggregation(payload: dict[str, Any]) -> dict[str, Any]:
    """Simulated I/O-bound aggregation job. Replace with the real unit of work."""
    await asyncio.sleep(0.2)
    return {
        "dataset_id": payload.get("dataset_id"),
        "operations_applied": list(payload.get("operations", [])),
        "summary_url": payload.get("destination"),
    }


def default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register("DATA_AGGREGATION", data_aggregation)
    return registry
