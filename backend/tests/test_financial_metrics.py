"""
Tests — Financial Metrics Service
"""

import pytest
import services.financial_service as fin


def test_total_revenue_positive(db):
    rev = fin.total_revenue(db)
    assert rev > 0, "Total revenue must be positive"


def test_total_expenses_positive(db):
    exp = fin.total_expenses(db)
    assert exp > 0, "Total expenses must be positive"


def test_net_cash_flow_calculation(db):
    rev = fin.total_revenue(db)
    exp = fin.total_expenses(db)
    net = fin.net_cash_flow(db)
    assert abs(net - (rev - exp)) < 0.01, "Net cash flow must equal revenue - expenses"


def test_current_cash_balance_equals_net(db):
    net = fin.net_cash_flow(db)
    bal = fin.current_cash_balance(db)
    assert abs(bal - net) < 0.01, "Cash balance must match net cash flow"


def test_monthly_revenue_has_12_months(db):
    months = fin.monthly_revenue(db)
    assert len(months) == 12, f"Expected 12 months of revenue, got {len(months)}"


def test_monthly_expenses_has_12_months(db):
    months = fin.monthly_expenses(db)
    assert len(months) == 12, f"Expected 12 months of expenses, got {len(months)}"


def test_monthly_revenue_sorted(db):
    months = fin.monthly_revenue(db)
    for i in range(1, len(months)):
        prev = (months[i-1]["year"], months[i-1]["month"])
        curr = (months[i]["year"],   months[i]["month"])
        assert curr > prev, "Monthly revenue must be sorted chronologically"


def test_expense_category_breakdown_not_empty(db):
    breakdown = fin.expense_category_breakdown(db)
    assert len(breakdown) > 0


def test_expense_category_percentages_sum_to_100(db):
    breakdown = fin.expense_category_breakdown(db)
    total_pct = sum(b["percentage"] for b in breakdown)
    assert abs(total_pct - 100.0) < 0.5, f"Category % should sum to ~100, got {total_pct}"


def test_revenue_growth_returns_dict(db):
    growth = fin.revenue_growth(db)
    assert "current_revenue" in growth
    assert "previous_revenue" in growth
    assert "growth_pct" in growth


def test_expense_growth_returns_dict(db):
    growth = fin.expense_growth(db)
    assert "current_expenses" in growth
    assert "previous_expenses" in growth


def test_profit_margin_in_range(db):
    pm = fin.profit_margin(db)
    assert "profit_margin_pct" in pm
    assert pm["profit_margin_pct"] is not None


def test_budget_variance_not_empty(db):
    rows = fin.budget_variance(db)
    assert len(rows) > 0


def test_budget_variance_has_required_fields(db):
    rows = fin.budget_variance(db)
    required = {"year", "month", "category", "planned", "actual", "variance", "variance_pct", "status"}
    for row in rows[:5]:
        assert required.issubset(row.keys()), f"Missing fields in budget row: {row}"


def test_outstanding_invoices_structure(db):
    result = fin.outstanding_invoices(db)
    assert "count" in result
    assert "total_outstanding" in result
    assert "invoices" in result
    assert result["count"] >= 0


def test_financial_summary_all_keys(db):
    summary = fin.financial_summary(db)
    required_keys = [
        "dataset_label", "total_revenue", "total_expenses",
        "net_cash_flow", "current_cash_balance", "profit_margin_pct",
    ]
    for key in required_keys:
        assert key in summary, f"Missing key in summary: {key}"


def test_financial_summary_dataset_label(db):
    summary = fin.financial_summary(db)
    assert summary["dataset_label"] == "SYNTHETIC DEMO DATA"
