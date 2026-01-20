"""Output schemas for job results."""

from typing import List, Optional

from pydantic import BaseModel, Field


class BaseOutput(BaseModel):
    """Schema for a single base output."""
    
    index: int = Field(..., description="Base index (1, 2, 3...)")
    pdf_uri: str = Field(..., description="URI of the PDF in storage")
    preview_uri: Optional[str] = Field(None, description="URI of preview PNG (optional)")
    width_mm: float = Field(..., description="Base width in millimeters")
    length_mm: float = Field(..., description="Base length in millimeters")
    items_count: int = Field(..., description="Number of items in this base")
    utilization: float = Field(..., description="Utilization percentage (0-100)")


class JobOutputsResponse(BaseModel):
    """Response schema for job outputs endpoint."""
    
    job_id: int = Field(..., description="Job ID")
    status: str = Field(..., description="Job status")
    bases: List[BaseOutput] = Field([], description="List of base outputs")
    total_bases: int = Field(..., description="Total number of bases")
    
    class Config:
        from_attributes = True
