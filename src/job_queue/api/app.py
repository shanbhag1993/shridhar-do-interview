from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from job_queue.api.errors import register_error_handlers
from job_queue.api.routes import health, tasks
from job_queue.config import Settings
from job_queue.services import HandlerRegistry, TaskService


def create_app(
    settings: Settings | None = None, handlers: HandlerRegistry | None = None
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        service = TaskService(settings, handlers)
        app.state.task_service = service
        await service.start()
        try:
            yield
        finally:
            # Uvicorn runs this on SIGTERM/SIGINT after it stops taking requests.
            await service.shutdown()

    app = FastAPI(title="In-Memory Job Queue", version="0.1.0", lifespan=lifespan)
    register_error_handlers(app)
    app.include_router(tasks.router)
    app.include_router(health.router)
    return app
