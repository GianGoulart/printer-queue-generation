"""SKU Layout schemas."""

import json
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _example_samples_to_list(v: Any) -> Optional[List[str]]:
    if v is None:
        return None
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        try:
            return json.loads(v) if v.strip() else None
        except json.JSONDecodeError:
            return None
    return None


class SkuLayoutBase(BaseModel):
    """Base SKU layout schema."""

    name: str = Field(..., min_length=1, max_length=255)
    pattern_type: str = Field(default="regex", pattern="^(regex|mask)$")
    pattern: str = Field(..., min_length=1)
    example_samples: Optional[List[str]] = None
    priority: int = Field(default=0, ge=-1000, le=1000)
    active: bool = True
    allow_hyphen_variants: bool = True


class SkuLayoutCreate(SkuLayoutBase):
    """Schema for creating an SKU layout."""

    created_by: Optional[str] = None


class SkuLayoutUpdate(BaseModel):
    """Schema for updating an SKU layout (partial)."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    pattern_type: Optional[str] = Field(None, pattern="^(regex|mask)$")
    pattern: Optional[str] = None
    example_samples: Optional[List[str]] = None
    priority: Optional[int] = Field(None, ge=-1000, le=1000)
    active: Optional[bool] = None
    allow_hyphen_variants: Optional[bool] = None


class SkuLayoutResponse(SkuLayoutBase):
    """Schema for SKU layout response."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("example_samples", mode="before")
    @classmethod
    def parse_example_samples(cls, v: Any) -> Optional[List[str]]:
        return _example_samples_to_list(v)


class SkuLayoutTestRequest(BaseModel):
    """Request body for testing a layout against sample text."""

    sample_text: str = Field(..., min_length=1)
    layout_id: Optional[int] = None  # If omitted, use pattern from body
    pattern: Optional[str] = None
    pattern_type: Optional[str] = Field(None, pattern="^(regex|mask)$")


class SkuLayoutTestMatch(BaseModel):
    """A single match from layout test."""

    full_match: str
    start: int
    end: int
    groups: Optional[dict[str, str]] = None
    layout_id: Optional[int] = None
    layout_name: Optional[str] = None


class SkuLayoutTestResponse(BaseModel):
    """Response for layout test: list of matches."""

    matches: List[SkuLayoutTestMatch]
    normalized: Optional[List[str]] = None
    error: Optional[str] = None
