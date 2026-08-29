from app.schemas import common
from app.schemas.exceptions import BadRequestError, BaseDomainError, NotFoundError


def test_legacy_entity_error_uses_entity_specific_translation(monkeypatch):
    translations = {
        "agent.not_found": "Agent 7 was not found",
        "entity.not_found": "Generic Agent 7 was not found",
    }
    monkeypatch.setattr(
        common,
        "_translate",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    error = NotFoundError("Agent", 7)

    assert error.i18n_key() == "agent.not_found"
    assert error.to_detail() == "Agent 7 was not found"


def test_entity_error_falls_back_to_generic_translation(monkeypatch):
    translations = {"entity.not_found": "{entity} {id} was not found"}
    monkeypatch.setattr(
        common,
        "_translate",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    assert NotFoundError("UnknownEntity", 9).to_detail() == (
        "UnknownEntity 9 was not found"
    )


def test_explicit_i18n_key_and_params_are_supported(monkeypatch):
    translations = {"judge.timeout": "Judge timed out after {timeout} seconds"}
    monkeypatch.setattr(
        common,
        "_translate",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    error = BaseDomainError(
        error_key="judge.timeout",
        params={"timeout": 30},
    )

    assert error.i18n_key() == "judge.timeout"
    assert error.to_detail() == "Judge timed out after 30 seconds"


def test_cause_is_kept_for_diagnostics_but_not_exposed(monkeypatch):
    cause = RuntimeError("provider secret")
    monkeypatch.setattr(
        common,
        "_translate",
        lambda key, **params: "Safe message" if key == "service.unavailable" else key,
    )

    error = BaseDomainError(error_key="service.unavailable", cause=cause)

    assert error.cause is cause
    assert error.__cause__ is cause
    assert error.to_detail() == "Safe message"
    assert "provider secret" not in str(error)


def test_bad_request_error_can_be_constructed(monkeypatch):
    monkeypatch.setattr(
        common,
        "_translate",
        lambda key, **params: "Bad request" if key == "entity.bad_request" else key,
    )

    error = BadRequestError("StrategyConfig", 3)

    assert error.i18n_key() == "strategyconfig.bad_request"
    assert error.to_detail() == "Bad request"
