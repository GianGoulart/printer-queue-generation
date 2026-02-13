"""Job business logic service."""

import json
from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.job import Job
from app.models.job_item import JobItem
from app.models.machine import Machine
from app.models.sizing_profile import SizingProfile
from app.models.storage_config import TenantStorageConfig
from app.schemas.job import (
    AssetCandidate,
    ItemResolution,
    JobDetailResponse,
    JobListItem,
    PendingItemResponse,
)


class JobServiceError(Exception):
    """Base exception for job service errors."""
    pass


class JobNotFoundError(JobServiceError):
    """Job not found."""
    pass


class InvalidJobStateError(JobServiceError):
    """Job is in invalid state for operation."""
    pass


def get_job_by_id(db: Session, job_id: int, tenant_id: int) -> Job:
    """
    Get job by ID and tenant.
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        
    Returns:
        Job instance
        
    Raises:
        JobNotFoundError: If job not found
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        Job.tenant_id == tenant_id
    ).first()
    
    if not job:
        raise JobNotFoundError(f"Job {job_id} not found")
    
    return job


def validate_job_requirements(
    db: Session,
    tenant_id: int,
    machine_id: Optional[int],
    sizing_profile_id: Optional[int]
) -> Tuple[bool, Optional[str]]:
    """
    Validate job creation requirements.
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        machine_id: Optional machine ID
        sizing_profile_id: Optional sizing profile ID
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check if tenant has storage configured
    storage_config = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.tenant_id == tenant_id
    ).first()
    
    if not storage_config:
        return False, "Tenant does not have storage configured"
    
    # Validate machine if provided
    if machine_id:
        machine = db.query(Machine).filter(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id
        ).first()
        if not machine:
            return False, f"Machine {machine_id} not found or does not belong to tenant"
    
    # Validate sizing profile if provided
    if sizing_profile_id:
        profile = db.query(SizingProfile).filter(
            SizingProfile.id == sizing_profile_id,
            SizingProfile.tenant_id == tenant_id
        ).first()
        if not profile:
            return False, f"Sizing profile {sizing_profile_id} not found or does not belong to tenant"
    
    return True, None


def create_job(
    db: Session,
    tenant_id: int,
    picklist_uri: str,
    mode: str,
    machine_id: Optional[int] = None,
    sizing_profile_id: Optional[int] = None
) -> Job:
    """
    Create a new job.
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        picklist_uri: URI to saved picklist PDF
        mode: Processing mode (sequence or optimize)
        machine_id: Optional machine ID
        sizing_profile_id: Optional sizing profile ID
        
    Returns:
        Created job
    """
    job = Job(
        tenant_id=tenant_id,
        machine_id=machine_id,
        sizing_profile_id=sizing_profile_id,
        status="queued",
        mode=mode,
        picklist_uri=picklist_uri,
        manifest_json=None
    )
    
    db.add(job)
    db.commit()
    db.refresh(job)
    
    return job


def list_jobs(
    db: Session,
    tenant_id: int,
    page: int = 1,
    size: int = 20,
    status_filter: Optional[str] = None
) -> Tuple[List[JobListItem], int]:
    """
    List jobs with pagination.
    
    Args:
        db: Database session
        tenant_id: Tenant ID
        page: Page number (1-indexed)
        size: Page size
        status_filter: Optional status filter
        
    Returns:
        Tuple of (jobs, total_count)
    """
    query = db.query(Job).filter(Job.tenant_id == tenant_id)
    
    if status_filter:
        query = query.filter(Job.status == status_filter)
    
    # Get total count
    total = query.count()
    
    # Get paginated results
    jobs = query.order_by(Job.created_at.desc()).offset((page - 1) * size).limit(size).all()
    
    # Build response items with counts
    items = []
    for job in jobs:
        items_count = db.query(func.count(JobItem.id)).filter(JobItem.job_id == job.id).scalar()
        
        items.append(JobListItem(
            id=job.id,
            status=job.status,
            mode=job.mode,
            picklist_uri=job.picklist_uri,
            items_count=items_count,
            created_at=job.created_at,
            updated_at=job.updated_at
        ))
    
    return items, total


