"""Image packing task."""

import asyncio
import logging
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

from app.celery_app import celery_app

logger = logging.getLogger(__name__)


def update_job_status(job_id: str, status: str, progress=None, message=None, result=None, error=None):
    """Update job status in Redis store."""
    try:
        # Add /shared to path to import job store
        if '/shared' not in sys.path:
            sys.path.insert(0, '/shared')
        
        from image_packing_job_store import set_job_status
        set_job_status(job_id, status, progress, message, result, error)
    except Exception as e:
        logger.error(f"Failed to update job status: {e}", exc_info=True)


@celery_app.task(bind=True, name="app.tasks.image_packing.process_image_packing")
def process_image_packing(
    self,
    job_id: str,
    file_uris: List[str],
    mode: str = "optimize",
    machine_id: int = None,
    tenant_id: int = None
) -> dict:
    """
    Process image packing job.
    
    Args:
        job_id: Unique job identifier
        file_uris: List of file URIs in storage
        mode: Packing mode ('sequence' or 'optimize')
        machine_id: Machine ID to use for packing
        tenant_id: Tenant ID
    
    Returns:
        Dict with status and result
    """
    logger.info(f"Starting image packing job {job_id} with {len(file_uris)} file(s)")
    
    try:
        update_job_status(job_id, "processing", progress=10, message="Downloading files...")
        
        # Import here to avoid circular imports
        import sys
        import importlib.util
        from types import SimpleNamespace
        
        # Import worker services BEFORE manipulating sys.modules
        from ..services.image_processor import ImageProcessorService
        from ..services.packing_service import PackingService
        
        # Save reference to worker's app module and temporarily remove it
        worker_app = sys.modules.get('app')
        if worker_app:
            del sys.modules['app']
        
        # Add /api_code to path
        sys.path.insert(0, '/api_code')
        
        # Import API modules
        import app.storage.factory as api_storage_module
        get_storage_driver = api_storage_module.get_storage_driver
        
        # Get storage driver and machine
        from sqlalchemy.orm import Session
        import app.database as api_db_module
        import app.models.machine as api_machine_module
        Machine = api_machine_module.Machine
        
        SessionLocal = api_db_module.SessionLocal
        
        # Remove /api_code from path
        sys.path.remove('/api_code')
        
        # Restore worker's app module
        if worker_app:
            sys.modules['app'] = worker_app
        
        db = SessionLocal()
        try:
            storage_driver = get_storage_driver(db, tenant_id)
            
            # Get machine
            machine = db.query(Machine).filter(
                Machine.id == machine_id,
                Machine.tenant_id == tenant_id
            ).first()
            
            if not machine:
                raise ValueError(f"Machine {machine_id} not found for tenant {tenant_id}")
        finally:
            db.close()
        
        # Download files to temporary directory
        temp_dir = Path(tempfile.mkdtemp(prefix=f"image_packing_{job_id}_"))
        downloaded_files = []
        # Map local file paths to original storage URIs
        local_to_storage_uri = {}
        
        try:
            for uri in file_uris:
                # Download file
                file_name = Path(uri).name
                dest_path = temp_dir / file_name
                
                # Download from storage
                file_content = asyncio.run(storage_driver.download_file(uri))
                with dest_path.open("wb") as f:
                    f.write(file_content)
                
                local_path = str(dest_path)
                downloaded_files.append(local_path)
                # Map local path to storage URI
                local_to_storage_uri[local_path] = uri
            
            update_job_status(job_id, "processing", progress=30, message="Processing images...")
            
            # Process images (extract ZIPs, calculate dimensions)
            image_processor = ImageProcessorService()
            image_infos = image_processor.process_images(
                downloaded_files, 
                extract_dir=temp_dir / "extracted",
                source_uris=file_uris  # Pass original storage URIs
            )
            
            if not image_infos:
                raise ValueError("No valid images found in uploaded files")
            
            # Map processed images to storage URIs using source_uri from ImageInfo
            image_to_storage_uri = {}
            for img_info in image_infos:
                if img_info.source_uri:
                    image_to_storage_uri[img_info.file_path] = img_info.source_uri
                else:
                    # Fallback: try to match by filename
                    for local_path, storage_uri in local_to_storage_uri.items():
                        if img_info.file_name in Path(local_path).name or Path(local_path).name == img_info.file_name:
                            image_to_storage_uri[img_info.file_path] = storage_uri
                            break
            
            update_job_status(
                job_id, "processing", progress=50,
                message=f"Packing {len(image_infos)} images..."
            )
            
            # Create simple items for packing service
            # Use SimpleNamespace to mimic JobItem structure
            packing_items = []
            for idx, img_info in enumerate(image_infos):
                item = SimpleNamespace(
                    id=idx + 1,
                    sku=img_info.file_name,  # Use filename as identifier
                    final_width_mm=img_info.width_mm,
                    final_height_mm=img_info.height_mm
                )
                packing_items.append(item)
            
            # Create machine object for packing service
            machine_obj = SimpleNamespace(
                max_width_mm=machine.max_width_mm,
                max_length_mm=machine.max_length_mm
            )
            
            # Pack images
            packing_service = PackingService()
            packing_result = asyncio.run(
                packing_service.pack_items(
                    items=packing_items,
                    machine=machine_obj,
                    mode=mode
                )
            )
            
            update_job_status(job_id, "processing", progress=80, message="Finalizing...")
            
            # Convert result to dict format
            result_dict = packing_result.to_dict()
            
            # Add file URIs to placements for rendering
            for base in result_dict["bases"]:
                for placement in base["placements"]:
                    # Find corresponding image info
                    item_id = placement["item_id"]
                    if item_id <= len(image_infos):
                        img_info = image_infos[item_id - 1]
                        # Use source_uri if available, otherwise try mapping
                        if img_info.source_uri:
                            placement["file_uri"] = img_info.source_uri
                        else:
                            # Fallback to mapping
                            storage_uri = image_to_storage_uri.get(img_info.file_path)
                            if storage_uri:
                                placement["file_uri"] = storage_uri
                            else:
                                logger.warning(
                                    f"Could not find storage URI for image {img_info.file_name} "
                                    f"(item_id={item_id})"
                                )
                                placement["file_uri"] = None
            
            update_job_status(
                job_id, "completed", progress=100,
                message=f"Packing completed: {len(packing_result.bases)} base(s)",
                result=result_dict
            )
            
            logger.info(
                f"Image packing job {job_id} completed: "
                f"{len(image_infos)} images into {len(packing_result.bases)} base(s)"
            )
            
            return {
                "status": "completed",
                "job_id": job_id,
                "result": result_dict
            }
        
        finally:
            # Cleanup temporary files
            import shutil
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
                logger.debug(f"Cleaned up temp directory: {temp_dir}")
    
    except Exception as e:
        error_msg = f"Image packing failed: {str(e)}"
        logger.error(f"Error in image packing job {job_id}: {e}", exc_info=True)
        update_job_status(job_id, "failed", error=error_msg)
        return {
            "status": "failed",
            "job_id": job_id,
            "error": error_msg
        }
