"""
FinSight — AI Financial Intelligence Platform
FastAPI application — Phase 1 Backend Foundation

Swagger UI:  http://127.0.0.1:8000/docs
ReDoc:       http://127.0.0.1:8000/redoc
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from config import APP_DESCRIPTION, APP_NAME, APP_VERSION, DATASET_LABEL
from database import get_db, init_db
try:
    from ai.qwen_orchestrator import process_financial_question
    from ai.schemas import FinancialQuestionRequest, FinancialQuestionResponse
except ImportError:  # pragma: no cover - package-style import
    from .ai.qwen_orchestrator import process_financial_question
    from .ai.schemas import FinancialQuestionRequest, FinancialQuestionResponse
from models.transaction import Transaction, TransactionType
from models.vendor import Vendor
from models.invoice import Invoice
from models.budget import Budget
import services.financial_service as fin
import services.anomaly_service as ano
import services.forecast_service as frc
import services.decision_service as decisions

# ──────────────────────────────────────────────────────────────
# Application
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title=APP_NAME,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    """Ensure DB tables exist on startup."""
    init_db()


# ──────────────────────────────────────────────────────────────
# Pydantic response schemas
# ──────────────────────────────────────────────────────────────

class TransactionOut(BaseModel):
    id: int
    date: str
    amount: float
    type: str
    category: str
    description: str
    vendor_id: Optional[int]
    reference_number: Optional[str]

    class Config:
        from_attributes = True


class VendorOut(BaseModel):
    id: int
    name: str
    category: str
    contact_email: Optional[str]
    payment_terms: str

    class Config:
        from_attributes = True


class InvoiceOut(BaseModel):
    id: int
    vendor_id: int
    invoice_number: str
    amount: float
    status: str
    issue_date: Optional[str]
    due_date: Optional[str]
    paid_date: Optional[str]
    description: Optional[str]

    class Config:
        from_attributes = True


class BudgetOut(BaseModel):
    id: int
    year: int
    month: int
    category: str
    planned_amount: float
    actual_amount: float

    class Config:
        from_attributes = True


class DecisionRequest(BaseModel):
    """Structured, deterministic decision input.

    ``parameters`` is intentionally open-ended so a future intent parser can
    pass normalized fields without changing this API.  Flat fields are also
    accepted for convenient API clients.
    """

    decision_type: Optional[str] = Field(
        default=None,
        description="One of hiring, purchase, budget_change, loan, expense_reduction.",
    )
    decision: Optional[str] = Field(
        default=None,
        description="Alias for decision_type, retained for client compatibility.",
    )
    parameters: Dict[str, Any] = Field(default_factory=dict)
    inputs: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Alias for parameters, useful for explicit scenario inputs.",
    )
    intent: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional future intent envelope; no LLM is invoked.",
    )

    model_config = ConfigDict(extra="allow")

    @model_validator(mode="before")
    @classmethod
    def normalize_decision_name(cls, values):
        if not isinstance(values, dict):
            return values
        if not values.get("decision_type"):
            if values.get("decision"):
                values["decision_type"] = values["decision"]
            elif isinstance(values.get("intent"), dict):
                values["decision_type"] = (
                    values["intent"].get("name") or values["intent"].get("type")
                )
        if not values.get("decision_type"):
            raise ValueError("decision_type is required")
        return values


class DecisionResponse(BaseModel):
    """Explainable decision result with actual/calculated/forecast labels."""

    decision_type: str
    decision: str
    recommendation: str
    current_cash: float
    average_monthly_revenue: float
    average_monthly_expenses: float
    current_monthly_net_cash_flow: float
    projected_cash_balance: float
    minimum_projected_cash: float
    risk_score: float = Field(ge=0, le=100)
    risk_level: str
    evidence: List[Dict[str, Any]]
    key_factors: List[str]
    calculation_summary: Dict[str, Any]
    assumptions: List[str]
    risks: List[str]
    labels: Dict[str, str]
    dataset_label: str


# ──────────────────────────────────────────────────────────────
# Helper
# ──────────────────────────────────────────────────────────────

def _fmt_dt(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def _tx_to_dict(t: Transaction) -> Dict:
    return {
        "id": t.id,
        "date": _fmt_dt(t.date),
        "amount": t.amount,
        "type": t.type.value if hasattr(t.type, "value") else t.type,
        "category": t.category,
        "description": t.description,
        "vendor_id": t.vendor_id,
        "reference_number": t.reference_number,
    }


def _vendor_to_dict(v: Vendor) -> Dict:
    return {
        "id": v.id,
        "name": v.name,
        "category": v.category,
        "contact_email": v.contact_email,
        "payment_terms": v.payment_terms,
    }


def _invoice_to_dict(inv: Invoice) -> Dict:
    return {
        "id": inv.id,
        "vendor_id": inv.vendor_id,
        "invoice_number": inv.invoice_number,
        "amount": inv.amount,
        "status": inv.status.value if hasattr(inv.status, "value") else inv.status,
        "issue_date": _fmt_dt(inv.issue_date),
        "due_date": _fmt_dt(inv.due_date),
        "paid_date": _fmt_dt(inv.paid_date),
        "description": inv.description,
    }


def _budget_to_dict(b: Budget) -> Dict:
    return {
        "id": b.id,
        "year": b.year,
        "month": b.month,
        "category": b.category,
        "planned_amount": b.planned_amount,
        "actual_amount": b.actual_amount,
    }


# ──────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["System"])
def health_check(db: Session = Depends(get_db)):
    """Returns service health status and basic DB stats."""
    tx_count  = db.query(Transaction).count()
    inv_count = db.query(Invoice).count()
    v_count   = db.query(Vendor).count()
    return {
        "status": "ok",
        "service": APP_NAME,
        "version": APP_VERSION,
        "dataset_label": DATASET_LABEL,
        "db_stats": {
            "transactions": tx_count,
            "invoices": inv_count,
            "vendors": v_count,
        },
    }


# ──────────────────────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────────────────────

@app.get("/transactions", tags=["Transactions"])
def list_transactions(
    type: Optional[str] = Query(None, description="Filter by type: revenue | expense"),
    category: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    offset: int = Query(0),
    db: Session = Depends(get_db),
):
    """List transactions with optional filters."""
    q = db.query(Transaction)
    if type:
        try:
            tx_type = TransactionType(type)
            q = q.filter(Transaction.type == tx_type)
        except ValueError:
            raise HTTPException(400, f"Invalid type '{type}'. Use 'revenue' or 'expense'.")
    if category:
        q = q.filter(Transaction.category.ilike(f"%{category}%"))
    total = q.count()
    rows  = q.order_by(Transaction.date.desc()).offset(offset).limit(limit).all()
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": [_tx_to_dict(t) for t in rows],
    }


@app.get("/transactions/{transaction_id}", tags=["Transactions"])
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    """Get a single transaction by ID."""
    t = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not t:
        raise HTTPException(404, f"Transaction {transaction_id} not found.")
    return _tx_to_dict(t)


# ──────────────────────────────────────────────────────────────
# Vendors
# ──────────────────────────────────────────────────────────────

@app.get("/vendors", tags=["Vendors"])
def list_vendors(db: Session = Depends(get_db)):
    """List all vendors."""
    vendors = db.query(Vendor).order_by(Vendor.name).all()
    return {"total": len(vendors), "vendors": [_vendor_to_dict(v) for v in vendors]}


# ──────────────────────────────────────────────────────────────
# Invoices
# ──────────────────────────────────────────────────────────────

@app.get("/invoices", tags=["Invoices"])
def list_invoices(
    status: Optional[str] = Query(None, description="Filter: pending | paid | overdue"),
    vendor_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """List invoices with optional status/vendor filter."""
    q = db.query(Invoice)
    if status:
        from models.invoice import InvoiceStatus
        try:
            s = InvoiceStatus(status)
            q = q.filter(Invoice.status == s)
        except ValueError:
            raise HTTPException(400, f"Invalid status '{status}'.")
    if vendor_id:
        q = q.filter(Invoice.vendor_id == vendor_id)
    rows = q.order_by(Invoice.issue_date.desc()).all()
    return {"total": len(rows), "invoices": [_invoice_to_dict(i) for i in rows]}


# ──────────────────────────────────────────────────────────────
# Budgets
# ──────────────────────────────────────────────────────────────

@app.get("/budgets", tags=["Budgets"])
def list_budgets(
    year: Optional[int] = Query(None),
    month: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """List budget rows, optionally filtered by year/month."""
    q = db.query(Budget)
    if year:
        q = q.filter(Budget.year == year)
    if month:
        q = q.filter(Budget.month == month)
    rows = q.order_by(Budget.year, Budget.month, Budget.category).all()
    return {"total": len(rows), "budgets": [_budget_to_dict(b) for b in rows]}


# ──────────────────────────────────────────────────────────────
# Metrics
# ──────────────────────────────────────────────────────────────

@app.get("/metrics/summary", tags=["Metrics"])
def metrics_summary(db: Session = Depends(get_db)):
    """Full financial summary: revenue, expenses, cash flow, margin, outstanding invoices."""
    return fin.financial_summary(db)


@app.get("/metrics/revenue", tags=["Metrics"])
def metrics_revenue(db: Session = Depends(get_db)):
    """Monthly revenue breakdown with growth rate."""
    return {
        "dataset_label": DATASET_LABEL,
        "total_revenue": fin.total_revenue(db),
        "monthly_revenue": fin.monthly_revenue(db),
        "revenue_growth": fin.revenue_growth(db),
    }


@app.get("/metrics/expenses", tags=["Metrics"])
def metrics_expenses(db: Session = Depends(get_db)):
    """Monthly expenses, category breakdown, and growth rate."""
    return {
        "dataset_label": DATASET_LABEL,
        "total_expenses": fin.total_expenses(db),
        "monthly_expenses": fin.monthly_expenses(db),
        "expense_growth": fin.expense_growth(db),
        "category_breakdown": fin.expense_category_breakdown(db),
    }


@app.get("/metrics/cashflow", tags=["Metrics"])
def metrics_cashflow(db: Session = Depends(get_db)):
    """Net cash flow, profit margin, and current balance."""
    return {
        "dataset_label": DATASET_LABEL,
        "net_cash_flow": fin.net_cash_flow(db),
        "current_cash_balance": fin.current_cash_balance(db),
        "profit_margin": fin.profit_margin(db),
    }


@app.get("/metrics/budget-variance", tags=["Metrics"])
def metrics_budget_variance(
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Budget variance analysis — planned vs actual per category and month."""
    rows = fin.budget_variance(db)
    if category:
        rows = [r for r in rows if r["category"].lower() == category.lower()]
    over  = sum(1 for r in rows if r["status"] == "over_budget")
    under = sum(1 for r in rows if r["status"] == "under_budget")
    return {
        "dataset_label": DATASET_LABEL,
        "total_rows": len(rows),
        "over_budget_count": over,
        "under_budget_count": under,
        "variance": rows,
    }


