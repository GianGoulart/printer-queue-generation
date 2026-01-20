"""Storage test endpoints."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.storage_config import TenantStorageConfig
from app.schemas.asset import StorageTestResponse
from app.storage.factory import get_storage_driver
import asyncio

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/test", response_model=StorageTestResponse)
def test_storage_connection(
    tenant_id: str = Depends(get_tenant_id),
    db: Session = Depends(get_db),
):
    """Test storage connection for tenant.

    Verifies that:
    - Storage is configured
    - Credentials are valid
    - Storage is accessible
    """
    try:
        # Get storage config
        config = (
            db.query(TenantStorageConfig)
            .filter(TenantStorageConfig.tenant_id == int(tenant_id))
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Storage not configured for tenant {tenant_id}",
            )

        # Get driver
        try:
            driver = get_storage_driver(db, int(tenant_id))
        except Exception as e:
            return StorageTestResponse(
                status="error",
                provider=config.provider,
                message=f"Failed to initialize driver: {str(e)}",
                base_path=config.base_path,
            )

        # Test connection
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            connected = loop.run_until_complete(driver.test_connection())
        finally:
            loop.close()

        if connected:
            return StorageTestResponse(
                status="ok",
                provider=config.provider,
                message="Connection successful",
                base_path=config.base_path,
            )
        else:
            return StorageTestResponse(
                status="error",
                provider=config.provider,
                message="Connection failed",
                base_path=config.base_path,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Storage test failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Storage test failed: {str(e)}",
        )
