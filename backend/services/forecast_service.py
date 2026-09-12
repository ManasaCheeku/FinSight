"""
FinSight — Cash-Flow Forecasting Service.

Method: transparent deterministic baseline.
  - Uses trailing 3-month average for revenue & expenses
  - Identifies recurring invoice amounts and schedules
  - Computes 30 / 60 / 90-day forward projections

All outputs are clearly labelled:  FORECAST — NOT ACTUAL
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.transaction import Transaction, TransactionType
from models.invoice import Invoice, InvoiceStatus
from services.financial_service import current_cash_balance

FORECAST_LABEL = "FORECAST — NOT ACTUAL"


# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def _trailing_monthly_avg(db: Session, tx_type: TransactionType, n_months: int = 3):
    """
    Return (mean, stdev) of monthly totals for the last n_months
    with data present in the DB.
    """
    from sqlalchemy import extract
    rows = (
        db.query(
            extract("year",  Transaction.date).label("yr"),
            extract("month", Transaction.date).label("mo"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(Transaction.type == tx_type)
        .group_by("yr", "mo")
        .order_by("yr", "mo")
        .all()
    )
    if not rows:
        return 0.0, 0.0

    # Take last n_months
    recent = rows[-n_months:]
    amounts = [r.total for r in recent]
    mean = statistics.mean(amounts)
    stdev = statistics.pstdev(amounts) if len(amounts) > 1 else mean * 0.05
    return mean, stdev


def _recurring_expense_per_day(db: Session) -> float:
    """
    Estimate daily recurring expense from paid invoices with similar amounts.
    Detects repeating invoice amounts (within 5%) as "recurring."
    """
    invoices = db.query(Invoice).filter(Invoice.status == InvoiceStatus.paid).all()
    amount_counts: Dict[int, int] = defaultdict(int)
    for inv in invoices:
        bucket = int(inv.amount / 100) * 100   # bucket to nearest $100
        amount_counts[bucket] += 1

    recurring_monthly = sum(
        bucket * count
        for bucket, count in amount_counts.items()
        if count >= 3   # appeared at least 3 times → recurring
    )
    return recurring_monthly / 30.0


# ──────────────────────────────────────────────────────────────
# Core forecast
# ──────────────────────────────────────────────────────────────

def _forecast_for_days(
    daily_rev: float,
    daily_exp: float,
    rev_stdev_daily: float,
    exp_stdev_daily: float,
    opening_balance: float,
    days: int,
) -> Dict:
    projected_revenue  = round(daily_rev * days, 2)
    projected_expenses = round(daily_exp * days, 2)
    projected_net      = round(projected_revenue - projected_expenses, 2)
    projected_balance  = round(opening_balance + projected_net, 2)

    # Minimum projected cash (pessimistic: subtract 1-sigma)
    pessimistic_rev = (daily_rev - rev_stdev_daily) * days
    pessimistic_exp = (daily_exp + exp_stdev_daily) * days
    min_cash = round(opening_balance + pessimistic_rev - pessimistic_exp, 2)

    # Uncertainty = coefficient of variation of monthly totals, scaled
    combined_stdev = ((rev_stdev_daily ** 2 + exp_stdev_daily ** 2) ** 0.5) * days
    base_magnitude  = abs(projected_net) or 1.0
    uncertainty_pct = round(min(combined_stdev / base_magnitude * 100, 100), 1)

    return {
        "horizon_days": days,
        "projected_revenue": projected_revenue,
        "projected_expenses": projected_expenses,
        "projected_net_cash_flow": projected_net,
        "projected_cash_balance": projected_balance,
        "minimum_projected_cash": min_cash,
        "uncertainty_pct": uncertainty_pct,
        "label": FORECAST_LABEL,
    }


def forecast_cashflow(db: Session) -> Dict:
    """
    Generate 30-, 60-, and 90-day cash-flow forecasts.
    Based on trailing 3-month averages with uncertainty bounds.
    """
    rev_mean_mo, rev_stdev_mo = _trailing_monthly_avg(db, TransactionType.revenue, 3)
    exp_mean_mo, exp_stdev_mo = _trailing_monthly_avg(db, TransactionType.expense, 3)

    daily_rev       = rev_mean_mo  / 30.0
    daily_exp       = exp_mean_mo  / 30.0
    rev_stdev_daily = rev_stdev_mo / 30.0
    exp_stdev_daily = exp_stdev_mo / 30.0

    opening_balance = current_cash_balance(db)

    forecasts = []
    for days in (30, 60, 90):
        forecasts.append(
            _forecast_for_days(daily_rev, daily_exp, rev_stdev_daily, exp_stdev_daily,
                               opening_balance, days)
        )

    # Trend insight
    trend = "positive" if daily_rev > daily_exp else "negative"

    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "label": FORECAST_LABEL,
        "disclaimer": (
            "Forecasts are generated from historical averages and recurring patterns. "
            "They are NOT guaranteed outcomes. Actual results will differ."
        ),
        "method": "trailing 3-month average with 1-sigma uncertainty bounds",
        "opening_cash_balance": opening_balance,
        "monthly_revenue_baseline": round(rev_mean_mo, 2),
        "monthly_expense_baseline": round(exp_mean_mo, 2),
        "cash_flow_trend": trend,
        "forecasts": forecasts,
    }
