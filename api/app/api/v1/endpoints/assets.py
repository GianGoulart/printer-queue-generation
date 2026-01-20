"""Asset endpoints."""

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.asset import Asset
from app.schemas.asset import (
    AssetListResponse,
    AssetReindexRequest,
    AssetReindexResponse,
    AssetReindexStatus,
    AssetResponse,
    AssetSearchRequest,
    AssetSearchResponse,
    AssetSearchResult,
    AssetWithMetadata,
)
from app.services.asset_service import search_assets_by_sku

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/reindex", response_model=AssetReindexResponse, status_code=status.HTTP_202_ACCEPTED)
def reindex_assets(
    request: AssetReindexRequest,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """Trigger asset reindexation for tenant.

    This endpoint dispatches an asynchronous task to reindex all assets
    from the tenant's storage. The task will:
    - List all files in storage
    - Extract SKU from filenames
    - Extract image metadata
    - Upsert assets in database

    Returns task ID to track progress.
    """
    from app.celery_app import celery_app

    try:
        # Dispatch async task by name (no need to import worker code)
        task = celery_app.send_task(
            "app.tasks.reindex.reindex_assets",
            args=[int(tenant_id)],
        )

        return AssetReindexResponse(
            task_id=task.id,
            status="accepted",
            message=f"Reindexation task started for tenant {tenant_id}",
        )

    except Exception as e:
        logger.error(f"Failed to start reindexation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start reindexation: {str(e)}",
        )


@router.get("/reindex/{task_id}", response_model=AssetReindexStatus)
def get_reindex_status(task_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Get status of reindexation task."""
    from app.celery_app import celery_app
    
    try:
        result = celery_app.AsyncResult(task_id)

        response = AssetReindexStatus(
            task_id=task_id,
            status=result.state,
        )

        if result.ready():
            if result.successful():
                response.result = result.result
            else:
                response.error = str(result.info)
        elif result.state == "PROGRESS":
            response.result = result.info

        return response

    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get task status: {str(e)}",
        )


@router.get("/search", response_model=AssetSearchResponse)
def search_assets(
    sku: str = Query(..., description="SKU to search for", min_length=1),
    threshold: float = Query(0.3, description="Minimum similarity score", ge=0.0, le=1.0),
    limit: int = Query(10, description="Maximum results", ge=1, le=100),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """Search assets by SKU using fuzzy matching.

    Uses PostgreSQL trigram similarity for fuzzy matching.
    Returns assets ordered by similarity score.
    """
    try:
        results = search_assets_by_sku(
            db=db,
            tenant_id=int(tenant_id),
            sku=sku,
            threshold=threshold,
            limit=limit,
        )

        search_results = [
            AssetSearchResult(
                asset=AssetResponse.model_validate(asset),
                score=round(score, 3),
            )
            for asset, score in results
        ]

        return AssetSearchResponse(
            query=sku,
            threshold=threshold,
            results=search_results,
            total=len(search_results),
        )

    except Exception as e:
        logger.error(f"Search failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Search failed: {str(e)}",
        )


@router.get("/", response_model=AssetListResponse)
def list_assets(
    page: int = Query(1, description="Page number", ge=1),
    size: int = Query(20, description="Page size", ge=1, le=100),
    sku_filter: Optional[str] = Query(None, description="Filter by SKU (partial match)"),
    format_filter: Optional[str] = Query(None, description="Filter by format"),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """List assets for tenant with pagination and filters."""
    try:
        # Build query
        query = db.query(Asset).filter(Asset.tenant_id == int(tenant_id))

        # Apply filters
        if sku_filter:
            query = query.filter(Asset.sku_normalized.ilike(f"%{sku_filter.lower()}%"))

        if format_filter:
            query = query.filter(Asset.metadata_json.ilike(f'%"format": "{format_filter.upper()}"%'))

        # Get total count
        total = query.count()

        # Calculate pagination
        offset = (page - 1) * size
        pages = (total + size - 1) // size  # Ceiling division

        # Get page of results
        assets = query.order_by(Asset.created_at.desc()).offset(offset).limit(size).all()

        return AssetListResponse(
            items=[AssetResponse.model_validate(asset) for asset in assets],
            total=total,
            page=page,
            size=size,
            pages=pages,
        )

    except Exception as e:
        logger.error(f"List assets failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list assets: {str(e)}",
        )


@router.get("/{asset_id}", response_model=AssetWithMetadata)
def get_asset(
    asset_id: int,
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """Get asset by ID with parsed metadata."""
    asset = (
        db.query(Asset)
        .filter(Asset.id == asset_id, Asset.tenant_id == int(tenant_id))
        .first()
    )

    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Asset {asset_id} not found",
        )

    # Parse metadata JSON
    response = AssetWithMetadata.model_validate(asset)
    if asset.metadata_json:
        try:
            response.metadata = json.loads(asset.metadata_json)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse metadata JSON for asset {asset_id}")
            response.metadata = None

    return response
