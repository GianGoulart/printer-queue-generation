"""Asset reindexing task."""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Any, Dict

API_CODE_ROOT = Path("/api_code")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Worker modules (from /app)
from app.celery_app import celery_app
from app.config import settings

logger = logging.getLogger(__name__)

# Create database connection for worker
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _load_api_modules():
    """Load API modules from /api_code so reindex can use sku_extractor, asset_service, etc."""
    if not API_CODE_ROOT.is_dir():
        raise FileNotFoundError(
            f"API code path not found: {API_CODE_ROOT}. "
            "In Docker, mount the api folder: -v ./api:/api_code"
        )
    app_dir = API_CODE_ROOT / "app"
    if not (app_dir / "services" / "sku_extractor.py").exists():
        raise FileNotFoundError(
            f"API app not found under {API_CODE_ROOT}. Expected {app_dir}/services/sku_extractor.py"
        )
    api_code_str = str(API_CODE_ROOT)
    # Remove worker's app from cache so 'app' resolves to API's app
    to_remove = [k for k in sys.modules if k == "app" or k.startswith("app.")]
    for k in to_remove:
        del sys.modules[k]
    # Build path with /api_code first and /app removed, so Python finds app under /api_code only
    path_without_app = [p for p in sys.path if p != "/app" and p != api_code_str]
    old_path = sys.path.copy()
    sys.path = [api_code_str] + path_without_app
    try:
        import app.services.sku_extractor as sku_extractor_module  # noqa: E402
        import app.services.image_metadata as image_metadata_module  # noqa: E402
        import app.services.asset_service as asset_service_module  # noqa: E402
        import app.storage.factory as storage_factory_module  # noqa: E402
        import app.models.sizing_profile as sizing_profile_module  # noqa: E402
        return {
            "extract_sku": sku_extractor_module.extract_sku,
            "extract_image_metadata": image_metadata_module.extract_image_metadata,
            "ImageMetadataError": image_metadata_module.ImageMetadataError,
            "upsert_asset": asset_service_module.upsert_asset,
            "get_storage_driver": storage_factory_module.get_storage_driver,
            "SizingProfile": sizing_profile_module.SizingProfile,
        }
    finally:
        sys.path = old_path


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
    # Load API modules from /api_code (clears worker's app from cache for this task only)
    original_sys_path = sys.path.copy()
    original_app_modules = {k: v for k, v in sys.modules.items() if k == "app" or k.startswith("app.")}
    try:
        api = _load_api_modules()
        extract_sku = api["extract_sku"]
        extract_image_metadata = api["extract_image_metadata"]
        ImageMetadataError = api["ImageMetadataError"]
        upsert_asset = api["upsert_asset"]
        get_storage_driver = api["get_storage_driver"]
        SizingProfile = api.get("SizingProfile")
    finally:
        # Restore worker's app so other tasks keep using worker code
        for k in list(sys.modules):
            if k == "app" or k.startswith("app."):
                del sys.modules[k]
        for k, v in original_app_modules.items():
            sys.modules[k] = v
        sys.path = original_sys_path

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

        # Filter image files (match on "name" or "path" for basename)
        image_extensions = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
        image_files = []
        for f in files:
            name = f.get("name") or Path(f.get("path", "")).name
            suffix = Path(name).suffix.lower()
            if suffix in image_extensions:
                image_files.append(f)
            elif len(files) <= 20:
                logger.debug(f"Skip non-image: path={f.get('path')} name={name} suffix={suffix}")

        if len(files) > 0 and len(image_files) == 0:
            sample = [f.get("path", f.get("name", "?")) for f in files[:10]]
            logger.warning(
                f"No image files found (extensions: {image_extensions}). "
                f"Sample of {len(files)} files: {sample}"
            )
        logger.info(f"Processing {len(image_files)} image files")

        # Load tenant sizing profile prefixes for SKU extraction (strip only these from start)
        sizing_prefixes = None
        if SizingProfile:
            try:
                profiles = db.query(SizingProfile).filter(
                    SizingProfile.tenant_id == tenant_id,
                    SizingProfile.sku_prefix.isnot(None),
                ).all()
                sizing_prefixes = [p.sku_prefix.strip() for p in profiles if p.sku_prefix]
                if sizing_prefixes:
                    logger.info(f"Using tenant sizing prefixes for SKU extraction: {sizing_prefixes[:5]}{'...' if len(sizing_prefixes) > 5 else ''}")
            except Exception as e:
                logger.warning(f"Could not load sizing profiles for tenant {tenant_id}: {e}")

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

                # Extract SKU from filename (tenant prefixes strip only sizing profile prefixes from start)
                sku = extract_sku(filename, sizing_prefixes=sizing_prefixes)
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
