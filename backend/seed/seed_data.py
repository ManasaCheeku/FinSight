"""
FinSight -- Synthetic seed data generator.

Label: SYNTHETIC DEMO DATA
Coverage: Sep 2025 - Aug 2026 (12 months)
Anomalies planted (no flag field -- discovered by the anomaly engine):
  A1 -- Unusually large vendor payment (CloudEdge invoice, Mar 2026)
  A2 -- Duplicate invoice (INV-MKT-0312 appears twice)
  A3 -- Marketing expense spike (Jun 2026 -> 4× normal)
  A4 -- Unusual vendor invoice frequency (DataStream: 5 invoices in Jul 2026 vs. normal 1)
  A5 -- Unusual transaction amount (single HR payroll line 3× category average)

Run directly:  python seed/seed_data.py
"""

import sys
import os
import random
from datetime import datetime, timedelta, date

# Allow running from project root or backend/ dir
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal, init_db
from models.vendor import Vendor
from models.transaction import Transaction, TransactionType
from models.invoice import Invoice, InvoiceStatus
from models.budget import Budget

# --------------------------------------------------------------
# Constants
# --------------------------------------------------------------
DATASET_LABEL = "SYNTHETIC DEMO DATA"
SEED = 42
random.seed(SEED)

START_DATE = date(2025, 9, 1)   # inclusive
END_DATE   = date(2026, 8, 31)  # inclusive


# --------------------------------------------------------------
# Helper
# --------------------------------------------------------------
def rand_date(year: int, month: int) -> datetime:
    """Return a random datetime within the given month (workdays 1-28)."""
    day = random.randint(1, 28)
    return datetime(year, month, day, random.randint(8, 17), random.randint(0, 59))


def month_range():
    """Yield (year, month) tuples from START_DATE to END_DATE."""
    y, m = START_DATE.year, START_DATE.month
    while (y, m) <= (END_DATE.year, END_DATE.month):
        yield y, m
        m += 1
        if m > 12:
            m = 1
            y += 1


# --------------------------------------------------------------
# Vendor definitions
# --------------------------------------------------------------
VENDOR_DEFS = [
    {"name": "CloudEdge Solutions",       "category": "Software",        "contact_email": "billing@cloudedge.io",       "payment_terms": "Net 30"},
    {"name": "DataStream Analytics",      "category": "Software",        "contact_email": "accounts@datastream.ai",     "payment_terms": "Net 15"},
    {"name": "BrightPulse Marketing",     "category": "Marketing",       "contact_email": "invoices@brightpulse.co",    "payment_terms": "Net 30"},
    {"name": "OfficeNest Supplies",       "category": "Office Supplies", "contact_email": "ar@officenest.com",          "payment_terms": "Net 15"},
    {"name": "TechGuard Security",        "category": "IT & Security",   "contact_email": "billing@techguard.net",      "payment_terms": "Net 30"},
    {"name": "GreenLeaf Facilities",      "category": "Facilities",      "contact_email": "pay@greenleaf.fm",           "payment_terms": "Net 30"},
    {"name": "NovaPay Payroll",           "category": "HR & Payroll",    "contact_email": "support@novapay.com",        "payment_terms": "Net 7"},
    {"name": "SwiftLogix Freight",        "category": "Logistics",       "contact_email": "billing@swiftlogix.com",     "payment_terms": "Net 15"},
    {"name": "MediaWave Agency",          "category": "Marketing",       "contact_email": "accounts@mediawave.agency",  "payment_terms": "Net 30"},
    {"name": "ProHealth Insurance",       "category": "Benefits",        "contact_email": "claims@prohealth.co",        "payment_terms": "Net 30"},
    {"name": "DigitalReach Ads",          "category": "Marketing",       "contact_email": "billing@digitalreach.io",    "payment_terms": "Net 15"},
    {"name": "Apex Legal Counsel",        "category": "Legal",           "contact_email": "invoices@apexlegal.com",     "payment_terms": "Net 30"},
]

# --------------------------------------------------------------
# Expense category -> typical monthly amount
# --------------------------------------------------------------
EXPENSE_PATTERNS = {
    "Software":        (8_000,  1_200),   # (mean, std)
    "Marketing":       (12_000, 2_000),
    "Office Supplies": (1_500,  300),
    "IT & Security":   (4_500,  700),
    "Facilities":      (6_000,  500),
    "HR & Payroll":    (45_000, 3_000),
    "Logistics":       (3_200,  600),
    "Benefits":        (8_500,  400),
    "Legal":           (2_500,  800),
}

# Monthly revenue mean/std (growing trend)
REVENUE_BASE    = 110_000
REVENUE_GROWTH  = 1_500      # per month
REVENUE_STD     = 8_000


