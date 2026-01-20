"""Sizing profile schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class SizingProfileBase(BaseModel):
    """Base sizing profile schema."""

    size_label: str = Field(..., description="Size label (e.g., P, M, G, GG)")
    target_width_mm: float = Field(..., description="Target width in millimeters", gt=0)


class SizingProfileCreate(SizingProfileBase):
    """Schema for creating a sizing profile."""
    
    # tenant_id comes from X-Tenant-ID header, not from body
    sku_prefix: Optional[str] = Field(None, max_length=20, description="SKU prefix for auto-matching (e.g., 'inf-', 'plus-', 'bl-')")
    is_default: bool = Field(False, description="Use as fallback when no prefix matches")


class SizingProfileUpdate(BaseModel):
    """Schema for updating a sizing profile."""

    size_label: Optional[str] = None
    target_width_mm: Optional[float] = Field(None, gt=0)
    sku_prefix: Optional[str] = Field(None, max_length=20)
    is_default: Optional[bool] = None


class SizingProfileResponse(SizingProfileBase):
    """Schema for sizing profile response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    sku_prefix: Optional[str] = None
    is_default: bool = False
    created_at: datetime
