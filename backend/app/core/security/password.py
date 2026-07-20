"""Configuration-driven password policy validation."""

import re

from app.core.config import settings


def password_policy_errors(password: str) -> list[str]:
    """Return all password-policy violations for a plain-text password."""
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(f"must be at least {settings.password_min_length} characters long")
    if settings.password_require_upper and not re.search(r"[A-Z]", password):
        errors.append("must contain an uppercase letter")
    if settings.password_require_lower and not re.search(r"[a-z]", password):
        errors.append("must contain a lowercase letter")
    if settings.password_require_digit and not re.search(r"[0-9]", password):
        errors.append("must contain a digit")
    if settings.password_require_special and not re.search(r"[^A-Za-z0-9]", password):
        errors.append("must contain a special character")
    return errors


def validate_password(password: str) -> str:
    """Pydantic-compatible validator that enforces the configured policy."""
    errors = password_policy_errors(password)
    if errors:
        raise ValueError("Password " + ", ".join(errors))
    return password
