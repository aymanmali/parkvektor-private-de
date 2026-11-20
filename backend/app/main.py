from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import update

from app.api.v1 import admin, autopay, disputes, ingest, public, validations, violations
from app.core.config import get_settings
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import SessionLocal, engine
from app.models import entities  # noqa: F401
from app.models.entities import Lane


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    if settings.auto_seed_demo_data:
        with SessionLocal() as db:
            seed_demo_data(db)
            # Refresh demo lane heartbeats on startup so pilot cameras report online cleanly
            db.execute(update(Lane).values(last_heartbeat_at=datetime.now(UTC)))
            db.commit()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ParkVektor Private DE API",
        version="0.1.0",
        description=(
            "Barrierless ANPR Private Parking & Ticketing API for Germany "
            "(DSGVO Privacy-by-Design, Flexible Mall Tariffs, Stripe/Mock Payments)"
        ),
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(ingest.router, prefix="/api/v1")
    app.include_router(public.router, prefix="/api/v1")
    app.include_router(autopay.router, prefix="/api/v1")
    app.include_router(validations.router, prefix="/api/v1")
    app.include_router(violations.router, prefix="/api/v1")
    app.include_router(disputes.router, prefix="/api/v1")
    app.include_router(admin.router, prefix="/api/v1")

    @app.get("/health", tags=["Health"])
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "parkvektor-private-de"}

    @app.get("/ready", tags=["Health"])
    def ready() -> dict[str, str]:
        return {"status": "ready", "payment_provider": settings.payment_provider}

    return app


app = create_app()
