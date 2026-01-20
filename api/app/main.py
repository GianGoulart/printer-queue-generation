"""Main FastAPI application."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.config import settings

app = FastAPI(
    title="Printer Queue Service",
    description="Multi-tenant service for DTF base automation",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Configure properly in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(api_router, prefix="/v1")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    from app.database import engine
    from sqlalchemy import text
    import redis

    # Check database
    db_status = "disconnected"
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"

    # Check Redis
    redis_status = "disconnected"
    try:
        r = redis.from_url(settings.redis_url)
        r.ping()
        redis_status = "connected"
    except Exception as e:
        redis_status = f"error: {str(e)}"

    overall_status = "ok" if db_status == "connected" and redis_status == "connected" else "degraded"

    return {
        "status": overall_status,
        "db": db_status,
        "redis": redis_status,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
    )
