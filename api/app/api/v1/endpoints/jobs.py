"""Jobs API endpoints."""

import json
import math
import os
from typing import Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.celery_app import celery_app
from app.models.job import Job
from app.schemas.job import (
    JobCreateResponse,
    JobDetailResponse,
    JobListResponse,
    JobResolveRequest,
    JobResolveResponse,
    PendingItemsResponse,
)
from app.schemas.output import BaseOutput, JobOutputsResponse
from app.services.job_service import (
    InvalidJobStateError,
    JobNotFoundError,
    JobServiceError,
    create_job,
    delete_job,
    get_job_detail,
    get_pending_items,
    list_jobs,
    resolve_items,
    validate_job_requirements,
)
from app.storage.factory import get_storage_driver

router = APIRouter()


@router.post("", response_model=JobCreateResponse, status_code=status.HTTP_201_CREATED)
async def upload_picklist(
    file: UploadFile = File(..., description="Picklist PDF file"),
    mode: str = Form(default="sequence", pattern="^(sequence|optimize)$"),
    sizing_profile_id: Optional[int] = Form(None),
    machine_id: Optional[int] = Form(None),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Upload picklist PDF and create job.
    
    - **file**: Picklist PDF (max 10MB)
    - **mode**: Processing mode - 'sequence' (default) or 'optimize'
    - **sizing_profile_id**: Optional default sizing profile ID
    - **machine_id**: Optional target machine ID
    
    Returns job ID and status.
    """
    # Validate file type
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are allowed"
        )
    
    # Read file content to check size
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    
    if file_size_mb > 10:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {file_size_mb:.2f}MB (max 10MB)"
        )
    
    # Validate job requirements
    is_valid, error_msg = validate_job_requirements(
        db, tenant_id, machine_id, sizing_profile_id
    )
    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_msg
        )
    
    try:
        # Create job first to get ID
        job = create_job(
            db=db,
            tenant_id=tenant_id,
            picklist_uri="",  # Will update after upload
            mode=mode,
            machine_id=machine_id,
            sizing_profile_id=sizing_profile_id
        )
        
        # Get storage driver for tenant
        storage_driver = get_storage_driver(db, tenant_id)
        
        # Save PDF to storage: tenant/{tenant_id}/picklists/{job_id}.pdf
        picklist_path = f"tenant/{tenant_id}/picklists/{job.id}.pdf"
        
        # Upload file to storage (async operation)
        await storage_driver.upload_file(picklist_path, content)
        
        # Update job with picklist URI
        job.picklist_uri = picklist_path
        db.commit()
        db.refresh(job)
        
        # Enqueue worker task
        celery_app.send_task(
            "app.tasks.process_job.process_job",
            args=[job.id]
        )
        
        return JobCreateResponse(
            id=job.id,
            status=job.status,
            mode=job.mode,
            picklist_uri=job.picklist_uri,
            created_at=job.created_at
        )
        
    except Exception as e:
        # Rollback and cleanup if job was created
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create job: {str(e)}"
        )


@router.get("", response_model=JobListResponse)
def list_all_jobs(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    status_filter: Optional[str] = Query(None, description="Filter by status"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    List jobs with pagination.
    
    - **page**: Page number (default: 1)
    - **size**: Page size (default: 20, max: 100)
    - **status_filter**: Optional status filter (queued, processing, completed, failed, needs_input)
    """
    try:
        items, total = list_jobs(db, tenant_id, page, size, status_filter)
        
        pages = math.ceil(total / size) if total > 0 else 1
        
        return JobListResponse(
            items=items,
            total=total,
            page=page,
            size=size,
            pages=pages
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list jobs: {str(e)}"
        )


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Get detailed job information.
    
    - **job_id**: Job ID
    """
    try:
        return get_job_detail(db, job_id, tenant_id)
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job: {str(e)}"
        )


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_job(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Cancel/delete a job.
    
    - **job_id**: Job ID
    """
    try:
        delete_job(db, job_id, tenant_id)
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete job: {str(e)}"
        )


