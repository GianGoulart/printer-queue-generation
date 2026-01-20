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
        JobItem.status.in_(["missing", "ambiguous"])
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
    job = get_job_by_id(db, job_id, tenant_id)
    
    # Get pending items
    pending_items = db.query(JobItem).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous"])
    ).all()
    
    result = []
    for item in pending_items:
        candidates = []
        
        # Parse candidates from manifest_json if exists
        if job.manifest_json:
            try:
                manifest = json.loads(job.manifest_json)
                item_data = manifest.get("pending_items_data", {}).get(str(item.id), {})
                candidate_data = item_data.get("candidates", [])
                
                for candidate in candidate_data:
                    candidates.append(AssetCandidate(
                        asset_id=candidate["asset_id"],
                        sku=candidate["sku"],
                        file_uri=candidate["file_uri"],
                        score=candidate["score"]
                    ))
            except (json.JSONDecodeError, KeyError):
                pass
        
        result.append(PendingItemResponse(
            id=item.id,
            sku=item.sku,
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
    
    # Check if all items are now resolved
    pending_count = db.query(func.count(JobItem.id)).filter(
        JobItem.job_id == job_id,
        JobItem.status.in_(["missing", "ambiguous"])
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
