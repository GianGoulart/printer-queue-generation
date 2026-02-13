"""Job schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class JobMode:
    """Job processing modes."""
    
    SEQUENCE = "sequence"  # Process in PDF order
    OPTIMIZE = "optimize"  # Optimize for minimal waste


class JobStatus:
    """Job status values."""
    
    QUEUED = "queued"
    PROCESSING = "processing"
    NEEDS_INPUT = "needs_input"
    COMPLETED = "completed"
    FAILED = "failed"


class JobItemStatus:
    """Job item status values."""
    
    PENDING = "pending"
    RESOLVED = "resolved"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    SKIPPED = "skipped"  # User chose to skip this item (generate base without it)
    PACKED = "packed"


# Job Create/Update Schemas
class JobCreateRequest(BaseModel):
    """Request to create a new job."""
    
    mode: str = Field(
        default=JobMode.SEQUENCE,
        description="Processing mode: 'sequence' or 'optimize'",
        pattern="^(sequence|optimize)$"
    )
    sizing_profile_id: Optional[int] = Field(
        None,
        description="Default sizing profile ID (optional, can vary per item)"
    )
    machine_id: Optional[int] = Field(
        None,
        description="Target machine ID (optional)"
    )


class JobCreateResponse(BaseModel):
    """Response after creating a job."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    status: str
    mode: str
    picklist_uri: str
    created_at: datetime


# Job Item Schemas
class JobItemResponse(BaseModel):
    """Response schema for job item."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    job_id: int
    sku: str
    quantity: int
    size_label: Optional[str]
    asset_id: Optional[int]
    status: str
    final_width_mm: Optional[float]
    final_height_mm: Optional[float]
    base_index: Optional[int]
    x_mm: Optional[float]
    y_mm: Optional[float]
    created_at: datetime


# Job Detail Schemas
class JobDetailResponse(BaseModel):
    """Detailed job response with items."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    tenant_id: int
    machine_id: Optional[int]
    sizing_profile_id: Optional[int]
    status: str
    mode: str
    picklist_uri: str
    manifest_json: Optional[str]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime]
    
    # Computed fields
    items_count: int = Field(0, description="Total number of items")
    items_resolved: int = Field(0, description="Number of resolved items")
    items_pending: int = Field(0, description="Number of items needing input")
    items_skipped: int = Field(0, description="Number of skipped items")


class JobListItem(BaseModel):
    """Simplified job info for list view."""
    
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    status: str
    mode: str
    picklist_uri: str
    items_count: int = 0
    created_at: datetime
    updated_at: datetime


class JobListResponse(BaseModel):
    """Paginated list of jobs."""
    
    items: List[JobListItem]
    total: int
    page: int
    size: int
    pages: int


# SKU Resolution Schemas
class AssetCandidate(BaseModel):
    """Asset candidate for ambiguous SKU."""
    
    asset_id: int
    sku: str
    file_uri: str
    score: float = Field(..., description="Similarity score (0.0 to 1.0)")


class PendingItemResponse(BaseModel):
    """Response for items needing manual resolution."""
    
    id: int
    sku: str
    sku_design: Optional[str] = Field(
        None,
        description="SKU with tenant sizing prefixes stripped (design-only), for display and matching"
    )
    quantity: int
    size_label: Optional[str]
    status: str  # 'missing', 'ambiguous', or 'needs_input' (render failure)
    candidates: List[AssetCandidate] = Field(
        default_factory=list,
        description="Candidate assets (empty for missing SKUs)"
    )


class PendingItemsResponse(BaseModel):
    """Response containing all pending items."""
    
    items: List[PendingItemResponse]


class ItemResolution(BaseModel):
    """Manual resolution for a single item."""
    
    item_id: int = Field(..., description="Job item ID to resolve")
    asset_id: int = Field(..., description="Asset ID to assign")


class JobResolveRequest(BaseModel):
    """Request to manually resolve job items."""
    
    resolutions: List[ItemResolution] = Field(
        ...,
        description="List of item resolutions",
        min_length=1
    )


class JobResolveResponse(BaseModel):
    """Response after resolving items."""
    
    status: str
    resolved_count: int
    job_status: str
    message: str


class JobSkipRequest(BaseModel):
    """Request to skip job items (generate base without them)."""
    
    item_ids: List[int] = Field(
        ...,
        description="List of item IDs to skip",
        min_length=1
    )


class JobSkipResponse(BaseModel):
    """Response after skipping items."""
    
    status: str
    skipped_count: int
    job_status: str
    message: str
