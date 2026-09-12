"""
Budget model — planned vs actual spending by category and month.
"""

from sqlalchemy import Column, Integer, String, Float, UniqueConstraint

from database import Base


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)          # 1–12
    category = Column(String(100), nullable=False)
    planned_amount = Column(Float, nullable=False)
    actual_amount = Column(Float, nullable=False, default=0.0)

    __table_args__ = (
        UniqueConstraint("year", "month", "category", name="uq_budget_period_category"),
    )

    def __repr__(self):
        return (
            f"<Budget year={self.year} month={self.month} "
            f"category='{self.category}' planned={self.planned_amount:.2f}>"
        )
