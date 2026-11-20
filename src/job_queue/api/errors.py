from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from job_queue.domain.errors import (
    QueueFullError,
    ServiceShuttingDownError,
    TaskNotCancellableError,
    TaskNotFoundError,
    UnknownTaskTypeError,
)


def _error(status_code: int, code: str, message: str, **extra: object) -> JSONResponse:
    return JSONResponse(
        status_code=status_code, content={"error": code, "message": message, **extra}
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
            for err in exc.errors()
        ]
        return _error(
            400,
            "INVALID_REQUEST",
            "Request validation failed.",
            details=jsonable_encoder(details),
        )

    @app.exception_handler(UnknownTaskTypeError)
    async def unknown_task_type(_: Request, exc: UnknownTaskTypeError) -> JSONResponse:
        return _error(400, "UNKNOWN_TASK_TYPE", f"Unsupported task_type '{exc.task_type}'.")

    @app.exception_handler(TaskNotFoundError)
    async def task_not_found(_: Request, exc: TaskNotFoundError) -> JSONResponse:
        return _error(404, "TASK_NOT_FOUND", f"Task '{exc.task_id}' was not found.")

    @app.exception_handler(TaskNotCancellableError)
    async def task_not_cancellable(_: Request, exc: TaskNotCancellableError) -> JSONResponse:
        return _error(
            409,
            "TASK_NOT_CANCELLABLE",
            f"Task is {exc.status.value}. Only QUEUED tasks can be cancelled.",
        )

    @app.exception_handler(QueueFullError)
    async def queue_full(_: Request, exc: QueueFullError) -> JSONResponse:
        response = _error(
            429,
            "QUEUE_CAPACITY_EXCEEDED",
            "In-memory queue is currently at capacity. Please retry shortly.",
            retry_after_seconds=exc.retry_after_seconds,
        )
        response.headers["Retry-After"] = str(exc.retry_after_seconds)
        return response

    @app.exception_handler(ServiceShuttingDownError)
    async def shutting_down(_: Request, exc: ServiceShuttingDownError) -> JSONResponse:
        return _error(
            503, "SERVICE_UNAVAILABLE", "Service is shutting down and not accepting new tasks."
        )
