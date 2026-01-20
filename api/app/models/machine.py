"""Machine model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class Machine(Base):
    """Machine model for DTF printers."""

    __tablename__ = "machines"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    max_width_mm = Column(Float, nullable=False)
    max_length_mm = Column(Float, nullable=False)
    min_dpi = Column(Integer, nullable=False, default=300)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="machines")
    jobs = relationship("Job", back_populates="machine")

    def __repr__(self):
        return f"<Machine(id={self.id}, name={self.name}, tenant_id={self.tenant_id})>"
