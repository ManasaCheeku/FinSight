"""Small, provider-neutral intent schema for future Qwen integration.

This module only validates intent; it does not call an LLM or infer intent.
"""

from enum import Enum
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class DecisionIntent(str, Enum):
    hiring = "hiring"
    purchase = "purchase"
    budget_change = "budget_change"
    loan = "loan"
    expense_reduction = "expense_reduction"


class Intent(BaseModel):
    """Normalized intent envelope that a future parser can produce."""

    name: DecisionIntent
    parameters: Dict[str, Any] = Field(default_factory=dict)
    source: str = "structured"
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


# Names kept intentionally lightweight for callers that prefer schema/model
# terminology over the generic Intent name.
IntentSchema = Intent
DecisionType = DecisionIntent
