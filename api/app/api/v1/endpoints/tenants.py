"""Tenant endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantResponse, TenantUpdate

router = APIRouter()


@router.get("/", response_model=List[TenantResponse])
def list_tenants(
    db: Session = Depends(get_db),
    include_inactive: bool = False
):
    """
    List all tenants.
    
    - **include_inactive**: Include inactive tenants (default: false)
    """
    query = db.query(Tenant)
    if not include_inactive:
        query = query.filter(Tenant.is_active == True)
    tenants = query.all()
    return tenants


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
def create_tenant(
    tenant_data: TenantCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new tenant.
    
    - **name**: Tenant name (required)
    """
    # Check if tenant with same name exists
    existing = db.query(Tenant).filter(Tenant.name == tenant_data.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant with name '{tenant_data.name}' already exists"
        )
    
    # Create tenant
    tenant = Tenant(
        name=tenant_data.name,
        is_active=True
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    
    return tenant


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: int,
    db: Session = Depends(get_db)
):
    """Get tenant by ID."""
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    return tenant


@router.put("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: int,
    tenant_data: TenantUpdate,
    db: Session = Depends(get_db)
):
    """
    Update tenant.
    
    - **name**: New tenant name (optional)
    - **is_active**: Active status (optional)
    """
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found"
        )
    
    # Update fields
    if tenant_data.name is not None:
        tenant.name = tenant_data.name
    if tenant_data.is_active is not None:
        tenant.is_active = tenant_data.is_active
    
    db.commit()
    db.refresh(tenant)
    
    return tenant
