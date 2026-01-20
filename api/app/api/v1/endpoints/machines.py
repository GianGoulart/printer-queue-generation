"""Machine endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_tenant_id
from app.models.machine import Machine
from app.schemas.machine import MachineCreate, MachineResponse, MachineUpdate

router = APIRouter()


@router.get("/", response_model=List[MachineResponse])
def list_machines(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """List all machines for the tenant."""
    machines = db.query(Machine).filter(Machine.tenant_id == tenant_id).all()
    return machines


@router.post("/", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
def create_machine(
    machine_data: MachineCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Create a new machine.
    
    - **name**: Machine name
    - **max_width_mm**: Maximum width in mm
    - **max_length_mm**: Maximum length in mm
    - **min_dpi**: Minimum DPI (default: 300)
    
    Note: tenant_id is automatically taken from X-Tenant-ID header
    """
    machine = Machine(
        tenant_id=tenant_id,  # Use tenant_id from header
        name=machine_data.name,
        max_width_mm=machine_data.max_width_mm,
        max_length_mm=machine_data.max_length_mm,
        min_dpi=machine_data.min_dpi
    )
    db.add(machine)
    db.commit()
    db.refresh(machine)
    
    return machine


@router.get("/{machine_id}", response_model=MachineResponse)
def get_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Get machine by ID."""
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == tenant_id
    ).first()
    
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found"
        )
    
    return machine


@router.put("/{machine_id}", response_model=MachineResponse)
def update_machine(
    machine_id: int,
    machine_data: MachineUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """
    Update machine.
    
    - **name**: Machine name (optional)
    - **max_width_mm**: Maximum width in mm (optional)
    - **max_length_mm**: Maximum length in mm (optional)
    - **min_dpi**: Minimum DPI (optional)
    """
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == tenant_id
    ).first()
    
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found"
        )
    
    # Update fields
    if machine_data.name is not None:
        machine.name = machine_data.name
    if machine_data.max_width_mm is not None:
        machine.max_width_mm = machine_data.max_width_mm
    if machine_data.max_length_mm is not None:
        machine.max_length_mm = machine_data.max_length_mm
    if machine_data.min_dpi is not None:
        machine.min_dpi = machine_data.min_dpi
    
    db.commit()
    db.refresh(machine)
    
    return machine


@router.delete("/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_machine(
    machine_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id)
):
    """Delete machine."""
    machine = db.query(Machine).filter(
        Machine.id == machine_id,
        Machine.tenant_id == tenant_id
    ).first()
    
    if not machine:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Machine {machine_id} not found"
        )
    
    db.delete(machine)
    db.commit()