# ──────────────────────────────────────────────────────────────
# Anomalies
# ──────────────────────────────────────────────────────────────

@app.get("/anomalies", tags=["Anomaly Detection"])
def anomaly_detection(db: Session = Depends(get_db)):
    """
    Run all deterministic anomaly detectors.
    Returns risk indicators with severity, deviation, and plain-English explanations.
    """
    return ano.detect_anomalies(db)


# ──────────────────────────────────────────────────────────────
# Forecasting
# ──────────────────────────────────────────────────────────────

@app.get("/forecast", tags=["Forecasting"])
def cashflow_forecast(db: Session = Depends(get_db)):
    """
    30-, 60-, and 90-day cash-flow forecasts.
    Labelled FORECAST — NOT ACTUAL.
    """
    return frc.forecast_cashflow(db)


# ──────────────────────────────────────────────────────────────
# Deterministic decision evaluation (Phase 2)
# ──────────────────────────────────────────────────────────────

@app.post(
    "/decisions/evaluate",
    response_model=DecisionResponse,
    tags=["Decisions"],
    summary="Evaluate a deterministic financial decision",
    description=(
        "Evaluates hiring, purchase, budget_change, loan, or expense_reduction "
        "using actual SQLite data and the existing deterministic forecast. "
        "No LLM is called and no database transaction is created."
    ),
)
def evaluate_decision(request: DecisionRequest, db: Session = Depends(get_db)):
    """Return an explainable what-if result with evidence and risk score."""
    try:
        return decisions.evaluate_decision(
            db,
            request.decision_type or request.decision or "",
            request.model_dump(exclude_none=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ──────────────────────────────────────────────────────────────
# Phase 3 grounded financial assistant
# ──────────────────────────────────────────────────────────────

@app.post(
    "/ai/ask",
    response_model=FinancialQuestionResponse,
    tags=["AI Assistant"],
    summary="Ask a grounded financial question",
    description=(
        "Routes a question to the allowlisted deterministic financial tools. "
        "MOCK_QWEN=true enables an explicitly labelled, no-network integration mode."
    ),
)
def ask_financial_question(
    request: FinancialQuestionRequest,
    db: Session = Depends(get_db),
):
    """Return an explainable answer whose financial values come from tools."""
    try:
        return process_financial_question(
            request.question,
            [message.model_dump() for message in request.conversation_history],
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
