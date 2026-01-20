"""Machine schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class MachineBase(BaseModel):
    """Base machine schema."""

    name: str = Field(..., description="Machine name")
    max_width_mm: float = Field(..., description="Maximum width in millimeters", gt=0)
    max_length_mm: float = Field(..., description="Maximum length in millimeters", gt=0)
    min_dpi: int = Field(300, description="Minimum DPI requirement", ge=72)


class MachineCreate(MachineBase):
    """Schema for creating a machine."""
    
    # tenant_id comes from X-Tenant-ID header, not from body
    pass


class MachineUpdate(BaseModel):
    """Schema for updating a machine."""

    name: Optional[str] = None
    max_width_mm: Optional[float] = Field(None, gt=0)
    max_length_mm: Optional[float] = Field(None, gt=0)
    min_dpi: Optional[int] = Field(None, ge=72)


class MachineResponse(MachineBase):
    """Schema for machine response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_at: datetime
