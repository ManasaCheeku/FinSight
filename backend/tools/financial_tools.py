"""
FinSight — LLM Tool Layer.

These are the structured callable functions exposed to the future LLM.
Architecture:

    USER
     ↓
    LLM
     ↓
    TOOL  (this file)
     ↓
    FINANCIAL SERVICE
     ↓
    DATABASE
     ↓
    CALCULATED RESULT
     ↓
    LLM EXPLANATION

Rules:
  - Every function calls a financial service; never invents numbers.
  - All tools accept a SQLAlchemy Session so they can be tested independently.
  - Tool schemas are defined as Python dicts for easy LLM function-calling integration.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

import services.financial_service as fin
import services.anomaly_service  as ano
import services.forecast_service as frc
import services.decision_service as dcs
from models.transaction import Transaction, TransactionType
from models.vendor import Vendor
from sqlalchemy import func


# ──────────────────────────────────────────────────────────────
# Tool definitions (JSON-schema style, for LLM registration)
# ──────────────────────────────────────────────────────────────
TOOL_SCHEMAS = [
    {
        "name": "get_cashflow",
        "description": (
            "Returns total revenue, total expenses, net cash flow, "
            "current cash balance, and profit margin calculated from the database. "
            "Never returns invented numbers."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_expense_breakdown",
        "description": (
            "Returns expenses broken down by category with amounts, "
            "transaction counts, and percentage of total spend."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "get_vendor_analysis",
        "description": (
            "Returns per-vendor spending totals, invoice counts, "
            "average invoice amount, and outstanding balance."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "vendor_id": {
                    "type": "integer",
                    "description": "Optional. Filter to a specific vendor by ID.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "detect_anomalies",
        "description": (
            "Runs deterministic anomaly detection on transactions and invoices. "
            "Returns anomalies with type, entity, severity, actual value, "
            "expected value, deviation, and plain-English explanation. "
            "Does not label anything as fraud unless proven."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "forecast_cashflow",
        "description": (
            "Generates 30-, 60-, and 90-day cash-flow forecasts using "
            "historical averages and recurring patterns. "
            "All results are clearly labelled FORECAST — NOT ACTUAL."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "budget_analysis",
        "description": (
            "Returns budget vs actual comparison for all categories and months, "
            "with variance amounts and percentages."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "description": "Optional. Filter to a specific budget category.",
                }
            },
            "required": [],
        },
    },
    {
        "name": "evaluate_decision",
        "description": (
            "Evaluate one deterministic financial scenario. Supported decision "
            "types are hiring, purchase, budget_change, loan, and expense_reduction. "
            "Returns evidence, calculations, assumptions, risks, recommendation, "
            "and a transparent 0-100 risk score."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "decision_type": {
                    "type": "string",
                    "enum": ["hiring", "purchase", "budget_change", "loan", "expense_reduction"],
                },
                "parameters": {"type": "object"},
            },
            "required": ["decision_type"],
        },
    },
]

# Individual wrappers are advertised as separate callable tools as well as
# through evaluate_decision, which keeps future model binding explicit.
for _decision_tool in (
    "hiring",
    "purchase",
    "budget_change",
    "loan",
    "expense_reduction",
):
    TOOL_SCHEMAS.append(
        {
            "name": f"evaluate_{_decision_tool}",
            "description": f"Evaluate a {_decision_tool} scenario using SQLite-backed deterministic calculations.",
            "parameters": {
                "type": "object",
                "properties": {"parameters": {"type": "object"}},
                "required": [],
            },
        }
    )


# ──────────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────────

def get_cashflow(db: Session) -> Dict[str, Any]:
    """
    Tool: get_cashflow
    Returns core cash-flow metrics from the database.
    """
    return fin.financial_summary(db)


def get_expense_breakdown(db: Session) -> Dict[str, Any]:
    """
    Tool: get_expense_breakdown
    Returns expense category breakdown with totals, counts, and percentages.
    """
    breakdown = fin.expense_category_breakdown(db)
    total_exp = fin.total_expenses(db)
    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "total_expenses": total_exp,
        "categories": breakdown,
    }


def get_vendor_analysis(db: Session, vendor_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Tool: get_vendor_analysis
    Returns per-vendor spending totals from the database.
    Optionally filters to a single vendor.
    """
    from models.invoice import Invoice
    from models.vendor import Vendor

    vendors = db.query(Vendor).all()
    if vendor_id:
        vendors = [v for v in vendors if v.id == vendor_id]

    results = []
    for v in vendors:
        invoices = db.query(Invoice).filter(Invoice.vendor_id == v.id).all()
        total_invoiced = sum(i.amount for i in invoices)
        paid_total = sum(i.amount for i in invoices if i.status == "paid")
        outstanding = sum(i.amount for i in invoices if i.status in ("pending", "overdue"))
        avg_inv = total_invoiced / len(invoices) if invoices else 0.0

        results.append({
            "vendor_id": v.id,
            "vendor_name": v.name,
            "category": v.category,
            "invoice_count": len(invoices),
            "total_invoiced": round(total_invoiced, 2),
            "paid_total": round(paid_total, 2),
            "outstanding_balance": round(outstanding, 2),
            "average_invoice_amount": round(avg_inv, 2),
        })

    results.sort(key=lambda x: x["total_invoiced"], reverse=True)
    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "vendor_count": len(results),
        "vendors": results,
    }


