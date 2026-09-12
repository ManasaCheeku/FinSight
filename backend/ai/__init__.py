"""Phase 3 financial question answering package.

The package is intentionally isolated from the web layer.  It can be used by
the API, a worker, or tests with a SQLAlchemy session.
"""

from .qwen_orchestrator import (
    ALLOWED_TOOL_NAMES,
    ToolValidationError,
    execute_tool,
    explain_anomaly,
    format_inr,
    process_financial_question,
)

__all__ = [
    "ALLOWED_TOOL_NAMES",
    "ToolValidationError",
    "execute_tool",
    "explain_anomaly",
    "format_inr",
    "process_financial_question",
]
