import pytest

from app.services.integration_auth import (
    IntegrationNotConfiguredError,
    InvalidIntegrationCredentialsError,
    authenticate_integration_api_key,
)


def test_integration_authentication_accepts_matching_key():
    authenticate_integration_api_key(
        provided_key="expected-key",
        expected_key="expected-key",
    )


@pytest.mark.parametrize("provided_key", [None, "wrong-key"])
def test_integration_authentication_rejects_invalid_key(provided_key):
    with pytest.raises(InvalidIntegrationCredentialsError):
        authenticate_integration_api_key(
            provided_key=provided_key,
            expected_key="expected-key",
        )


def test_integration_authentication_fails_closed_without_configuration():
    with pytest.raises(IntegrationNotConfiguredError):
        authenticate_integration_api_key(
            provided_key="some-key",
            expected_key="",
        )
