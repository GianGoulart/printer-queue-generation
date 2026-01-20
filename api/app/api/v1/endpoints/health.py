"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def healthz():
    """Simple health check for Kubernetes/Docker."""
    return {"status": "ok"}