def detect_anomalies(db: Session) -> Dict[str, Any]:
    """
    Tool: detect_anomalies
    Runs all anomaly detectors and returns a consolidated risk report.
    """
    return ano.detect_anomalies(db)


def forecast_cashflow(db: Session) -> Dict[str, Any]:
    """
    Tool: forecast_cashflow
    Generates 30/60/90-day baseline cash-flow forecasts.
    """
    return frc.forecast_cashflow(db)


def budget_analysis(db: Session, category: Optional[str] = None) -> Dict[str, Any]:
    """
    Tool: budget_analysis
    Returns budget variance analysis, optionally filtered by category.
    """
    variance_rows = fin.budget_variance(db)
    if category:
        variance_rows = [r for r in variance_rows if r["category"].lower() == category.lower()]

    over_budget  = [r for r in variance_rows if r["status"] == "over_budget"]
    under_budget = [r for r in variance_rows if r["status"] == "under_budget"]
    on_budget    = [r for r in variance_rows if r["status"] == "on_budget"]

    return {
        "dataset_label": "SYNTHETIC DEMO DATA",
        "total_rows": len(variance_rows),
        "over_budget_count": len(over_budget),
        "under_budget_count": len(under_budget),
        "on_budget_count": len(on_budget),
        "variance_rows": variance_rows,
    }


def evaluate_decision(
    db: Session,
    decision_type: str,
    parameters: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Tool wrapper for the deterministic Phase 2 decision service."""
    return dcs.evaluate_decision(db, decision_type, parameters or {})


def evaluate_hiring(db: Session, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured tool wrapper for hiring evaluation."""
    return dcs.hiring(db, parameters or {})


def evaluate_purchase(db: Session, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured tool wrapper for purchase evaluation."""
    return dcs.purchase(db, parameters or {})


def evaluate_budget_change(db: Session, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured tool wrapper for budget-change evaluation."""
    return dcs.budget_change(db, parameters or {})


def evaluate_loan(db: Session, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured tool wrapper for loan evaluation."""
    return dcs.loan(db, parameters or {})


def evaluate_expense_reduction(db: Session, parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Structured tool wrapper for expense-reduction evaluation."""
    return dcs.expense_reduction(db, parameters or {})


# ──────────────────────────────────────────────────────────────
# Tool registry — for future LLM binding
# ──────────────────────────────────────────────────────────────
TOOL_REGISTRY = {
    "get_cashflow":         get_cashflow,
    "get_expense_breakdown": get_expense_breakdown,
    "get_vendor_analysis":  get_vendor_analysis,
    "detect_anomalies":     detect_anomalies,
    "forecast_cashflow":    forecast_cashflow,
    "budget_analysis":      budget_analysis,
    "evaluate_decision":    evaluate_decision,
    "evaluate_hiring":      evaluate_hiring,
    "evaluate_purchase":    evaluate_purchase,
    "evaluate_budget_change": evaluate_budget_change,
    "evaluate_loan":        evaluate_loan,
    "evaluate_expense_reduction": evaluate_expense_reduction,
}
