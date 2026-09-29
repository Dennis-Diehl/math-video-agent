import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import jobs as job_routes
from config.config import settings
from jobs.sandbox import DockerSandbox, Sandbox
from jobs.store import JobStore
from jobs.worker import Worker, start_workers, stop_workers

API_PREFIX = "/api/v1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def create_app(sandbox: Sandbox | None = None) -> FastAPI:
    """`sandbox` defaults to Docker; tests pass a fake."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        # The API never calls Gemini itself, but every job would fail without a key.
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set. Add it to backend/.env.")
        store = JobStore(
            output_root=Path(settings.job_output_dir),
            max_queued=settings.max_queued_jobs,
            ttl_seconds=settings.job_ttl_seconds,
        )
        app.state.store = store
        workers = start_workers(Worker(store, sandbox or DockerSandbox()))
        yield
        await stop_workers(workers)

    app = FastAPI(title="Math Video Agent", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Unversioned: the Docker healthcheck depends on this path."""
        return {"status": "ok"}

    api = APIRouter(prefix=API_PREFIX)
    api.include_router(job_routes.router)
    app.include_router(api)
    return app


app = create_app()
