"""Errors for explicit LLM execution policies, independent of application APIs."""

class ContextBudgetExceeded(ValueError):
    """The complete payload cannot fit without discarding content."""
