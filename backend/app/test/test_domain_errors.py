from app.core.i18n import error_translation
from app.core.i18n.error_translation import translate_domain_error
from app.schemas.exceptions import BadRequestError, BaseDomainError, NotFoundError


def test_legacy_entity_error_uses_entity_specific_translation(monkeypatch):
    translations = {
        "agent.not_found": "Agent 7 was not found",
        "entity.not_found": "Generic Agent 7 was not found",
    }
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    error = NotFoundError("Agent", 7)

    assert error.i18n_key() == "agent.not_found"
    assert translate_domain_error(error) == "Agent 7 was not found"


def test_entity_error_falls_back_to_generic_translation(monkeypatch):
    translations = {"entity.not_found": "{entity} {id} was not found"}
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    assert translate_domain_error(NotFoundError("UnknownEntity", 9)) == (
        "UnknownEntity 9 was not found"
    )


def test_explicit_i18n_key_and_params_are_supported(monkeypatch):
    translations = {"judge.timeout": "Judge timed out after {timeout} seconds"}
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: translations.get(key, key).format(**params),
    )

    error = BaseDomainError(
        error_key="judge.timeout",
        params={"timeout": 30},
    )

    assert error.i18n_key() == "judge.timeout"
    assert translate_domain_error(error) == "Judge timed out after 30 seconds"


def test_cause_is_kept_for_diagnostics_but_not_exposed(monkeypatch):
    cause = RuntimeError("provider secret")
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: "Safe message" if key == "service.unavailable" else key,
    )

    error = BaseDomainError(error_key="service.unavailable", cause=cause)

    assert error.cause is cause
    assert error.__cause__ is cause
    assert translate_domain_error(error) == "Safe message"
    assert "provider secret" not in str(error)


def test_bad_request_error_can_be_constructed(monkeypatch):
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: "Bad request" if key == "entity.bad_request" else key,
    )

    error = BadRequestError("StrategyConfig", 3)

    assert error.i18n_key() == "strategyconfig.bad_request"
    assert translate_domain_error(error) == "Bad request"


def test_translation_is_deferred_until_the_response_boundary(monkeypatch):
    error = BaseDomainError(
        error_key="judge.timeout",
        params={"timeout": 15},
    )
    messages = {
        "zh": "15 秒后超时",
        "en": "Timed out after 15 seconds",
    }
    active_language = {"value": "zh"}
    monkeypatch.setattr(
        error_translation,
        "t",
        lambda key, **params: messages[active_language["value"]],
    )

    assert translate_domain_error(error) == messages["zh"]
    active_language["value"] = "en"
    assert translate_domain_error(error) == messages["en"]
