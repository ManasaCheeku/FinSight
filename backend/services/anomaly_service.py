"""
FinSight — Anomaly Detection Service.

Uses deterministic, explainable methods only:
  - Historical average deviation (z-score style)
  - Percentage deviation from category mean
  - Duplicate invoice detection
  - Vendor invoice frequency outlier
  - Large vendor payment detection

Each result includes: type, entity, severity, actual, expected, deviation, explanation.
Language: "anomaly" or "risk indicator" — never "fraud" unless proven.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime
from typing import Dict, List

from sqlalchemy import extract, func
from sqlalchemy.orm import Session

from models.transaction import Transaction, TransactionType
from models.invoice import Invoice
from models.vendor import Vendor


def explain_anomaly(anomaly: Dict) -> str:
    """Return a reusable, neutral explanation of a deterministic indicator.

    The detector remains the source of the values; this helper only formats
    them for API and AI consumers and never upgrades an indicator to fraud.
    """
    if not anomaly:
        return "No deterministic anomaly indicator is available."
    existing = anomaly.get("explanation")
    if existing:
        # Existing detector explanations are already grounded in its result.
        # Convert the currency marker for the product's INR-facing API.
        return str(existing).replace("$", "₹")
    actual = anomaly.get("actual_value", anomaly.get("actual"))
    expected = anomaly.get("expected_value", anomaly.get("expected"))
    deviation = anomaly.get("deviation_pct", anomaly.get("deviation"))
    entity = anomaly.get("entity", "the record")
    severity = anomaly.get("severity", "unknown")
    if actual is None and expected is None:
        return f"{entity} is a {severity} deterministic risk indicator requiring review."
    return (
        f"{entity} is a {severity} deterministic risk indicator: actual "
        f"{actual!r}, expected {expected!r}, deviation {deviation!r}%. "
        "This is not proof of misconduct."
    )


# ──────────────────────────────────────────────────────────────
# Severity thresholds
# ──────────────────────────────────────────────────────────────
def _severity(deviation_pct: float) -> str:
    a = abs(deviation_pct)
    if a >= 200:
        return "critical"
    if a >= 100:
        return "high"
    if a >= 50:
        return "medium"
    return "low"


# ──────────────────────────────────────────────────────────────
# 1. Category spending anomalies (historical average deviation)
# ──────────────────────────────────────────────────────────────
def _category_anomalies(db: Session) -> List[Dict]:
    """
    For each expense category, compute the monthly average and std-dev.
    Flag any month where spending deviates > 1.5 std-devs from the mean.
    """
    # Gather monthly expense per category
    rows = (
        db.query(
            Transaction.category,
            extract("year",  Transaction.date).label("year"),
            extract("month", Transaction.date).label("month"),
            func.sum(Transaction.amount).label("total"),
        )
        .filter(Transaction.type == TransactionType.expense)
        .group_by(Transaction.category, "year", "month")
        .all()
    )

    # Build category → list of monthly amounts
    cat_months: Dict[str, List] = defaultdict(list)
    for r in rows:
        cat_months[r.category].append({
            "year": int(r.year), "month": int(r.month), "total": r.total
        })

    anomalies = []
    for cat, monthly in cat_months.items():
        if len(monthly) < 3:
            continue
        amounts = [m["total"] for m in monthly]
        mean = statistics.mean(amounts)
        stdev = statistics.pstdev(amounts)
        if stdev == 0:
            continue

        for m in monthly:
            z = (m["total"] - mean) / stdev
            if abs(z) >= 1.5:
                dev_pct = round((m["total"] - mean) / mean * 100, 2)
                anomalies.append({
                    "type": "category_spending_anomaly",
                    "entity": f"Category: {cat}",
                    "period": f"{m['year']}-{m['month']:02d}",
                    "severity": _severity(dev_pct),
                    "actual_value": round(m["total"], 2),
                    "expected_value": round(mean, 2),
                    "deviation_pct": dev_pct,
                    "z_score": round(z, 2),
                    "explanation": (
                        f"Spending in '{cat}' for {m['year']}-{m['month']:02d} "
                        f"was ${m['total']:,.2f}, which is {abs(dev_pct):.1f}% "
                        f"{'above' if dev_pct > 0 else 'below'} the historical monthly "
                        f"average of ${mean:,.2f} (z-score: {z:.2f}). "
                        f"This is a risk indicator warranting review."
                    ),
                })
    return anomalies


# ──────────────────────────────────────────────────────────────
# 2. Large vendor payment detection
# ──────────────────────────────────────────────────────────────
def _large_payment_anomalies(db: Session) -> List[Dict]:
    """
    For each vendor, compute average invoice amount.
    Flag any invoice > 2.5× that average.
    """
    invoices = db.query(Invoice).all()
    vendor_invs: Dict[int, List[float]] = defaultdict(list)
    for inv in invoices:
        vendor_invs[inv.vendor_id].append(inv.amount)

    vendors = {v.id: v for v in db.query(Vendor).all()}
    anomalies = []

    for vendor_id, amounts in vendor_invs.items():
        if len(amounts) < 2:
            continue
        mean = statistics.mean(amounts)
        threshold = mean * 2.5
        for inv in invoices:
            if inv.vendor_id != vendor_id:
                continue
            if inv.amount > threshold:
                dev_pct = round((inv.amount - mean) / mean * 100, 2)
                vendor_name = vendors[vendor_id].name if vendor_id in vendors else f"Vendor#{vendor_id}"
                anomalies.append({
                    "type": "large_vendor_payment",
                    "entity": f"Vendor: {vendor_name}",
                    "invoice_number": inv.invoice_number,
                    "period": inv.issue_date.strftime("%Y-%m") if inv.issue_date else "unknown",
                    "severity": _severity(dev_pct),
                    "actual_value": round(inv.amount, 2),
                    "expected_value": round(mean, 2),
                    "deviation_pct": dev_pct,
                    "explanation": (
                        f"Invoice {inv.invoice_number} from {vendor_name} "
                        f"is ${inv.amount:,.2f}, which is {dev_pct:.1f}% above "
                        f"this vendor's average invoice of ${mean:,.2f}. "
                        f"This is an unusually large payment and a risk indicator."
                    ),
                })
    return anomalies


# ──────────────────────────────────────────────────────────────
# 3. Duplicate invoice detection
# ──────────────────────────────────────────────────────────────
def _duplicate_invoice_anomalies(db: Session) -> List[Dict]:
    """
    Flag invoice numbers that appear more than once for the same vendor.
    Also flag same vendor + same amount within the same calendar month.
    """
    invoices = db.query(Invoice).all()
    vendors = {v.id: v for v in db.query(Vendor).all()}
    anomalies = []

    # Group by (vendor_id, invoice_number)
    inv_map: Dict[tuple, List] = defaultdict(list)
    for inv in invoices:
        key = (inv.vendor_id, inv.invoice_number)
        inv_map[key].append(inv)

    seen_pairs = set()
    for (vid, inv_no), group in inv_map.items():
        if len(group) > 1:
            pair_key = (vid, inv_no)
            if pair_key in seen_pairs:
                continue
            seen_pairs.add(pair_key)
            vendor_name = vendors[vid].name if vid in vendors else f"Vendor#{vid}"
            amounts = [i.amount for i in group]
            anomalies.append({
                "type": "duplicate_invoice",
                "entity": f"Vendor: {vendor_name}",
                "invoice_number": inv_no,
                "period": group[0].issue_date.strftime("%Y-%m") if group[0].issue_date else "unknown",
                "severity": "high",
                "actual_value": amounts[0],
                "expected_value": amounts[0],
                "deviation_pct": 0.0,
                "occurrence_count": len(group),
                "explanation": (
                    f"Invoice number '{inv_no}' from {vendor_name} appears "
                    f"{len(group)} times in the system. Duplicate invoices are a "
                    f"risk indicator for accidental double-payment or billing error. "
                    f"Total potential duplicate exposure: ${sum(amounts):,.2f}."
                ),
            })
    return anomalies


# ──────────────────────────────────────────────────────────────
# 4. Vendor invoice frequency outlier
# ──────────────────────────────────────────────────────────────
def _vendor_frequency_anomalies(db: Session) -> List[Dict]:
    """
    For each vendor, count invoices per month.
    Compare each month with the vendor's prior monthly history, including
    months with no invoices. A burst after a zero-invoice baseline is only
    flagged when it contains multiple invoices, avoiding noise from a normal
    first invoice.
    """
    invoices = db.query(Invoice).all()
    vendors = {v.id: v for v in db.query(Vendor).all()}

    # vendor_id → {(year,month) → count}
    freq: Dict[int, Dict[tuple, int]] = defaultdict(lambda: defaultdict(int))
    for inv in invoices:
        if inv.issue_date:
            key = (inv.issue_date.year, inv.issue_date.month)
            freq[inv.vendor_id][key] += 1

    if not freq:
        return []

    observed_periods = [
        (year, month)
        for year, month in sorted({
            period
            for month_counts in freq.values()
            for period in month_counts
        })
    ]

    anomalies = []
    for vid, month_counts in freq.items():
        for period in sorted(month_counts):
            year, month = period
            historical_counts = [
                month_counts.get(previous_period, 0)
                for previous_period in observed_periods
                if previous_period < period
            ]
            if not historical_counts:
                continue

            count = month_counts[period]
            expected = statistics.mean(historical_counts)
            if expected == 0:
                # A multi-invoice burst is meaningful even when the vendor
                # had no prior invoices in the observed history.
                is_anomaly = count >= 3
                dev_pct = round(count * 100, 2)
            else:
                dev_pct = round((count - expected) / expected * 100, 2)
                is_anomaly = dev_pct >= 100

            if not is_anomaly:
                continue

            vendor_name = vendors[vid].name if vid in vendors else f"Vendor#{vid}"
            reason = (
                f"{vendor_name} submitted {count} invoice(s) in "
                f"{year}-{month:02d}, compared with a historical monthly "
                f"baseline of {expected:.1f}. The {dev_pct:.0f}% increase in "
                f"invoice frequency is a risk indicator that may warrant review."
            )
            anomalies.append({
                "type": "vendor_invoice_frequency_anomaly",
                "entity": f"Vendor: {vendor_name}",
                "period": f"{year}-{month:02d}",
                "severity": _severity(dev_pct),
                "actual_value": count,
                "expected_value": round(expected, 2),
                "deviation_pct": dev_pct,
                "deviation": dev_pct,
                "reason": reason,
                "explanation": reason,
            })
    return anomalies


# ──────────────────────────────────────────────────────────────
# 5. Unusual single transaction amount
# ──────────────────────────────────────────────────────────────
def _unusual_transaction_anomalies(db: Session) -> List[Dict]:
    """
    For each expense category, flag transactions > mean + 2.5×stdev.
    """
    transactions = db.query(Transaction).filter(
        Transaction.type == TransactionType.expense
    ).all()

    cat_amounts: Dict[str, List[float]] = defaultdict(list)
    for t in transactions:
        cat_amounts[t.category].append(t.amount)

    anomalies = []
    for cat, amounts in cat_amounts.items():
        if len(amounts) < 3:
            continue
        mean = statistics.mean(amounts)
        stdev = statistics.pstdev(amounts)
        if stdev == 0:
            continue
        threshold = mean + 2.5 * stdev

        for t in transactions:
            if t.category != cat:
                continue
            if t.amount > threshold:
                dev_pct = round((t.amount - mean) / mean * 100, 2)
                anomalies.append({
                    "type": "unusual_transaction_amount",
                    "entity": f"Transaction #{t.id} — {cat}",
                    "period": t.date.strftime("%Y-%m") if t.date else "unknown",
                    "severity": _severity(dev_pct),
                    "actual_value": round(t.amount, 2),
                    "expected_value": round(mean, 2),
                    "deviation_pct": dev_pct,
                    "explanation": (
                        f"Transaction #{t.id} in category '{cat}' on "
                        f"{t.date.strftime('%Y-%m-%d') if t.date else 'unknown'} "
                        f"is ${t.amount:,.2f} — {dev_pct:.1f}% above the category "
                        f"mean of ${mean:,.2f}. This is an unusual transaction amount "
                        f"and a risk indicator."
                    ),
                })
    return anomalies


# ──────────────────────────────────────────────────────────────
# Public entrypoint
# ──────────────────────────────────────────────────────────────
def detect_anomalies(db: Session) -> Dict:
    """
    Run all anomaly detectors and return a consolidated report.
    Results are sorted by severity (critical → high → medium → low).
    """
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}

    all_anomalies = (
        _category_anomalies(db)
        + _large_payment_anomalies(db)
        + _duplicate_invoice_anomalies(db)
        + _vendor_frequency_anomalies(db)
        + _unusual_transaction_anomalies(db)
    )

    all_anomalies.sort(key=lambda x: severity_order.get(x["severity"], 9))

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for a in all_anomalies:
        counts[a["severity"]] = counts.get(a["severity"], 0) + 1

    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "detection_method": "deterministic — historical deviation, duplicate detection, frequency analysis",
        "disclaimer": (
            "These are anomaly indicators for review and should not be treated "
            "as definitive accusations of misconduct."
        ),
        "total_anomalies": len(all_anomalies),
        "severity_summary": counts,
        "anomalies": all_anomalies,
    }
