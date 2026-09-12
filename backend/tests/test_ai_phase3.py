"""Phase 3 grounded assistant tests."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

from database import Base, get_db
from main import app
from services.financial_service import financial_summary
from ai.qwen_orchestrator import (
    ToolValidationError,
    execute_tool,
    format_inr,
    process_financial_question,
)


def test_tool_allowlist_and_argument_validation(db):
    with pytest.raises(ToolValidationError):
        execute_tool("read_database", {}, db)
    with pytest.raises(ToolValidationError):
        execute_tool("get_cashflow", {"unexpected": True}, db)
    with pytest.raises(ToolValidationError):
        execute_tool("get_vendor_analysis", {"vendor_id": 0}, db)


def test_mock_orchestration_has_complete_contract_and_grounded_values(db, monkeypatch):
    monkeypatch.setenv("MOCK_QWEN", "true")
    result = process_financial_question("How is our cash flow?", db=db)
    assert set(
        (
            "answer",
            "decision",
            "recommendation",
            "tools_used",
            "evidence",
            "key_factors",
            "assumptions",
            "risks",
            "data_labels",
        )
    ) <= set(result)
    assert "MOCK_QWEN" in result["answer"]
    assert result["data_labels"]["actual"].startswith("ACTUAL")
    expected = financial_summary(db)["total_revenue"]
    assert result["evidence"][0]["data"]["total_revenue"] == expected


def test_inr_formatting():
    assert format_inr(1234567.8) == "₹12,34,567.80"
    assert format_inr(-1200) == "-₹1,200.00"


def test_history_and_four_question_classes(db, monkeypatch):
    monkeypatch.setenv("MOCK_QWEN", "true")
    history = [{"role": "user", "content": "Previous question"}]
    questions = (
        ("How is our cash flow?", "get_cashflow"),
        ("Where are we overspending?", "get_expense_breakdown"),
        ("Are there any anomalies?", "detect_anomalies"),
        ("What is our 90-day forecast?", "forecast_cashflow"),
    )
    for question, tool in questions:
        response = process_financial_question(question, history, db)
        assert response["tools_used"] == [tool]
        assert "prior conversation" in " ".join(response["assumptions"])


def test_missing_data_is_explicit():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        result = process_financial_question("How is cash flow?", db=session)
        assert "Insufficient data" in result["answer"]
    finally:
        session.close()


def test_ai_endpoint_has_swagger_contract(db, monkeypatch):
    monkeypatch.setenv("MOCK_QWEN", "true")

    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            response = client.post("/ai/ask", json={"question": "How is our cash flow?"})
            assert response.status_code == 200
            body = response.json()
            assert body["tools_used"] == ["get_cashflow"]
            assert {"answer", "evidence", "data_labels"} <= set(body)
            assert client.get("/openapi.json").status_code == 200
            assert "/ai/ask" in client.get("/openapi.json").json()["paths"]
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def ai_client(db):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_db, None)


def test_ai_endpoint_required_mock_questions(ai_client, monkeypatch):
    monkeypatch.setenv("MOCK_QWEN", "true")
    questions = (
        ("Why did expenses increase?", "get_expense_breakdown"),
        ("Can we afford to hire 3 employees at 80000 per month?", "evaluate_decision"),
        ("Find unusual transactions.", "detect_anomalies"),
        ("What will our cash balance look like in 90 days?", "forecast_cashflow"),
    )
    for question, expected_tool in questions:
        response = ai_client.post("/ai/ask", json={"question": question})
        assert response.status_code == 200
        body = response.json()
        assert body["tools_used"] == [expected_tool]
        assert "MOCK_QWEN" in body["data_labels"]["mode"]
