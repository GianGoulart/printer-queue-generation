"""API v1 router."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    assets,
    health,
    jobs,
    machines,
    sizing_profiles,
    storage,
    storage_configs,
    tenants,
)

api_router = APIRouter()

api_router.include_router(health.router, tags=["health"])
api_router.include_router(tenants.router, prefix="/tenants", tags=["tenants"])
api_router.include_router(machines.router, prefix="/machines", tags=["machines"])
api_router.include_router(sizing_profiles.router, prefix="/sizing-profiles", tags=["sizing-profiles"])
api_router.include_router(storage_configs.router, prefix="/storage-configs", tags=["storage-configs"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])
api_router.include_router(jobs.router, prefix="/jobs", tags=["jobs"])
