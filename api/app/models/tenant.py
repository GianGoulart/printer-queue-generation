"""Tenant model."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Tenant(Base):
    """Tenant model for multi-tenancy."""

    __tablename__ = "tenants"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    machines = relationship("Machine", back_populates="tenant", cascade="all, delete-orphan")
    storage_configs = relationship("TenantStorageConfig", back_populates="tenant", cascade="all, delete-orphan")
    assets = relationship("Asset", back_populates="tenant", cascade="all, delete-orphan")
    jobs = relationship("Job", back_populates="tenant", cascade="all, delete-orphan")
    sizing_profiles = relationship("SizingProfile", back_populates="tenant", cascade="all, delete-orphan")
    sku_layouts = relationship("SkuLayout", back_populates="tenant", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Tenant(id={self.id}, name={self.name})>"
