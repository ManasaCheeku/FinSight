"""Pydantic contracts for the Phase 3 financial assistant."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConversationMessage(BaseModel):
    """A prior message supplied as context; it is never used as a tool call."""

    model_config = ConfigDict(extra="allow")

    role: str = Field(description="Message role, for example user or assistant.")
    content: str


class FinancialQuestionRequest(BaseModel):
    """Request body for ``POST /ai/ask``."""

    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    conversation_history: List[ConversationMessage] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def question_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()


class FinancialQuestionResponse(BaseModel):
    """Explainable answer with explicit provenance labels."""

    model_config = ConfigDict(extra="forbid")

    answer: str
    decision: str
    recommendation: str
    tools_used: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    key_factors: List[str] = Field(default_factory=list)
    assumptions: List[str] = Field(default_factory=list)
    risks: List[str] = Field(default_factory=list)
    data_labels: Dict[str, str] = Field(default_factory=dict)


# Short aliases are useful to clients and preserve the terminology used by
# the Phase 3 requirements.
AIQuestionRequest = FinancialQuestionRequest
AIQuestionResponse = FinancialQuestionResponse
