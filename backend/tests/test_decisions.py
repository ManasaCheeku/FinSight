"""Phase 2 deterministic decision tests."""

import pytest
from fastapi.testclient import TestClient

from services import decision_service
from services.risk_service import calculate_risk_score
from database import get_db
from main import app


@pytest.fixture
def client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


REQUIRED_RESULT_KEYS = {
    "evidence",
    "key_factors",
    "calculation_summary",
    "assumptions",
    "risks",
    "recommendation",
}


@pytest.mark.parametrize(
    ("decision_type", "parameters"),
    [
        ("hiring", {"monthly_cost": 5000}),
        ("purchase", {"purchase_cost": 10000}),
        ("budget_change", {"category": "Software", "proposed_budget": 9000}),
        ("loan", {"loan_amount": 50000, "interest_rate": 8, "term_months": 24}),
        ("expense_reduction", {"category": "Marketing", "reduction_pct": 10}),
    ],
)
def test_decision_types_are_explainable(db, decision_type, parameters):
    result = decision_service.evaluate_decision(db, decision_type, parameters)
    assert result["decision_type"] == decision_type
    assert REQUIRED_RESULT_KEYS.issubset(result)
    assert 0 <= result["risk_score"] <= 100
    assert result["labels"]["scenario"].startswith("SCENARIO")


def test_risk_calculation_is_bounded_and_documented(db):
    result = calculate_risk_score(
        db, monthly_change=-1000000, one_time_cash_change=-1000000, monthly_debt_service=100000
    )
    assert 0 <= result["risk_score"] <= 100
    assert "calculation_method" in result
    assert set(result["components"]) == {
        "cash_pressure",
        "margin_pressure",
        "debt_service_pressure",
        "volatility_pressure",
    }


def test_hiring_calculates_employee_cost_from_requested_inputs(db):
    result = decision_service.evaluate_decision(
        db,
        "hiring",
        {
            "number_of_employees": 3,
            "monthly_salary_per_employee": 80000,
            "optional_monthly_benefit_cost": 15000,
            "forecast_period_days": 90,
        },
    )
    assert result["current_cash"] > 0
    assert result["calculation_summary"]["scenario"]["monthly_cost"] == 255000
    assert result["calculation_summary"]["scenario"]["number_of_employees"] == 3
    assert result["calculation_summary"]["scenario"]["monthly_salary_per_employee"] == 80000
    assert result["labels"]["forecast"].startswith("FORECAST")


def test_decision_endpoint(client):
    response = client.post(
        "/decisions/evaluate",
        json={"decision_type": "hiring", "parameters": {"monthly_cost": 5000}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["decision_type"] == "hiring"
    assert "evidence" in body


def test_decision_endpoint_rejects_unknown_type(client):
    response = client.post(
        "/decisions/evaluate",
        json={"decision_type": "unknown", "parameters": {}},
    )
    assert response.status_code == 400
