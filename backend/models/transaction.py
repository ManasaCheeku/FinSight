"""
Transaction model — a single financial movement (revenue or expense).
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from database import Base


class TransactionType(str, enum.Enum):
    revenue = "revenue"
    expense = "expense"


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime, nullable=False, index=True)
    amount = Column(Float, nullable=False)                       # Always positive
    type = Column(Enum(TransactionType), nullable=False)        # revenue | expense
    category = Column(String(100), nullable=False)
    description = Column(String(500), nullable=False)
    vendor_id = Column(Integer, ForeignKey("vendors.id"), nullable=True)
    reference_number = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    vendor = relationship("Vendor", back_populates="transactions")

    def __repr__(self):
        return (
            f"<Transaction id={self.id} type='{self.type}' "
            f"amount={self.amount:.2f} date={self.date.date()}>"
        )
