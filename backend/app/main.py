"""FastAPI entry point.

Run locally:  uvicorn app.main:app --reload
Docs:         http://localhost:8000/docs
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import ai, auth, billing, connectors, dashboards, datasets, orgs, stream
from app.core.config import settings
from app.core.database import Base, engine

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Simple for a project: create tables on boot. Swap for Alembic migrations
    # (alembic revision --autogenerate) once the schema settles.
    Base.metadata.create_all(engine)
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=f"{settings.APP_NAME} API", version="1.0.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for r in (auth, orgs, datasets, connectors, dashboards, ai, billing, stream):
        app.include_router(r.router, prefix="/api/v1")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
