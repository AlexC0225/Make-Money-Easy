from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import get_settings
from app.db.session import create_db_and_tables
from app.jobs.scheduler import build_scheduler


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    create_db_and_tables()
    scheduler = None
    if settings.scheduler_enabled:
        scheduler = build_scheduler()
        scheduler.start()

    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        debug=settings.debug,
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", tags=["system"])
    def healthcheck() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name, "env": settings.env}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