# --------------------------------------------------------------
# Main seeding function
# --------------------------------------------------------------
def seed(db):
    print(f"\n{'='*60}")
    print(f"  FinSight Seed -- {DATASET_LABEL}")
    print(f"  Period: {START_DATE} -> {END_DATE}")
    print(f"{'='*60}\n")

    # -- 1. Vendors ---------------------------------------------
    vendor_map = {}   # name -> Vendor ORM object
    for vdef in VENDOR_DEFS:
        v = Vendor(**vdef)
        db.add(v)
    db.flush()

    for v in db.query(Vendor).all():
        vendor_map[v.name] = v

    print(f"  [OK] Vendors seeded: {len(vendor_map)}")

    # -- 2. Transactions & Invoices -----------------------------
    transactions = []
    invoices     = []
    inv_seq      = 1     # global invoice sequence
    months       = list(month_range())
    month_idx    = 0

    for year, month in months:
        # --- Revenue ---
        rev_mean = REVENUE_BASE + REVENUE_GROWTH * month_idx
        rev_amt  = max(50_000, random.gauss(rev_mean, REVENUE_STD))

        # Split revenue into 3-5 line items (product sales, subscriptions, etc.)
        n_rev = random.randint(3, 5)
        splits = [random.random() for _ in range(n_rev)]
        total_s = sum(splits)
        for i, s in enumerate(splits):
            cat = random.choice(["Product Sales", "Subscription", "Consulting", "License"])
            transactions.append(Transaction(
                date=rand_date(year, month),
                amount=round(rev_amt * s / total_s, 2),
                type=TransactionType.revenue,
                category=cat,
                description=f"{cat} revenue -- {year}-{month:02d}",
                reference_number=f"REV-{year}{month:02d}-{i+1:03d}",
            ))

        # --- Expenses per category ---
        for cat, (mean, std) in EXPENSE_PATTERNS.items():
            # Find vendor in this category
            cat_vendors = [v for v in vendor_map.values() if v.category == cat]
            vendor = random.choice(cat_vendors) if cat_vendors else None

            amount = max(500, random.gauss(mean, std))

            # -- A3: Marketing spike in Jun 2026 ---------------
            if cat == "Marketing" and year == 2026 and month == 6:
                amount = mean * 4.1   # ~4× normal

            # -- A5: HR payroll spike in Feb 2026 --------------
            if cat == "HR & Payroll" and year == 2026 and month == 2:
                amount = mean * 3.2   # 3× average -- unusual transaction

            amount = round(amount, 2)

            transactions.append(Transaction(
                date=rand_date(year, month),
                amount=amount,
                type=TransactionType.expense,
                category=cat,
                description=f"{cat} -- {year}-{month:02d}",
                vendor_id=vendor.id if vendor else None,
                reference_number=f"EXP-{year}{month:02d}-{cat[:3].upper()}",
            ))

            # Generate invoice for this expense
            inv_number = f"INV-{cat[:3].upper()}-{inv_seq:04d}"

            # -- A2: Duplicate invoice -- marketing, Mar 2026 ---
            if cat == "Marketing" and year == 2026 and month == 3:
                dup_number = "INV-MKT-0312"
                # First occurrence (the original)
                inv_seq_for_dup = inv_seq
                inv_number = dup_number

            issue_dt = rand_date(year, month)
            due_dt   = issue_dt + timedelta(days=30)
            paid = random.random() > 0.15   # 85% paid
            paid_dt  = issue_dt + timedelta(days=random.randint(5, 28)) if paid else None
            status   = InvoiceStatus.paid if paid else (
                InvoiceStatus.overdue if due_dt < datetime.utcnow() else InvoiceStatus.pending
            )

            invoices.append(Invoice(
                vendor_id=vendor.id if vendor else vendor_map["CloudEdge Solutions"].id,
                invoice_number=inv_number,
                amount=amount,
                status=status,
                issue_date=issue_dt,
                due_date=due_dt,
                paid_date=paid_dt,
                description=f"{DATASET_LABEL} | {cat} -- {year}-{month:02d}",
            ))

            # -- A2 cont.: plant the duplicate invoice ---------
            if cat == "Marketing" and year == 2026 and month == 3:
                invoices.append(Invoice(
                    vendor_id=vendor.id if vendor else vendor_map["CloudEdge Solutions"].id,
                    invoice_number="INV-MKT-0312",    # exact duplicate number
                    amount=amount,                     # same amount
                    status=InvoiceStatus.pending,
                    issue_date=issue_dt + timedelta(days=2),  # slightly later
                    due_date=due_dt + timedelta(days=2),
                    paid_date=None,
                    description=f"{DATASET_LABEL} | DUPLICATE -- {cat} -- {year}-{month:02d}",
                ))

            inv_seq += 1

        # -- A4: DataStream invoice frequency spike -- Jul 2026 -
        if year == 2026 and month == 7:
            ds_vendor = vendor_map["DataStream Analytics"]
            for extra_i in range(4):   # 4 extra -> total 5 invoices this month
                extra_amt = round(random.gauss(2_200, 200), 2)
                extra_dt  = rand_date(year, month)
                invoices.append(Invoice(
                    vendor_id=ds_vendor.id,
                    invoice_number=f"INV-DS-FREQ-{extra_i+1:02d}",
                    amount=extra_amt,
                    status=InvoiceStatus.pending,
                    issue_date=extra_dt,
                    due_date=extra_dt + timedelta(days=15),
                    paid_date=None,
                    description=f"{DATASET_LABEL} | DataStream extra billing -- {year}-{month:02d}",
                ))
            print(f"    -> [A4] DataStream frequency spike planted (Jul 2026)")

        month_idx += 1

    # -- A1: Unusually large CloudEdge payment -- Mar 2026 ------
    ce_vendor = vendor_map["CloudEdge Solutions"]
    # Normal CloudEdge invoice ~$8k; plant $47k
    anomaly_inv = Invoice(
        vendor_id=ce_vendor.id,
        invoice_number="INV-CE-ANOMALY-2603",
        amount=47_500.00,
        status=InvoiceStatus.paid,
        issue_date=datetime(2026, 3, 10, 9, 0),
        due_date=datetime(2026, 4, 9, 9, 0),
        paid_date=datetime(2026, 3, 25, 14, 30),
        description=f"{DATASET_LABEL} | CloudEdge enterprise upgrade -- UNUSUALLY LARGE",
    )
    invoices.append(anomaly_inv)

    # Corresponding transaction
    transactions.append(Transaction(
        date=datetime(2026, 3, 25, 14, 30),
        amount=47_500.00,
        type=TransactionType.expense,
        category="Software",
        description="CloudEdge enterprise license upgrade -- unusually large payment",
        vendor_id=ce_vendor.id,
        reference_number="EXP-202603-CE-ANOMALY",
    ))
    print("    -> [A1] Large CloudEdge payment anomaly planted (Mar 2026, $47,500)")

    # -- Flush all transactions & invoices ---------------------
    for t in transactions:
        db.add(t)
    for inv in invoices:
        db.add(inv)
    db.flush()

    # -- 3. Budgets ---------------------------------------------
    expense_cats = list(EXPENSE_PATTERNS.keys())
    revenue_cats = ["Product Sales", "Subscription", "Consulting", "License"]

    budget_rows = []
    mi = 0
    for year, month in month_range():
        # Revenue budgets
        rev_budget = REVENUE_BASE + REVENUE_GROWTH * mi
        budget_rows.append(Budget(
            year=year, month=month,
            category="Revenue",
            planned_amount=round(rev_budget, 2),
            actual_amount=round(random.gauss(rev_budget, REVENUE_STD * 0.5), 2),
        ))

        # Expense category budgets
        for cat, (mean, std) in EXPENSE_PATTERNS.items():
            planned = round(mean * random.uniform(0.95, 1.05), 2)
            # Compute actual from transactions (approximate here, updated later)
            actual_amt = round(random.gauss(mean, std * 0.4), 2)
            # A3 budget vs actual spike
            if cat == "Marketing" and year == 2026 and month == 6:
                actual_amt = round(mean * 4.1, 2)

            budget_rows.append(Budget(
                year=year, month=month,
                category=cat,
                planned_amount=planned,
                actual_amount=actual_amt,
            ))
        mi += 1

    for b in budget_rows:
        db.add(b)

    db.commit()

    # -- Summary -----------------------------------------------
    total_t = db.query(Transaction).count()
    total_i = db.query(Invoice).count()
    total_v = db.query(Vendor).count()
    total_b = db.query(Budget).count()

    print(f"\n  Dataset label : {DATASET_LABEL}")
    print(f"  Transactions  : {total_t}")
    print(f"  Invoices      : {total_i}")
    print(f"  Vendors       : {total_v}")
    print(f"  Budget rows   : {total_b}")
    print(f"\n  Anomalies planted (no flag field):")
    print(f"    A1 -- Large CloudEdge payment ($47,500 vs ~$8,000 avg)")
    print(f"    A2 -- Duplicate invoice INV-MKT-0312 (Mar 2026)")
    print(f"    A3 -- Marketing spike (Jun 2026: ~4× budget)")
    print(f"    A4 -- DataStream invoice frequency (5 in Jul 2026 vs 1 normally)")
    print(f"    A5 -- HR payroll spike (Feb 2026: 3× monthly avg)")
    print(f"\n{'='*60}\n")


# --------------------------------------------------------------
# Entrypoint
# --------------------------------------------------------------
if __name__ == "__main__":
    print("Initialising database…")
    init_db()

    db = SessionLocal()
    try:
        # Clear existing data (idempotent re-seed)
        db.query(Budget).delete()
        db.query(Invoice).delete()
        db.query(Transaction).delete()
        db.query(Vendor).delete()
        db.commit()

        seed(db)
        print("Seeding complete.")
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()
