"""Asset model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Asset(Base):
    """Asset model for artwork files."""

    __tablename__ = "assets"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    original_filename = Column(String(500), nullable=False)
    file_uri = Column(String(1000), nullable=False)
    sku_normalized = Column(String(255), nullable=False, index=True)  # Trigram index will be added via migration
    metadata_json = Column(Text, nullable=True)  # JSON metadata (dimensions, format, etc.)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="assets")
    job_items = relationship("JobItem", back_populates="asset")

    def __repr__(self):
        return f"<Asset(id={self.id}, sku={self.sku_normalized}, tenant_id={self.tenant_id})>"
