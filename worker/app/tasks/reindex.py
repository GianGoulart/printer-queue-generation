"""Asset reindexing task."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Worker modules (from /app)
from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

# Create database connection for worker
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@celery_app.task(name="app.tasks.reindex.reindex_assets", bind=True)
def reindex_assets(self, tenant_id: int) -> Dict[str, Any]:
    """Reindex all assets for a tenant.

    This task:
    1. Lists all files from tenant's storage
    2. For each image file:
       - Downloads the file
       - Extracts SKU from filename
       - Extracts image metadata
       - Upserts asset in database
    3. Returns summary of results

    Args:
        tenant_id: Tenant ID to reindex assets for

    Returns:
        Dict with results:
            - total: Total files processed
            - success: Successfully indexed
            - failed: Failed to index
            - errors: List of errors
            - skipped: Files skipped (non-images)

    Examples:
        >>> result = reindex_assets.delay(tenant_id=1)
        >>> result.get()
        {'total': 20, 'success': 18, 'failed': 2, 'skipped': 0}
    """
    # CRITICAL: Temporarily manipulate sys.path and sys.modules to load API modules
    # Save original state
    original_sys_path = sys.path.copy()
    original_app_module = sys.modules.get('app')
    
    try:
        # Remove worker's app module temporarily
        if 'app' in sys.modules:
            del sys.modules['app']
        
        # Put /api_code FIRST in sys.path
        sys.path.insert(0, "/api_code")
        
        # Now import API modules normally - they will come from /api_code
        from app.services.sku_extractor import extract_sku
        from app.services.image_metadata import extract_image_metadata, ImageMetadataError
        from app.services.asset_service import upsert_asset
        from app.storage.factory import get_storage_driver
        
    finally:
        # Restore worker's app module
        if original_app_module is not None:
            sys.modules['app'] = original_app_module
        
        # Restore original sys.path
        sys.path = original_sys_path
    
    # At this point, the functions are loaded and ready to use
    # (they hold references to their API modules)
    
    db = SessionLocal()
    
    try:
        logger.info(f"Starting asset reindexation for tenant {tenant_id}")

        # Get storage driver for tenant
        try:
            driver = get_storage_driver(db, tenant_id)
        except Exception as e:
            logger.error(f"Failed to get storage driver: {e}")
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [f"Storage driver error: {str(e)}"],
            }

        # List all files
        try:
            # Run async list_files in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            files = loop.run_until_complete(driver.list_files())
            loop.close()
        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return {
                "total": 0,
                "success": 0,
                "failed": 0,
                "skipped": 0,
                "errors": [f"Failed to list files: {str(e)}"],
            }

        logger.info(f"Found {len(files)} files for tenant {tenant_id}")

        # Filter image files
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        image_files = [
            f for f in files if Path(f["name"]).suffix.lower() in image_extensions
        ]

        logger.info(f"Processing {len(image_files)} image files")

        # Process each file
        total = len(image_files)
        success = 0
        failed = 0
        skipped = total - len(image_files)  # Non-image files
        errors = []

        for idx, file_info in enumerate(image_files, 1):
            filename = file_info["name"]
            file_path = file_info["path"]

            try:
                # Update progress
                self.update_state(
                    state="PROGRESS",
                    meta={
                        "current": idx,
                        "total": total,
                        "status": f"Processing {filename}",
                    },
                )

                logger.info(f"[{idx}/{total}] Processing {filename}")

                # Extract SKU from filename
                sku = extract_sku(filename)
                if not sku:
                    logger.warning(f"Could not extract SKU from {filename}, skipping")
                    skipped += 1
                    continue

                logger.debug(f"Extracted SKU: {sku} from {filename}")

                # Download file
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                file_bytes = loop.run_until_complete(driver.download_file(file_path))
                loop.close()

                logger.debug(f"Downloaded {len(file_bytes)} bytes")

                # Extract image metadata
                try:
                    metadata = extract_image_metadata(file_bytes)
                    logger.debug(f"Extracted metadata: {metadata}")
                except ImageMetadataError as e:
                    logger.warning(f"Failed to extract metadata from {filename}: {e}")
                    metadata = {"error": str(e)}

                # Build file URI
                file_uri = f"{file_path}"

                # Upsert asset
                asset = upsert_asset(
                    db=db,
                    tenant_id=tenant_id,
                    filename=filename,
                    file_uri=file_uri,
                    sku_normalized=sku,
                    metadata=metadata,
                )

                logger.info(
                    f"Asset {asset.id} upserted for SKU {sku} ({filename})"
                )
                success += 1

            except Exception as e:
                logger.error(f"Error processing {filename}: {e}", exc_info=True)
                errors.append(f"{filename}: {str(e)}")
                failed += 1

        # Return summary
        result = {
            "total": total,
            "success": success,
            "failed": failed,
            "skipped": skipped,
            "errors": errors[:10],  # Limit errors to first 10
        }

        logger.info(f"Reindexation complete for tenant {tenant_id}: {result}")
        return result

    finally:
        db.close()
