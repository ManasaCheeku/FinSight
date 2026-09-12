"""
Vendor model — represents a business the company pays or receives from.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.orm import relationship

from database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, unique=True)
    category = Column(String(100), nullable=False)          # e.g. "Software", "Marketing"
    contact_email = Column(String(200), nullable=True)
    payment_terms = Column(String(50), nullable=False, default="Net 30")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    transactions = relationship("Transaction", back_populates="vendor")
    invoices = relationship("Invoice", back_populates="vendor")

    def __repr__(self):
        return f"<Vendor id={self.id} name='{self.name}' category='{self.category}'>"
