"""Sizing profile model."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class SizingProfile(Base):
    """Sizing profile for different garment sizes."""

    __tablename__ = "sizing_profiles"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    size_label = Column(String(50), nullable=False)  # P, M, G, GG, Infantil, Plus Size, etc.
    target_width_mm = Column(Float, nullable=False)
    sku_prefix = Column(String(20), nullable=True)  # SKU prefix for auto-matching (e.g., 'inf-', 'plus-')
    is_default = Column(Boolean, default=False, nullable=False)  # Use as fallback when no prefix matches
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="sizing_profiles")

    def __repr__(self):
        return f"<SizingProfile(id={self.id}, size={self.size_label}, width={self.target_width_mm}mm, prefix={self.sku_prefix})>"
