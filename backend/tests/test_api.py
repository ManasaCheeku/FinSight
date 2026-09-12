"""
Tests — FastAPI endpoints (health check + key routes)
Uses HTTPX TestClient with in-memory DB via dependency override.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base, get_db
from main import app

# ──────────────────────────────────────────────────────────────
# In-memory DB + app override
# ──────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def client(db):
    """FastAPI TestClient wired to the shared in-memory DB."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ──────────────────────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────────────────────

def test_health_returns_200(client):
    r = client.get("/health")
    assert r.status_code == 200


def test_health_status_ok(client):
    r = client.get("/health")
    assert r.json()["status"] == "ok"


def test_health_has_db_stats(client):
    r = client.get("/health")
    data = r.json()
    assert "db_stats" in data
    assert data["db_stats"]["transactions"] > 0
    assert data["db_stats"]["vendors"] > 0


# ──────────────────────────────────────────────────────────────
# Transactions
# ──────────────────────────────────────────────────────────────

def test_list_transactions_200(client):
    r = client.get("/transactions")
    assert r.status_code == 200


def test_list_transactions_has_data(client):
    r = client.get("/transactions")
    data = r.json()
    assert data["total"] > 0
    assert len(data["transactions"]) > 0


def test_list_transactions_filter_by_type(client):
    r = client.get("/transactions?type=expense")
    assert r.status_code == 200
    data = r.json()
    for tx in data["transactions"]:
        assert tx["type"] == "expense"


def test_get_transaction_by_id(client):
    # Get first transaction id
    r = client.get("/transactions?limit=1")
    first_id = r.json()["transactions"][0]["id"]
    r2 = client.get(f"/transactions/{first_id}")
    assert r2.status_code == 200
    assert r2.json()["id"] == first_id


def test_get_transaction_not_found(client):
    r = client.get("/transactions/999999")
    assert r.status_code == 404


def test_list_transactions_invalid_type(client):
    r = client.get("/transactions?type=invalid")
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────
# Vendors
# ──────────────────────────────────────────────────────────────

def test_list_vendors_200(client):
    r = client.get("/vendors")
    assert r.status_code == 200


def test_list_vendors_has_data(client):
    r = client.get("/vendors")
    data = r.json()
    assert data["total"] >= 4


# ──────────────────────────────────────────────────────────────
# Invoices
# ──────────────────────────────────────────────────────────────

def test_list_invoices_200(client):
    r = client.get("/invoices")
    assert r.status_code == 200


def test_list_invoices_has_data(client):
    r = client.get("/invoices")
    assert r.json()["total"] > 0


def test_list_invoices_filter_status(client):
    r = client.get("/invoices?status=pending")
    assert r.status_code == 200
    for inv in r.json()["invoices"]:
        assert inv["status"] == "pending"


def test_list_invoices_invalid_status(client):
    r = client.get("/invoices?status=bogus")
    assert r.status_code == 400


# ──────────────────────────────────────────────────────────────
# Budgets
# ──────────────────────────────────────────────────────────────

def test_list_budgets_200(client):
    r = client.get("/budgets")
    assert r.status_code == 200


def test_list_budgets_has_data(client):
    r = client.get("/budgets")
    assert r.json()["total"] > 0


# ──────────────────────────────────────────────────────────────
# Metrics
# ──────────────────────────────────────────────────────────────

def test_metrics_summary_200(client):
    r = client.get("/metrics/summary")
    assert r.status_code == 200


def test_metrics_summary_has_revenue(client):
    r = client.get("/metrics/summary")
    data = r.json()
    assert data["total_revenue"] > 0
    assert data["total_expenses"] > 0


def test_metrics_revenue_200(client):
    r = client.get("/metrics/revenue")
    assert r.status_code == 200
    assert "monthly_revenue" in r.json()


def test_metrics_expenses_200(client):
    r = client.get("/metrics/expenses")
    assert r.status_code == 200
    assert "category_breakdown" in r.json()


def test_metrics_cashflow_200(client):
    r = client.get("/metrics/cashflow")
    assert r.status_code == 200
    assert "net_cash_flow" in r.json()


def test_metrics_budget_variance_200(client):
    r = client.get("/metrics/budget-variance")
    assert r.status_code == 200
    assert "variance" in r.json()


# ──────────────────────────────────────────────────────────────
# Anomalies & Forecast
# ──────────────────────────────────────────────────────────────

def test_anomalies_200(client):
    r = client.get("/anomalies")
    assert r.status_code == 200


def test_anomalies_has_results(client):
    r = client.get("/anomalies")
    data = r.json()
    assert data["total_anomalies"] > 0


def test_forecast_200(client):
    r = client.get("/forecast")
    assert r.status_code == 200


def test_forecast_has_three_horizons(client):
    r = client.get("/forecast")
    forecasts = r.json()["forecasts"]
    horizons = {f["horizon_days"] for f in forecasts}
    assert horizons == {30, 60, 90}


def test_forecast_labelled(client):
    r = client.get("/forecast")
    assert r.json()["label"] == "FORECAST — NOT ACTUAL"
