"""Storage configuration model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class TenantStorageConfig(Base):
    """Tenant storage configuration for assets (S3/Dropbox/local)."""

    __tablename__ = "tenant_storage_configs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    provider = Column(String(50), nullable=False)  # 's3', 'dropbox', 'local'
    base_path = Column(String(500), nullable=False)
    credentials_encrypted = Column(Text, nullable=True)  # JSON encrypted credentials
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="storage_configs")

    def __repr__(self):
        return f"<TenantStorageConfig(id={self.id}, tenant_id={self.tenant_id}, provider={self.provider})>"
