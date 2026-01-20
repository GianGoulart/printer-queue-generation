"""Sizing profile endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.sizing_profile import SizingProfile
from app.schemas.sizing_profile import (
    SizingProfileCreate,
    SizingProfileResponse,
    SizingProfileUpdate,
)

router = APIRouter()


@router.get("/", response_model=List[SizingProfileResponse])
def list_sizing_profiles(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """List all sizing profiles for the tenant."""
    profiles = db.query(SizingProfile).filter(
        SizingProfile.tenant_id == tenant_id
    ).order_by(SizingProfile.target_width_mm).all()
    return profiles


@router.post("/", response_model=SizingProfileResponse, status_code=status.HTTP_201_CREATED)
def create_sizing_profile(
    profile_data: SizingProfileCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Create a new sizing profile.
    
    - **size_label**: Size label (e.g., P, M, G, GG, Infantil, Plus Size)
    - **target_width_mm**: Target width in millimeters
    - **sku_prefix**: Optional SKU prefix for auto-matching (e.g., 'inf-', 'plus-', 'bl-')
    - **is_default**: Set as default profile when no prefix matches
    
    Note: tenant_id is automatically taken from X-Tenant-ID header
    """
    
    # Check if size_label already exists for this tenant
    existing = db.query(SizingProfile).filter(
        SizingProfile.tenant_id == tenant_id,
        SizingProfile.size_label == profile_data.size_label
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Sizing profile with label '{profile_data.size_label}' already exists"
        )
    
    # Check if sku_prefix already exists (if provided)
    if profile_data.sku_prefix:
        existing_prefix = db.query(SizingProfile).filter(
            SizingProfile.tenant_id == tenant_id,
            SizingProfile.sku_prefix == profile_data.sku_prefix
        ).first()
        
        if existing_prefix:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sizing profile with prefix '{profile_data.sku_prefix}' already exists"
            )
    
    profile = SizingProfile(
        tenant_id=tenant_id,  # Use tenant_id from header
        size_label=profile_data.size_label,
        target_width_mm=profile_data.target_width_mm,
        sku_prefix=profile_data.sku_prefix,
        is_default=profile_data.is_default
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    
    return profile


@router.get("/{profile_id}", response_model=SizingProfileResponse)
def get_sizing_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Get sizing profile by ID."""
    profile = db.query(SizingProfile).filter(
        SizingProfile.id == profile_id,
        SizingProfile.tenant_id == tenant_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sizing profile {profile_id} not found"
        )
    
    return profile


@router.put("/{profile_id}", response_model=SizingProfileResponse)
def update_sizing_profile(
    profile_id: int,
    profile_data: SizingProfileUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Update sizing profile.
    
    - **size_label**: Size label (optional)
    - **target_width_mm**: Target width in mm (optional)
    - **sku_prefix**: SKU prefix for auto-matching (optional)
    - **is_default**: Set as default profile (optional)
    """
    profile = db.query(SizingProfile).filter(
        SizingProfile.id == profile_id,
        SizingProfile.tenant_id == tenant_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sizing profile {profile_id} not found"
        )
    
    # Check if sku_prefix conflicts with another profile (if being updated)
    if profile_data.sku_prefix is not None and profile_data.sku_prefix != profile.sku_prefix:
        existing_prefix = db.query(SizingProfile).filter(
            SizingProfile.tenant_id == tenant_id,
            SizingProfile.sku_prefix == profile_data.sku_prefix,
            SizingProfile.id != profile_id
        ).first()
        
        if existing_prefix:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Sizing profile with prefix '{profile_data.sku_prefix}' already exists"
            )
    
    # Update fields
    if profile_data.size_label is not None:
        profile.size_label = profile_data.size_label
    if profile_data.target_width_mm is not None:
        profile.target_width_mm = profile_data.target_width_mm
    if profile_data.sku_prefix is not None:
        profile.sku_prefix = profile_data.sku_prefix
    if profile_data.is_default is not None:
        profile.is_default = profile_data.is_default
    
    db.commit()
    db.refresh(profile)
    
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_sizing_profile(
    profile_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Delete sizing profile."""
    profile = db.query(SizingProfile).filter(
        SizingProfile.id == profile_id,
        SizingProfile.tenant_id == tenant_id
    ).first()
    
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sizing profile {profile_id} not found"
        )
    
    db.delete(profile)
    db.commit()
