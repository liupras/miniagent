import pytest

from app.api.integrations.errors import IntegrationAPIError
from app.retrieval.embedding_inputs import EmbeddingInputTooLongError
from app.runtime.agent.tool_builder import ToolBuildError
from app.runtime.llm.models import LLMClientError
from app.schemas.common import BaseDomainError, InfrastructureError
from app.schemas.integrations.virtual_court import IntegrationErrorCode
from app.services.virtual_court import (
    JudgeConfigurationError,
    JudgeInvalidResponseError,
    JudgeServiceError,
    JudgeTimeoutError,
    JudgeUnavailableError,
)


@pytest.mark.parametrize(
    ("error", "expected_key"),
    [
        (ToolBuildError("tool failed"), "tool.build_failed"),
        (LLMClientError("provider failed"), "llm.client_error"),
        (
            EmbeddingInputTooLongError("input is too long"),
            "embedding.input_too_long",
        ),
        (JudgeServiceError("judge failed"), "judge.failed"),
        (
            JudgeConfigurationError("bad configuration"),
            "judge.configuration_error",
        ),
        (JudgeUnavailableError("provider unavailable"), "judge.unavailable"),
        (JudgeTimeoutError("timed out"), "judge.timeout"),
        (JudgeInvalidResponseError("bad output"), "judge.invalid_response"),
    ],
)
def test_custom_errors_inherit_base_domain_error(error, expected_key):
    assert isinstance(error, BaseDomainError)
    assert error.i18n_key() == expected_key


def test_infrastructure_errors_share_infrastructure_base():
    assert isinstance(ToolBuildError("failed"), InfrastructureError)
    assert isinstance(LLMClientError("failed"), InfrastructureError)
    assert isinstance(EmbeddingInputTooLongError("failed"), InfrastructureError)


def test_integration_api_error_is_localizable_domain_error():
    error = IntegrationAPIError(
        status_code=401,
        code=IntegrationErrorCode.AUTHENTICATION_FAILED,
        message="invalid credentials",
        retryable=False,
        error_key="integration.authentication_failed",
    )

    assert isinstance(error, BaseDomainError)
    assert error.i18n_key() == "integration.authentication_failed"
    assert error.status_code == 401
    assert error.code == IntegrationErrorCode.AUTHENTICATION_FAILED
    assert error.retryable is False
