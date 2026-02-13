"""Image packing API endpoints."""

import logging
import tempfile
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.celery_app import celery_app
from app.models.machine import Machine
from app.schemas.image_packing import (
    ImagePackingStatusResponse,
    ImagePackingUploadResponse,
)
from app.storage.factory import get_storage_driver

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/upload", response_model=ImagePackingUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_images(
    files: List[UploadFile] = File(..., description="Image files or ZIP archive"),
    mode: str = Form(default="optimize", pattern="^(sequence|optimize)$"),
    machine_id: int = Form(..., description="Machine ID for packing"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """
    Upload images or ZIP file for automatic packing/layout generation.
    
    - Accepts multiple image files or a single ZIP file
    - No SKU validation or sizing profiles required
    - Generates best possible layout to minimize bases and waste
    - Respects base dimensions and cut margins
    - Uses machine dimensions from registered machine
    """
    try:
        # Validate machine exists and belongs to tenant
        machine = db.query(Machine).filter(
            Machine.id == machine_id,
            Machine.tenant_id == tenant_id
        ).first()
        
        if not machine:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Machine {machine_id} not found for tenant {tenant_id}"
            )
        
        # Generate job ID
        job_id = str(uuid.uuid4())
        
        # Get storage driver
        storage_driver = get_storage_driver(db, tenant_id)
        
        # Save uploaded files temporarily
        temp_dir = Path(tempfile.mkdtemp(prefix=f"image_packing_{job_id}_"))
        file_uris = []
        
        try:
            for file in files:
                # Read file content
                content = await file.read()
                
                # Generate unique filename
                file_name = file.filename or f"upload_{uuid.uuid4()}"
                file_uri = f"tenant/{tenant_id}/image_packing/{job_id}/{file_name}"
                
                # Upload to storage
                await storage_driver.upload_file(file_path=file_uri, content=content)
                file_uris.append(file_uri)
                
                logger.info(f"Uploaded file {file_name} to {file_uri}")
        
        except Exception as e:
            logger.error(f"Failed to upload files: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to upload files: {str(e)}"
            )
        
        # Initialize job status
        try:
            import sys
            sys.path.insert(0, '/shared')
            from image_packing_job_store import set_job_status
            
            set_job_status(
                job_id=job_id,
                status="queued",
                progress=0,
                message="Files uploaded, queued for processing"
            )
        except Exception as e:
            logger.error(f"Failed to initialize job status: {e}", exc_info=True)
            # Continue anyway - job will be created
        
        # Enqueue Celery task
        try:
            celery_app.send_task(
                "app.tasks.image_packing.process_image_packing",
                args=(),
                kwargs={
                    "job_id": job_id,
                    "file_uris": file_uris,
                    "mode": mode,
                    "machine_id": machine_id,
                    "tenant_id": tenant_id,
                }
            )
            logger.info(f"Enqueued image packing task for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to enqueue task: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to enqueue processing task: {str(e)}"
            )
        
        return ImagePackingUploadResponse(
            job_id=job_id,
            status="queued",
            message="Images uploaded successfully, processing started"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in upload_images: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}"
        )


@router.get("/status/{job_id}", response_model=ImagePackingStatusResponse)
def get_job_status(
    job_id: str,
    tenant_id: int = Depends(get_tenant_id),
):
    """Get status of image packing job."""
    try:
        import sys
        sys.path.insert(0, '/shared')
        from image_packing_job_store import get_job_status
        
        job_data = get_job_status(job_id)
        
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        
        # Ensure required fields exist (for backward compatibility with old jobs)
        from datetime import datetime
        if "created_at" not in job_data:
            job_data["created_at"] = datetime.utcnow().isoformat()
        if "updated_at" not in job_data:
            job_data["updated_at"] = datetime.utcnow().isoformat()
        
        return ImagePackingStatusResponse(**job_data)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job status: {str(e)}"
        )


@router.get("/result/{job_id}")
def get_job_result(
    job_id: str,
    tenant_id: int = Depends(get_tenant_id),
):
    """Get result of image packing job."""
    try:
        import sys
        sys.path.insert(0, '/shared')
        from image_packing_job_store import get_job_status
        
        job_data = get_job_status(job_id)
        
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        
        if job_data.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job {job_id} is not completed yet (status: {job_data.get('status')})"
            )
        
        result = job_data.get("result")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Result not found for job {job_id}"
            )
        
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get job result: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get job result: {str(e)}"
        )


