"""Storage config endpoints."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.storage_config import TenantStorageConfig
from app.schemas.storage_config import (
    StorageConfigCreate,
    StorageConfigResponse,
    StorageConfigUpdate,
)

router = APIRouter()


@router.get("/", response_model=Optional[StorageConfigResponse])
def get_storage_config(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Get storage configuration for the tenant."""
    config = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.tenant_id == tenant_id
    ).first()
    
    return config


@router.post("/", response_model=StorageConfigResponse, status_code=status.HTTP_201_CREATED)
def create_storage_config(
    config_data: StorageConfigCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Create storage configuration for tenant.
    
    - **provider**: Storage provider (local, s3, dropbox)
    - **base_path**: Base path for storage
    
    Note: tenant_id is automatically taken from X-Tenant-ID header
    """
    
    # Check if config already exists
    existing = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.tenant_id == tenant_id
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Storage config already exists for this tenant. Use PUT to update."
        )
    
    # Validate provider
    valid_providers = ["local", "s3", "dropbox"]
    if config_data.provider not in valid_providers:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
        )
    
    config = TenantStorageConfig(
        tenant_id=tenant_id,  # Use tenant_id from header
        provider=config_data.provider,
        base_path=config_data.base_path,
        credentials_encrypted=None  # TODO: Implement credentials encryption
    )
    db.add(config)
    db.commit()
    db.refresh(config)
    
    return config


@router.put("/", response_model=StorageConfigResponse)
def update_storage_config(
    config_data: StorageConfigUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Update storage configuration.
    
    All fields are optional. Only provided fields will be updated.
    """
    config = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.tenant_id == tenant_id
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage config not found. Use POST to create."
        )
    
    # Update fields
    if config_data.provider is not None:
        valid_providers = ["local", "s3", "dropbox"]
        if config_data.provider not in valid_providers:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid provider. Must be one of: {', '.join(valid_providers)}"
            )
        config.provider = config_data.provider
    
    if config_data.base_path is not None:
        config.base_path = config_data.base_path
    
    if config_data.credentials_encrypted is not None:
        config.credentials_encrypted = config_data.credentials_encrypted
    
    db.commit()
    db.refresh(config)
    
    return config


@router.delete("/", status_code=status.HTTP_204_NO_CONTENT)
def delete_storage_config(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Delete storage configuration."""
    config = db.query(TenantStorageConfig).filter(
        TenantStorageConfig.tenant_id == tenant_id
    ).first()
    
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Storage config not found"
        )
    
    db.delete(config)
    db.commit()
