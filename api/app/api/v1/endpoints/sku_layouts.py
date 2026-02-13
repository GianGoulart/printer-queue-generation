"""SKU Layout endpoints: CRUD and test per tenant."""

import json
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.sku_layout import SkuLayout
from app.models.tenant import Tenant
from app.schemas.sku_layout import (
    SkuLayoutCreate,
    SkuLayoutResponse,
    SkuLayoutTestMatch,
    SkuLayoutTestRequest,
    SkuLayoutTestResponse,
    SkuLayoutUpdate,
)
from app.services.sku_layout_service import find_matches, normalize_sku_for_catalog

router = APIRouter()


def get_tenant_or_404(
    tenant_id: int = Path(..., description="Tenant ID"),
    db: Session = Depends(get_db),
) -> Tenant:
    """Ensure tenant exists and return it."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )
    return tenant


def get_layout_or_404(
    layout_id: int,
    tenant_id: int,
    db: Session,
) -> SkuLayout:
    """Ensure layout exists for tenant and return it."""
    layout = (
        db.query(SkuLayout)
        .filter(SkuLayout.id == layout_id, SkuLayout.tenant_id == tenant_id)
        .first()
    )
    if not layout:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SKU layout {layout_id} not found for tenant {tenant_id}",
        )
    return layout


@router.get("/", response_model=List[SkuLayoutResponse])
def list_sku_layouts(
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
    active_only: bool = True,
):
    """List SKU layouts for the tenant, ordered by priority (asc)."""
    q = db.query(SkuLayout).filter(SkuLayout.tenant_id == tenant.id)
    if active_only:
        q = q.filter(SkuLayout.active == True)
    layouts = q.order_by(SkuLayout.priority.asc(), SkuLayout.id.asc()).all()
    return layouts


@router.post("/", response_model=SkuLayoutResponse, status_code=status.HTTP_201_CREATED)
def create_sku_layout(
    body: SkuLayoutCreate,
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
):
    """Create a new SKU layout for the tenant."""
    layout = SkuLayout(
        tenant_id=tenant.id,
        name=body.name,
        pattern_type=body.pattern_type,
        pattern=body.pattern,
        example_samples=json.dumps(body.example_samples) if body.example_samples else None,
        priority=body.priority,
        active=body.active,
        allow_hyphen_variants=body.allow_hyphen_variants,
        created_by=body.created_by,
    )
    db.add(layout)
    db.commit()
    db.refresh(layout)
    return layout


@router.get("/{layout_id}", response_model=SkuLayoutResponse)
def get_sku_layout(
    layout_id: int,
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
):
    """Get a single SKU layout by ID."""
    layout = get_layout_or_404(layout_id, tenant.id, db)
    return layout


@router.put("/{layout_id}", response_model=SkuLayoutResponse)
def update_sku_layout(
    layout_id: int,
    body: SkuLayoutUpdate,
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
):
    """Update an SKU layout (partial)."""
    layout = get_layout_or_404(layout_id, tenant.id, db)
    if body.name is not None:
        layout.name = body.name
    if body.pattern_type is not None:
        layout.pattern_type = body.pattern_type
    if body.pattern is not None:
        layout.pattern = body.pattern
    if body.example_samples is not None:
        layout.example_samples = json.dumps(body.example_samples)
    if body.priority is not None:
        layout.priority = body.priority
    if body.active is not None:
        layout.active = body.active
    if body.allow_hyphen_variants is not None:
        layout.allow_hyphen_variants = body.allow_hyphen_variants
    db.commit()
    db.refresh(layout)
    return layout


@router.delete("/{layout_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sku_layout(
    layout_id: int,
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
):
    """Delete an SKU layout."""
    layout = get_layout_or_404(layout_id, tenant.id, db)
    db.delete(layout)
    db.commit()
    return None


@router.post("/test", response_model=SkuLayoutTestResponse)
def test_sku_layout(
    body: SkuLayoutTestRequest,
    tenant: Tenant = Depends(get_tenant_or_404),
    db: Session = Depends(get_db),
):
    """
    Test a layout (or ad-hoc pattern) against sample text.
    Returns matches with positions and optional normalized SKUs.
    """
    pattern = body.pattern
    pattern_type = body.pattern_type or "regex"
    layout_id = body.layout_id
    layout_name = None

    allow_hyphen = True
    if layout_id:
        layout = get_layout_or_404(layout_id, tenant.id, db)
        pattern = layout.pattern
        pattern_type = layout.pattern_type
        layout_name = layout.name
        allow_hyphen = layout.allow_hyphen_variants
    elif not pattern:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either layout_id or pattern",
        )

    try:
        raw_matches = find_matches(
            body.sample_text,
            pattern=pattern,
            pattern_type=pattern_type,
            allow_hyphen_variants=allow_hyphen,
        )
    except Exception as e:
        return SkuLayoutTestResponse(matches=[], error=str(e))

    matches = [
        SkuLayoutTestMatch(
            full_match=m[0],
            start=m[1],
            end=m[2],
            groups=m[3],
            layout_id=layout_id,
            layout_name=layout_name,
        )
        for m in raw_matches
    ]
    normalized = [normalize_sku_for_catalog(m.full_match) for m in matches]
    return SkuLayoutTestResponse(matches=matches, normalized=normalized)
