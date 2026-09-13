from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

from database import SessionLocal
from tools.financial_tools import (
    get_cashflow as fin_get_cashflow,
    get_expense_breakdown as fin_get_expense_breakdown,
    get_vendor_analysis as fin_get_vendor_analysis,
    detect_anomalies as fin_detect_anomalies,
    forecast_cashflow as fin_forecast_cashflow,
    budget_analysis as fin_budget_analysis,
    evaluate_decision as fin_evaluate_decision,
    evaluate_hiring as fin_evaluate_hiring,
    evaluate_purchase as fin_evaluate_purchase,
    evaluate_budget_change as fin_evaluate_budget_change,
    evaluate_loan as fin_evaluate_loan,
    evaluate_expense_reduction as fin_evaluate_expense_reduction,
)

mcp = FastMCP("FinSight")


def _run_tool(function, *args, **kwargs) -> Any:
    """Create a database session, execute a deterministic tool, then close it."""
    db = SessionLocal()
    try:
        return function(db, *args, **kwargs)
    finally:
        db.close()


@mcp.tool()
def get_cashflow() -> dict:
    """Return actual FinSight cash-flow and profitability metrics."""
    return _run_tool(fin_get_cashflow)


@mcp.tool()
def get_expense_breakdown() -> dict:
    """Return deterministic expense breakdown by category."""
    return _run_tool(fin_get_expense_breakdown)


@mcp.tool()
def get_vendor_analysis(vendor_id: Optional[int] = None) -> dict:
    """Return vendor spending, invoices, paid amounts and outstanding balances."""
    return _run_tool(fin_get_vendor_analysis, vendor_id)


@mcp.tool()
def detect_anomalies() -> dict:
    """Run deterministic anomaly detection on FinSight financial data."""
    return _run_tool(fin_detect_anomalies)


@mcp.tool()
def forecast_cashflow() -> dict:
    """Return 30, 60 and 90-day baseline cash-flow forecasts."""
    return _run_tool(fin_forecast_cashflow)


@mcp.tool()
def budget_analysis(category: Optional[str] = None) -> dict:
    """Return budget-versus-actual analysis, optionally filtered by category."""
    return _run_tool(fin_budget_analysis, category)


@mcp.tool()
def evaluate_decision(
    decision_type: str,
    parameters: Optional[dict] = None,
) -> dict:
    """
    Evaluate a deterministic financial scenario.

    Supported decision types:
    hiring, purchase, budget_change, loan, expense_reduction
    """
    return _run_tool(
        fin_evaluate_decision,
        decision_type,
        parameters or {},
    )


@mcp.tool()
def evaluate_hiring(parameters: Optional[dict] = None) -> dict:
    """Evaluate whether a proposed hiring scenario is financially viable."""
    return _run_tool(fin_evaluate_hiring, parameters or {})


@mcp.tool()
def evaluate_purchase(parameters: Optional[dict] = None) -> dict:
    """Evaluate whether a proposed business purchase is financially viable."""
    return _run_tool(fin_evaluate_purchase, parameters or {})


@mcp.tool()
def evaluate_budget_change(parameters: Optional[dict] = None) -> dict:
    """Evaluate a proposed budget change using deterministic calculations."""
    return _run_tool(fin_evaluate_budget_change, parameters or {})


@mcp.tool()
def evaluate_loan(parameters: Optional[dict] = None) -> dict:
    """Evaluate a proposed loan scenario using deterministic calculations."""
    return _run_tool(fin_evaluate_loan, parameters or {})


@mcp.tool()
def evaluate_expense_reduction(parameters: Optional[dict] = None) -> dict:
    """Evaluate a proposed expense-reduction scenario."""
    return _run_tool(fin_evaluate_expense_reduction, parameters or {})


@mcp.tool()
def health_check() -> str:
    """Check that the FinSight MCP server is running."""
    return "FinSight MCP server is running with deterministic financial tools."


if __name__ == "__main__":
    mcp.run(transport="streamable-http")