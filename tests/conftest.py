from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from job_queue.api import create_app
from job_queue.config import Settings
from job_queue.services import HandlerRegistry, TaskService

TEST_SETTINGS: dict[str, Any] = {
    "queue_capacity": 100,
    "num_workers": 2,
    "drain_timeout_seconds": 2,
    "retry_backoff_base_seconds": 0.01,
    "retry_backoff_max_seconds": 0.05,
}

StartApp = Callable[..., Awaitable[tuple[AsyncClient, TaskService]]]


def make_settings(**overrides: Any) -> Settings:
    return Settings(**{**TEST_SETTINGS, **overrides})


@pytest.fixture
async def start_app() -> AsyncIterator[StartApp]:
    """Start the app with its lifespan (workers + cleaner) on the test's event loop.

    Returns an HTTP client bound to the app and the running TaskService.
    The app is shut down, including the queue drain, when the test ends.
    """
    async with AsyncExitStack() as stack:

        async def _start(
            handlers: HandlerRegistry | None = None, **overrides: Any
        ) -> tuple[AsyncClient, TaskService]:
            app = create_app(settings=make_settings(**overrides), handlers=handlers)
            await stack.enter_async_context(app.router.lifespan_context(app))
            client = await stack.enter_async_context(
                AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
            )
            return client, app.state.task_service

        yield _start
