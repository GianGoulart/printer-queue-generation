"""Job model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database import Base


class Job(Base):
    """Job model for processing requests."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(Integer, ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    machine_id = Column(Integer, ForeignKey("machines.id", ondelete="SET NULL"), nullable=True, index=True)
    sizing_profile_id = Column(Integer, ForeignKey("sizing_profiles.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="queued", index=True)
    # Status: queued, processing, completed, failed, needs_input
    mode = Column(String(50), nullable=False, default="sequence")  # sequence or optimize
    picklist_uri = Column(String(1000), nullable=False)
    manifest_json = Column(Text, nullable=True)  # JSON with final manifest
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    tenant = relationship("Tenant", back_populates="jobs")
    machine = relationship("Machine", back_populates="jobs")
    sizing_profile = relationship("SizingProfile")
    items = relationship(
        "JobItem",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="JobItem.id"  # ✅ Garantir ordem consistente (mesma ordem do picklist)
    )

    def __repr__(self):
        return f"<Job(id={self.id}, status={self.status}, tenant_id={self.tenant_id})>"