@router.get("/download/{job_id}")
async def download_packing_result(
    job_id: str,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
):
    """Download generated layout as multi-page PDF."""
    try:
        import sys
        sys.path.insert(0, '/shared')
        from image_packing_job_store import get_job_status
        
        job_data = get_job_status(job_id)
        
        if not job_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Job {job_id} not found"
            )
        
        if job_data.get("status") != "completed":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Job {job_id} is not completed yet (status: {job_data.get('status')})"
            )
        
        result = job_data.get("result")
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Result not found for job {job_id}"
            )
        
        # Get storage driver
        storage_driver = get_storage_driver(db, tenant_id)
        
        # Generate multi-page PDF
        pdf_content = await _render_multi_page_pdf(
            result=result,
            storage_driver=storage_driver,
            tenant_id=tenant_id,
            job_id=job_id
        )
        
        return Response(
            content=pdf_content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="packing_result_{job_id}.pdf"'
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download packing result: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download result: {str(e)}"
        )


async def _render_multi_page_pdf(result: dict, storage_driver, tenant_id: int, job_id: str) -> bytes:
    """Render all bases as a multi-page PDF."""
    import io
    from PIL import Image as PILImage
    import tempfile
    
    buffer = io.BytesIO()
    bases = result.get("bases", [])
    
    if not bases:
        raise ValueError("No bases to render")
    
    # Create PDF canvas
    # Use first base dimensions for page size (all bases should have same width)
    first_base = bases[0]
    page_width = first_base["width_mm"] * mm
    page_length = first_base["length_mm"] * mm
    
    c = canvas.Canvas(buffer, pagesize=(page_width, page_length))
    
    for base in bases:
        # Render each base as a page
        await _render_base_page(c, base, storage_driver, tenant_id, job_id)
        c.showPage()
    
    c.save()
    buffer.seek(0)
    return buffer.read()


async def _render_base_page(canvas_obj, base: dict, storage_driver, tenant_id: int, job_id: str):
    """Render a single base page with all images."""
    from PIL import Image as PILImage
    import tempfile
    import zipfile
    import io
    import zipfile
    import io
    
    placements = base.get("placements", [])
    
    for placement in placements:
        # Get image file URI from placement (stored during processing)
        try:
            image_uri = placement.get("file_uri")
            if not image_uri:
                logger.warning(f"No file_uri for placement {placement.get('item_id')}")
                continue
            
            # Download file from storage
            file_content = await storage_driver.download_file(image_uri)
            
            # Check if it's a ZIP file (for images extracted from ZIPs)
            image_content = None
            file_name = placement.get("sku", "")  # Use SKU (filename) to identify image in ZIP
            
            if image_uri.lower().endswith('.zip') or (len(file_content) > 4 and file_content[:2] == b'PK'):
                # It's a ZIP file - extract the specific image
                logger.debug(f"Extracting image {file_name} from ZIP {image_uri}")
                with zipfile.ZipFile(io.BytesIO(file_content), 'r') as zip_ref:
                    # Find the image file in the ZIP
                    for zip_file_name in zip_ref.namelist():
                        if file_name in zip_file_name or Path(zip_file_name).name == file_name:
                            image_content = zip_ref.read(zip_file_name)
                            break
                    
                    if not image_content:
                        logger.warning(f"Image {file_name} not found in ZIP {image_uri}")
                        continue
            else:
                # Direct image file
                image_content = file_content
            
            if not image_content:
                logger.warning(f"Empty image content for placement {placement.get('item_id')}")
                continue
            
            # Save to temp file and open with PIL
            with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_file:
                tmp_file.write(image_content)
                tmp_path = tmp_file.name
            
            try:
                with PILImage.open(tmp_path) as img:
                    # Convert to RGB if needed
                    if img.mode != 'RGB':
                        img = img.convert('RGB')
                    
                    # Save as temporary PNG for ReportLab
                    rgb_path = tmp_path.replace('.png', '_rgb.png')
                    img.save(rgb_path, 'PNG')
                    
                    # Draw on canvas
                    x_mm = placement["x_mm"]
                    y_mm = placement["y_mm"]
                    width_mm = placement["width_mm"]
                    height_mm = placement["height_mm"]
                    
                    canvas_obj.drawImage(
                        rgb_path,
                        x_mm * mm,
                        (base["length_mm"] - y_mm - height_mm) * mm,  # Flip Y axis
                        width_mm * mm,
                        height_mm * mm,
                        preserveAspectRatio=True
                    )
            finally:
                # Cleanup
                import os
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                if os.path.exists(rgb_path):
                    os.unlink(rgb_path)
        
        except Exception as e:
            logger.error(f"Failed to render placement {placement.get('item_id')}: {e}", exc_info=True)
            continue