def get_job_detail(db: Session, job_id: int, tenant_id: int) -> JobDetailResponse:
    """
    Get detailed job information.
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        
    Returns:
        JobDetailResponse
        
    Raises:
        JobNotFoundError: If job not found
    """
    job = get_job_by_id(db, job_id, tenant_id)
    
    # Get item counts
    total_items = db.query(func.count(JobItem.id)).filter(JobItem.job_id == job_id).scalar()
    
    resolved_items = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["resolved", "packed"])
    ).scalar()
    
    pending_items = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous", "needs_input"])
    ).scalar()
    
    skipped_items = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status == "skipped"
    ).scalar()
    
    return JobDetailResponse(
        id=job.id,
        tenant_id=job.tenant_id,
        machine_id=job.machine_id,
        sizing_profile_id=job.sizing_profile_id,
        status=job.status,
        mode=job.mode,
        picklist_uri=job.picklist_uri,
        manifest_json=job.manifest_json,
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=job.completed_at,
        items_count=total_items,
        items_resolved=resolved_items,
        items_pending=pending_items
    )


def get_pending_items(
    db: Session,
    job_id: int,
    tenant_id: int
) -> List[PendingItemResponse]:
    """
    Get items needing manual resolution.
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        
    Returns:
        List of pending items with candidates
        
    Raises:
        JobNotFoundError: If job not found
    """
    from app.services.asset_service import search_assets_by_sku
    from app.services.sku_extractor import normalize_sku, sku_to_design
    
    job = get_job_by_id(db, job_id, tenant_id)
    
    # Load tenant sizing prefixes to compute sku_design (strip prefixes from item.sku)
    sizing_prefixes = []
    try:
        profiles = db.query(SizingProfile).filter(
            SizingProfile.tenant_id == tenant_id,
            SizingProfile.sku_prefix.isnot(None),
        ).all()
        sizing_prefixes = [p.sku_prefix for p in profiles if p.sku_prefix]
    except Exception:
        pass
    
    # Get pending items (missing, ambiguous, or needs_input from render failures)
    pending_items = db.query(JobItem).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous", "needs_input"])
    ).all()
    
    result = []
    for item in pending_items:
        sku_design = sku_to_design(item.sku, sizing_prefixes) if sizing_prefixes else None
        if sku_design and sku_design == normalize_sku(item.sku or ""):
            sku_design = None  # no prefix was stripped, avoid redundant value
        candidates = []
        candidate_asset_ids = set()  # Track asset IDs to avoid duplicates
        
        # Parse candidates from manifest_json if exists
        if job.manifest_json:
            try:
                manifest = json.loads(job.manifest_json)
                item_data = manifest.get("pending_items_data", {}).get(str(item.id), {})
                candidate_data = item_data.get("candidates", [])
                
                for candidate in candidate_data:
                    asset_id = candidate["asset_id"]
                    if asset_id not in candidate_asset_ids:
                        candidates.append(AssetCandidate(
                            asset_id=asset_id,
                            sku=candidate["sku"],
                            file_uri=candidate["file_uri"],
                            score=candidate["score"]
                        ))
                        candidate_asset_ids.add(asset_id)
            except (json.JSONDecodeError, KeyError):
                pass
        
        # Also search for assets dynamically in the database (by full SKU and by design SKU)
        # Assets are indexed by design-only after reindex; job item sku may include size prefix
        try:
            search_queries = [item.sku]
            if sku_design and sku_design != item.sku:
                search_queries.append(sku_design)
            for search_sku in search_queries:
                search_results = search_assets_by_sku(
                    db=db,
                    tenant_id=tenant_id,
                    sku=search_sku,
                    threshold=0.3,  # Minimum similarity threshold
                    limit=10
                )
            
                for asset, score in search_results:
                    # Only add if not already in candidates
                    if asset.id not in candidate_asset_ids:
                        candidates.append(AssetCandidate(
                            asset_id=asset.id,
                            sku=asset.sku_normalized,
                            file_uri=asset.file_uri,
                            score=float(score)
                        ))
                        candidate_asset_ids.add(asset.id)
        except Exception as e:
            # Log error but don't fail the request
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to search assets for SKU {item.sku}: {e}")
        
        # Sort candidates by score (highest first)
        candidates.sort(key=lambda c: c.score, reverse=True)
        
        result.append(PendingItemResponse(
            id=item.id,
            sku=item.sku,
            sku_design=sku_design or None,
            quantity=item.quantity,
            size_label=item.size_label,
            status=item.status,
            candidates=candidates
        ))
    
    return result


