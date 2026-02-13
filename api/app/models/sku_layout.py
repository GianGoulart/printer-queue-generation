"""SKU Layout model: tenant-specific regex/mask patterns for SKU extraction."""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class SkuLayout(Base):
    """
    SKU layout (mask) per tenant for deterministic extraction from picklists.
    Applied by priority; supports regex or mask syntax with optional separators.
    """

    __tablename__ = "sku_layouts"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(255), nullable=False)
    # regex | mask
    pattern_type = Column(String(20), nullable=False, default="regex")
    # Raw regex or mask e.g. {categoria}-{id}-{nome}-{tamanho}
    pattern = Column(Text, nullable=False)
    # JSON array of example SKU strings for testing
    example_samples = Column(Text, nullable=True)
    priority = Column(Integer, nullable=False, default=0)
    active = Column(Boolean, nullable=False, default=True)
    allow_hyphen_variants = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="sku_layouts")

    def __repr__(self):
        return f"<SkuLayout(id={self.id}, tenant_id={self.tenant_id}, name={self.name!r}, priority={self.priority})>"
