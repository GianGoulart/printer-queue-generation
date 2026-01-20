"""Job item model."""

from datetime import datetime

from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class JobItem(Base):
    """Job item model for individual items in a job."""

    __tablename__ = "job_items"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = Column(String(255), nullable=False, index=True)
    quantity = Column(Integer, nullable=False, default=1)
    size_label = Column(String(50), nullable=True)  # P, M, G, GG, etc.
    picklist_position = Column(Integer, nullable=True, index=True)  # ✅ Ordem original do picklist
    asset_id = Column(Integer, ForeignKey("assets.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="pending")
    # Status: pending, resolved, needs_input, packed
    final_width_mm = Column(Float, nullable=True)
    final_height_mm = Column(Float, nullable=True)
    base_index = Column(Integer, nullable=True)  # Which base PDF (Base 1, Base 2, etc.)
    x_mm = Column(Float, nullable=True)  # X position in base
    y_mm = Column(Float, nullable=True)  # Y position in base
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    job = relationship("Job", back_populates="items")
    asset = relationship("Asset", back_populates="job_items")

    def __repr__(self):
        return f"<JobItem(id={self.id}, sku={self.sku}, job_id={self.job_id})>"
