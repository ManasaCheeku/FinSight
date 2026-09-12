"""
conftest.py — shared pytest fixtures for FinSight tests.

Uses an in-memory SQLite database seeded with a minimal
but complete dataset for deterministic testing.
"""

import sys
import os
import pytest
from datetime import datetime, timedelta

# Make backend/ importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.vendor import Vendor
from models.transaction import Transaction, TransactionType
from models.invoice import Invoice, InvoiceStatus
from models.budget import Budget


@pytest.fixture(scope="session")
def db():
    """
    In-memory SQLite session seeded with test data.
    Shared across the test session for performance.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    # Patch the engine used by services
    import database as db_module
    original_engine = db_module.engine
    db_module.engine = engine

    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    # ── Seed vendors ──────────────────────────────────────────
    vendors = [
        Vendor(name="CloudEdge Solutions",  category="Software",  contact_email="a@ce.io",  payment_terms="Net 30"),
        Vendor(name="BrightPulse Marketing",category="Marketing", contact_email="b@bp.co",  payment_terms="Net 30"),
        Vendor(name="NovaPay Payroll",       category="HR & Payroll", contact_email="c@np.com", payment_terms="Net 7"),
        Vendor(name="DataStream Analytics", category="Software",  contact_email="d@ds.ai",  payment_terms="Net 15"),
    ]
    for v in vendors:
        session.add(v)
    session.flush()

    ce_id  = vendors[0].id
    bp_id  = vendors[1].id
    np_id  = vendors[2].id
    ds_id  = vendors[3].id

    # ── Seed 12 months of transactions ────────────────────────
    base_rev = 100_000
    base_exp = 80_000

    for i in range(12):
        mo = (9 + i - 1) % 12 + 1
        yr = 2025 if i < 4 else 2026

        # Revenue
        session.add(Transaction(
            date=datetime(yr, mo, 15),
            amount=round(base_rev + i * 1_000, 2),
            type=TransactionType.revenue,
            category="Product Sales",
            description=f"Revenue {yr}-{mo:02d}",
            reference_number=f"REV-{yr}{mo:02d}",
        ))

        # Normal Software expense
        session.add(Transaction(
            date=datetime(yr, mo, 10),
            amount=8_000.0,
            type=TransactionType.expense,
            category="Software",
            description=f"Software {yr}-{mo:02d}",
            vendor_id=ce_id,
            reference_number=f"EXP-{yr}{mo:02d}-SW",
        ))

        # Normal Marketing expense
        mkt_amt = 12_000.0
        # A3: Marketing spike in Jun 2026
        if yr == 2026 and mo == 6:
            mkt_amt = 48_000.0
        session.add(Transaction(
            date=datetime(yr, mo, 12),
            amount=mkt_amt,
            type=TransactionType.expense,
            category="Marketing",
            description=f"Marketing {yr}-{mo:02d}",
            vendor_id=bp_id,
            reference_number=f"EXP-{yr}{mo:02d}-MKT",
        ))

        # HR Payroll — A5 spike Feb 2026
        hr_amt = 45_000.0
        if yr == 2026 and mo == 2:
            hr_amt = 144_000.0   # 3× spike
        session.add(Transaction(
            date=datetime(yr, mo, 28),
            amount=hr_amt,
            type=TransactionType.expense,
            category="HR & Payroll",
            description=f"Payroll {yr}-{mo:02d}",
            vendor_id=np_id,
            reference_number=f"EXP-{yr}{mo:02d}-HR",
        ))

    # A1: Unusually large CloudEdge payment
    session.add(Transaction(
        date=datetime(2026, 3, 25),
        amount=47_500.0,
        type=TransactionType.expense,
        category="Software",
        description="CloudEdge enterprise upgrade — large payment",
        vendor_id=ce_id,
        reference_number="EXP-202603-CE-ANOMALY",
    ))

    session.flush()

    # ── Seed invoices ─────────────────────────────────────────
    # Normal invoices
    for i in range(10):
        session.add(Invoice(
            vendor_id=ce_id,
            invoice_number=f"INV-CE-{i+1:04d}",
            amount=8_000.0,
            status=InvoiceStatus.paid,
            issue_date=datetime(2025, 9 + i % 3, 5),
            due_date=datetime(2025, 9 + i % 3, 5) + timedelta(days=30),
            paid_date=datetime(2025, 9 + i % 3, 20),
        ))

    # A1 large invoice
    session.add(Invoice(
        vendor_id=ce_id,
        invoice_number="INV-CE-ANOMALY-2603",
        amount=47_500.0,
        status=InvoiceStatus.paid,
        issue_date=datetime(2026, 3, 10),
        due_date=datetime(2026, 4, 9),
        paid_date=datetime(2026, 3, 25),
    ))

    # A2 duplicate invoice
    for _ in range(2):
        session.add(Invoice(
            vendor_id=bp_id,
            invoice_number="INV-MKT-0312",
            amount=12_000.0,
            status=InvoiceStatus.pending,
            issue_date=datetime(2026, 3, 12),
            due_date=datetime(2026, 4, 11),
        ))

    # A4 DataStream frequency: 5 invoices in Jul 2026
    for j in range(5):
        session.add(Invoice(
            vendor_id=ds_id,
            invoice_number=f"INV-DS-FREQ-{j+1:02d}",
            amount=2_200.0,
            status=InvoiceStatus.pending,
            issue_date=datetime(2026, 7, j + 1),
            due_date=datetime(2026, 7, j + 16),
        ))

    # A pending invoice
    session.add(Invoice(
        vendor_id=bp_id,
        invoice_number="INV-BP-PENDING",
        amount=5_000.0,
        status=InvoiceStatus.pending,
        issue_date=datetime(2026, 8, 1),
        due_date=datetime(2026, 8, 31),
    ))

    session.flush()

    # ── Seed budgets ──────────────────────────────────────────
    for i in range(12):
        mo = (9 + i - 1) % 12 + 1
        yr = 2025 if i < 4 else 2026
        mkt_actual = 48_000.0 if (yr == 2026 and mo == 6) else 12_000.0
        session.add(Budget(year=yr, month=mo, category="Software",
                           planned_amount=8_500.0, actual_amount=8_000.0))
        session.add(Budget(year=yr, month=mo, category="Marketing",
                           planned_amount=13_000.0, actual_amount=mkt_actual))
        session.add(Budget(year=yr, month=mo, category="HR & Payroll",
                           planned_amount=46_000.0,
                           actual_amount=144_000.0 if (yr == 2026 and mo == 2) else 45_000.0))

    session.commit()

    yield session

    session.close()
    db_module.engine = original_engine
