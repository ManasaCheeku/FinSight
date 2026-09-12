"""
Deterministic Phase 2 decision evaluation.

These evaluators use the existing financial and forecasting services.  They
never write transactions and never present a scenario as an actual result.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Dict, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.budget import Budget
from models.transaction import Transaction, TransactionType
import services.financial_service as financial_service
from services.forecast_service import forecast_cashflow
from services.risk_service import calculate_risk_score


DECISION_TYPES = ("hiring", "purchase", "budget_change", "loan", "expense_reduction")


def _as_dict(params: Any) -> Dict[str, Any]:
    if params is None:
        return {}
    if isinstance(params, Mapping):
        result = dict(params)
    elif hasattr(params, "model_dump"):
        result = params.model_dump(exclude_none=True)
    else:
        result = {
            key: getattr(params, key)
            for key in dir(params)
            if not key.startswith("_") and not callable(getattr(params, key))
        }
    # ``inputs`` and ``payload`` are accepted as equivalent envelopes for
    # clients that use a request/intent naming convention.
    for envelope in ("parameters", "inputs", "payload"):
        nested = result.pop(envelope, None)
        if isinstance(nested, Mapping):
            nested_result = dict(nested)
            nested_result.update(result)
            result = nested_result
    return result


def _number(params: Dict[str, Any], *names: str, default: Optional[float] = None) -> Optional[float]:
    for name in names:
        value = params.get(name)
        if value is not None and value != "":
            try:
                return float(value)
            except (TypeError, ValueError):
                raise ValueError(f"{name} must be numeric")
    return default


def _round(value: float) -> float:
    return round(float(value), 2)


def _context(db: Session) -> Dict[str, Any]:
    actual = financial_service.financial_summary(db)
    forecast = forecast_cashflow(db)
    return {"actual": actual, "forecast": forecast}


def _evidence(context: Dict[str, Any], scenario: Dict[str, Any]) -> list[Dict[str, Any]]:
    actual = context["actual"]
    forecast = context["forecast"]
    forecast_90 = next(item for item in forecast["forecasts"] if item["horizon_days"] == 90)
    return [
        {
            "source": "financial_service.financial_summary",
            "classification": "ACTUAL",
            "metric": "current_cash_balance",
            "value": actual["current_cash_balance"],
            "description": "Cumulative revenue less expense transactions in SQLite.",
        },
        {
            "source": "financial_service.financial_summary",
            "classification": "ACTUAL",
            "metric": "monthly_operating_totals",
            "value": {
                "total_revenue": actual["total_revenue"],
                "total_expenses": actual["total_expenses"],
                "net_cash_flow": actual["net_cash_flow"],
            },
            "description": "Historical totals calculated from SQLite transactions.",
        },
        {
            "source": "forecast_service.forecast_cashflow",
            "classification": "FORECAST",
            "metric": "90_day_projected_cash_balance",
            "value": forecast_90["projected_cash_balance"],
            "description": forecast["method"],
        },
        {
            "source": "decision_service",
            "classification": "SCENARIO",
            "metric": "scenario_outputs",
            "value": scenario,
            "description": "Calculated what-if values; no database records were changed.",
        },
    ]


def _result(
    db: Session,
    decision_type: str,
    *,
    scenario: Dict[str, Any],
    key_factors: list[str],
    assumptions: list[str],
    risks: list[str],
    recommendation: str,
    monthly_change: float = 0.0,
    one_time_cash_change: float = 0.0,
    monthly_debt_service: float = 0.0,
) -> Dict[str, Any]:
    context = _context(db)
    risk = calculate_risk_score(
        db,
        monthly_change=monthly_change,
        one_time_cash_change=one_time_cash_change,
        monthly_debt_service=monthly_debt_service,
    )
    scenario = dict(scenario)
    scenario["risk_adjusted"] = {
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
    }
    forecast_90 = next(
        item for item in context["forecast"]["forecasts"]
        if item["horizon_days"] == 90
    )
    return {
        "decision_type": decision_type,
        "decision": recommendation,
        "recommendation": recommendation,
        "current_cash": _round(context["actual"]["current_cash_balance"]),
        "average_monthly_revenue": _round(context["forecast"]["monthly_revenue_baseline"]),
        "average_monthly_expenses": _round(context["forecast"]["monthly_expense_baseline"]),
        "current_monthly_net_cash_flow": _round(
            context["forecast"]["monthly_revenue_baseline"]
            - context["forecast"]["monthly_expense_baseline"]
        ),
        "projected_cash_balance": _round(forecast_90["projected_cash_balance"]),
        "minimum_projected_cash": _round(forecast_90["minimum_projected_cash"]),
        "risk_score": risk["risk_score"],
        "risk_level": risk["risk_level"],
        "evidence": _evidence(context, scenario),
        "key_factors": key_factors,
        "calculation_summary": {
            "method": "deterministic SQLite aggregates plus existing trailing-3-month forecast",
            "scenario": scenario,
            "risk_calculation": risk["calculation_method"],
        },
        "assumptions": assumptions,
        "risks": risks,
        "labels": {
            "actual": "ACTUAL — historical SQLite data",
            "calculated": "CALCULATED — deterministic arithmetic",
            "forecast": "FORECAST — NOT ACTUAL",
            "scenario": "SCENARIO — what-if estimate, not an actual transaction",
        },
        "dataset_label": "SYNTHETIC DEMO DATA",
    }


def hiring(db: Session, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    values = _as_dict(params)
    values.update(kwargs)
    monthly_cost = _number(values, "monthly_cost", "monthly_salary", "salary", default=None)
    employee_count = _number(values, "number_of_employees", "employees", default=None)
    salary_per_employee = _number(
        values,
        "monthly_salary_per_employee",
        "salary_per_employee",
        default=None,
    )
    benefit_cost = _number(
        values,
        "optional_monthly_benefit_cost",
        "monthly_benefit_cost",
        "benefit_cost",
        default=0.0,
    ) or 0.0
    if monthly_cost is None and employee_count is not None and salary_per_employee is not None:
        if employee_count <= 0 or employee_count != int(employee_count):
            raise ValueError("number_of_employees must be a positive whole number")
        monthly_cost = employee_count * salary_per_employee + benefit_cost
    annual_salary = _number(values, "annual_salary", "annual_cost", default=None)
    if monthly_cost is None and annual_salary is not None:
        monthly_cost = annual_salary / 12.0
    if monthly_cost is None:
        raise ValueError(
            "hiring requires number_of_employees and monthly_salary_per_employee, "
            "monthly_cost, or annual_salary"
        )
    if monthly_cost < 0:
        raise ValueError("monthly_cost cannot be negative")
    if salary_per_employee is not None and salary_per_employee < 0:
        raise ValueError("monthly_salary_per_employee cannot be negative")
    if benefit_cost < 0:
        raise ValueError("optional_monthly_benefit_cost cannot be negative")
    revenue_impact = _number(values, "monthly_revenue_impact", "revenue_impact", default=0.0) or 0.0
    net_change = revenue_impact - monthly_cost
    annual_net = net_change * 12
    context = _context(db)
    forecast_90 = next(x for x in context["forecast"]["forecasts"] if x["horizon_days"] == 90)
    projected_90 = forecast_90["projected_cash_balance"] + net_change * 3
    recommendation = (
        "Proceed with hiring"
        if net_change >= 0 and projected_90 >= 0
        else "Defer hiring or reduce the compensation commitment"
    )
    return _result(
        db,
        "hiring",
        scenario={
            "number_of_employees": int(employee_count) if employee_count is not None else None,
            "monthly_salary_per_employee": _round(salary_per_employee) if salary_per_employee is not None else None,
            "optional_monthly_benefit_cost": _round(benefit_cost),
            "monthly_cost": _round(monthly_cost),
            "monthly_revenue_impact": _round(revenue_impact),
            "monthly_net_change": _round(net_change),
            "annual_net_change": _round(annual_net),
            "projected_90_day_cash_balance": _round(projected_90),
        },
        key_factors=[
            f"Monthly cost is {_round(monthly_cost)} (CALCULATED from supplied scenario input).",
            f"Monthly net change is {_round(net_change)} after estimated revenue impact.",
            f"90-day cash balance would be {_round(projected_90)} under this scenario.",
        ],
        assumptions=["Compensation and benefits are treated as recurring monthly expenses.", "Revenue impact is an optional scenario estimate and is not actual revenue."],
        risks=["Revenue impact may not materialize.", "Hiring creates a recurring commitment."],
        recommendation=recommendation,
        monthly_change=net_change,
    )


def purchase(db: Session, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    values = _as_dict(params)
    values.update(kwargs)
    cost = _number(values, "purchase_cost", "cost", "price", "amount", default=None)
    if cost is None:
        raise ValueError("purchase requires purchase_cost")
    if cost < 0:
        raise ValueError("purchase_cost cannot be negative")
    monthly_benefit = _number(values, "monthly_benefit", "expected_monthly_return", "monthly_revenue_impact", "revenue_impact", default=0.0) or 0.0
    context = _context(db)
    current_cash = context["actual"]["current_cash_balance"]
    after_purchase = current_cash - cost
    forecast_90 = next(x for x in context["forecast"]["forecasts"] if x["horizon_days"] == 90)
    projected_90 = forecast_90["projected_cash_balance"] - cost + monthly_benefit * 3
    recommendation = (
        "Proceed with purchase"
        if after_purchase >= 0 and projected_90 >= 0
        else "Defer purchase, negotiate the price, or preserve cash"
    )
    return _result(
        db,
        "purchase",
        scenario={
            "one_time_purchase_cost": _round(cost),
            "monthly_benefit": _round(monthly_benefit),
            "cash_after_purchase": _round(after_purchase),
            "projected_90_day_cash_balance": _round(projected_90),
        },
        key_factors=[f"Cash after one-time purchase is {_round(after_purchase)}.", f"90-day projected cash balance is {_round(projected_90)}.", f"Expected monthly benefit is {_round(monthly_benefit)}."],
        assumptions=["Purchase cost is paid immediately.", "Any benefit is a scenario estimate, not actual revenue."],
        risks=["The benefit may be delayed or lower than estimated.", "One-time cash draw is not a booked transaction."],
        recommendation=recommendation,
        monthly_change=monthly_benefit,
        one_time_cash_change=-cost,
    )


def budget_change(db: Session, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    values = _as_dict(params)
    values.update(kwargs)
    category = str(values.get("category") or "All categories")
    proposed = _number(values, "proposed_budget", "new_budget", "budget_amount", "monthly_budget", default=None)
    current_input = _number(values, "current_budget", default=None)
    rows = db.query(Budget).filter(Budget.category.ilike(category)).all() if category != "All categories" else db.query(Budget).all()
    observed_current = (
        sum(float(row.planned_amount) for row in rows) / len(rows) if rows else 0.0
    )
    current = current_input if current_input is not None else observed_current
    if proposed is None:
        change_amount = _number(values, "change_amount", "monthly_change", default=None)
        if change_amount is None:
            raise ValueError("budget_change requires proposed_budget, new_budget, or change_amount")
        proposed = current + change_amount
    delta = proposed - current
    recommendation = "Approve budget change" if delta <= 0 else "Approve only with a measured return or offsetting reduction"
    return _result(
        db,
        "budget_change",
        scenario={"category": category, "current_monthly_budget": _round(current), "proposed_monthly_budget": _round(proposed), "monthly_change": _round(delta)},
        key_factors=[f"Historical planned budget baseline is {_round(observed_current)}.", f"Proposed monthly budget changes by {_round(delta)}.", f"Budget category: {category}."],
        assumptions=["When current_budget is omitted, the SQLite planned-budget average is used.", "Budget change is treated as a monthly scenario amount."],
        risks=["A lower budget may constrain delivery.", "A higher budget increases recurring spending."],
        recommendation=recommendation,
        monthly_change=-delta,
    )


def loan(db: Session, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    values = _as_dict(params)
    values.update(kwargs)
    principal = _number(values, "loan_amount", "principal", "amount", default=None)
    if principal is None:
        raise ValueError("loan requires loan_amount or principal")
    annual_rate = _number(values, "annual_interest_rate", "interest_rate", "rate", default=0.0) or 0.0
    term_months = _number(values, "term_months", "term", default=12.0) or 12.0
    if principal < 0 or annual_rate < 0 or term_months <= 0:
        raise ValueError("loan amount/rate must be non-negative and term_months must be positive")
    monthly_rate = annual_rate / 100.0 / 12.0
    if monthly_rate == 0:
        payment = principal / term_months
    else:
        payment = principal * monthly_rate * (1 + monthly_rate) ** term_months / ((1 + monthly_rate) ** term_months - 1)
    total_repayment = payment * term_months
    context = _context(db)
    net_change = -payment
    projected_90 = next(x for x in context["forecast"]["forecasts"] if x["horizon_days"] == 90)["projected_cash_balance"] + principal - payment * 3
    recommendation = "Proceed with loan only if the financing purpose is confirmed" if projected_90 >= 0 else "Defer or reduce the loan amount"
    return _result(
        db,
        "loan",
        scenario={"principal": _round(principal), "annual_interest_rate_pct": _round(annual_rate), "term_months": _round(term_months), "monthly_payment": _round(payment), "total_repayment": _round(total_repayment), "projected_90_day_cash_balance": _round(projected_90)},
        key_factors=[f"Calculated monthly payment is {_round(payment)}.", f"Total calculated repayment is {_round(total_repayment)}.", f"90-day projected cash balance after proceeds and payments is {_round(projected_90)}."],
        assumptions=["Standard amortising monthly payments are assumed.", "Loan proceeds are received immediately; interest rate is annual percentage."],
        risks=["Debt service is recurring.", "The calculation excludes lender fees, taxes, and collateral terms."],
        recommendation=recommendation,
        monthly_change=net_change,
        one_time_cash_change=principal,
        monthly_debt_service=payment,
    )


def expense_reduction(db: Session, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    values = _as_dict(params)
    values.update(kwargs)
    category = values.get("category")
    query = db.query(func.sum(Transaction.amount)).filter(Transaction.type == TransactionType.expense)
    if category:
        query = query.filter(Transaction.category.ilike(str(category)))
    total = float(query.scalar() or 0.0)
    count = db.query(Transaction).filter(Transaction.type == TransactionType.expense, *( [Transaction.category.ilike(str(category))] if category else [])).count()
    observed_monthly = total / max(len({(tx.date.year, tx.date.month) for tx in db.query(Transaction).filter(Transaction.type == TransactionType.expense).all()}), 1)
    reduction = _number(values, "reduction_amount", "monthly_savings", "savings", "amount", default=None)
    reduction_pct = _number(values, "reduction_pct", "reduction_percentage", "reduction_percent", "percentage", default=None)
    if reduction is None and reduction_pct is not None:
        reduction = observed_monthly * reduction_pct / 100.0
    if reduction is None:
        raise ValueError("expense_reduction requires reduction_amount or reduction_pct")
    reduction = max(0.0, min(reduction, observed_monthly))
    net_change = reduction
    recommendation = "Implement expense reduction" if reduction > 0 else "No reduction is available from the observed baseline"
    return _result(
        db,
        "expense_reduction",
        scenario={"category": category or "All categories", "observed_monthly_expense": _round(observed_monthly), "reduction_amount": _round(reduction), "remaining_monthly_expense": _round(observed_monthly - reduction)},
        key_factors=[f"Observed monthly expense baseline is {_round(observed_monthly)}.", f"Calculated monthly savings are {_round(reduction)}.", f"Transactions contributing to the baseline: {count}."],
        assumptions=["Historical expense totals are averaged across months present in SQLite.", "Savings are assumed to recur monthly and do not change revenue."],
        risks=["Reducing spend may reduce service quality or growth.", "Savings are a scenario and are not actual until transactions change."],
        recommendation=recommendation,
        monthly_change=net_change,
    )


def evaluate_decision(db: Session, decision_type: Any, params: Any = None, **kwargs: Any) -> Dict[str, Any]:
    if not isinstance(decision_type, str):
        request_values = _as_dict(decision_type)
        decision_type = (
            request_values.pop("decision_type", None)
            or request_values.pop("decision", None)
            or request_values.pop("name", None)
        )
        if params is None:
            params = request_values
        else:
            merged = _as_dict(request_values)
            merged.update(_as_dict(params))
            params = merged
    if not decision_type:
        raise ValueError("decision_type is required")
    if hasattr(decision_type, "value"):
        decision_type = decision_type.value
    normalized = str(decision_type).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {"hire": "hiring", "buy": "purchase", "budget": "budget_change", "reduce_expenses": "expense_reduction"}
    normalized = aliases.get(normalized, normalized)
    if normalized not in DECISION_TYPES:
        raise ValueError(f"Unsupported decision_type '{decision_type}'. Supported: {', '.join(DECISION_TYPES)}")
    return globals()[normalized](db, params, **kwargs)


# Explicit evaluator alias for callers that prefer a verb.
evaluate = evaluate_decision

# Verb-oriented aliases make the service convenient for direct callers and
# preserve the names commonly used by tool/function-calling clients.
evaluate_hiring = hiring
evaluate_purchase = purchase
evaluate_budget_change = budget_change
evaluate_loan = loan
evaluate_expense_reduction = expense_reduction
