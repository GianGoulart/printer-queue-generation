"""Tenant schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TenantBase(BaseModel):
    """Base tenant schema."""

    name: str


class TenantCreate(TenantBase):
    """Schema for creating a tenant."""

    pass


class TenantUpdate(BaseModel):
    """Schema for updating a tenant."""

    name: Optional[str] = None
    is_active: Optional[bool] = None


class TenantResponse(TenantBase):
    """Schema for tenant response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
