"""Secure, deterministic orchestration for financial questions.

The model is not trusted with database access.  It can only be given results
from the explicit allowlist below, and every tool argument is validated before
the existing Phase 2/financial services are called.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Type

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.orm import Session

try:  # Works both as ``ai`` (the existing backend test layout) and ``backend.ai``.
    from tools.financial_tools import TOOL_REGISTRY, TOOL_SCHEMAS
    from services.anomaly_service import explain_anomaly as _service_explain_anomaly
except ImportError:  # pragma: no cover - package import path
    # The pre-Phase-3 modules use top-level imports (``services``, ``models``).
    # Add their established backend module root when imported as ``backend.ai``.
    import sys
    from pathlib import Path

    backend_root = str(Path(__file__).resolve().parents[1])
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)
    from tools.financial_tools import TOOL_REGISTRY, TOOL_SCHEMAS
    from services.anomaly_service import explain_anomaly as _service_explain_anomaly

from .qwen_client import QwenClient
from .prompts import SYSTEM_PROMPT, build_explanation_prompt


class ToolValidationError(ValueError):
    """Raised when an untrusted tool name or argument envelope is rejected."""


# A literal allowlist is deliberate: adding a function to TOOL_REGISTRY does
# not silently expose it to an LLM.
ALLOWED_TOOL_NAMES = frozenset(
    {
        "get_cashflow",
        "get_expense_breakdown",
        "get_vendor_analysis",
        "detect_anomalies",
        "forecast_cashflow",
        "budget_analysis",
        "evaluate_decision",
        "evaluate_hiring",
        "evaluate_purchase",
        "evaluate_budget_change",
        "evaluate_loan",
        "evaluate_expense_reduction",
    }
)


class _NoArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _VendorArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_id: Optional[int] = Field(default=None, ge=1)


class _CategoryArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Optional[str] = None


class _DecisionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_type: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class _ScenarioArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    parameters: Dict[str, Any] = Field(default_factory=dict)


_ARGUMENT_MODELS: Dict[str, Type[BaseModel]] = {
    "get_cashflow": _NoArguments,
    "get_expense_breakdown": _NoArguments,
    "get_vendor_analysis": _VendorArguments,
    "detect_anomalies": _NoArguments,
    "forecast_cashflow": _NoArguments,
    "budget_analysis": _CategoryArguments,
    "evaluate_decision": _DecisionArguments,
    "evaluate_hiring": _ScenarioArguments,
    "evaluate_purchase": _ScenarioArguments,
    "evaluate_budget_change": _ScenarioArguments,
    "evaluate_loan": _ScenarioArguments,
    "evaluate_expense_reduction": _ScenarioArguments,
}


def _validate_arguments(tool_name: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
    if tool_name not in ALLOWED_TOOL_NAMES or tool_name not in TOOL_REGISTRY:
        raise ToolValidationError(f"Tool '{tool_name}' is not allowlisted")
    if not isinstance(arguments, Mapping):
        raise ToolValidationError("Tool arguments must be a JSON object")
    try:
        return _ARGUMENT_MODELS[tool_name].model_validate(dict(arguments)).model_dump(
            exclude_none=True
        )
    except ValidationError as exc:
        raise ToolValidationError(f"Invalid arguments for '{tool_name}': {exc}") from exc


def execute_tool(tool_name: str, arguments: Mapping[str, Any], db: Session) -> Dict[str, Any]:
    """Validate and execute one allowlisted financial tool.

    ``db`` is supplied by the trusted application layer and can never be
    supplied through the JSON argument object.
    """

    validated = _validate_arguments(tool_name, arguments)
    try:
        return TOOL_REGISTRY[tool_name](db, **validated)
    except TypeError as exc:
        # Do not leak a Python callable invocation path to callers.
        raise ToolValidationError(f"Invalid arguments for '{tool_name}'") from exc


class ToolExecutor:
    """Object-oriented facade useful for dependency injection in tests."""

    def __init__(self, db: Session):
        self.db = db

    def execute(self, tool_name: str, arguments: Mapping[str, Any]) -> Dict[str, Any]:
        return execute_tool(tool_name, arguments, self.db)


def format_inr(value: Any) -> str:
    """Format a numeric value using Indian grouping and the INR symbol."""

    try:
        number = float(value)
    except (TypeError, ValueError):
        return "₹—"
    sign = "-" if number < 0 else ""
    formatted = f"{abs(number):.2f}"
    whole, fraction = formatted.split(".")
    if len(whole) > 3:
        last = whole[-3:]
        head = whole[:-3]
        groups: List[str] = []
        while head:
            groups.insert(0, head[-2:])
            head = head[:-2]
        whole = ",".join(groups + [last])
    return f"{sign}₹{whole}.{fraction}"


def explain_anomaly(anomaly: Mapping[str, Any]) -> str:
    """Explain a deterministic anomaly without making a fraud allegation."""

    return _service_explain_anomaly(anomaly)


def _money_values(question: str) -> List[float]:
    values = []
    for match in re.findall(r"(?:₹|rs\.?|inr)?\s*([0-9][0-9,]*(?:\.[0-9]+)?)", question, re.I):
        try:
            values.append(float(match.replace(",", "")))
        except ValueError:
            continue
    return values


def route_question(question: str) -> Tuple[str, Dict[str, Any]]:
    """Map common question classes to deterministic tools and arguments."""

    q = question.lower()
    if any(word in q for word in ("anomal", "unusual", "duplicate", "risk indicator")):
        return "detect_anomalies", {}
    if any(word in q for word in ("forecast", "predict", "runway", "next 30", "next 90")) or (
        "cash balance" in q and any(word in q for word in ("will", "look", "future"))
    ):
        return "forecast_cashflow", {}
    if "budget" in q or "over budget" in q or "planned" in q:
        category = None
        for candidate in ("software", "marketing", "hr & payroll", "payroll"):
            if candidate in q:
                category = "HR & Payroll" if candidate == "payroll" else candidate.title()
                break
        return "budget_analysis", {"category": category} if category else {}
    if any(word in q for word in ("vendor", "supplier", "invoice", "payables")):
        return "get_vendor_analysis", {}
    decision_terms = {
        "hire": "hiring",
        "employee": "hiring",
        "purchase": "purchase",
        "buy ": "purchase",
        "loan": "loan",
        "borrow": "loan",
        "reduce expense": "expense_reduction",
        "cut spend": "expense_reduction",
        "budget change": "budget_change",
    }
    for term, decision_type in decision_terms.items():
        if term in q:
            values = _money_values(q)
            params: Dict[str, Any] = {}
            if decision_type == "hiring":
                count = re.search(r"(\d+)\s+(?:new\s+)?(?:employees?|people|staff)", q)
                if count and values:
                    params = {
                        "number_of_employees": int(count.group(1)),
                        "monthly_salary_per_employee": values[-1],
                    }
                elif values:
                    params = {"monthly_cost": values[-1]}
            elif values:
                params = {"amount": values[-1]}
            return "evaluate_decision", {
                "decision_type": decision_type,
                "parameters": params,
            }
    if any(word in q for word in ("expense", "spend", "overspend", "cost")):
        return "get_expense_breakdown", {}
    return "get_cashflow", {}


def _classify(tool_name: str) -> str:
    if tool_name == "forecast_cashflow":
        return "FORECAST"
    if tool_name.startswith("evaluate_") or tool_name == "evaluate_decision":
        return "SCENARIO"
    return "ACTUAL"


def _evidence(tool_name: str, result: Mapping[str, Any]) -> List[Dict[str, Any]]:
    classification = _classify(tool_name)
    evidence = [
        {
            "source": f"tools.financial_tools.{tool_name}",
            "classification": classification,
            "data": dict(result),
        }
    ]
    # Decision services already provide granular provenance; retain it while
    # adding the tool source so consumers can trace the call itself.
    if tool_name == "evaluate_decision":
        nested = result.get("evidence")
        if isinstance(nested, list):
            evidence.extend(dict(item) for item in nested if isinstance(item, Mapping))
    return evidence


def _has_data(result: Mapping[str, Any]) -> bool:
    if result.get("categories") or result.get("vendors") or result.get("anomalies"):
        return True
    if result.get("variance_rows"):
        return True
    if result.get("forecasts"):
        return bool(
            result.get("opening_cash_balance")
            or result.get("monthly_revenue_baseline")
            or result.get("monthly_expense_baseline")
        )
    for key in (
        "total_revenue",
        "total_expenses",
        "current_cash_balance",
        "current_cash",
        "average_monthly_revenue",
        "average_monthly_expenses",
    ):
        if result.get(key):
            return True
    return False


def _render_answer(
    intent: str,
    result: Mapping[str, Any],
    *,
    mock: bool,
    history_count: int,
) -> Tuple[str, str, str, List[str], List[str], List[str]]:
    """Render grounded text plus recommendation metadata."""

    prefix = "[MOCK_QWEN] " if mock else ""
    assumptions = ["All financial values are calculated from the supplied SQLite dataset."]
    risks = ["This explanation is informational and is not professional financial advice."]
    factors: List[str] = []

    if not _has_data(result):
        answer = (
            f"{prefix}Insufficient data is available to answer this question. "
            "Load transactions, invoices, or budgets and ask again."
        )
        return answer, "Insufficient data", "Provide the missing financial data", factors, assumptions, risks

    if intent == "get_cashflow":
        answer = (
            f"{prefix}ACTUAL cash flow is {format_inr(result.get('net_cash_flow'))}: "
            f"revenue {format_inr(result.get('total_revenue'))}, expenses "
            f"{format_inr(result.get('total_expenses'))}, and current balance "
            f"{format_inr(result.get('current_cash_balance'))}. "
            f"CALCULATED profit margin is {result.get('profit_margin_pct') or 0:.2f}%."
        )
        factors = [
            f"Revenue: {format_inr(result.get('total_revenue'))}.",
            f"Expenses: {format_inr(result.get('total_expenses'))}.",
        ]
        decision, recommendation = "Monitor cash flow", "Maintain a cash buffer and review the expense trend."
    elif intent == "get_expense_breakdown":
        categories = result.get("categories") or []
        top = categories[0] if categories else {}
        answer = (
            f"{prefix}ACTUAL expenses total {format_inr(result.get('total_expenses'))}. "
            f"The largest category is {top.get('category', 'not available')} at "
            f"{format_inr(top.get('total'))} ({top.get('percentage', 0):.2f}% of spend)."
        )
        factors = [f"{row.get('category')}: {format_inr(row.get('total'))}." for row in categories[:3]]
        decision, recommendation = "Review spending", "Review the largest expense categories before changing budgets."
    elif intent == "detect_anomalies":
        anomalies = result.get("anomalies") or []
        top = anomalies[0] if anomalies else {}
        answer = (
            f"{prefix}ACTUAL deterministic checks found {result.get('total_anomalies', 0)} "
            f"anomaly indicators. "
            f"{explain_anomaly(top) if top else 'No anomaly details are available.'}"
        )
        factors = [explain_anomaly(item) for item in anomalies[:3]]
        decision, recommendation = "Review anomaly indicators", "Review the flagged records; an indicator is not proof of misconduct."
        assumptions.append("Anomalies are deterministic risk indicators, not fraud conclusions.")
    elif intent == "forecast_cashflow":
        forecasts = result.get("forecasts") or []
        ninety = next((row for row in forecasts if row.get("horizon_days") == 90), forecasts[-1] if forecasts else {})
        answer = (
            f"{prefix}FORECAST (NOT ACTUAL) 90-day projected cash balance is "
            f"{format_inr(ninety.get('projected_cash_balance'))}, with projected net cash flow "
            f"{format_inr(ninety.get('projected_net_cash_flow'))}."
        )
        factors = [
            f"Opening ACTUAL balance: {format_inr(result.get('opening_cash_balance'))}.",
            f"Forecast method: {result.get('method', 'deterministic historical baseline')}.",
        ]
        assumptions.append("Forecast uses the existing trailing historical averages and uncertainty bounds.")
        risks.append("Forecast outcomes are not guaranteed and are explicitly not actuals.")
        decision, recommendation = "Plan against forecast", "Use the forecast as a planning baseline and monitor actuals."
    elif intent == "budget_analysis":
        rows = result.get("variance_rows") or []
        top = rows[0] if rows else {}
        answer = (
            f"{prefix}ACTUAL-vs-plan CALCULATED analysis found "
            f"{result.get('over_budget_count', 0)} over-budget rows. "
            f"Largest variance is {top.get('category', 'not available')} at "
            f"{format_inr(top.get('variance'))}."
        )
        factors = [f"{row.get('category')} {row.get('year')}-{row.get('month'):02d}: {format_inr(row.get('variance'))}." for row in rows[:3]]
        decision, recommendation = "Review budget variance", "Investigate the largest over-budget categories before revising plans."
    elif intent == "get_vendor_analysis":
        vendors = result.get("vendors") or []
        top = vendors[0] if vendors else {}
        answer = (
            f"{prefix}ACTUAL vendor analysis covers {result.get('vendor_count', 0)} vendors. "
            f"The largest invoiced total is {top.get('vendor_name', 'not available')} at "
            f"{format_inr(top.get('total_invoiced'))}."
        )
        factors = [f"{v.get('vendor_name')}: {format_inr(v.get('total_invoiced'))}." for v in vendors[:3]]
        decision, recommendation = "Review vendor exposure", "Review the highest vendor totals and outstanding balances."
    else:  # evaluate_decision
        answer = (
            f"{prefix}SCENARIO recommendation: {result.get('recommendation', 'No recommendation')}. "
            f"Risk score is {result.get('risk_score', 0):.2f}/100 ({result.get('risk_level', 'unknown')})."
        )
        factors = [str(item) for item in result.get("key_factors", [])]
        assumptions.extend(str(item) for item in result.get("assumptions", []))
        risks.extend(str(item) for item in result.get("risks", []))
        decision, recommendation = str(result.get("decision", "Evaluate scenario")), str(
            result.get("recommendation", "Review scenario")
        )

    if history_count:
        assumptions.append(f"{history_count} prior conversation message(s) were supplied as context.")
    return answer, decision, recommendation, factors, assumptions, risks


def process_financial_question(
    question: str,
    conversation_history: Optional[Iterable[Mapping[str, Any]]] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Route, securely execute, and explain a financial question."""

    # Convenient ``process_financial_question(question, db)`` compatibility
    # for service callers that do not need conversation context.
    if db is None and conversation_history is not None and hasattr(conversation_history, "query"):
        db = conversation_history  # type: ignore[assignment]
        conversation_history = None
    if db is None:
        raise ValueError("db is required")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must not be blank")
    history = list(conversation_history or [])
    intent, arguments = route_question(question)
    tools_used = [intent]
    try:
        result = execute_tool(intent, arguments, db)
    except (ToolValidationError, ValueError) as exc:
        # A decision without a supplied cost is a valid question, but cannot
        # be evaluated. Return a grounded cashflow response rather than
        # inventing scenario inputs.
        if intent == "evaluate_decision":
            intent = "get_cashflow"
            tools_used = [intent]
            result = execute_tool(intent, {}, db)
            result = dict(result)
            result["_decision_input_error"] = str(exc)
        else:
            raise

    client = QwenClient()
    answer, decision, recommendation, factors, assumptions, risks = _render_answer(
        intent, result, mock=client.is_mock, history_count=len(history)
    )
    if client.is_configured:
        model_answer = client.complete(
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                *[
                    {
                        "role": str(message.get("role", "user")),
                        "content": str(message.get("content", "")),
                    }
                    for message in history
                ],
                {
                    "role": "user",
                    "content": build_explanation_prompt(question, result),
                },
            ],
            tools=TOOL_SCHEMAS,
        )
        if model_answer.strip():
            answer = model_answer.strip()
    if "_decision_input_error" in result:
        assumptions.append("The requested scenario did not include a numeric cost, so no scenario number was invented.")
        risks.append("Provide the cost or amount to run a scenario evaluation.")

    labels = {
        "actual": "ACTUAL — historical SQLite data",
        "calculated": "CALCULATED — deterministic service arithmetic",
        "forecast": "FORECAST — NOT ACTUAL",
        "scenario": "SCENARIO — what-if estimate, not an actual transaction",
        "ai_recommendation": "AI_RECOMMENDATION — grounded in deterministic tool evidence",
        "mode": "MOCK_QWEN — deterministic integration mode" if client.is_mock else "DETERMINISTIC — no external model call",
    }
    return {
        "answer": answer,
        "decision": decision,
        "recommendation": recommendation,
        "tools_used": tools_used,
        "evidence": _evidence(intent, result),
        "key_factors": factors,
        "assumptions": assumptions,
        "risks": risks,
        "data_labels": labels,
    }


# Compatibility aliases for callers that prefer verb-oriented names.
execute_allowed_tool = execute_tool
execute_tool_call = execute_tool
format_inr_amount = format_inr
ALLOWED_TOOLS = ALLOWED_TOOL_NAMES