def resolve_items(
    db: Session,
    job_id: int,
    tenant_id: int,
    resolutions: List[ItemResolution]
) -> Tuple[int, str]:
    """
    Manually resolve job items.
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        resolutions: List of item resolutions
        
    Returns:
        Tuple of (resolved_count, new_job_status)
        
    Raises:
        JobNotFoundError: If job not found
        InvalidJobStateError: If job is not in needs_input state
    """
    job = get_job_by_id(db, job_id, tenant_id)
    
    if job.status != "needs_input":
        raise InvalidJobStateError(
            f"Job {job_id} is not in 'needs_input' state (current: {job.status})"
        )
    
    resolved_count = 0
    
    for resolution in resolutions:
        # Get the item
        item = db.query(JobItem).filter(
            JobItem.id == resolution.item_id,
            JobItem.job_id == job_id
        ).first()
        
        if not item:
            continue
        
        # Verify asset exists and belongs to tenant
        asset = db.query(Asset).filter(
            Asset.id == resolution.asset_id,
            Asset.tenant_id == tenant_id
        ).first()
        
        if not asset:
            continue
        
        # Update item
        item.asset_id = resolution.asset_id
        item.status = "resolved"
        resolved_count += 1
    
    # Check if all items are now resolved or skipped
    pending_count = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous", "needs_input"])
    ).scalar()
    
    # Update job status
    if pending_count == 0:
        job.status = "queued"  # Re-queue for processing
        new_status = "queued"
    else:
        new_status = "needs_input"  # Still has pending items
    
    job.updated_at = datetime.utcnow()
    
    db.commit()
    
    return resolved_count, new_status


def skip_items(
    db: Session,
    job_id: int,
    tenant_id: int,
    item_ids: List[int]
) -> Tuple[int, str]:
    """
    Skip job items (mark as skipped to generate base without them).
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        item_ids: List of item IDs to skip
        
    Returns:
        Tuple of (skipped_count, new_job_status)
        
    Raises:
        JobNotFoundError: If job not found
        InvalidJobStateError: If job is not in needs_input state
    """
    job = get_job_by_id(db, job_id, tenant_id)
    
    if job.status != "needs_input":
        raise InvalidJobStateError(
            f"Job {job_id} is not in 'needs_input' state (current: {job.status})"
        )
    
    skipped_count = 0
    
    for item_id in item_ids:
        # Get the item
        item = db.query(JobItem).filter(
            JobItem.id == item_id,
            JobItem.job_id == job_id
        ).first()
        
        if not item:
            continue
        
        # Only skip items that are missing, ambiguous, or needs_input
        if item.status not in ["missing", "ambiguous", "needs_input"]:
            continue
        
        # Mark as skipped
        item.status = "skipped"
        skipped_count += 1
    
    # Check if all items are now resolved or skipped
    pending_count = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous", "needs_input"])
    ).scalar()
    
    # Update job status
    if pending_count == 0:
        job.status = "queued"  # Re-queue for processing
        new_status = "queued"
    else:
        new_status = "needs_input"  # Still has pending items
    
    job.updated_at = datetime.utcnow()
    
    db.commit()
    
    return skipped_count, new_status


def delete_job(db: Session, job_id: int, tenant_id: int) -> None:
    """
    Delete (soft delete) a job.
    
    Args:
        db: Database session
        job_id: Job ID
        tenant_id: Tenant ID
        
    Raises:
        JobNotFoundError: If job not found
    """
    job = get_job_by_id(db, job_id, tenant_id)
    
    # For now, we do hard delete (cascade will remove items)
    # In production, consider soft delete with a deleted_at column
    db.delete(job)
    db.commit()
