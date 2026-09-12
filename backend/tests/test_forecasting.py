"""
Tests — Cash-Flow Forecasting Service
"""

import pytest
import services.forecast_service as frc


def test_forecast_returns_dict(db):
    result = frc.forecast_cashflow(db)
    assert isinstance(result, dict)


def test_forecast_has_required_top_level_keys(db):
    result = frc.forecast_cashflow(db)
    required = {
        "label", "disclaimer", "method",
        "opening_cash_balance", "monthly_revenue_baseline",
        "monthly_expense_baseline", "forecasts",
    }
    assert required.issubset(result.keys())


def test_forecast_label_correct(db):
    result = frc.forecast_cashflow(db)
    assert result["label"] == "FORECAST — NOT ACTUAL"


def test_three_forecast_horizons(db):
    result = frc.forecast_cashflow(db)
    horizons = [f["horizon_days"] for f in result["forecasts"]]
    assert set(horizons) == {30, 60, 90}, f"Expected 30/60/90 horizons, got {horizons}"


def test_each_forecast_has_required_fields(db):
    result = frc.forecast_cashflow(db)
    required = {
        "horizon_days", "projected_revenue", "projected_expenses",
        "projected_net_cash_flow", "projected_cash_balance",
        "minimum_projected_cash", "uncertainty_pct", "label",
    }
    for f in result["forecasts"]:
        assert required.issubset(f.keys()), f"Missing fields in forecast: {f}"


def test_each_forecast_labelled(db):
    result = frc.forecast_cashflow(db)
    for f in result["forecasts"]:
        assert f["label"] == "FORECAST — NOT ACTUAL"


def test_projected_revenue_positive(db):
    result = frc.forecast_cashflow(db)
    for f in result["forecasts"]:
        assert f["projected_revenue"] > 0, "Projected revenue should be positive"


def test_projected_expenses_positive(db):
    result = frc.forecast_cashflow(db)
    for f in result["forecasts"]:
        assert f["projected_expenses"] > 0, "Projected expenses should be positive"


def test_net_equals_rev_minus_exp(db):
    result = frc.forecast_cashflow(db)
    for f in result["forecasts"]:
        expected = round(f["projected_revenue"] - f["projected_expenses"], 2)
        assert abs(f["projected_net_cash_flow"] - expected) < 0.05


def test_90_day_revenue_greater_than_30(db):
    result = frc.forecast_cashflow(db)
    by_horizon = {f["horizon_days"]: f for f in result["forecasts"]}
    assert by_horizon[90]["projected_revenue"] > by_horizon[30]["projected_revenue"]


def test_uncertainty_in_valid_range(db):
    result = frc.forecast_cashflow(db)
    for f in result["forecasts"]:
        assert 0.0 <= f["uncertainty_pct"] <= 100.0


def test_monthly_baseline_positive(db):
    result = frc.forecast_cashflow(db)
    assert result["monthly_revenue_baseline"] > 0
    assert result["monthly_expense_baseline"] > 0


def test_disclaimer_present(db):
    result = frc.forecast_cashflow(db)
    assert len(result["disclaimer"]) > 20
