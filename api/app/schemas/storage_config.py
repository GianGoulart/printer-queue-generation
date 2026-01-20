"""Storage config schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StorageConfigBase(BaseModel):
    """Base storage config schema."""

    provider: str = Field(..., description="Storage provider (local, s3, dropbox)")
    base_path: str = Field(..., description="Base path for storage")


class StorageConfigCreate(StorageConfigBase):
    """Schema for creating a storage config."""
    
    # tenant_id comes from X-Tenant-ID header, not from body
    pass


class StorageConfigUpdate(BaseModel):
    """Schema for updating a storage config."""

    provider: Optional[str] = None
    base_path: Optional[str] = None
    credentials_encrypted: Optional[str] = None


class StorageConfigResponse(BaseModel):
    """Schema for storage config response (without sensitive data)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    provider: str
    base_path: str
    created_at: datetime
    updated_at: datetime
    
    # credentials_encrypted is excluded from response for security