@router.get("/{job_id}/pending-items", response_model=PendingItemsResponse)
def get_job_pending_items(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Get items needing manual resolution.
    
    - **job_id**: Job ID
    
    Returns items with status 'missing' or 'ambiguous' along with candidate assets.
    """
    try:
        items = get_pending_items(db, job_id, tenant_id)
        return PendingItemsResponse(items=items)
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get pending items: {str(e)}"
        )


@router.post("/{job_id}/resolve", response_model=JobResolveResponse)
def resolve_job_items(
    job_id: int,
    request: JobResolveRequest,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Manually resolve job items.
    
    - **job_id**: Job ID
    - **resolutions**: List of item_id to asset_id mappings
    
    Resolves pending items and re-queues job for processing if all items are resolved.
    """
    try:
        resolved_count, new_status = resolve_items(
            db, job_id, tenant_id, request.resolutions
        )
        
        # Re-enqueue if job is back to queued
        if new_status == "queued":
            celery_app.send_task(
                "app.tasks.process_job.process_job",
                args=[job_id]
            )
            message = "Items resolved. Job re-queued for processing."
        else:
            message = f"Resolved {resolved_count} items. {resolved_count} items still need input."
        
        return JobResolveResponse(
            status="success",
            resolved_count=resolved_count,
            job_status=new_status,
            message=message
        )
    except JobNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except InvalidJobStateError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resolve items: {str(e)}"
        )


@router.get("/{job_id}/outputs", response_model=JobOutputsResponse)
def get_job_outputs(
    job_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Get job output files (PDFs).
    
    - **job_id**: Job ID
    
    Returns list of generated PDF bases with URIs and metadata.
    Only available for completed jobs.
    """
    try:
        # Get job
        job = db.query(Job).filter(
            Job.id == job_id,
            Job.tenant_id == tenant_id
        ).first()
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        
        # Check if job is completed
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job outputs not available. Current status: {job.status}"
            )
        
        # Parse manifest
        try:
            manifest = json.loads(job.manifest_json) if job.manifest_json else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid job manifest"
            )
        
        # Extract packing and output info
        packing = manifest.get("packing", {})
        outputs = manifest.get("outputs", {})
        
        bases_data = packing.get("bases", [])
        pdf_uris = outputs.get("pdfs", [])
        preview_uris = outputs.get("previews", [])
        
        # Build response
        bases = []
        for i, base_data in enumerate(bases_data):
            base = BaseOutput(
                index=base_data.get("index", i + 1),
                pdf_uri=pdf_uris[i] if i < len(pdf_uris) else "",
                preview_uri=preview_uris[i] if i < len(preview_uris) else None,
                width_mm=base_data.get("width_mm", 0),
                length_mm=base_data.get("length_mm", 0),
                items_count=base_data.get("items_count", 0),
                utilization=base_data.get("utilization", 0)
            )
            bases.append(base)
        
        return JobOutputsResponse(
            job_id=job.id,
            status=job.status,
            bases=bases,
            total_bases=len(bases)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job outputs: {str(e)}"
        )


@router.get("/{job_id}/outputs/{base_index}/download")
async def download_base_pdf(
    job_id: int,
    base_index: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Download PDF for a specific base.
    
    - **job_id**: Job ID
    - **base_index**: Base index (1, 2, 3...)
    
    Returns the PDF file as a download.
    """
    try:
        # Get job
        job = db.query(Job).filter(
            Job.id == job_id,
            Job.tenant_id == tenant_id
        ).first()
        
        if not job:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        
        # Check if job is completed
        if job.status != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job outputs not available. Current status: {job.status}"
            )
        
        # Parse manifest to get PDF URI
        try:
            manifest = json.loads(job.manifest_json) if job.manifest_json else {}
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Invalid job manifest"
            )
        
        outputs = manifest.get("outputs", {})
        pdf_uris = outputs.get("pdfs", [])
        
        # Find PDF for this base index
        pdf_uri = None
        for uri in pdf_uris:
            if f"base_{base_index}.pdf" in uri:
                pdf_uri = uri
                break
        
        if not pdf_uri:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Base {base_index} not found for job {job_id}"
            )
        
        # Download from storage
        storage_driver = get_storage_driver(db, tenant_id)
        pdf_content = await storage_driver.download_file(pdf_uri)
        
        # Return as streaming response
        filename = f"job_{job_id}_base_{base_index}.pdf"
        
        return StreamingResponse(
            iter([pdf_content]),
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download PDF: {str(e)}"
        )
