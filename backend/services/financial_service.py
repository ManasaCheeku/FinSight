"""
FinSight — Financial Calculation Service.

All numbers are derived from SQLite; nothing is hard-coded.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from models.transaction import Transaction, TransactionType
from models.invoice import Invoice, InvoiceStatus
from models.budget import Budget


# ──────────────────────────────────────────────────────────────
# Core aggregates
# ──────────────────────────────────────────────────────────────

def total_revenue(db: Session) -> float:
    """Sum of all revenue transactions."""
    result = db.query(func.sum(Transaction.amount)).filter(
        Transaction.type == TransactionType.revenue
    ).scalar()
    return round(result or 0.0, 2)


def total_expenses(db: Session) -> float:
    """Sum of all expense transactions."""
    result = db.query(func.sum(Transaction.amount)).filter(
        Transaction.type == TransactionType.expense
    ).scalar()
    return round(result or 0.0, 2)


def net_cash_flow(db: Session) -> float:
    """Net cash flow = total revenue − total expenses."""
    return round(total_revenue(db) - total_expenses(db), 2)


def current_cash_balance(db: Session) -> float:
    """
    Running cash balance = cumulative revenue − cumulative expenses,
    ordered chronologically up to the latest transaction date.
    (Assumes initial balance is 0; this is relative.)
    """
    rev = db.query(func.sum(Transaction.amount)).filter(
        Transaction.type == TransactionType.revenue
    ).scalar() or 0.0

    exp = db.query(func.sum(Transaction.amount)).filter(
        Transaction.type == TransactionType.expense
    ).scalar() or 0.0

    return round(rev - exp, 2)


# ──────────────────────────────────────────────────────────────
# Monthly breakdowns
# ──────────────────────────────────────────────────────────────

def monthly_revenue(db: Session) -> List[Dict]:
    """Return list of {year, month, revenue} sorted chronologically."""
    rows = (
        db.query(
            extract("year",  Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("revenue"),
        )
        .filter(Transaction.type == TransactionType.revenue)
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )
    return [
        {"year": int(r.year), "month": int(r.month), "revenue": round(r.revenue, 2)}
        for r in rows
    ]


def monthly_expenses(db: Session) -> List[Dict]:
    """Return list of {year, month, expenses} sorted chronologically."""
    rows = (
        db.query(
            extract("year",  Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("expenses"),
        )
        .filter(Transaction.type == TransactionType.expense)
        .group_by("year", "month")
        .order_by("year", "month")
        .all()
    )
    return [
        {"year": int(r.year), "month": int(r.month), "expenses": round(r.expenses, 2)}
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────
# Category breakdown
# ──────────────────────────────────────────────────────────────

def expense_category_breakdown(db: Session) -> List[Dict]:
    """Expenses grouped by category with amount, count, and % share."""
    rows = (
        db.query(
            Transaction.category,
            func.sum(Transaction.amount).label("total"),
            func.count(Transaction.id).label("count"),
        )
        .filter(Transaction.type == TransactionType.expense)
        .group_by(Transaction.category)
        .order_by(func.sum(Transaction.amount).desc())
        .all()
    )

    grand_total = sum(r.total for r in rows) or 1.0
    return [
        {
            "category": r.category,
            "total": round(r.total, 2),
            "transaction_count": r.count,
            "percentage": round(r.total / grand_total * 100, 2),
        }
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────
# Growth rates
# ──────────────────────────────────────────────────────────────

def _growth_rate(current: float, previous: float) -> Optional[float]:
    if previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def revenue_growth(db: Session) -> Dict:
    """Month-over-month revenue growth for most recent two months."""
    months = monthly_revenue(db)
    if len(months) < 2:
        return {"growth_pct": None, "message": "Insufficient data"}
    latest, prev = months[-1], months[-2]
    pct = _growth_rate(latest["revenue"], prev["revenue"])
    return {
        "current_month": f"{latest['year']}-{latest['month']:02d}",
        "previous_month": f"{prev['year']}-{prev['month']:02d}",
        "current_revenue": latest["revenue"],
        "previous_revenue": prev["revenue"],
        "growth_pct": pct,
    }


def expense_growth(db: Session) -> Dict:
    """Month-over-month expense growth for most recent two months."""
    months = monthly_expenses(db)
    if len(months) < 2:
        return {"growth_pct": None, "message": "Insufficient data"}
    latest, prev = months[-1], months[-2]
    pct = _growth_rate(latest["expenses"], prev["expenses"])
    return {
        "current_month": f"{latest['year']}-{latest['month']:02d}",
        "previous_month": f"{prev['year']}-{prev['month']:02d}",
        "current_expenses": latest["expenses"],
        "previous_expenses": prev["expenses"],
        "growth_pct": pct,
    }


# ──────────────────────────────────────────────────────────────
# Profit margin
# ──────────────────────────────────────────────────────────────

def profit_margin(db: Session) -> Dict:
    """Overall profit margin = net_cash_flow / total_revenue × 100."""
    rev = total_revenue(db)
    net = net_cash_flow(db)
    margin = round(net / rev * 100, 2) if rev else None
    return {
        "total_revenue": rev,
        "total_expenses": total_expenses(db),
        "net_cash_flow": net,
        "profit_margin_pct": margin,
    }


# ──────────────────────────────────────────────────────────────
# Budget variance
# ──────────────────────────────────────────────────────────────

def budget_variance(db: Session) -> List[Dict]:
    """
    For each budget row, compute variance = actual − planned and the %.
    Returns list sorted by absolute variance descending.
    """
    rows = db.query(Budget).all()
    result = []
    for b in rows:
        var = round(b.actual_amount - b.planned_amount, 2)
        var_pct = round(var / b.planned_amount * 100, 2) if b.planned_amount else None
        result.append({
            "id": b.id,
            "year": b.year,
            "month": b.month,
            "category": b.category,
            "planned": b.planned_amount,
            "actual": b.actual_amount,
            "variance": var,
            "variance_pct": var_pct,
            "status": "over_budget" if var > 0 else ("under_budget" if var < 0 else "on_budget"),
        })
    result.sort(key=lambda x: abs(x["variance"]), reverse=True)
    return result


# ──────────────────────────────────────────────────────────────
# Outstanding invoices
# ──────────────────────────────────────────────────────────────

def outstanding_invoices(db: Session) -> Dict:
    """Invoices that are pending or overdue, with totals."""
    rows = (
        db.query(Invoice)
        .filter(Invoice.status.in_([InvoiceStatus.pending, InvoiceStatus.overdue]))
        .order_by(Invoice.due_date)
        .all()
    )
    total_amt = sum(inv.amount for inv in rows)
    return {
        "count": len(rows),
        "total_outstanding": round(total_amt, 2),
        "invoices": [
            {
                "id": inv.id,
                "invoice_number": inv.invoice_number,
                "vendor_id": inv.vendor_id,
                "amount": inv.amount,
                "status": inv.status,
                "due_date": inv.due_date.isoformat() if inv.due_date else None,
            }
            for inv in rows
        ],
    }


# ──────────────────────────────────────────────────────────────
# Full summary
# ──────────────────────────────────────────────────────────────

def financial_summary(db: Session) -> Dict:
    """Aggregate all key metrics into one dict."""
    rev   = total_revenue(db)
    exp   = total_expenses(db)
    net   = net_cash_flow(db)
    bal   = current_cash_balance(db)
    margin = round(net / rev * 100, 2) if rev else None
    outstanding = outstanding_invoices(db)

    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "total_revenue": rev,
        "total_expenses": exp,
        "net_cash_flow": net,
        "current_cash_balance": bal,
        "profit_margin_pct": margin,
        "outstanding_invoices_count": outstanding["count"],
        "outstanding_invoices_total": outstanding["total_outstanding"],
        "revenue_growth": revenue_growth(db),
        "expense_growth": expense_growth(db),
    }
