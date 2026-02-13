"""Schemas for image packing feature."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class ImagePlacementResponse(BaseModel):
    """Placement information for an image."""
    
    model_config = ConfigDict(from_attributes=True)
    
    item_id: int
    sku: str
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    rotated: bool


class BaseResponse(BaseModel):
    """Base information."""
    
    model_config = ConfigDict(from_attributes=True)
    
    index: int
    width_mm: float
    length_mm: float
    utilization: float
    items_count: int
    placements: List[ImagePlacementResponse]


class ImagePackingResultResponse(BaseModel):
    """Complete packing result."""
    
    model_config = ConfigDict(from_attributes=True)
    
    total_bases: int
    total_length_mm: float
    avg_utilization: float
    mode: str
    bases: List[BaseResponse]


class ImagePackingStatusResponse(BaseModel):
    """Job status response."""
    
    model_config = ConfigDict(from_attributes=True)
    
    job_id: str
    status: str
    progress: Optional[int] = None
    message: Optional[str] = None
    result: Optional[ImagePackingResultResponse] = None
    error: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ImagePackingUploadResponse(BaseModel):
    """Response after uploading images."""
    
    model_config = ConfigDict(from_attributes=True)
    
    job_id: str
    status: str
    message: str
