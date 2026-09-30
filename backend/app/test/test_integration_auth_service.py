import pytest

from app.services.integration_auth import (
    IntegrationNotConfiguredError,
    InvalidIntegrationCredentialsError,
    authenticate_internal_service_token,
)


def test_integration_authentication_accepts_matching_key():
    authenticate_internal_service_token(
        provided_token="expected-token",
        expected_token="expected-token",
    )


@pytest.mark.parametrize("provided_key", [None, "wrong-key"])
def test_integration_authentication_rejects_invalid_key(provided_key):
    with pytest.raises(InvalidIntegrationCredentialsError):
        authenticate_internal_service_token(
            provided_token=provided_key,
            expected_token="expected-token",
        )


def test_integration_authentication_fails_closed_without_configuration():
    with pytest.raises(IntegrationNotConfiguredError):
        authenticate_internal_service_token(
            provided_token="some-token",
            expected_token="",
        )
