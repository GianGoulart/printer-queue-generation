"""Asset endpoints."""

import json
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
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
from app.services.asset_service import search_assets_by_sku, upsert_asset
from app.services.image_metadata import extract_image_metadata, ImageMetadataError
from app.storage.factory import get_storage_driver

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


@router.post("/upload", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_asset(
    file: UploadFile = File(..., description="Image file"),
    sku: str = Form(..., description="SKU for the asset"),
    job_id: Optional[int] = Form(None, description="Optional job ID to resolve item after upload"),
    item_id: Optional[int] = Form(None, description="Optional item ID to resolve after upload"),
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """Upload an asset image file.
    
    - Uploads file to storage
    - Extracts image metadata (dimensions, DPI, format)
    - Creates or updates asset in database
    - Normalizes SKU automatically
    - If job_id and item_id are provided, automatically resolves the item and reruns the job if all items are resolved
    """
    try:
        # Read file content
        content = await file.read()
        
        # Extract image metadata
        try:
            metadata = extract_image_metadata(content)
        except ImageMetadataError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid image file: {str(e)}"
            )
        
        # Normalize SKU
        sku_normalized = sku.lower().strip()
        
        # Get storage driver
        storage_driver = get_storage_driver(db, int(tenant_id))
        
        # Generate file path
        filename = file.filename or f"{sku_normalized}.{metadata.get('format', 'png').lower()}"
        file_uri = f"tenant/{tenant_id}/assets/{uuid.uuid4()}/{filename}"
        
        # Upload to storage
        try:
            uploaded_uri = await storage_driver.upload_file(file_path=file_uri, content=content)
        except Exception as e:
            logger.error(f"Failed to upload file to storage: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload file to storage: {str(e)}"
            )
        
        # Upsert asset in database
        try:
            asset = upsert_asset(
                db=db,
                tenant_id=int(tenant_id),
                filename=filename,
                file_uri=uploaded_uri,
                sku_normalized=sku_normalized,
                metadata=metadata,
            )
            
            # If job_id and item_id are provided, resolve the item automatically
            if job_id and item_id:
                from app.services.job_service import resolve_items, get_job_by_id
                from app.celery_app import celery_app
                from app.schemas.job import ItemResolution
                from datetime import datetime
                from sqlalchemy import func
                from app.models.job_item import JobItem
                
                try:
                    # Verify job exists and belongs to tenant
                    job = get_job_by_id(db, job_id, int(tenant_id))
                    
                    # Verify item exists and belongs to job
                    item = db.query(JobItem).filter(
                        JobItem.id == item_id,
                        JobItem.job_id == job_id
                    ).first()
                    
                    if not item:
                        logger.warning(f"Item {item_id} not found for job {job_id}")
                    elif item.status in ["missing", "ambiguous", "needs_input"]:
                        # Resolve the item
                        item.asset_id = asset.id
                        item.status = "resolved"
                        db.flush()  # Ensure item status is saved before checking
                        
                        # Check if all items are now resolved or skipped
                        pending_count = db.query(func.count(JobItem.id)).filter(
                            JobItem.job_id == job_id,
                            JobItem.status.in_(["missing", "ambiguous", "needs_input"])
                        ).scalar()
                        
                        logger.info(
                            f"Item {item_id} resolved. Pending items count: {pending_count}, "
                            f"Job status: {job.status}"
                        )
                        
                        # Update job status if all items are resolved
                        if pending_count == 0:
                            old_status = job.status
                            
                            # Only update to queued if job was in needs_input or completed/failed
                            # (don't change if already processing or queued)
                            if old_status in ["needs_input", "completed", "failed"]:
                                job.status = "queued"  # Re-queue for processing
                                job.updated_at = datetime.utcnow()
                                db.commit()
                                
                                logger.info(
                                    f"Job {job_id} status updated from {old_status} to queued. "
                                    f"All items resolved. Re-queuing for processing."
                                )
                                
                                # Re-enqueue job for processing
                                try:
                                    celery_app.send_task(
                                        "app.tasks.process_job.process_job",
                                        args=[job_id]
                                    )
                                    logger.info(f"Job {job_id} re-queued after resolving item {item_id}")
                                except Exception as celery_error:
                                    logger.error(
                                        f"Failed to re-queue job {job_id} after resolving item: {celery_error}",
                                        exc_info=True
                                    )
                            else:
                                # Job is already queued or processing, just update timestamp
                                job.updated_at = datetime.utcnow()
                                db.commit()
                                logger.info(
                                    f"All items resolved for job {job_id}, but job is already in {old_status} status. "
                                    f"Not changing status."
                                )
                        else:
                            # Still has pending items, but update job timestamp
                            job.updated_at = datetime.utcnow()
                            db.commit()
                            logger.info(
                                f"Item {item_id} resolved, but {pending_count} items still pending. "
                                f"Job remains in {job.status} status."
                            )
                        
                        logger.info(f"Item {item_id} resolved with asset {asset.id}")
                    else:
                        logger.warning(f"Item {item_id} is not in missing/ambiguous/needs_input state (current: {item.status})")
                        
                except Exception as e:
                    logger.error(f"Failed to resolve item after upload: {e}", exc_info=True)
                    # Don't fail the upload if resolution fails
                    db.rollback()
            
            return AssetResponse.model_validate(asset)
            
        except Exception as e:
            logger.error(f"Failed to create asset: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to create asset: {str(e)}"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload_asset: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )
