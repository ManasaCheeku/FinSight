"""Prompt material for a real Qwen deployment.

The deterministic orchestrator remains the source of all financial values.
These prompts are only used when a caller explicitly chooses the real client.
"""

SYSTEM_PROMPT = """You are FinSight's financial explanation assistant.
Use only the supplied deterministic tool results for financial numbers.
Never invent, round away, or silently change a value. Distinguish ACTUAL,
CALCULATED, FORECAST, SCENARIO, and AI_RECOMMENDATION. The dataset may be
synthetic demo data. Do not call tools that are not supplied in the tool list.
"""


def build_explanation_prompt(question: str, tool_results: object) -> str:
    """Build a grounded prompt without putting credentials or SQL in it."""

    return (
        f"Question: {question}\n"
        "Deterministic tool results (the only source of numbers):\n"
        f"{tool_results!r}\n"
        "Write a concise explanation and preserve the supplied provenance labels."
    )
