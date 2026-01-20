"""Asset schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AssetBase(BaseModel):
    """Base asset schema."""

    sku_normalized: str = Field(..., description="Normalized SKU")
    original_filename: str = Field(..., description="Original filename")
    file_uri: str = Field(..., description="File URI in storage")


class AssetCreate(AssetBase):
    """Schema for creating an asset."""

    tenant_id: int
    metadata_json: Optional[str] = None


class AssetUpdate(BaseModel):
    """Schema for updating an asset."""

    original_filename: Optional[str] = None
    file_uri: Optional[str] = None
    sku_normalized: Optional[str] = None
    metadata_json: Optional[str] = None


class AssetResponse(AssetBase):
    """Schema for asset response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    metadata_json: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class AssetWithMetadata(AssetResponse):
    """Asset response with parsed metadata."""

    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Parsed metadata dict"
    )


class AssetReindexRequest(BaseModel):
    """Request to reindex assets."""

    force: bool = Field(
        default=False, description="Force reindex even if assets exist"
    )


class AssetReindexResponse(BaseModel):
    """Response for reindex request."""

    task_id: str = Field(..., description="Celery task ID")
    status: str = Field(..., description="Task status")
    message: str = Field(..., description="Human-readable message")


class AssetReindexStatus(BaseModel):
    """Status of reindex task."""

    task_id: str
    status: str  # pending, started, success, failure
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class AssetSearchRequest(BaseModel):
    """Request for asset search."""

    sku: str = Field(..., description="SKU to search for", min_length=1)
    threshold: float = Field(
        default=0.3,
        description="Minimum similarity score (0.0 to 1.0)",
        ge=0.0,
        le=1.0,
    )
    limit: int = Field(default=10, description="Maximum results", ge=1, le=100)


class AssetSearchResult(BaseModel):
    """Single search result with score."""

    asset: AssetResponse
    score: float = Field(..., description="Similarity score (0.0 to 1.0)")


class AssetSearchResponse(BaseModel):
    """Response for asset search."""

    query: str = Field(..., description="Original query")
    threshold: float = Field(..., description="Threshold used")
    results: List[AssetSearchResult] = Field(..., description="Search results")
    total: int = Field(..., description="Total results found")


class AssetListRequest(BaseModel):
    """Request for listing assets."""

    page: int = Field(default=1, description="Page number", ge=1)
    size: int = Field(default=20, description="Page size", ge=1, le=100)
    sku_filter: Optional[str] = Field(
        None, description="Filter by SKU (partial match)"
    )
    format_filter: Optional[str] = Field(None, description="Filter by format (PNG, JPEG, etc)")


class AssetListResponse(BaseModel):
    """Response for listing assets."""

    items: List[AssetResponse] = Field(..., description="Assets in this page")
    total: int = Field(..., description="Total assets matching filters")
    page: int = Field(..., description="Current page")
    size: int = Field(..., description="Page size")
    pages: int = Field(..., description="Total pages")


class StorageTestResponse(BaseModel):
    """Response for storage connection test."""

    status: str = Field(..., description="Status: ok or error")
    provider: str = Field(..., description="Storage provider")
    message: Optional[str] = Field(None, description="Error message if failed")
    base_path: Optional[str] = Field(None, description="Base path")
