"""
Deterministic decision risk scoring.

The score is intentionally explainable and is not a credit or underwriting
score.  It combines four independently calculated pressures:

* cash pressure (0-40): one-time scenario cash draw and a negative balance;
* margin pressure (0-25): deterioration of the monthly operating surplus;
* debt-service pressure (0-15): proposed monthly debt service as a share of
  monthly revenue; and
* volatility pressure (0-20): observed anomaly count in the SQLite data.

The components are capped at their stated weights and summed to a 0-100
score.  A higher score means that the scenario deserves more caution.
"""

from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

import services.anomaly_service as anomaly_service
import services.financial_service as financial_service
from services.forecast_service import forecast_cashflow


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def calculate_risk_score(
    db: Session,
    *,
    monthly_change: float = 0.0,
    one_time_cash_change: float = 0.0,
    monthly_debt_service: float = 0.0,
) -> Dict[str, Any]:
    """Return a transparent 0-100 score for a proposed scenario.

    ``monthly_change`` is the scenario's monthly net cash-flow change
    (positive is beneficial), while ``one_time_cash_change`` is a cash
    movement at implementation (negative is a cash draw).
    """
    actual = financial_service.financial_summary(db)
    forecast = forecast_cashflow(db)
    baseline_monthly_net = (
        forecast["monthly_revenue_baseline"] - forecast["monthly_expense_baseline"]
    )
    scenario_monthly_net = baseline_monthly_net + monthly_change
    scenario_cash = actual["current_cash_balance"] + one_time_cash_change

    # Cash pressure: penalise an immediate negative balance, otherwise scale
    # the one-time draw against available cash.
    cash_pressure = 0.0
    if scenario_cash < 0:
        cash_pressure = 40.0
    elif one_time_cash_change < 0:
        cash_pressure = min(
            40.0,
            abs(one_time_cash_change) / max(abs(actual["current_cash_balance"]), 1.0) * 40.0,
        )

    # Margin pressure only applies when the scenario worsens the operating
    # surplus.  A baseline with no surplus is already fully exposed.
    if baseline_monthly_net <= 0 and scenario_monthly_net <= 0:
        margin_pressure = 25.0
    elif scenario_monthly_net <= 0:
        margin_pressure = 25.0
    elif baseline_monthly_net > 0 and scenario_monthly_net < baseline_monthly_net:
        margin_pressure = min(
            25.0,
            (baseline_monthly_net - scenario_monthly_net) / baseline_monthly_net * 25.0,
        )
    else:
        margin_pressure = 0.0

    monthly_revenue = max(float(forecast["monthly_revenue_baseline"]), 1.0)
    debt_pressure = min(15.0, max(monthly_debt_service, 0.0) / monthly_revenue * 15.0)

    anomaly_report = anomaly_service.detect_anomalies(db)
    anomaly_count = int(anomaly_report.get("total_anomalies", 0))
    volatility_pressure = min(20.0, anomaly_count / 10.0 * 20.0)

    components = {
        "cash_pressure": round(cash_pressure, 2),
        "margin_pressure": round(margin_pressure, 2),
        "debt_service_pressure": round(debt_pressure, 2),
        "volatility_pressure": round(volatility_pressure, 2),
    }
    score = round(_clamp(sum(components.values()), 0.0, 100.0), 2)
    if score < 25:
        level = "LOW"
    elif score < 50:
        level = "MEDIUM"
    elif score < 75:
        level = "HIGH"
    else:
        level = "CRITICAL"

    return {
        "risk_score": score,
        "risk_level": level,
        "calculation_method": (
            "cash pressure (0-40) + margin pressure (0-25) + debt-service "
            "pressure (0-15) + observed anomaly volatility (0-20), capped at 100"
        ),
        "components": components,
        "inputs": {
            "actual_cash_balance": round(actual["current_cash_balance"], 2),
            "baseline_monthly_net_cash_flow": round(baseline_monthly_net, 2),
            "scenario_monthly_net_cash_flow": round(scenario_monthly_net, 2),
            "monthly_change": round(monthly_change, 2),
            "one_time_cash_change": round(one_time_cash_change, 2),
            "monthly_debt_service": round(monthly_debt_service, 2),
            "observed_anomaly_count": anomaly_count,
        },
        "labels": {
            "actual": "ACTUAL — historical SQLite transactions",
            "calculated": "CALCULATED — deterministic risk formula",
            "forecast": "FORECAST — NOT ACTUAL",
            "scenario": "SCENARIO — proposed decision, not a booked transaction",
        },
    }


# Short alias useful to future tool/function-calling clients.
risk_score = calculate_risk_score
compute_risk_score = calculate_risk_score
evaluate_risk = calculate_risk_score
calculate_risk = calculate_risk_score
get_risk_score = calculate_risk_score
